"""TETHER_AUTO_SEED: an empty cloud instance comes up with the signed demo fleet; restarts do not duplicate it."""
from app.audit import chain
from app.contracts import registry
from app.demo_seed import FLEET, seed_if_empty
from app.models import Agent, ChangeRequest


def test_seed_creates_signed_fleet_once(db):
    assert seed_if_empty(db) is True
    db.commit()
    assert db.query(Agent).count() == len(FLEET)
    for aid, *_ in FLEET:
        assert registry.verify_version(registry.active_version(db, aid))["valid"]
    assert db.query(ChangeRequest).filter_by(status="pending").count() == 1
    assert seed_if_empty(db) is False and db.query(Agent).count() == len(FLEET)
    assert chain.verify_chain(db)["valid"]


def test_auto_seed_on_startup(monkeypatch):
    monkeypatch.setenv("TETHER_AUTO_SEED", "1")
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        tok = c.post("/v1/auth/login", json={"username": "auditor", "password": "tether-demo"}).json()["token"]
        agents = c.get("/v1/agents", headers={"Authorization": f"Bearer {tok}"}).json()
    assert {a["id"] for a in agents} == {f[0] for f in FLEET}
