"""Role-Fit Engine (TRD 4.1). Deterministic contract rules + semantic similarity to anchors.

An explicit rule hit can only *raise* s_R: semantic similarity never overrides a denial.
Needs only the contract, so it scores an agent's very first action (cold start).
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from ..config import settings
from ..contracts.schema import RoleContract
from ..gateway.tools import ActionDesc
from .embeddings import embedder


@dataclass
class RoleFitResult:
    s_r: float
    rules: list[dict] = field(default_factory=list)
    fit: float | None = None
    nearest_anchor: str | None = None
    semantic_score: float | None = None
    mode: str = ""
    hard_deny: list[str] = field(default_factory=list)  # rule ids that force a deny
    out_of_contract: bool = False


def domain_match(path: str, globs: list[str]) -> str | None:
    for g in globs:
        if fnmatch.fnmatch(path, g) or fnmatch.fnmatch(path + "/", g):
            return g
    return None


def score(action: ActionDesc, contract: RoleContract, *, reads_last_min: int = 0,
          session_bytes_out: int = 0) -> RoleFitResult:
    rules: list[dict] = []
    hard: list[str] = []
    s_rule = 0.0

    def hit(rule: str, value: float, detail: str, deny: bool = False):
        nonlocal s_rule
        rules.append({"rule": rule, "score": value, "detail": detail})
        s_rule = max(s_rule, value)
        if deny:
            hard.append(rule)

    dom = action.domain or ""
    checks_domain = action.action_type in {"data_read", "data_write", "tool_call"} and not dom.startswith(("external/", "agents/"))
    denied = domain_match(dom, contract.data_domains.deny) if dom else None
    if denied:
        hit("deny_domain", 1.0, f"resource {action.resource} matches deny-list '{denied}'", deny=True)
    if action.tool not in contract.allowed_tools:
        hit("tool_not_allowed", 0.6, f"tool {action.tool} is not in the role contract", deny=True)
    if checks_domain and dom and not denied and not domain_match(dom, contract.data_domains.allow):
        hit("domain_not_allowed", 0.5, f"data domain of {action.resource} is outside the contract", deny=True)
    if action.destination and action.action_type in {"egress", "ingest", "tool_call"} and action.tool not in {"agent.message"}:
        allowed = set(contract.egress_allowlist)
        if action.destination not in allowed and not action.tool.startswith(("supplier_api", "procurement", "erp", "kb", "hr.")):
            hit("egress_not_allowlisted", 0.6, f"destination {action.destination} is not on the egress allowlist",
                deny=True)
    lim = contract.limits
    if action.action_type == "data_read" and reads_last_min >= lim.reads_per_min:
        hit("rate_limit", 0.5, f"{reads_last_min} reads in the last minute exceeds {lim.reads_per_min}/min")
    if action.bytes_out and session_bytes_out + action.bytes_out > lim.bytes_out_per_task:
        hit("bytes_out_limit", 0.7, f"outbound bytes {session_bytes_out + action.bytes_out} exceed "
                                    f"{lim.bytes_out_per_task} per task", deny=True)
    amount = action.extra.get("amount_inr")
    if amount and lim.pr_value_max_inr and amount > lim.pr_value_max_inr:
        hit("value_limit", 0.7, f"amount INR {amount:,.0f} exceeds contract limit {lim.pr_value_max_inr:,}", deny=True)

    res = RoleFitResult(s_r=0.0, rules=rules, hard_deny=hard, mode=embedder.mode or "")
    if settings.pillars.get("role_fit", True):
        sims = embedder.similarity(action.text(), list(contract.anchors))
        i = int(sims.argmax())
        fit = float(sims[i])
        s_sem = 1.0 - min(1.0, max(0.0, (fit - settings.f_lo) / (settings.f_hi - settings.f_lo)))
        res.fit, res.nearest_anchor, res.semantic_score, res.mode = round(fit, 4), contract.anchors[i], round(s_sem, 4), embedder.mode
        # TRD: deny-list = 1.0, semantic distance otherwise -> take the max.
        res.s_r = max(s_rule, s_sem)
    else:
        res.s_r = s_rule if hard else 0.0  # ablation: rules still enforce, they just do not score
    res.out_of_contract = bool(hard) or res.s_r >= 0.6
    res.s_r = round(min(1.0, res.s_r), 4)
    return res
