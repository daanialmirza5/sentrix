"""Operator (dashboard) authentication and role-based authorization.

Demo principals model the PRD personas. Passwords come from TETHER_DEMO_PASSWORD;
this is demo authentication, not an enterprise IdP (documented in docs/security.md).
"""
from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException, Query, status

from ..config import settings
from .keys import secret_file


@dataclass(frozen=True)
class Principal:
    username: str
    display: str
    roles: frozenset[str]
    signing_identity: str


# roles: viewer < owner (agent owner) | security (SOC / approver) | admin (platform)
USERS: dict[str, Principal] = {
    "priya": Principal("priya", "Priya (SOC analyst, security approver)", frozenset({"viewer", "security"}), "priya"),
    "meera": Principal("meera", "Meera (agent owner)", frozenset({"viewer", "owner"}), "meera"),
    "arjun": Principal("arjun", "Arjun (platform engineer)", frozenset({"viewer", "owner", "admin"}), "arjun"),
    "auditor": Principal("auditor", "Compliance auditor (read-only)", frozenset({"viewer"}), "tether-system"),
}

SYSTEM = Principal("tether-system", "TETHER system", frozenset({"viewer", "admin", "security", "owner"}), "tether-system")


def _secret() -> str:
    return settings.operator_jwt_secret or secret_file("operator_jwt")


def authenticate(username: str, password: str) -> Principal | None:
    user = USERS.get(username)
    if not user:
        return None
    if not hmac.compare_digest(password.encode(), settings.demo_password.encode()):
        return None
    return user


def issue_operator_token(user: Principal) -> str:
    now = int(time.time())
    return jwt.encode({"sub": user.username, "roles": sorted(user.roles), "iat": now,
                       "exp": now + settings.operator_session_minutes * 60, "typ": "operator"},
                      _secret(), algorithm="HS256")


def decode_operator_token(token: str) -> Principal:
    try:
        claims = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid operator session") from exc
    if claims.get("typ") != "operator" or claims.get("sub") not in USERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid operator session")
    return USERS[claims["sub"]]


def current_user(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "operator login required",
                            headers={"WWW-Authenticate": "Bearer"})
    return decode_operator_token(authorization.split(" ", 1)[1].strip())


def ws_user(token: str | None = Query(default=None)) -> Principal:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token query parameter required")
    return decode_operator_token(token)


def require(*roles: str):
    def dep(user: Principal = Depends(current_user)) -> Principal:
        if not user.roles.intersection(roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {' or '.join(roles)}")
        return user
    return dep


class RateLimiter:
    """Small in-memory sliding-window limiter for sensitive endpoints."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate limit exceeded")
        q.append(now)

    def reset(self) -> None:
        self.hits.clear()


login_limiter = RateLimiter(20, 60)
change_request_limiter = RateLimiter(10, 3600)
