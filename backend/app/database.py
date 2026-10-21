"""SQLite (MVP) persistence. WAL mode so the async worker and request threads can share it."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


# One process-wide lock serialises security-critical state transitions
# (audit append, trust-level changes, revocation) so the hash chain stays linear.
STATE_LOCK = threading.RLock()

_engine = None
_SessionLocal: sessionmaker | None = None


def _make_engine(url: str):
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    eng = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _pragmas(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return eng


def init_engine(url: str | None = None):
    global _engine, _SessionLocal
    url = url or settings.database_url
    if url.startswith("sqlite:///"):
        from pathlib import Path
        Path(url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    if _engine is not None:
        _engine.dispose()
    _engine = _make_engine(url)
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def create_all() -> None:
    from . import models  # noqa: F401 - register tables
    Base.metadata.create_all(get_engine())


def SessionLocal() -> Session:
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal()


@contextmanager
def db_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
