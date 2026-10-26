"""Credential Broker (FR-3, TRD 3.3): per-task, short-lived, scope-attenuated tokens.

effective_scope = contract_scope ∩ task_scope ∩ parent_scope (parent only when delegated).
Tokens are EdDSA (Ed25519) JWTs signed by the broker identity; the gateway verifies the
signature, expiry, revocation, agent/task/session binding and contract version on every call.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import chain
from ..config import settings
from ..database import STATE_LOCK
from ..models import TokenRecord, utcnow
from ..security import keys


class TokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes(keys.signing_key("token-broker")))


def _public_key():
    return _private_key().public_key()


def intent_hash(description: str) -> str:
    return "sha256:" + hashlib.sha256(description.strip().lower().encode()).hexdigest()


def effective_scope(contract_tools: list[str], task_scope: list[str] | None, parent_scope: list[str] | None) -> list[str]:
    scope = list(contract_tools)
    if task_scope is not None:
        scope = [t for t in scope if t in set(task_scope)]
    if parent_scope is not None:
        scope = [t for t in scope if t in set(parent_scope)]
    return scope


@dataclass
class Minted:
    token: str
    claims: dict
    record: TokenRecord


def mint(db: Session, *, agent_id: str, task_id: str, session_id: str, scope: list[str], contract_version: int,
         description: str, ttl: int | None = None, parent_agent_id: str | None = None,
         parent_jti: str | None = None, depth: int = 0, lane: str = "normal") -> Minted:
    ttl = int(ttl or settings.token_ttl_seconds)
    ttl = max(30, min(ttl, settings.token_ttl_max_seconds))
    now = int(time.time())
    jti = "tk-" + uuid.uuid4().hex[:12]
    claims = {"sub": agent_id, "task": task_id, "sid": session_id, "intent_hash": intent_hash(description),
              "scope": scope, "depth": depth, "max_depth": settings.max_delegation_depth, "ver": contract_version,
              "iat": now, "exp": now + ttl, "jti": jti, "lane": lane, "iss": "sentrix-broker"}
    if parent_agent_id:
        claims["parent"] = parent_agent_id
        claims["parent_jti"] = parent_jti
    token = jwt.encode(claims, _private_key(), algorithm="EdDSA")
    rec = TokenRecord(jti=jti, agent_id=agent_id, task_id=task_id, session_id=session_id, parent_jti=parent_jti,
                      scope=scope, depth=depth, contract_version=contract_version, issued_at=now, expires_at=now + ttl)
    db.add(rec)
    db.flush()
    chain.append(db, "token", agent_id=agent_id, session_id=session_id, task_id=task_id, parent_agent_id=parent_agent_id,
                 verdict="issued", actor="token-broker", lane=lane,
                 details={"jti": jti, "scope": scope, "ttl_s": ttl, "depth": depth, "contract_version": contract_version})
    return Minted(token, claims, rec)


def decode_unverified(token: str) -> dict | None:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None


def verify(db: Session, token: str, *, current_contract_version: int | None = None,
           ttl_cap: int | None = None) -> dict:
    """Full verification; raises TokenError with a stable code."""
    if not isinstance(token, str) or token.count(".") != 2 or len(token) > 4096:
        raise TokenError("malformed", "token is malformed")
    try:
        claims = jwt.decode(token, _public_key(), algorithms=["EdDSA"], issuer="sentrix-broker",
                            options={"require": ["exp", "iat", "jti", "sub", "task", "sid", "scope", "ver"]})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("expired", "token expired") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("invalid_signature", "token signature or claims invalid") from exc
    rec = db.get(TokenRecord, claims["jti"])
    if rec is None:
        raise TokenError("unknown", "token was not issued by this broker")
    if rec.revoked:
        raise TokenError("revoked", f"token revoked: {rec.revoked_reason}")
    if (rec.agent_id, rec.task_id, rec.session_id) != (claims["sub"], claims["task"], claims["sid"]):
        raise TokenError("binding", "token binding mismatch")
    if sorted(rec.scope) != sorted(claims["scope"]):
        raise TokenError("binding", "token scope does not match issued scope")
    if current_contract_version is not None and claims["ver"] != current_contract_version:
        raise TokenError("stale_contract", f"token bound to contract v{claims['ver']}, current is v{current_contract_version}")
    if ttl_cap is not None and int(time.time()) > claims["iat"] + ttl_cap:
        raise TokenError("expired", "token TTL shortened by trust level (restricted) and has lapsed")
    return claims


def revoke(db: Session, jti: str, reason: str, actor: str) -> list[str]:
    """Revoke a token and, transitively, every token delegated from it."""
    revoked: list[str] = []
    with STATE_LOCK:
        frontier = [jti]
        seen = set()
        while frontier:
            cur = frontier.pop()
            if cur in seen:
                continue
            seen.add(cur)
            rec = db.get(TokenRecord, cur)
            if rec is None:
                continue
            if not rec.revoked:
                rec.revoked = True
                rec.revoked_reason = reason if cur == jti else f"ancestor {jti} revoked: {reason}"
                rec.revoked_at = utcnow()
                revoked.append(cur)
                chain.append(db, "token", agent_id=rec.agent_id, session_id=rec.session_id, task_id=rec.task_id,
                             verdict="revoked", actor=actor,
                             details={"jti": cur, "reason": rec.revoked_reason, "cascade_from": jti if cur != jti else None})
            frontier.extend(db.execute(select(TokenRecord.jti).where(TokenRecord.parent_jti == cur)).scalars())
        db.flush()
    return revoked


def revoke_session(db: Session, session_id: str, reason: str, actor: str) -> list[str]:
    out: list[str] = []
    for jti in list(db.execute(select(TokenRecord.jti).where(TokenRecord.session_id == session_id)).scalars()):
        out += revoke(db, jti, reason, actor)
    return out


def revoke_agent(db: Session, agent_id: str, reason: str, actor: str) -> list[str]:
    out: list[str] = []
    for jti in list(db.execute(select(TokenRecord.jti).where(TokenRecord.agent_id == agent_id,
                                                              TokenRecord.revoked.is_(False))).scalars()):
        out += revoke(db, jti, reason, actor)
    return out
