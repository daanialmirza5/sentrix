from app.contracts.schema import procurement_example
from app.models import AuditEvent
from tests.conftest import login


def _register(client, h):
    r = client.post("/v1/agents", headers=h, json={"agent_id": "proc-agent-07", "name": "Procurement-Agent-07",
                                                   "owner": "meera", "role": "procurement"})
    assert r.status_code == 201, r.text
    return r.json()["agent_secret"]


def test_health_reports_disabled_components(client):
    r = client.get("/v1/health").json()
    assert r["policy_engine"]["available"] is False
    assert r["behavior_engine"]["implemented"] is False


def test_auth_required_and_roles(client):
    assert client.get("/v1/agents").status_code == 401
    assert client.post("/v1/auth/login", json={"username": "priya", "password": "wrong"}).status_code == 401
    viewer = login(client, "auditor")
    r = client.post("/v1/agents", headers=viewer, json={"agent_id": "x-agent", "name": "x", "owner": "meera",
                                                        "role": "r"})
    assert r.status_code == 403


def test_end_to_end_contract_and_change_request(client, db):
    arjun, priya, meera = login(client, "arjun"), login(client, "priya"), login(client, "meera")
    secret = _register(client, arjun)
    body = {"contract": procurement_example(), "reviewed": True}
    assert client.post("/v1/contracts/proc-agent-07/versions", headers=meera, json=body).status_code == 403
    assert client.post("/v1/contracts/proc-agent-07/versions", headers=priya,
                       json={**body, "reviewed": False}).status_code == 422
    assert client.post("/v1/contracts/proc-agent-07/versions", headers=priya, json=body).status_code == 201
    vs = client.get("/v1/contracts/proc-agent-07", headers=meera).json()
    assert vs[0]["verification"]["valid"]

    cr = client.post("/v1/change-requests", headers=meera, json={
        "agent_id": "proc-agent-07", "changes": {"add_tools": ["erp.create_po"]},
        "justification": "Owner needs purchase orders"}).json()
    assert cr["status"] == "pending" and cr["requester_signed"]
    assert client.post(f"/v1/change-requests/{cr['id']}/approve", headers=meera, json={}).status_code == 403
    ok = client.post(f"/v1/change-requests/{cr['id']}/approve", headers=priya, json={"note": "approved"})
    assert ok.status_code == 200 and ok.json()["new_version"] == 2
    d = client.get("/v1/contracts/proc-agent-07/diff?a=1&b=2", headers=meera).json()
    assert any(x["field"] == "allowed_tools" and x["added"] == ["erp.create_po"] for x in d)
    assert client.post(f"/v1/change-requests/{cr['id']}/approve", headers=priya, json={}).status_code == 409

    # Task tokens are bound to the current contract version and require agent credentials.
    assert client.post("/v1/tasks", json={"agent_id": "proc-agent-07", "description": "quotes"}).status_code == 401
    t = client.post("/v1/tasks", headers={"X-Agent-Secret": secret},
                    json={"agent_id": "proc-agent-07", "description": "quotes",
                          "scope": ["supplier_api.get_quote", "http.post"]}).json()
    assert t["scope"] == ["supplier_api.get_quote"]  # http.post not in contract -> intersected away

    # Gateway fails closed while the policy engine is unavailable; the denial is audited, nothing executes.
    from app.gateway import tools
    r = client.post("/v1/gateway/invoke", json={"token": t["token"], "tool": "supplier_api.get_quote",
                                                "args": {"supplier": "supplier-a"}})
    assert r.status_code == 503 and not tools.SINK.deliveries
    last = db.query(AuditEvent).order_by(AuditEvent.seq.desc()).first()
    assert last.verdict == "deny" and last.details["executed"] is False

    v = client.get("/v1/audit/verify", headers=meera).json()
    assert v["valid"] and v["checked"] >= 6


def test_oversized_body_rejected(client):
    r = client.post("/v1/gateway/invoke", content=b"x" * (2 * 1024 * 1024 + 10),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_malformed_invoke_rejected(client):
    assert client.post("/v1/gateway/invoke", json={"tool": "fs.read"}).status_code == 422


def test_validate_endpoint(client):
    h = login(client, "auditor")
    assert client.post("/v1/contracts/validate", headers=h, json={"contract": procurement_example()}).json()["valid"]
    bad = client.post("/v1/contracts/validate", headers=h, json={"contract_text": "agent_id: x"}).json()
    assert not bad["valid"]
