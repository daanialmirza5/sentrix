"""Tests for code paths that previously had none: retention purge, explainer, rate limiting, auth edges."""
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.engines import provenance
from app.fusion import explainer
from app.fusion.risk import fuse
from app.gateway import tools
from app.models import IngestedContent, utcnow
from app.security.auth import RateLimiter, decode_operator_token, issue_operator_token, USERS


# ---------------------------------------------------------------- privacy: retention purge
def test_purge_drops_expired_raw_spans_but_keeps_hash(db):
    c, w = provenance.ingest(db, agent_id="a", session_id="s", source="doc.pdf", text=tools.CLEAN_QUOTE_A,
                             trust="untrusted", step=0, taint_seq=1)
    c.retain_until = utcnow() - timedelta(minutes=1)
    db.flush()
    assert provenance.purge_expired(db) == 1
    row = db.get(IngestedContent, c.id)
    assert row.spans is None and row.content_hash.startswith("sha256:") and row.span_count > 0
    attr = provenance.attribute(db, w.id, "read something")
    assert attr["span"] is None and attr["uncertain"] and "no longer retained" in attr["note"]


def test_purge_leaves_unexpired_content(db):
    provenance.ingest(db, agent_id="a", session_id="s", source="doc.pdf", text="hello world line", trust="untrusted",
                      step=0, taint_seq=2)
    assert provenance.purge_expired(db) == 0


def test_flagged_span_survives_purge(db):
    c, w = provenance.ingest(db, agent_id="a", session_id="s", source="q.pdf", text=tools.POISONED_QUOTE,
                             trust="untrusted", step=0, taint_seq=3)
    provenance.attribute(db, w.id, "read fs read hr salary backup xlsx")
    c.retain_until = utcnow() - timedelta(minutes=1)
    provenance.purge_expired(db)
    row = db.get(IngestedContent, c.id)
    assert row.spans is None and row.flagged and row.flagged_spans[0]["line"] == 14


def test_decayed_window_deactivates(db):
    _, w = provenance.ingest(db, agent_id="a", session_id="s9", source="x", text="line one here",
                             trust="untrusted", step=0, taint_seq=4)
    r = provenance.score(db, session_id="s9", step=100, out_of_contract=True, s_r=1.0)
    assert r.s_p == 0 and w.active is False


# ---------------------------------------------------------------- explainer (deterministic templates)
def test_factor_line_orders_and_flags_disabled_behavior():
    line = explainer.factor_line(fuse({"R": 1.0, "P": 0.5}))
    assert line.index("Role-fit") < line.index("Provenance")
    assert "Behavior: disabled (not implemented)" in line


def test_factor_line_overrides():
    assert explainer.factor_line(fuse({"R": 0.1}, deception=True)).startswith("Deception override")
    assert explainer.factor_line(fuse({"R": 0.1}, drift_term=0.6)).startswith("Drift override")
    assert "no weighted signal" in explainer.factor_line(fuse({}))


def test_why_and_cause_lines():
    action = {"verb": "read", "resource": "/hr/salary_backup.xlsx", "tool": "fs.read"}
    text = explainer.why(action, {"rules": [{"detail": "matches deny-list 'hr/*'"}]},
                         {"window_id": "tn-1", "steps_since": 1, "source": "supplier_quote.pdf"},
                         {"honey": "hr/salary_backup.xlsx", "canaries": [{"masked": "CNRY-1234…"}]})
    for part in ("deny-list", "1 step(s) after ingesting UNTRUSTED supplier_quote.pdf", "honey-resource", "CNRY-1234…"):
        assert part in text
    attr = {"source": "q.pdf", "content_hash": "sha256:" + "a" * 64, "confidence": 0.9, "uncertain": False,
            "span": {"page": 2, "line": 14, "text": "marker"}}
    assert explainer.cause_line(attr).startswith("q.pdf, page 2, line 14")
    assert "uncertain" in explainer.cause_line({**attr, "uncertain": True})
    assert "no longer retained" in explainer.cause_line({**attr, "span": None})
    assert explainer.cause_line(None) is None


def test_explanations_are_reproducible():
    f = fuse({"R": 0.97, "P": 0.9, "S": 1.0})
    assert explainer.factor_line(f) == explainer.factor_line(fuse({"R": 0.97, "P": 0.9, "S": 1.0}))


@pytest.mark.parametrize("level,verdict,dec,expect", [
    (4, "deny", {"honey": "x"}, "confirmed compromise"),
    (3, "allow", {}, "sandbox"),
    (2, "allow", {}, "Owner should acknowledge"),
    (1, "allow", {}, "step-up"),
    (0, "deny", {}, "No side effects"),
])
def test_recommendations(level, verdict, dec, expect):
    assert any(expect in r for r in explainer.recommendations(level, verdict, dec))


# ---------------------------------------------------------------- auth / rate limiting
def test_rate_limiter_blocks_then_resets():
    rl = RateLimiter(2, 60)
    rl.check("k")
    rl.check("k")
    with pytest.raises(HTTPException) as e:
        rl.check("k")
    assert e.value.status_code == 429
    rl.check("other-key")  # keys are independent
    rl.reset()
    rl.check("k")


def test_operator_token_roundtrip_and_tamper():
    tok = issue_operator_token(USERS["priya"])
    assert decode_operator_token(tok).username == "priya"
    with pytest.raises(HTTPException):
        decode_operator_token(tok[:-2] + ("AA" if not tok.endswith("AA") else "BB"))


def test_login_rate_limited(client):
    for _ in range(20):
        client.post("/v1/auth/login", json={"username": "priya", "password": "wrong"})
    assert client.post("/v1/auth/login", json={"username": "priya", "password": "wrong"}).status_code == 429


def test_change_request_endpoint_rejects_unknown_change_keys(client):
    from tests.conftest import login
    from app.contracts.schema import procurement_example
    arjun, priya, meera = login(client, "arjun"), login(client, "priya"), login(client, "meera")
    client.post("/v1/agents", headers=arjun, json={"agent_id": "proc-agent-07", "name": "P", "owner": "meera",
                                                   "role": "procurement"})
    client.post("/v1/contracts/proc-agent-07/versions", headers=priya,
                json={"contract": procurement_example(), "reviewed": True})
    r = client.post("/v1/change-requests", headers=meera, json={
        "agent_id": "proc-agent-07", "changes": {"grant_admin": True}, "justification": "please give me admin"})
    assert r.status_code == 400 and "unsupported change keys" in r.json()["detail"]
