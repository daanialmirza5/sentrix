import time

import jwt
import pytest

from app.audit import chain
from app.broker import tokens
from app.models import AuditEvent


def _mint(db, **kw):
    args = dict(agent_id="proc-agent-07", task_id="t-1", session_id="s-1", scope=["supplier_api.get_quote"],
                contract_version=1, description="get quotes")
    args.update(kw)
    return tokens.mint(db, **args)


def test_scope_intersection():
    assert tokens.effective_scope(["a.x", "b.y", "c.z"], ["b.y", "c.z", "d.w"], None) == ["b.y", "c.z"]
    assert tokens.effective_scope(["a.x", "b.y", "c.z"], ["b.y", "c.z"], ["c.z"]) == ["c.z"]
    assert tokens.effective_scope(["a.x"], None, None) == ["a.x"]
    assert tokens.effective_scope(["a.x"], [], None) == []


def test_mint_and_verify(db):
    m = _mint(db)
    claims = tokens.verify(db, m.token, current_contract_version=1)
    assert claims["scope"] == ["supplier_api.get_quote"] and claims["sub"] == "proc-agent-07"
    assert 300 <= claims["exp"] - claims["iat"] <= 900


def test_ttl_clamped_to_trd_maximum(db):
    m = _mint(db, ttl=99999)
    assert m.claims["exp"] - m.claims["iat"] == 900


def test_expired_rejected(db):
    m = _mint(db, ttl=30)
    payload = dict(m.claims, exp=int(time.time()) - 5)
    forged_expired = jwt.encode(payload, tokens._private_key(), algorithm="EdDSA")
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(db, forged_expired)
    assert e.value.code == "expired"


def test_forged_signature_rejected(db):
    m = _mint(db)
    forged = jwt.encode(dict(m.claims, scope=["http.post"]), "attacker-controlled-key-0123456789abcdef", algorithm="HS256")
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(db, forged)
    assert e.value.code == "invalid_signature"


def test_scope_escalation_by_resigning_impossible(db):
    """Even a validly signed token whose scope differs from the issued record is rejected."""
    m = _mint(db)
    widened = jwt.encode(dict(m.claims, scope=["supplier_api.get_quote", "http.post"]), tokens._private_key(),
                         algorithm="EdDSA")
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(db, widened)
    assert e.value.code == "binding"


def test_stale_contract_version_rejected(db):
    m = _mint(db)
    with pytest.raises(tokens.TokenError) as e:
        tokens.verify(db, m.token, current_contract_version=2)
    assert e.value.code == "stale_contract"


@pytest.mark.parametrize("bad", ["", "abc", "a.b", "x" * 5000, None])
def test_malformed_rejected(db, bad):
    with pytest.raises(tokens.TokenError):
        tokens.verify(db, bad)


def test_revocation_cascades_to_descendants(db):
    root = _mint(db)
    child = _mint(db, agent_id="child-a", task_id="t-2", session_id="s-2", parent_agent_id="proc-agent-07",
                  parent_jti=root.claims["jti"], depth=1)
    grandchild = _mint(db, agent_id="child-b", task_id="t-3", session_id="s-3", parent_agent_id="child-a",
                       parent_jti=child.claims["jti"], depth=2)
    revoked = tokens.revoke(db, root.claims["jti"], "isolate", "test")
    assert set(revoked) == {root.claims["jti"], child.claims["jti"], grandchild.claims["jti"]}
    for m in (root, child, grandchild):
        with pytest.raises(tokens.TokenError) as e:
            tokens.verify(db, m.token)
        assert e.value.code == "revoked"


def test_restricted_ttl_cap(db):
    m = _mint(db)
    with pytest.raises(tokens.TokenError):
        tokens.verify(db, m.token, ttl_cap=-1)


def test_audit_chain_verifies_and_detects_tampering(db):
    for i in range(5):
        chain.append(db, "system", verdict=f"e{i}", details={"i": i})
    db.commit()
    assert chain.verify_chain(db)["valid"]
    ev = db.query(AuditEvent).filter(AuditEvent.seq == 3).one()
    ev.details = {"i": 999}
    db.commit()
    r = chain.verify_chain(db)
    assert not r["valid"] and r["broken_at_seq"] == 3


def test_audit_chain_detects_deletion(db):
    for i in range(4):
        chain.append(db, "system", verdict=f"e{i}")
    db.commit()
    db.query(AuditEvent).filter(AuditEvent.seq == 2).delete()
    db.commit()
    r = chain.verify_chain(db)
    assert not r["valid"] and r["broken_at_seq"] == 3


def test_anchor_detects_full_rewrite(db):
    for i in range(3):
        chain.append(db, "system", verdict=f"e{i}")
    db.commit()
    chain.anchor_head(db)
    db.query(AuditEvent).delete()
    db.commit()
    for i in range(3):
        chain.append(db, "system", verdict=f"forged{i}")
    db.commit()
    r = chain.verify_chain(db)
    assert not r["valid"] and "anchored" in r["reason"]
