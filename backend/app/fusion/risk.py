"""Noisy-OR risk fusion and per-factor contributions (TRD 4.8, FR-6).

risk_raw = 1 - prod_i (1 - w_i * s_i)        over s = {R, B, P, S}
risk     = 100 * max(risk_raw, drift_term, 0.95 if D else 0)
c_i      = -ln(1 - w_i s_i) / sum_j -ln(1 - w_j s_j)   (sums to 100 %)

B is currently always 0 because the Behavior Engine is not implemented (BLOCKERS.md #2);
the result reports it as disabled rather than as a measured zero.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..config import settings

NAMES = {"R": "Role-fit", "B": "Behavior", "P": "Provenance", "S": "Sensitivity x egress"}


@dataclass
class Fused:
    risk: float
    risk_raw: float
    signals: dict
    contributions: dict
    override: str | None = None
    drift_term: float = 0.0
    disabled: list[str] = field(default_factory=list)


def weights() -> dict:
    return {"R": settings.w_r, "B": settings.w_b, "P": settings.w_p, "S": settings.w_s}


def fuse(s: dict[str, float], deception: bool = False, drift_term: float = 0.0) -> Fused:
    w = weights()
    sig = {k: max(0.0, min(1.0, float(s.get(k, 0.0)))) for k in w}
    terms = {k: min(w[k] * sig[k], 0.999999) for k in w}
    prod = 1.0
    for t in terms.values():
        prod *= 1 - t
    raw = 1 - prod
    logs = {k: abs(-math.log(1 - t)) for k, t in terms.items()}  # abs() avoids displaying -0.0
    total = sum(logs.values())
    contrib = {k: round(100 * v / total, 1) for k, v in logs.items()} if total > 1e-9 else {k: 0.0 for k in w}
    if total > 1e-9:  # fix rounding so the displayed numbers sum to exactly 100
        top = max(contrib, key=contrib.get)
        contrib[top] = round(contrib[top] + 100 - sum(contrib.values()), 1)
    floor = settings.deception_floor if deception else 0.0
    final = max(raw, drift_term, floor)
    override = None
    if deception and floor >= raw and floor >= drift_term:
        override = "deception"
    elif drift_term > raw and drift_term >= floor:
        override = "drift"
    return Fused(risk=round(100 * final, 1), risk_raw=round(100 * raw, 1), signals=sig, contributions=contrib,
                 override=override, drift_term=drift_term, disabled=["B"])
