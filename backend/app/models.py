"""SQLAlchemy models. Schema is created with metadata.create_all (see docs/decisions.md, ADR-007)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Agent(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    owner: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="simulated")  # simulated | external
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | archived
    secret_hash: Mapped[str] = mapped_column(String(128))
    canary: Mapped[str] = mapped_column(String(40), unique=True)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    scenario: Mapped[str | None] = mapped_column(String(40), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContractVersion(Base):
    __tablename__ = "contract_versions"
    __table_args__ = (UniqueConstraint("agent_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[dict] = mapped_column(JSON)
    body_hash: Mapped[str] = mapped_column(String(80))
    signatures: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | superseded
    change_request_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ContractDraft(Base):
    __tablename__ = "contract_drafts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    body: Mapped[dict] = mapped_column(JSON)
    inferred: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    created_by: Mapped[str] = mapped_column(String(80))
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    requested_scope: Mapped[list] = mapped_column(JSON, default=list)
    effective_scope: Mapped[list] = mapped_column(JSON, default=list)
    parent_agent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lane: Mapped[str] = mapped_column(String(20), default="normal")  # normal | shadow
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[str] = mapped_column(String(40))
    level: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    lane: Mapped[str] = mapped_column(String(20), default="normal")
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    max_risk: Mapped[float] = mapped_column(Float, default=0.0)
    carried_sensitivity: Mapped[float] = mapped_column(Float, default=0.0)
    bytes_out: Mapped[int] = mapped_column(Integer, default=0)
    last_state: Mapped[str | None] = mapped_column(String(160), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    released_by: Mapped[str | None] = mapped_column(String(80), nullable=True)


class TokenRecord(Base):
    __tablename__ = "tokens"
    jti: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[str] = mapped_column(String(40))
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    parent_jti: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    scope: Mapped[list] = mapped_column(JSON, default=list)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    contract_version: Mapped[int] = mapped_column(Integer)
    issued_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEvent(Base):
    """The hash-chained append-only log. Every security-relevant fact lands here."""
    __tablename__ = "audit_events"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(40), unique=True)
    ts: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    parent_agent_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sensitivity: Mapped[float | None] = mapped_column(Float, nullable=True)
    destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bytes_out: Mapped[int] = mapped_column(Integer, default=0)
    content_trust: Mapped[str | None] = mapped_column(String(20), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    taint_ids: Mapped[list] = mapped_column(JSON, default=list)
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lane: Mapped[str] = mapped_column(String(20), default="normal")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(80))
    hash: Mapped[str] = mapped_column(String(80))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    severity: Mapped[str] = mapped_column(String(20))  # low | medium | high | critical
    risk: Mapped[float] = mapped_column(Float)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    card: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | acknowledged | resolved
    event_seqs: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IngestedContent(Base):
    __tablename__ = "ingested_content"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_hash: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(300))
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    trust: Mapped[str] = mapped_column(String(20))
    spans: Mapped[list | None] = mapped_column(JSON, nullable=True)  # raw spans; purged after retention unless flagged
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    flagged_spans: Mapped[list] = mapped_column(JSON, default=list)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    retain_until: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TaintWindow(Base):
    __tablename__ = "taint_windows"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    source: Mapped[str] = mapped_column(String(300))
    content_id: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(80))
    opened_step: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HoneyResource(Base):
    __tablename__ = "honey_resources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(300), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # file | endpoint
    description: Mapped[str] = mapped_column(String(300))
    decoy_kind: Mapped[str] = mapped_column(String(40), default="salary_sheet")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeceptionHit(Base):
    __tablename__ = "deception_hits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # honey | canary | dlp
    resource: Mapped[str | None] = mapped_column(String(300), nullable=True)
    canary_owner: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canary_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    event_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    base_version: Mapped[int] = mapped_column(Integer)
    changes: Mapped[dict] = mapped_column(JSON)
    justification: Mapped[str] = mapped_column(Text)
    requester: Mapped[str] = mapped_column(String(80))
    requester_sig: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected
    approver: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approver_sig: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StepUpRequest(Base):
    __tablename__ = "step_up_requests"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str] = mapped_column(String(40))
    tool: Mapped[str] = mapped_column(String(80))
    args_hash: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(300))
    risk: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | denied | used
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DelegationEdge(Base):
    __tablename__ = "delegation_edges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_agent_id: Mapped[str] = mapped_column(String(80), index=True)
    child_agent_id: Mapped[str] = mapped_column(String(80), index=True)
    task_id: Mapped[str] = mapped_column(String(40))
    parent_jti: Mapped[str] = mapped_column(String(40))
    child_jti: Mapped[str] = mapped_column(String(40))
    scope: Mapped[list] = mapped_column(JSON, default=list)
    depth: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AgentState(Base):
    """Trust-ladder state per agent (sessions carry their own level too)."""
    __tablename__ = "agent_state"
    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    level_since: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    clean_windows: Mapped[int] = mapped_column(Integer, default=0)
    window_actions: Mapped[int] = mapped_column(Integer, default=0)
    window_max_risk: Mapped[float] = mapped_column(Float, default=0.0)
    pending: Mapped[str | None] = mapped_column(String(40), nullable=True)  # owner_ack | security_review | manual_release
    owner_acked: Mapped[bool] = mapped_column(Boolean, default=False)
    probation_actions_left: Mapped[int] = mapped_column(Integer, default=0)
    probation_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contagion_level: Mapped[int] = mapped_column(Integer, default=0)
    contagion_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    contagion_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    isi: Mapped[float | None] = mapped_column(Float, nullable=True)
    defaults: Mapped[dict] = mapped_column(JSON, default=dict)
    stripped_caps: Mapped[list] = mapped_column(JSON, default=list)
    last_risk: Mapped[float] = mapped_column(Float, default=0.0)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actions_total: Mapped[int] = mapped_column(Integer, default=0)


class BehaviorBaseline(Base):
    __tablename__ = "behavior_baselines"
    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    role: Mapped[str] = mapped_column(String(80), index=True)
    transitions: Mapped[dict] = mapped_column(JSON, default=dict)  # "a" -> {"b": count}
    n: Mapped[int] = mapped_column(Integer, default=0)
    rate_samples: Mapped[dict] = mapped_column(JSON, default=dict)  # feature -> [values]
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DriftState(Base):
    __tablename__ = "drift_state"
    agent_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="enrolling")  # enrolling | frozen
    anchor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    enroll_windows: Mapped[list] = mapped_column(JSON, default=list)
    current_window: Mapped[list] = mapped_column(JSON, default=list)
    cusum: Mapped[float] = mapped_column(Float, default=0.0)
    cusum_rolling: Mapped[float] = mapped_column(Float, default=0.0)
    rolling_mu: Mapped[list | None] = mapped_column(JSON, nullable=True)
    alarm: Mapped[bool] = mapped_column(Boolean, default=False)
    rolling_alarm: Mapped[bool] = mapped_column(Boolean, default=False)
    history: Mapped[list] = mapped_column(JSON, default=list)
    window_index: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HeartbeatTrial(Base):
    __tablename__ = "heartbeat_trials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    session_id: Mapped[str] = mapped_column(String(40))
    marker: Mapped[str] = mapped_column(String(60))
    obeyed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    profile: Mapped[str] = mapped_column(String(20), default="quick")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(300), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_by: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SystemError_(Base):
    __tablename__ = "system_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    component: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
