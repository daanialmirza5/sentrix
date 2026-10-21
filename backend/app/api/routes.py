"""REST API (TRD 6). Endpoints that need the Trust Ladder policy engine (BLOCKERS.md #3) fail closed."""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import chain
from ..broker import tokens
from ..config import REPO_DIR, settings
from ..contracts import registry
from ..contracts.compiler import compile_contract
from ..contracts.schema import RoleContract, parse_contract_text, to_yaml
from ..database import get_db
from ..engines import behavior, deception, provenance, rolefit
from ..engines.deception import canary_for, mask
from ..engines.embeddings import embedder
from ..fusion import explainer
from ..fusion.risk import fuse
from ..gateway import tools
from ..models import (Agent, AgentSession, AuditEvent, ChangeRequest, ContractDraft, HoneyResource, Task, TokenRecord,
                      utcnow)
from ..security import keys
from ..security.auth import (USERS, Principal, authenticate, change_request_limiter, current_user,
                             issue_operator_token, login_limiter, require)

router = APIRouter(prefix="/v1")
POLICY_ENGINE_STATUS = {"available": False, "reason": "Trust Ladder policy engine not implemented (docs/BLOCKERS.md #3)"}


def _err(exc: registry.ContractError):
    raise HTTPException(exc.status, str(exc))


# ------------------------------------------------------------------ health / auth
@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "degraded", "database": "ok", "event_bus": "in-process (Redis not configured)"
            if not settings.redis_url else "redis configured (unverified)",
            "embeddings": embedder.status(), "behavior_engine": behavior.status(),
            "policy_engine": POLICY_ENGINE_STATUS,
            "note": "degraded: gateway fails closed because the policy engine is unavailable"}


class LoginIn(BaseModel):
    username: str = Field(max_length=40)
    password: str = Field(max_length=200)


@router.post("/auth/login")
def login(body: LoginIn, request: Request):
    login_limiter.check(request.client.host if request.client else "local")
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(401, "invalid credentials")
    return {"token": issue_operator_token(user), "user": {"username": user.username, "display": user.display,
                                                          "roles": sorted(user.roles)}}


@router.get("/auth/me")
def me(user: Principal = Depends(current_user)):
    return {"username": user.username, "display": user.display, "roles": sorted(user.roles)}


# ------------------------------------------------------------------ agents
class AgentIn(BaseModel):
    agent_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,79}$")
    name: str = Field(max_length=120)
    owner: str
    role: str = Field(max_length=80)
    kind: str = Field(default="simulated", pattern="^(simulated|external)$")


@router.post("/agents", status_code=201)
def register_agent(body: AgentIn, db: Session = Depends(get_db), user: Principal = Depends(require("admin", "owner"))):
    if body.owner not in USERS:
        raise HTTPException(422, "owner must be a known user")
    if db.get(Agent, body.agent_id):
        raise HTTPException(409, "agent already exists")
    secret = secrets.token_urlsafe(24)
    db.add(Agent(id=body.agent_id, name=body.name, owner=body.owner, role=body.role, kind=body.kind,
                 secret_hash=keys.sha256_hex(secret), canary=canary_for(body.agent_id)))
    chain.append(db, "admin", agent_id=body.agent_id, actor=user.username, verdict="agent_registered",
                 details={"owner": body.owner, "role": body.role})
    return {"agent_id": body.agent_id, "agent_secret": secret, "note": "agent_secret is shown once"}


def _agent_view(db: Session, a: Agent) -> dict:
    cv = registry.active_version(db, a.id)
    return {"id": a.id, "name": a.name, "owner": a.owner, "role": a.role, "kind": a.kind, "status": a.status,
            "contract_version": cv.version if cv else None, "canary": mask(a.canary),
            "created_at": a.created_at.isoformat()}


