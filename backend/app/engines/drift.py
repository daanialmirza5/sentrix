"""Frozen-anchor drift detection with one-sided CUSUM (TRD 4.4, FR-9).

* Enrollment: the first `drift_enroll_windows` clean windows after registration (or after an
  approved change's probation) define mu_0, sigma_0. The anchor is then frozen and signed by the
  tether-system identity. Observed traffic never moves it; only approved changes do (ADR-005).
* Per window: d_t = RMS of z-scores against the anchor; x_t = (d_t - d_mean0) / d_std0.
* CUSUM: S_t = max(0, S_{t-1} + x_t - k), alarm when S_t > h (k=0.5, h=5 by default).
* A rolling EWMA baseline runs alongside the frozen anchor for comparison only.
"""
from __future__ import annotations

import math

import numpy as np
from sqlalchemy.orm import Session

from ..config import settings
from ..models import DriftState, utcnow
from ..security import keys

HISTORY_MAX = 300


def action_features(tool: str, tools: list[str], out_of_contract: bool, s_r: float, sensitivity: float,
                    untrusted_ingest: bool, resource: str | None, bytes_out: int) -> dict:
    return {"tool": tool if tool in tools else "other", "ooc": 1.0 if out_of_contract else 0.0, "s_r": s_r,
            "sens": 1.0 if sensitivity >= 0.4 else 0.0, "untrusted": 1.0 if untrusted_ingest else 0.0,
            "res": resource or "", "bytes": math.log1p(max(0, bytes_out))}


def window_vector(window: list[dict], tools: list[str]) -> list[float]:
    n = len(window)
    vec = [sum(1 for a in window if a["tool"] == t) / n for t in tools + ["other"]]
    vec += [sum(a[k] for a in window) / n for k in ("ooc", "s_r", "sens", "untrusted", "bytes")]
    vec.append(len({a["res"] for a in window}) / n)
    return vec


def _sigma_floor(n_feat: int) -> np.ndarray:
    floor = np.full(n_feat, 0.05)
    floor[-2] = 0.5  # log bytes
    return floor


def _distance(vec: np.ndarray, mu: np.ndarray, sigma: np.ndarray) -> float:
    return float(np.sqrt(np.mean(((vec - mu) / sigma) ** 2)))


def get_state(db: Session, agent_id: str) -> DriftState:
    st = db.get(DriftState, agent_id)
    if st is None:
        st = DriftState(agent_id=agent_id)
        db.add(st)
        db.flush()
    return st


def _freeze(st: DriftState, tools: list[str], contract_version: int) -> None:
    arr = np.asarray(st.enroll_windows, dtype=float)
    mu = arr.mean(0)
    sigma = np.maximum(arr.std(0), _sigma_floor(arr.shape[1]))
    # Leave-one-out: score each enrollment window against an anchor fitted WITHOUT it, so d_mean/d_std
    # describe unseen benign windows. In-sample stats were optimistic and caused benign false alarms.
    d = []
    for i in range(len(arr)):
        rest = np.delete(arr, i, axis=0)
        d.append(_distance(arr[i], rest.mean(0), np.maximum(rest.std(0), _sigma_floor(arr.shape[1]))))
    d = np.asarray(d)
    anchor = {"tools": tools, "mu": mu.round(5).tolist(), "sigma": sigma.round(5).tolist(),
              "d_mean": round(float(d.mean()), 5), "d_std": round(max(float(d.std()), 0.25), 5),
              "windows": len(arr), "contract_version": contract_version, "captured_at": utcnow().isoformat()}
    anchor["signature"] = keys.sign("tether-system", "anchor", {k: v for k, v in anchor.items() if k != "signature"})
    st.anchor = anchor
    st.status = "frozen"
    st.rolling_mu = anchor["mu"]
    st.cusum = st.cusum_rolling = 0.0
    st.alarm = st.rolling_alarm = False


def anchor_valid(st: DriftState) -> bool:
    if not st.anchor:
        return False
    a = {k: v for k, v in st.anchor.items() if k != "signature"}
    return keys.verify(st.anchor.get("signature", {}), a)


def observe(db: Session, agent_id: str, feat: dict, tools: list[str], contract_version: int,
            clean: bool) -> dict | None:
    """Add one action. Returns the window record when a window closes."""
    if not settings.pillars.get("drift", True):
        return None
    st = get_state(db, agent_id)
    cur = list(st.current_window or []) + [feat]
    if len(cur) < settings.drift_window:
        st.current_window = cur
        return None
    st.current_window = []
    st.window_index += 1
    if st.status == "enrolling":
        if clean:
            st.enroll_windows = list(st.enroll_windows or []) + [window_vector(cur, tools)]
            if len(st.enroll_windows) >= settings.drift_enroll_windows:
                _freeze(st, tools, contract_version)
        st.updated_at = utcnow()
        return {"window": st.window_index, "status": "enrolling", "enrolled": len(st.enroll_windows or [])}

    if not anchor_valid(st):
        rec = {"window": st.window_index, "status": "anchor_invalid", "alarm": True}
        st.alarm = True
        st.history = (list(st.history or []) + [rec])[-HISTORY_MAX:]
        return rec
    a = st.anchor
    vec = np.asarray(window_vector(cur, a["tools"]), dtype=float)
    mu, sigma = np.asarray(a["mu"]), np.asarray(a["sigma"])
    x = (_distance(vec, mu, sigma) - a["d_mean"]) / a["d_std"]
    roll_mu = np.asarray(st.rolling_mu or a["mu"])
    x_roll = (_distance(vec, roll_mu, sigma) - a["d_mean"]) / a["d_std"]
    st.rolling_mu = ((1 - settings.rolling_alpha) * roll_mu + settings.rolling_alpha * vec).round(5).tolist()
    st.cusum = max(0.0, st.cusum + x - settings.cusum_k)
    st.cusum_rolling = max(0.0, st.cusum_rolling + x_roll - settings.cusum_k)
    newly = (not st.alarm) and st.cusum > settings.cusum_h
    st.alarm = st.alarm or st.cusum > settings.cusum_h
    st.rolling_alarm = st.rolling_alarm or st.cusum_rolling > settings.cusum_h
    rec = {"window": st.window_index, "x": round(x, 3), "S": round(st.cusum, 3), "x_rolling": round(x_roll, 3),
           "S_rolling": round(st.cusum_rolling, 3), "alarm": st.alarm, "rolling_alarm": st.rolling_alarm,
           "new_alarm": newly, "h": settings.cusum_h, "ts": utcnow().isoformat()}
    st.history = (list(st.history or []) + [rec])[-HISTORY_MAX:]
    st.updated_at = utcnow()
    return rec


def drift_term(db: Session, agent_id: str, in_probation: bool) -> float:
    """Risk floor contributed by an active drift alarm (fusion: max(risk_raw, drift_term, ...))."""
    if not settings.pillars.get("drift", True):
        return 0.0
    st = db.get(DriftState, agent_id)
    if st is None or not st.alarm or in_probation:
        return 0.0
    over = max(0.0, st.cusum - settings.cusum_h)
    return round(min(0.74, 0.56 + 0.02 * over), 4)  # drift alone -> L2 restrict, never isolate


def reset_for_new_version(db: Session, agent_id: str) -> None:
    """Approved change: re-enroll a fresh anchor after the probation window."""
    st = get_state(db, agent_id)
    st.status = "enrolling"
    st.enroll_windows = []
    st.current_window = []
    st.alarm = st.rolling_alarm = False
    st.cusum = st.cusum_rolling = 0.0
