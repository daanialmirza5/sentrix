import shutil
from pathlib import Path

import pytest

from app.config import REPO_DIR, reload_settings, settings


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    """Every test gets its own data dir + SQLite DB; demo data is never touched."""
    model_dir = REPO_DIR / "data" / "models"
    (tmp_path / "models").mkdir()
    if model_dir.exists():  # reuse the downloaded model read-only via a junction-free copy of the path
        settings_models = tmp_path / "models"
        settings_models.rmdir()
        try:
            settings_models.symlink_to(model_dir, target_is_directory=True)
        except OSError:
            shutil.copytree(model_dir, settings_models)
    reload_settings(data_dir=tmp_path, database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    from app.security import keys
    keys.reset_cache()
    from app.database import create_all, init_engine
    init_engine()
    create_all()
    from app.audit import chain
    chain.clear_listeners()
    from app.security.auth import change_request_limiter, login_limiter
    login_limiter.reset()
    change_request_limiter.reset()
    from app.gateway import tools
    tools.SINK.deliveries.clear()
    tools.INBOX.clear()
    yield tmp_path


@pytest.fixture
def db():
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def login(client, user):
    r = client.post("/v1/auth/login", json={"username": user, "password": settings.demo_password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def publish_proc(db):
    """Register proc-agent-07 with the TRD reference contract signed by owner + security."""
    from app.contracts import registry
    from app.contracts.schema import procurement_example
    from app.engines.deception import canary_for
    from app.models import Agent
    from app.security.auth import USERS

    def _make(agent_id="proc-agent-07"):
        db.add(Agent(id=agent_id, name="Procurement-Agent-07", owner="meera", role="procurement",
                     secret_hash="x", canary=canary_for(agent_id)))
        cv = registry.publish_initial(db, procurement_example(agent_id), "meera", USERS["priya"], "priya")
        db.commit()
        return cv
    return _make
