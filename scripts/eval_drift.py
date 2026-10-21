"""Drift-pillar benchmark: calibrate CUSUM h on calibration seeds, report on held-out seeds.

Synthetic, isolated (temp DB). Usage:  backend\\.venv\\Scripts\\python.exe scripts\\eval_drift.py
Writes reports/drift_eval.json and reports/drift_eval.md.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import reload_settings, settings  # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp())
reload_settings(data_dir=tmp, database_url=f"sqlite:///{(tmp / 'drift.db').as_posix()}")

import numpy as np  # noqa: E402

from app.database import SessionLocal, create_all, init_engine  # noqa: E402
from app.engines import drift  # noqa: E402
from tests.unit.test_engines import C, _feat  # noqa: E402  (same synthetic action model as the unit test)

ENROLL, BENIGN, DRIFT = 20, 40, 60  # windows of 10 actions


def run(seed: int, h: float, db) -> dict:
    settings.cusum_h = h
    rng = np.random.default_rng(seed)
    a = f"a{seed}-{h}"
    for _ in range(ENROLL * 10):
        drift.observe(db, a, _feat(rng), C.allowed_tools, 1, True)
    max_s = 0.0
    for _ in range(BENIGN * 10):
        r = drift.observe(db, a, _feat(rng), C.allowed_tools, 1, True)
        if r and "S" in r:
            max_s = max(max_s, r["S"])
    st = drift.get_state(db, a)
    fa_frozen, fa_rolling = st.alarm, st.rolling_alarm
    frozen_at = rolling_at = None
    for w in range(DRIFT):
        for _ in range(10):
            r = drift.observe(db, a, _feat(rng, 0.01 * w), C.allowed_tools, 1, True)
        if r and r.get("alarm") and frozen_at is None:
            frozen_at = w
        if r and r.get("rolling_alarm") and rolling_at is None:
            rolling_at = w
    return {"seed": seed, "benign_max_S": round(max_s, 3), "false_alarm": fa_frozen, "rolling_false_alarm": fa_rolling,
            "frozen_alarm_window": frozen_at, "rolling_alarm_window": rolling_at,
            "_trace": [{"window": i + 1, "phase": "benign" if i < BENIGN else "drift", "S": h_["S"],
                        "S_rolling": h_["S_rolling"]} for i, h_ in enumerate(st.history)]}


def summarise(rows: list[dict]) -> dict:
    clean = [r for r in rows if not r["false_alarm"]]
    det = [r for r in clean if r["frozen_alarm_window"] is not None]
    clean_r = [r for r in rows if not r["rolling_false_alarm"]]
    det_r = [r for r in clean_r if r["rolling_alarm_window"] is not None]
    return {"n": len(rows),
            "frozen": {"benign_false_alarm_rate": round(1 - len(clean) / len(rows), 3),
                       "detection_rate": round(len(det) / max(1, len(clean)), 3),
                       "median_delay_windows": float(np.median([r["frozen_alarm_window"] for r in det])) if det else None},
            "rolling": {"benign_false_alarm_rate": round(1 - len(clean_r) / len(rows), 3),
                        "detection_rate": round(len(det_r) / max(1, len(clean_r)), 3),
                        "median_delay_windows": float(np.median([r["rolling_alarm_window"] for r in det_r])) if det_r else None}}


def main() -> None:
    init_engine()
    create_all()
    db = SessionLocal()
    calib_seeds, test_seeds = range(0, 10), range(10, 40)
    default = [run(s, 5.0, db) for s in calib_seeds]
    # Calibrate: smallest h (0.5 steps) above every benign max S on the calibration seeds, x1.2 margin.
    h = float(np.ceil(max(r["benign_max_S"] for r in default) * 1.2 * 2) / 2)
    held_default = [run(s, 5.0, db) for s in test_seeds]
    held_tuned = [run(s, h, db) for s in test_seeds]
    out = {"description": "Synthetic drift benchmark (not production accuracy). 10-action windows; "
                          f"{ENROLL} enrollment, {BENIGN} benign, {DRIFT} drift windows (bank-detail read share 0->0.59).",
           "k": settings.cusum_k, "calibration_seeds": list(calib_seeds), "held_out_seeds": list(test_seeds),
           "calibrated_h": h, "calibration_default_h5": summarise(default),
           "held_out_default_h5": summarise(held_default), "held_out_calibrated": summarise(held_tuned),
           # Time series for the FIRST held-out seed (fixed choice, not cherry-picked) for charting.
           "trace": {"seed": held_tuned[0]["seed"], "h": h, "drift_starts_after_window": BENIGN,
                     "points": held_tuned[0]["_trace"]},
           "rows_held_out_calibrated": [{k: v for k, v in r.items() if k != "_trace"} for r in held_tuned]}
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "drift_eval.json").write_text(json.dumps(out, indent=2))
    md = ["# Drift benchmark (synthetic)", "", out["description"], "",
          f"Calibrated h = **{h}** (k = {settings.cusum_k}), chosen on seeds 0-9 only.", "",
          "| Set | Detector | Benign false-alarm rate | Detection rate | Median delay (windows) |", "|---|---|---|---|---|"]
    for name, key in [("calibration, h=5", "calibration_default_h5"), ("held-out, h=5", "held_out_default_h5"),
                      (f"held-out, h={h}", "held_out_calibrated")]:
        for det in ("frozen", "rolling"):
            s = out[key][det]
            md.append(f"| {name} | {det} | {s['benign_false_alarm_rate']} | {s['detection_rate']} | {s['median_delay_windows']} |")
    (ROOT / "reports" / "drift_eval.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
