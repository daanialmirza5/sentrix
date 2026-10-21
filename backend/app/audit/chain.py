"""Hash-chained, append-only audit log (TRD 3.2 event schema, FR-14).

hash_n = SHA-256(canonical_json(event_fields_n) || prev_hash_n), prev_hash_0 = GENESIS.
Appends are serialised by STATE_LOCK so the chain is strictly linear. A local chain is
tamper-*evident* when verified; a fully compromised host could rewrite an unanchored chain,
which is why the head is periodically anchored to an external file (see anchor_head()).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import STATE_LOCK
from ..models import AuditEvent
from ..security.keys import canonical_json, sha256_hex

GENESIS = "sha256:" + "0" * 64

HASHED_FIELDS = (
    "event_id", "ts", "kind", "agent_id", "session_id", "task_id", "parent_agent_id", "action_type",
    "tool", "resource", "sensitivity", "destination", "bytes_out", "content_trust", "content_hash",
    "taint_ids", "verdict", "risk", "level", "actor", "lane", "details",
)

_listeners: list = []


def add_listener(fn) -> None:
    """Called with the event dict after each committed append (dashboard stream, bus)."""
    _listeners.append(fn)


def clear_listeners() -> None:
    _listeners.clear()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _round(v):
    return None if v is None else round(float(v), 4)


def event_payload(ev: AuditEvent | dict) -> dict:
    get = (lambda k: ev.get(k)) if isinstance(ev, dict) else (lambda k: getattr(ev, k))
    data = {k: get(k) for k in HASHED_FIELDS}
    data["sensitivity"] = _round(data["sensitivity"])
    data["risk"] = _round(data["risk"])
    data["bytes_out"] = int(data["bytes_out"] or 0)
    data["taint_ids"] = list(data["taint_ids"] or [])
    data["details"] = json.loads(json.dumps(data["details"] or {}, default=str))
    return data


def compute_hash(payload: dict, prev_hash: str) -> str:
    return "sha256:" + sha256_hex(canonical_json(payload) + prev_hash.encode())


def last_hash(db: Session) -> str:
    row = db.execute(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)).scalar()
    return row or GENESIS


def append(db: Session, kind: str, **fields: Any) -> AuditEvent:
    """Append one event and flush it (caller's transaction commits)."""
    with STATE_LOCK:
        ev = AuditEvent(
            event_id=str(uuid.uuid4()), ts=_now_iso(), kind=kind,
            agent_id=fields.get("agent_id"), session_id=fields.get("session_id"),
            task_id=fields.get("task_id"), parent_agent_id=fields.get("parent_agent_id"),
            action_type=fields.get("action_type"), tool=fields.get("tool"), resource=fields.get("resource"),
            sensitivity=_round(fields.get("sensitivity")), destination=fields.get("destination"),
            bytes_out=int(fields.get("bytes_out") or 0), content_trust=fields.get("content_trust"),
            content_hash=fields.get("content_hash"), taint_ids=list(fields.get("taint_ids") or []),
            verdict=fields.get("verdict"), risk=_round(fields.get("risk")), level=fields.get("level"),
            actor=fields.get("actor"), lane=fields.get("lane") or "normal",
            details=json.loads(json.dumps(fields.get("details") or {}, default=str)),
        )
        prev = last_hash(db)
        ev.prev_hash = prev
        ev.hash = compute_hash(event_payload(ev), prev)
        db.add(ev)
        db.flush()
    return ev


def notify(ev: AuditEvent) -> None:
    data = to_dict(ev)
    for fn in list(_listeners):
        try:
            fn(data)
        except Exception:  # listeners must never break the security path
            pass


def to_dict(ev: AuditEvent) -> dict:
    d = event_payload(ev)
    d.update(seq=ev.seq, prev_hash=ev.prev_hash, hash=ev.hash)
    return d


def verify_chain(db: Session, start_seq: int | None = None, end_seq: int | None = None) -> dict:
    """Recompute every hash. Returns first broken link if any."""
    q = select(AuditEvent).order_by(AuditEvent.seq)
    if start_seq:
        q = q.where(AuditEvent.seq >= start_seq)
    if end_seq:
        q = q.where(AuditEvent.seq <= end_seq)
    prev = None
    checked = 0
    if start_seq and start_seq > 1:
        prev = db.execute(select(AuditEvent.hash).where(AuditEvent.seq < start_seq)
                          .order_by(AuditEvent.seq.desc()).limit(1)).scalar()
    prev = prev or GENESIS
    head = None
    for ev in db.execute(q).scalars():
        checked += 1
        if ev.prev_hash != prev:
            return {"valid": False, "checked": checked, "broken_at_seq": ev.seq,
                    "reason": "prev_hash does not match previous event hash (deletion or reorder)"}
        expected = compute_hash(event_payload(ev), prev)
        if expected != ev.hash:
            return {"valid": False, "checked": checked, "broken_at_seq": ev.seq,
                    "reason": "event content does not match its hash (modified)"}
        prev = ev.hash
        head = ev.hash
    total = db.execute(select(func.count(AuditEvent.seq))).scalar()
    anchor = read_anchor()
    anchor_ok = None
    if anchor and not start_seq:
        row = db.execute(select(AuditEvent.hash).where(AuditEvent.seq == anchor["seq"])).scalar()
        anchor_ok = row == anchor["hash"]
        if anchor_ok is False:
            return {"valid": False, "checked": checked, "broken_at_seq": anchor["seq"],
                    "reason": "chain no longer contains the externally anchored head (chain rewritten)"}
    return {"valid": True, "checked": checked, "total_events": total, "head": head, "anchor_verified": anchor_ok}


def _anchor_path():
    return settings.data_dir / "audit_anchor.json"


def anchor_head(db: Session) -> dict | None:
    """Write the current chain head to a separate file (stand-in for external WORM storage)."""
    row = db.execute(select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)).first()
    if not row:
        return None
    data = {"seq": row[0], "hash": row[1], "anchored_at": _now_iso()}
    _anchor_path().parent.mkdir(parents=True, exist_ok=True)
    _anchor_path().write_text(json.dumps(data))
    return data


def read_anchor() -> dict | None:
    p = _anchor_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None