@router.get("/agents")
def list_agents(db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    return [_agent_view(db, a) for a in db.execute(select(Agent).order_by(Agent.id)).scalars()]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    a = db.get(Agent, agent_id) or _404("agent")
    return _agent_view(db, a)


def _404(what: str):
    raise HTTPException(404, f"{what} not found")


# ------------------------------------------------------------------ contracts
class CompileIn(BaseModel):
    agent_id: str
    owner: str
    manifest: dict
    system_prompt: str = Field(max_length=20000)


@router.post("/contracts/compile", status_code=201)
def compile_(body: CompileIn, db: Session = Depends(get_db), user: Principal = Depends(require("admin", "owner"))):
    out = compile_contract(body.manifest, body.system_prompt, body.agent_id, body.owner)
    d = ContractDraft(id="dr-" + uuid.uuid4().hex[:8], agent_id=body.agent_id, body=out["body"],
                      inferred=out["inferred"], warnings=out["warnings"], created_by=user.username)
    db.add(d)
    return {"draft_id": d.id, **out}


class PublishIn(BaseModel):
    contract: dict | None = None
    contract_text: str | None = Field(default=None, max_length=100000)
    draft_id: str | None = None
    reviewed: bool = False


@router.post("/contracts/{agent_id}/versions", status_code=201)
def publish(agent_id: str, body: PublishIn, db: Session = Depends(get_db), user: Principal = Depends(require("security"))):
    agent = db.get(Agent, agent_id) or _404("agent")
    if not body.reviewed:
        raise HTTPException(422, "human review must be confirmed (reviewed=true) before publishing")
    if body.draft_id:
        d = db.get(ContractDraft, body.draft_id) or _404("draft")
        data = body.contract or d.body
        d.status, d.reviewed_by = "published", user.username
    elif body.contract_text:
        try:
            data = parse_contract_text(body.contract_text)
        except Exception as exc:
            raise HTTPException(422, f"could not parse contract: {exc}") from exc
    elif body.contract:
        data = body.contract
    else:
        raise HTTPException(422, "provide contract, contract_text or draft_id")
    if data.get("agent_id") != agent_id:
        raise HTTPException(422, "contract agent_id does not match the path")
    try:
        cv = registry.publish_initial(db, data, agent.owner, user, user.username)
    except registry.ContractError as exc:
        _err(exc)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"agent_id": agent_id, "version": cv.version, "body_hash": cv.body_hash}


