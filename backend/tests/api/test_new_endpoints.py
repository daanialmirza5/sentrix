"""Credentials management, Signal Lab analyser and drift report endpoints."""
import pytest

from app.contracts.schema import procurement_example
from app.gateway import tools
from app.models import AuditEvent, ContractVersion
from tests.conftest import login


@pytest.fixture
def seeded(client):
    arjun, priya, meera = login(client, "arjun"), login(client, "priya"), login(client, "meera")
    secret = client.post("/v1/agents", headers=arjun, json={"agent_id": "proc-agent-07", "name": "P",
                                                            "owner": "meera", "role": "procurement"}).json()["agent_secret"]
    assert client.post("/v1/contracts/proc-agent-07/versions", headers=priya,
                       json={"contract": procurement_example(), "reviewed": True}).status_code == 201
    return {"arjun": arjun, "priya": priya, "meera": meera, "auditor": login(client, "auditor"), "secret": secret}


def _task(client, secret):
    return client.post("/v1/tasks", headers={"X-Agent-Secret": secret},
                       json={"agent_id": "proc-agent-07", "description": "get quotes"}).json()


# ---------------------------------------------------------------- credentials
def test_tokens_listing_requires_security_or_admin(client, seeded):
    _task(client, seeded["secret"])
    assert client.get("/v1/tokens", headers=seeded["meera"]).status_code == 403
    rows = client.get("/v1/tokens", headers=seeded["priya"]).json()
    assert len(rows) == 1 and rows[0]["status"] == "active" and rows[0]["contract_version"] == 1


def test_manual_revoke_blocks_the_token_and_is_audited(client, seeded, db):
    t = _task(client, seeded["secret"])
    jti = client.get("/v1/tokens", headers=seeded["priya"]).json()[0]["jti"]
    assert client.post(f"/v1/tokens/{jti}/revoke", headers=seeded["meera"], json={"reason": "suspicious"}).status_code == 403
    r = client.post(f"/v1/tokens/{jti}/revoke", headers=seeded["priya"], json={"reason": "suspicious"})
    assert r.status_code == 200 and r.json()["revoked"] == [jti]
    assert client.post(f"/v1/tokens/{jti}/revoke", headers=seeded["priya"], json={"reason": "again"}).status_code == 409
    assert client.get("/v1/tokens", headers=seeded["priya"]).json()[0]["status"] == "revoked"
    from app.broker import tokens
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(db, t["token"])
    assert e.value.code == "revoked"
    ev = db.query(AuditEvent).filter(AuditEvent.kind == "token", AuditEvent.verdict == "revoked").one()
    assert ev.actor == "priya" and "manual: suspicious" in ev.details["reason"]


def test_revoke_unknown_token_404(client, seeded):
    assert client.post("/v1/tokens/tk-nope/revoke", headers=seeded["priya"], json={"reason": "x-y-z"}).status_code == 404


# ---------------------------------------------------------------- Signal Lab
def _analyze(client, h, **body):
    return client.post("/v1/analyze", headers=h, json={"agent_id": "proc-agent-07", **body})


def test_analyze_in_role_action_is_low_and_executes_nothing(client, seeded, db):
    before = db.query(AuditEvent).count()
    r = _analyze(client, seeded["auditor"], tool="supplier_api.get_quote", args={"supplier": "supplier-a"}).json()
    assert r["analysis_only"] and r["trust_level"] is None and not r["would_hard_deny"]
    assert r["risk"] < 30 and r["disabled_signals"] == ["B"]
    assert db.query(AuditEvent).count() == before  # no state change, nothing audited as an action
    assert not tools.SINK.deliveries


def test_analyze_poisoned_flow_attributes_marker_and_masks_canary(client, seeded):
    r = _analyze(client, seeded["auditor"], tool="fs.read", args={"path": "/hr/salary_backup.xlsx"},
                 steps_since_untrusted=1, fixture="poisoned_quote").json()
    assert r["override"] == "deception" and r["risk"] == 95.0 and r["would_hard_deny"]
    assert r["deception"]["honey"] == "hr/salary_backup.xlsx"
    span = r["provenance"]["attribution"]["span"]
    assert (span["page"], span["line"]) == (2, 14)
    assert "page 2, line 14" in r["explanation"]["cause"]
    assert abs(sum(r["contributions"].values()) - 100) < 0.11

    from app.engines.deception import canary_for, decoy_content
    body = decoy_content("salary_sheet", "proc-agent-07")
    r = _analyze(client, seeded["auditor"], tool="http.post",
                 args={"url": f"https://{tools.MOCK_EXTERNAL_HOST}/u", "body": body}).json()
    assert r["deception"]["canaries"][0]["owner"] == "proc-agent-07"
    assert canary_for("proc-agent-07") not in str(r)  # full canary never returned
    assert not tools.SINK.deliveries  # analysis never delivers


def test_reference_attack_t3_payload_from_honey(client, seeded):
    """PRD Flow A t3: the outbound payload is the honey decoy; the canary identifies the agent, never returned."""
    from app.engines.deception import canary_for
    r = _analyze(client, seeded["auditor"], tool="http.post", args={"url": f"https://{tools.MOCK_EXTERNAL_HOST}/upload"},
                 steps_since_untrusted=2, fixture="poisoned_quote", payload_from_honey=True).json()
    assert r["override"] == "deception" and r["risk"] >= 95
    assert r["deception"]["canaries"][0]["owner"] == "proc-agent-07" and "decoy_marker" in r["deception"]["dlp"]
    assert "egress_not_allowlisted" in r["role_fit"]["hard_deny"]
    assert canary_for("proc-agent-07") not in str(r) and not tools.SINK.deliveries
    bad = _analyze(client, seeded["auditor"], tool="fs.read", args={"path": "/x"}, payload_from_honey=True)
    assert bad.status_code == 422


def test_analyze_rejects_bad_input(client, seeded):
    assert _analyze(client, seeded["auditor"], tool="fs.read", args={"path": "../etc"}).status_code == 422
    assert _analyze(client, seeded["auditor"], tool="nope.tool", args={}).status_code == 422
    assert _analyze(client, seeded["auditor"], tool="fs.read", args={}, fixture="evil").status_code == 422
    assert client.post("/v1/analyze", json={"agent_id": "proc-agent-07", "tool": "fs.read"}).status_code == 401


def test_analyze_refuses_tampered_contract(client, seeded, db):
    cv = db.query(ContractVersion).one()
    cv.body = {**cv.body, "allowed_tools": cv.body["allowed_tools"] + ["http.post"]}
    db.commit()
    r = _analyze(client, seeded["auditor"], tool="supplier_api.get_quote", args={"supplier": "supplier-a"})
    assert r.status_code == 409


# ---------------------------------------------------------------- drift report
def test_drift_report(client, seeded):
    r = client.get("/v1/reports/drift", headers=seeded["auditor"])
    if r.status_code == 404:
        pytest.skip("reports/drift_eval.json not generated (run scripts/eval_drift.py)")
    d = r.json()
    assert d["calibrated_h"] > 0 and d["trace"]["points"] and "held_out_calibrated" in d
