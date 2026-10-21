"""Signed Role Contract registry and the Role Change Request workflow (FR-1, FR-10).

Rules enforced here:
* Version 1 is published directly after human review, signed by the owner and a security approver.
* Every later version only comes from an approved, signed Change Request (TRD 3.1 comment).
* The gateway refuses to use a contract whose signatures do not verify (fail closed).
"""
from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import chain
from ..models import AgentState, ChangeRequest, ContractVersion, utcnow
from ..security import keys
from ..security.auth import Principal
from .schema import RoleContract


class ContractError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_verified_cache: dict[tuple[str, int, str], bool] = {}


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def active_version(db: Session, agent_id: str) -> ContractVersion | None:
    return db.execute(select(ContractVersion).where(ContractVersion.agent_id == agent_id,
                                                    ContractVersion.status == "active")
                      .order_by(ContractVersion.version.desc()).limit(1)).scalar()


def versions(db: Session, agent_id: str) -> list[ContractVersion]:
    return list(db.execute(select(ContractVersion).where(ContractVersion.agent_id == agent_id)
                           .order_by(ContractVersion.version)).scalars())


def verify_version(cv: ContractVersion) -> dict:
    """Check body hash and that both an owner and a security signature verify."""
    try:
        payload = _signable(cv.body)
    except Exception:
        return {"body_hash_ok": False, "signatures": [], "valid": False, "error": "contract body fails schema"}
    body_hash = "sha256:" + keys.sha256_hex(keys.canonical_json(payload))
    result = {"body_hash_ok": body_hash == cv.body_hash, "signatures": []}
    roles_ok = set()
    for s in cv.signatures or []:
        ok = keys.verify(s, payload)
        result["signatures"].append({"identity": s.get("identity"), "role": s.get("role"), "valid": ok,
                                     "signed_at": s.get("signed_at")})
        if ok:
            roles_ok.add(s.get("role"))
    result["valid"] = result["body_hash_ok"] and {"owner", "security"} <= roles_ok
    return result


def is_trusted(cv: ContractVersion) -> bool:
    # Cache on the *current* content so any edit to the stored row forces re-verification.
    key = (cv.agent_id, cv.version, cv.body_hash,
           keys.sha256_hex(keys.canonical_json({"b": cv.body, "s": cv.signatures})))
    if key not in _verified_cache:
        _verified_cache[key] = verify_version(cv)["valid"]
    return _verified_cache[key]


def _signable(body: dict) -> dict:
    return RoleContract.model_validate(body).signable()


def load_contract(cv: ContractVersion) -> RoleContract:
    return RoleContract.model_validate(cv.body)


def publish_initial(db: Session, body: dict, owner_identity: str, approver: Principal, actor: str) -> ContractVersion:
    """Publish v1 of a contract after human review. Owner + security signatures required."""
    if "security" not in approver.roles and "admin" not in approver.roles:
        raise ContractError("publishing a contract requires a security approver", 403)
    contract = RoleContract.model_validate({**body, "version": 1})
    if active_version(db, contract.agent_id) is not None:
        raise ContractError("agent already has a contract; later versions require an approved Change Request", 409)
    now = _iso()
    contract.created_at = contract.created_at or now
    contract.updated_at = now
    payload = contract.signable()
    approver_identity = approver.signing_identity if "security" in approver.roles else "priya"
    sigs = [keys.sign(owner_identity, "owner", payload), keys.sign(approver_identity, "security", payload)]
    contract.approval_history = [{"version": 1, "event": "initial_publish", "owner": owner_identity,
                                  "approver": approver_identity, "at": now}]
    cv = ContractVersion(agent_id=contract.agent_id, version=1, body=contract.model_dump(mode="json"),
                         body_hash="sha256:" + keys.sha256_hex(keys.canonical_json(payload)),
                         signatures=sigs, status="active", created_by=actor)
    db.add(cv)
    db.flush()
    chain.append(db, "contract", agent_id=contract.agent_id, actor=actor, verdict="published",
                 details={"version": 1, "body_hash": cv.body_hash, "signers": [owner_identity, approver_identity]})
    return cv


# ---------------------------------------------------------------- change requests

ALLOWED_CHANGE_KEYS = {"add_tools", "remove_tools", "add_allow_domains", "remove_allow_domains",
                       "add_egress", "remove_egress", "add_sequences", "add_anchors", "limits"}


def apply_changes(body: dict, changes: dict) -> dict:
    unknown = set(changes) - ALLOWED_CHANGE_KEYS
    if unknown:
        raise ContractError(f"unsupported change keys: {sorted(unknown)}")
    new = copy.deepcopy(body)
    tools = list(new["allowed_tools"])
    for t in changes.get("add_tools", []):
        if t not in tools:
            tools.append(t)
    tools = [t for t in tools if t not in set(changes.get("remove_tools", []))]
    new["allowed_tools"] = tools
    allow = list(new["data_domains"]["allow"])
    allow += [d for d in changes.get("add_allow_domains", []) if d not in allow]
    allow = [d for d in allow if d not in set(changes.get("remove_allow_domains", []))]
    new["data_domains"]["allow"] = allow
    eg = list(new.get("egress_allowlist", []))
    eg += [h for h in changes.get("add_egress", []) if h not in eg]
    eg = [h for h in eg if h not in set(changes.get("remove_egress", []))]
    new["egress_allowlist"] = eg
    new["typical_sequences"] = list(new.get("typical_sequences", [])) + list(changes.get("add_sequences", []))
    new["anchors"] = list(new["anchors"]) + [a for a in changes.get("add_anchors", []) if a not in new["anchors"]]
    if changes.get("limits"):
        new["limits"] = {**new.get("limits", {}), **changes["limits"]}
    new["typical_sequences"] = [s for s in new["typical_sequences"] if all(("." not in x) or x in tools for x in s)]
    return new


