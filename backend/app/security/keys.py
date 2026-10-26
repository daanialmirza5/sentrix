"""Ed25519 signing identities (PyNaCl) and canonical serialisation.

Demo identities are generated on first start into data/keys/ (git-ignored). They are
demonstration keys, not enterprise identity credentials (see docs/security.md).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from ..config import settings

_lock = threading.Lock()
_cache: dict[str, SigningKey] = {}

# Identities that can sign. Users map onto these in security/auth.py.
IDENTITIES = ("meera", "arjun", "priya", "sentrix-system", "token-broker")


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _key_path(identity: str) -> Path:
    return settings.keys_dir / f"{identity}.ed25519"


def signing_key(identity: str) -> SigningKey:
    if identity not in IDENTITIES:
        raise KeyError(f"unknown signing identity {identity}")
    with _lock:
        if identity in _cache:
            return _cache[identity]
        path = _key_path(identity)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            sk = SigningKey(base64.b64decode(path.read_bytes()))
        else:
            sk = SigningKey.generate()
            path.write_bytes(base64.b64encode(bytes(sk)))
            try:
                os.chmod(path, 0o600)
            except OSError:  # pragma: no cover - Windows ACLs
                pass
        _cache[identity] = sk
        return sk


def public_key_b64(identity: str) -> str:
    return base64.b64encode(bytes(signing_key(identity).verify_key)).decode()


def sign(identity: str, role: str, payload: Any) -> dict:
    """Return a detached signature record over canonical(payload)."""
    sk = signing_key(identity)
    sig = sk.sign(canonical_json(payload)).signature
    return {
        "identity": identity,
        "role": role,
        "alg": "ed25519",
        "public_key": base64.b64encode(bytes(sk.verify_key)).decode(),
        "signature": base64.b64encode(sig).decode(),
        "payload_sha256": sha256_hex(canonical_json(payload)),
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }


def verify(sig_record: dict, payload: Any) -> bool:
    """Verify against the *registered* public key for the identity, not the one in the record."""
    try:
        identity = sig_record["identity"]
        expected_pk = public_key_b64(identity)
        if sig_record.get("public_key") != expected_pk:
            return False
        VerifyKey(base64.b64decode(expected_pk)).verify(
            canonical_json(payload), base64.b64decode(sig_record["signature"]))
        return True
    except (BadSignatureError, KeyError, ValueError, TypeError):
        return False


def secret_file(name: str, nbytes: int = 32) -> str:
    """Persisted random secret (e.g. operator JWT secret, canary HMAC key)."""
    path = settings.keys_dir / f"{name}.secret"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path.read_text().strip()
        value = secrets.token_hex(nbytes)
        path.write_text(value)
        return value


def reset_cache() -> None:
    with _lock:
        _cache.clear()
