"""Deception Monitor (TRD 4.5, FR-8): honey-resources, per-agent canary values, egress DLP.

Honey-resources are synthetic decoys no contract should touch; any touch sets D = 1.
Each agent has a unique canary (CNRY-xxxxxxxx, HMAC-derived, never shown to agents) that is
embedded in decoy content. Finding a canary in an outbound payload identifies the leaking agent.
"""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..gateway.tools import ActionDesc
from ..models import Agent, HoneyResource
from ..security.keys import secret_file

CANARY_RE = re.compile(r"CNRY-[0-9a-f]{8}")
DECOY_MARK = "SYNTHETIC-DECOY"
DLP_PATTERNS = {
    "decoy_marker": re.compile(DECOY_MARK),
    "salary_row": re.compile(r"\bEMP-\d{4}\b.*\bINR\b", re.I),
    "bank_account": re.compile(r"\baccount_number\b|\b\d{12}\b"),
}

DEFAULT_HONEY = [
    ("hr/salary_backup.xlsx", "file", "Decoy salary backup (reference honey-resource)", "salary_sheet"),
    ("procurement/vendor_master_export.csv", "file", "Decoy vendor export placed inside the procurement domain",
     "vendor_export"),
    ("secrets/root_credentials.txt", "file", "Decoy credentials file", "credentials"),
    ("internal-api.local/export-all", "endpoint", "Decoy bulk-export endpoint", "bulk_export"),
]


@dataclass
class DeceptionResult:
    d: bool = False
    honey: str | None = None
    canaries: list[dict] = field(default_factory=list)
    dlp: list[str] = field(default_factory=list)
    payload_sensitivity: float = 0.0


def canary_for(agent_id: str) -> str:
    key = secret_file("canary_hmac").encode()
    return "CNRY-" + hmac.new(key, agent_id.encode(), hashlib.sha256).hexdigest()[:8]


def mask(canary: str) -> str:
    return canary[:9] + "…"


def seed_honey(db: Session) -> None:
    for pattern, kind, desc, decoy in DEFAULT_HONEY:
        if not db.execute(select(HoneyResource).where(HoneyResource.pattern == pattern)).scalar():
            db.add(HoneyResource(pattern=pattern, kind=kind, description=desc, decoy_kind=decoy))
    db.flush()


def honey_match(db: Session, action: ActionDesc) -> HoneyResource | None:
    if not action.domain:
        return None
    candidates = [action.domain]
    if action.domain.startswith("external/"):
        candidates.append(action.domain[len("external/"):])
    for h in db.execute(select(HoneyResource).where(HoneyResource.active.is_(True))).scalars():
        if any(fnmatch.fnmatch(c, h.pattern) for c in candidates):
            return h
    return None


def inspect(db: Session, action: ActionDesc) -> DeceptionResult:
    res = DeceptionResult()
    if not settings.pillars.get("deception", True):
        return res
    h = honey_match(db, action)
    if h is not None:
        res.d, res.honey = True, h.pattern
    if action.payload_text:
        found = set(CANARY_RE.findall(action.payload_text))
        if found:
            owners = {a.canary: a.id for a in db.execute(select(Agent).where(Agent.canary.in_(found))).scalars()}
            for c in sorted(found):
                res.canaries.append({"masked": mask(c), "owner": owners.get(c), "value": c})
            if owners:
                res.d = True
        for name, pat in DLP_PATTERNS.items():
            if pat.search(action.payload_text):
                res.dlp.append(name)
        if res.dlp or res.canaries:
            res.payload_sensitivity = 0.95
    return res


def decoy_content(kind: str, agent_id: str) -> str:
    """Synthetic decoy data with the requesting agent's canary. Contains no real records."""
    c = canary_for(agent_id)
    if kind == "salary_sheet":
        rows = [f"EMP-{1000 + i:04d},Test Person {i},INR {(12 + i) * 100000:,},ref={c}" for i in range(1, 9)]
        return f"# {DECOY_MARK} salary sheet\nemployee_id,name,annual_ctc,ref\n" + "\n".join(rows)
    if kind == "vendor_export":
        rows = [f"vendor-{i:03d},SYNTH{i:05d},{c}" for i in range(1, 9)]
        return f"# {DECOY_MARK} vendor export\nvendor,gstin,ref\n" + "\n".join(rows)
    if kind == "credentials":
        return f"# {DECOY_MARK}\nuser=svc-test\ntoken=placeholder-{c}"
    return f"{DECOY_MARK} export ref={c}"