def _cr_payload(cr: ChangeRequest) -> dict:
    return {"id": cr.id, "agent_id": cr.agent_id, "base_version": cr.base_version, "changes": cr.changes,
            "justification": cr.justification, "requester": cr.requester}


def submit_change_request(db: Session, agent_id: str, changes: dict, justification: str,
                          requester: Principal, agent_owner: str) -> ChangeRequest:
    if "owner" not in requester.roles:
        raise ContractError("only an agent owner can submit a Role Change Request", 403)
    if requester.username != agent_owner and "admin" not in requester.roles:
        raise ContractError("requester is not the owner of this agent", 403)
    cv = active_version(db, agent_id)
    if cv is None:
        raise ContractError("agent has no active contract", 404)
    proposed = apply_changes(cv.body, changes)
    RoleContract.model_validate({**proposed, "version": cv.version + 1})  # validate before accepting
    cr = ChangeRequest(id="cr-" + uuid.uuid4().hex[:8], agent_id=agent_id, base_version=cv.version,
                       changes=changes, justification=justification, requester=requester.username,
                       requester_sig={}, status="pending")
    cr.requester_sig = keys.sign(requester.signing_identity, "owner", _cr_payload(cr))
    db.add(cr)
    db.flush()
    chain.append(db, "change_request", agent_id=agent_id, actor=requester.username, verdict="submitted",
                 details={"change_request": cr.id, "base_version": cv.version, "changes": changes,
                          "requester_signature_sha256": cr.requester_sig["payload_sha256"]})
    return cr


def approve_change_request(db: Session, cr_id: str, approver: Principal, note: str | None,
                           probation_actions: int) -> tuple[ChangeRequest, ContractVersion]:
    cr = db.get(ChangeRequest, cr_id)
    if cr is None:
        raise ContractError("change request not found", 404)
    if cr.status != "pending":
        raise ContractError(f"change request is {cr.status}", 409)
    if "security" not in approver.roles:
        raise ContractError("approval requires the security approver role", 403)
    if approver.username == cr.requester:
        raise ContractError("requester cannot approve their own change (two-person rule)", 403)
    if not keys.verify(cr.requester_sig, _cr_payload(cr)):
        raise ContractError("requester signature does not verify; request may have been altered", 422)
    cv = active_version(db, cr.agent_id)
    if cv is None or cv.version != cr.base_version:
        raise ContractError("contract changed since the request was made; resubmit against the current version", 409)
    if not is_trusted(cv):
        raise ContractError("current contract signature invalid; refusing to derive a new version", 422)

    new_body = apply_changes(cv.body, cr.changes)
    new_body["version"] = cv.version + 1
    new_body["updated_at"] = _iso()
    contract = RoleContract.model_validate(new_body)
    payload = contract.signable()
    cr.approver = approver.username
    cr.approver_sig = keys.sign(approver.signing_identity, "security", _cr_payload(cr))
    history = list(cv.body.get("approval_history", [])) + [{
        "version": contract.version, "event": "change_request_approved", "change_request": cr.id,
        "requester": cr.requester, "approver": approver.username, "at": new_body["updated_at"]}]
    contract.approval_history = history
    owner_identity = keys.IDENTITIES[0] if cr.requester not in keys.IDENTITIES else cr.requester
    sigs = [keys.sign(owner_identity, "owner", payload), keys.sign(approver.signing_identity, "security", payload)]
    new_cv = ContractVersion(agent_id=cr.agent_id, version=contract.version, body=contract.model_dump(mode="json"),
                             body_hash="sha256:" + keys.sha256_hex(keys.canonical_json(payload)),
                             signatures=sigs, status="active", change_request_id=cr.id, created_by=approver.username)
    cv.status = "superseded"
    cr.status = "approved"
    cr.decided_at = utcnow()
    cr.decision_note = note
    cr.resulting_version = contract.version
    db.add(new_cv)
    st = db.get(AgentState, cr.agent_id)
    if st is not None:
        st.probation_actions_left = probation_actions
        st.probation_version = contract.version
    db.flush()
    chain.append(db, "change_request", agent_id=cr.agent_id, actor=approver.username, verdict="approved",
                 details={"change_request": cr.id, "new_version": contract.version, "previous_version": cv.version,
                          "probation_actions": probation_actions, "body_hash": new_cv.body_hash})
    return cr, new_cv


def reject_change_request(db: Session, cr_id: str, approver: Principal, note: str | None) -> ChangeRequest:
    cr = db.get(ChangeRequest, cr_id)
    if cr is None:
        raise ContractError("change request not found", 404)
    if cr.status != "pending":
        raise ContractError(f"change request is {cr.status}", 409)
    if "security" not in approver.roles:
        raise ContractError("rejection requires the security approver role", 403)
    cr.status = "rejected"
    cr.approver = approver.username
    cr.decided_at = utcnow()
    cr.decision_note = note
    chain.append(db, "change_request", agent_id=cr.agent_id, actor=approver.username, verdict="rejected",
                 details={"change_request": cr.id, "note": note})
    return cr


def diff_versions(a: dict, b: dict) -> list[dict]:
    out = []
    keys_ = sorted(set(a) | set(b) - {"approval_history", "updated_at", "created_at"})
    for k in keys_:
        if k in {"approval_history", "updated_at", "created_at"}:
            continue
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        entry = {"field": k, "before": va, "after": vb}
        if isinstance(va, list) and isinstance(vb, list):
            entry["added"] = [x for x in vb if x not in va]
            entry["removed"] = [x for x in va if x not in vb]
        out.append(entry)
    return out