@router.get("/contracts/{agent_id}")
def contract_versions(agent_id: str, db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    out = []
    for cv in registry.versions(db, agent_id):
        out.append({"version": cv.version, "status": cv.status, "body": cv.body, "body_hash": cv.body_hash,
                    "verification": registry.verify_version(cv), "change_request_id": cv.change_request_id,
                    "created_by": cv.created_by, "created_at": cv.created_at.isoformat()})
    if not out:
        _404("contract")
    return out


@router.get("/contracts/{agent_id}/export", response_class=PlainTextResponse)
def export_contract(agent_id: str, fmt: str = "yaml", db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    cv = registry.active_version(db, agent_id) or _404("contract")
    import json
    body = {**cv.body, "signatures": cv.signatures}
    return to_yaml(body) if fmt == "yaml" else json.dumps(body, indent=2)


@router.get("/contracts/{agent_id}/diff")
def diff(agent_id: str, a: int, b: int, db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    vs = {cv.version: cv for cv in registry.versions(db, agent_id)}
    if a not in vs or b not in vs:
        _404("version")
    return registry.diff_versions(vs[a].body, vs[b].body)


@router.post("/contracts/validate")
def validate(body: PublishIn, _: Principal = Depends(current_user)):
    try:
        data = parse_contract_text(body.contract_text) if body.contract_text else (body.contract or {})
        RoleContract.model_validate(data)
        return {"valid": True}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


# ------------------------------------------------------------------ change requests
class CRIn(BaseModel):
    agent_id: str
    changes: dict
    justification: str = Field(min_length=10, max_length=2000)


class DecisionIn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


def _cr_view(cr: ChangeRequest) -> dict:
    return {"id": cr.id, "agent_id": cr.agent_id, "base_version": cr.base_version, "changes": cr.changes,
            "justification": cr.justification, "requester": cr.requester, "status": cr.status,
            "approver": cr.approver, "resulting_version": cr.resulting_version, "decision_note": cr.decision_note,
            "requester_signed": bool(cr.requester_sig), "approver_signed": bool(cr.approver_sig),
            "created_at": cr.created_at.isoformat(), "decided_at": cr.decided_at.isoformat() if cr.decided_at else None}


@router.post("/change-requests", status_code=201)
def submit_cr(body: CRIn, db: Session = Depends(get_db), user: Principal = Depends(require("owner"))):
    change_request_limiter.check(body.agent_id)
    agent = db.get(Agent, body.agent_id) or _404("agent")
    try:
        cr = registry.submit_change_request(db, body.agent_id, body.changes, body.justification, user, agent.owner)
    except registry.ContractError as exc:
        _err(exc)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _cr_view(cr)


@router.get("/change-requests")
def list_crs(db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    return [_cr_view(c) for c in db.execute(select(ChangeRequest).order_by(ChangeRequest.created_at.desc())).scalars()]


@router.post("/change-requests/{cr_id}/approve")
def approve_cr(cr_id: str, body: DecisionIn, db: Session = Depends(get_db), user: Principal = Depends(require("security"))):
    try:
        cr, cv = registry.approve_change_request(db, cr_id, user, body.note, settings.probation_actions)
    except registry.ContractError as exc:
        _err(exc)
    return {**_cr_view(cr), "new_version": cv.version}


@router.post("/change-requests/{cr_id}/reject")
def reject_cr(cr_id: str, body: DecisionIn, db: Session = Depends(get_db), user: Principal = Depends(require("security"))):
    try:
        return _cr_view(registry.reject_change_request(db, cr_id, user, body.note))
    except registry.ContractError as exc:
        _err(exc)


# ------------------------------------------------------------------ tasks / gateway
class TaskIn(BaseModel):
    agent_id: str
    description: str = Field(min_length=3, max_length=500)
    scope: list[str] | None = None
    ttl_seconds: int | None = Field(default=None, ge=30, le=900)


@router.post("/tasks", status_code=201)
def create_task(body: TaskIn, request: Request, db: Session = Depends(get_db)):
    agent = db.get(Agent, body.agent_id) or _404("agent")
    secret = request.headers.get("x-agent-secret", "")
    if not secret or keys.sha256_hex(secret) != agent.secret_hash:
        raise HTTPException(401, "agent credentials required (X-Agent-Secret)")
    cv = registry.active_version(db, agent.id)
    if cv is None or not registry.is_trusted(cv):
        raise HTTPException(409, "agent has no trusted (signed) contract; refusing to mint credentials")
    scope = tokens.effective_scope(cv.body["allowed_tools"], body.scope, None)
    tid, sid = "t-" + uuid.uuid4().hex[:8], "s-" + uuid.uuid4().hex[:8]
    db.add(Task(id=tid, agent_id=agent.id, session_id=sid, description=body.description,
                requested_scope=body.scope or [], effective_scope=scope))
    db.add(AgentSession(id=sid, agent_id=agent.id, task_id=tid))
    m = tokens.mint(db, agent_id=agent.id, task_id=tid, session_id=sid, scope=scope, contract_version=cv.version,
                    description=body.description, ttl=body.ttl_seconds)
    return {"task_id": tid, "session_id": sid, "token": m.token, "scope": scope, "expires_at": m.claims["exp"]}


class InvokeIn(BaseModel):
    token: str = Field(max_length=4096)
    tool: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)


@router.post("/gateway/invoke")
def invoke(body: InvokeIn, db: Session = Depends(get_db)):
    """Fail-closed (TRD 5 fail policy): no verdicts can be produced without the policy engine."""
    claims = tokens.decode_unverified(body.token) or {}
    chain.append(db, "gateway", agent_id=claims.get("sub"), session_id=claims.get("sid"), task_id=claims.get("task"),
                 tool=body.tool, verdict="deny", actor="gateway",
                 details={"reason": "fail_closed_policy_engine_unavailable", "executed": False})
    db.commit()  # persist the audit record before the error response (get_db rolls back on exceptions)
    raise HTTPException(503, "gateway fail-closed: policy engine unavailable; the action was not executed")


# ------------------------------------------------------------------ audit / deception
@router.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    return chain.verify_chain(db)


@router.post("/audit/anchor")
def anchor(db: Session = Depends(get_db), _: Principal = Depends(require("security", "admin"))):
    return chain.anchor_head(db) or {}


@router.get("/audit/events")
def events(limit: int = 100, before: int | None = None, agent_id: str | None = None, db: Session = Depends(get_db),
           _: Principal = Depends(current_user)):
    q = select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(min(max(limit, 1), 500))
    if before:
        q = q.where(AuditEvent.seq < before)
    if agent_id:
        q = q.where(AuditEvent.agent_id == agent_id)
    return [chain.to_dict(e) for e in db.execute(q).scalars()]


@router.get("/deception/honey")
def honey(db: Session = Depends(get_db), _: Principal = Depends(require("security", "admin"))):
    return [{"pattern": h.pattern, "kind": h.kind, "description": h.description, "hits": h.hits, "active": h.active}
            for h in db.execute(select(HoneyResource)).scalars()]


# ------------------------------------------------------------------ credentials
def _token_view(t: TokenRecord, now: int) -> dict:
    status = "revoked" if t.revoked else ("expired" if t.expires_at <= now else "active")
    return {"jti": t.jti, "agent_id": t.agent_id, "task_id": t.task_id, "session_id": t.session_id,
            "parent_jti": t.parent_jti, "scope": t.scope, "depth": t.depth, "contract_version": t.contract_version,
            "issued_at": t.issued_at, "expires_at": t.expires_at, "status": status, "revoked_reason": t.revoked_reason}


@router.get("/tokens")
def list_tokens(agent_id: str | None = None, limit: int = 200, db: Session = Depends(get_db),
                _: Principal = Depends(require("security", "admin"))):
    q = select(TokenRecord).order_by(TokenRecord.issued_at.desc()).limit(min(max(limit, 1), 500))
    if agent_id:
        q = q.where(TokenRecord.agent_id == agent_id)
    now = int(time.time())
    return [_token_view(t, now) for t in db.execute(q).scalars()]


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


@router.post("/tokens/{jti}/revoke")
def revoke_token(jti: str, body: RevokeIn, db: Session = Depends(get_db), user: Principal = Depends(require("security"))):
    rec = db.get(TokenRecord, jti) or _404("token")
    if rec.revoked:
        raise HTTPException(409, "token already revoked")
    revoked = tokens.revoke(db, jti, f"manual: {body.reason}", user.username)
    return {"revoked": revoked, "cascade": len(revoked) - 1}


# ------------------------------------------------------------------ Signal Lab (analysis only)
FIXTURES = {"poisoned_quote": ("supplier_quote.pdf", tools.POISONED_QUOTE),
            "clean_quote": ("quote_clean.pdf", tools.CLEAN_QUOTE_A)}


class AnalyzeIn(BaseModel):
    agent_id: str
    tool: str = Field(max_length=80)
    args: dict = Field(default_factory=dict)
    steps_since_untrusted: int | None = Field(default=None, ge=0, le=100)
    fixture: str | None = Field(default=None, pattern="^(poisoned_quote|clean_quote)$")
    # Reference attack t3: the payload is what the honey-resource served (synthetic decoy + this agent's canary).
    # Built server-side so the canary value never leaves the backend.
    payload_from_honey: bool = False


@router.post("/analyze")
def analyze(body: AnalyzeIn, db: Session = Depends(get_db), _: Principal = Depends(current_user)):
    """Score a hypothetical action with the real engines. Nothing executes; no state changes; no trust level."""
    cv = registry.active_version(db, body.agent_id) or _404("contract")
    if not registry.is_trusted(cv):
        raise HTTPException(409, "contract signatures invalid; refusing to analyse against it")
    contract = registry.load_contract(cv)
    args = dict(body.args)
    if body.payload_from_honey:
        if body.tool != "http.post":
            raise HTTPException(422, "payload_from_honey applies to http.post only")
        args["body"] = deception.decoy_content("salary_sheet", body.agent_id)
    try:
        action = tools.describe(body.tool, args)
    except tools.ToolError as exc:
        raise HTTPException(422, f"invalid action: {exc}") from exc
    rf = rolefit.score(action, contract)
    dec = deception.inspect(db, action)
    prov: dict[str, Any] = {"s_p": 0.0, "tau": None, "window_id": None, "source": None, "steps_since": None, "attribution": None}
    if body.steps_since_untrusted is not None and body.fixture:
        src, text = FIXTURES[body.fixture]
        tau = provenance.tau(body.steps_since_untrusted)
        o = 1.0 if rf.out_of_contract else 0.4 * rf.s_r
        prov.update(s_p=round(tau * o, 4), tau=round(tau, 4), window_id="what-if", source=src,
                    steps_since=body.steps_since_untrusted)
        if rf.out_of_contract:
            prov["attribution"] = {"source": src, "content_hash": "sha256:" + keys.sha256_hex(text),
                                   **provenance.rank_spans(provenance.split_spans(text), action.text())}
    # S: sensitivity x egress (analysis approximation, documented in docs/decisions.md ADR-011)
    if action.action_type in {"egress", "message"} or (action.destination and action.action_type == "tool_call"):
        dest_risk = 0.05 if action.destination in contract.egress_allowlist or action.destination == "erp.internal" else 1.0
        s_s = max(action.sensitivity, dec.payload_sensitivity) * dest_risk
    else:
        s_s = 0.5 * action.sensitivity if "domain_not_allowed" in rf.hard_deny or "deny_domain" in rf.hard_deny else 0.0
    fused = fuse({"R": rf.s_r, "B": 0.0, "P": prov["s_p"], "S": s_s}, deception=dec.d)
    rf_d = {"rules": rf.rules, "fit": rf.fit, "nearest_anchor": rf.nearest_anchor}
    dec_d = {"honey": dec.honey, "canaries": [{"masked": c["masked"], "owner": c["owner"]} for c in dec.canaries],
             "dlp": dec.dlp}
    act = {"verb": action.verb, "resource": action.resource, "tool": action.tool}
    return {
        "analysis_only": True,
        "action": {**act, "action_type": action.action_type, "destination": action.destination,
                   "bytes_out": action.bytes_out, "sensitivity": action.sensitivity, "text": action.text()},
        "signals": fused.signals, "contributions": fused.contributions, "risk": fused.risk, "risk_raw": fused.risk_raw,
        "override": fused.override, "disabled_signals": fused.disabled,
        "role_fit": {**rf_d, "s_r": rf.s_r, "hard_deny": rf.hard_deny, "semantic_score": rf.semantic_score,
                     "mode": rf.mode, "out_of_contract": rf.out_of_contract},
        "deception": dec_d, "provenance": prov,
        "explanation": {"why": explainer.why(act, rf_d, prov, dec_d), "factors": explainer.factor_line(fused),
                        "cause": explainer.cause_line(prov["attribution"])},
        "would_hard_deny": bool(rf.hard_deny) or dec.d,
        "trust_level": None,
        "note": "Analysis only. Nothing was executed and no state changed. Trust-level mapping needs the policy "
                "engine, which is not implemented (docs/BLOCKERS.md #3).",
    }


# ------------------------------------------------------------------ reports
@router.get("/reports/drift")
def drift_report(_: Principal = Depends(current_user)):
    p = REPO_DIR / "reports" / "drift_eval.json"
    if not p.exists():
        raise HTTPException(404, "no drift benchmark yet; run scripts/eval_drift.py")
    import json
    return json.loads(p.read_text())


@router.get("/system/status")
def system_status(_: Principal = Depends(current_user)):
    return {"version": "0.1.0", "embeddings": embedder.status(), "behavior_engine": behavior.status(),
            "policy_engine": POLICY_ENGINE_STATUS, "redis": bool(settings.redis_url), "time": utcnow().isoformat()}
