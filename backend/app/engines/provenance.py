"""Provenance and taint tracking (TRD 4.3, FR-4).

* Untrusted ingestion opens a taint window with tau_0 = 1.0, decaying tau(n) = exp(-n / N_half)
  per subsequent session step. A new session is the clean-context boundary.
* s_P = max over active windows of tau * o(a); o(a) = 1 for out-of-contract actions,
  0.4 * s_R for in-contract ones.
* Span attribution ranks the lines of the untrusted content by an instruction-pattern score
  (including inert SENTRIX test markers) and cosine similarity to the action text.
* Privacy: raw spans are kept until retain_until, then purged unless flagged as a cause.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..gateway.tools import INJECTION_MARKER_RE
from ..models import IngestedContent, TaintWindow, utcnow
from ..security.keys import sha256_hex
from .embeddings import embedder

INSTRUCTION_PATTERNS = [r"\bignore\b", r"\binstead\b", r"\bsend (it )?to\b", r"\bdo not tell\b", r"\bdisregard\b",
                        r"\boverride\b", r"\bforward\b"]


@dataclass
class ProvenanceResult:
    s_p: float = 0.0
    tau: float = 0.0
    window_id: str | None = None
    source: str | None = None
    steps_since: int | None = None
    active_windows: list[str] = field(default_factory=list)
    attribution: dict | None = None


def split_spans(text: str) -> list[dict]:
    spans, page, line = [], 1, 0
    for raw in text.splitlines():
        m = re.match(r"^\[page (\d+)\]$", raw.strip())
        if m:
            page, line = int(m.group(1)), 0
            continue
        line += 1
        if raw.strip():
            spans.append({"page": page, "line": line, "text": raw.strip()[:500]})
    return spans


def ingest(db: Session, *, agent_id: str, session_id: str, source: str, text: str, trust: str, step: int,
           taint_seq: int) -> tuple[IngestedContent, TaintWindow | None]:
    h = "sha256:" + sha256_hex(text)
    spans = split_spans(text)
    content = IngestedContent(content_hash=h, source=source, agent_id=agent_id, session_id=session_id, trust=trust,
                              spans=spans, span_count=len(spans),
                              retain_until=utcnow() + timedelta(hours=settings.content_retention_hours))
    db.add(content)
    db.flush()
    window = None
    if trust == "untrusted" and settings.pillars.get("provenance", True):
        window = TaintWindow(id=f"tn-{taint_seq}", session_id=session_id, agent_id=agent_id, source=source,
                             content_id=content.id, content_hash=h, opened_step=step)
        db.add(window)
        db.flush()
    return content, window


def tau(steps: int) -> float:
    return math.exp(-max(0, steps) / settings.taint_n_half)


def active_windows(db: Session, session_id: str) -> list[TaintWindow]:
    return list(db.execute(select(TaintWindow).where(TaintWindow.session_id == session_id,
                                                     TaintWindow.active.is_(True))).scalars())


def score(db: Session, *, session_id: str, step: int, out_of_contract: bool, s_r: float) -> ProvenanceResult:
    res = ProvenanceResult()
    if not settings.pillars.get("provenance", True):
        return res
    o = 1.0 if out_of_contract else 0.4 * s_r
    for w in active_windows(db, session_id):
        n = step - w.opened_step
        t = tau(n)
        if t < settings.taint_floor:
            w.active = False  # fully decayed
            continue
        res.active_windows.append(w.id)
        if t * o >= res.s_p:
            res.s_p, res.tau, res.window_id, res.source, res.steps_since = round(t * o, 4), round(t, 4), w.id, w.source, n
    return res


def _instruction_score(text: str) -> tuple[float, list[str]]:
    if INJECTION_MARKER_RE.search(text):
        return 1.0, ["sentrix-test-injection-marker"]
    hits = [p for p in INSTRUCTION_PATTERNS if re.search(p, text, re.I)]
    return min(1.0, 0.35 * len(hits)), hits


def attribute(db: Session, window_id: str, action_text: str) -> dict | None:
    w = db.get(TaintWindow, window_id)
    if w is None:
        return None
    content = db.get(IngestedContent, w.content_id)
    if content is None or not content.spans:
        return {"source": w.source, "content_hash": w.content_hash, "span": None, "confidence": 0.0,
                "uncertain": True, "note": "raw content no longer retained; only the hash is available"}
    ranked = rank_spans(content.spans, action_text)
    span = ranked["span"]
    content.flagged = True
    flagged = list(content.flagged_spans or [])
    if not any(f["line"] == span["line"] and f["page"] == span["page"] for f in flagged):
        flagged.append(span)
    content.flagged_spans = flagged
    return {"source": w.source, "content_hash": w.content_hash, **ranked}


def rank_spans(spans: list[dict], action_text: str) -> dict:
    """Rank lines by instruction pattern (0.6) + similarity to the action (0.4). Pure; no DB writes."""
    sims = embedder.similarity(action_text, [s["text"] for s in spans])
    scored = []
    for s, sim in zip(spans, sims):
        inst, pats = _instruction_score(s["text"])
        sim_n = max(0.0, min(1.0, (float(sim) - 0.1) / 0.5))
        scored.append((0.6 * inst + 0.4 * sim_n, s, inst, round(float(sim), 3), pats))
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    return {"span": {**best[1], "instruction_score": best[2], "similarity": best[3], "patterns": best[4]},
            "confidence": round(min(1.0, best[0] * 0.7 + (best[0] - second) * 0.6), 3),
            "uncertain": best[0] < 0.4 or (best[0] - second) < 0.1,
            "candidates": [{"page": s["page"], "line": s["line"], "score": round(sc, 3)} for sc, s, *_ in scored[:3]]}


def purge_expired(db: Session) -> int:
    """Drop raw spans past retention unless flagged (flagged spans are kept separately anyway)."""
    db.flush()  # sessions use autoflush=False; pending retention changes must be visible to the query
    n = 0
    for c in db.execute(select(IngestedContent).where(IngestedContent.retain_until < utcnow(),
                                                      IngestedContent.spans.is_not(None))).scalars():
        c.spans = None
        n += 1
    return n
