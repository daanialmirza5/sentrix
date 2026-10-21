"""Behavior Engine - DISABLED STUB.

The TRD 4.2 Behavior Engine is NOT IMPLEMENTED in this build (see docs/BLOCKERS.md #2).
This stub performs no behavior analysis. It always returns s_b = 0 and reports that the signal
is disabled, so the fusion engine, API and dashboard can show the gap explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import settings

STATUS_REASON = "Behavior Engine not implemented in this build (docs/BLOCKERS.md #2); s_b fixed at 0."


@dataclass
class BehaviorResult:
    s_b: float = 0.0
    enabled: bool = False
    reason: str = STATUS_REASON


def score(*_args, **_kwargs) -> BehaviorResult:
    return BehaviorResult()


def status() -> dict:
    return {"enabled": False, "implemented": False, "configured_flag": settings.behavior_engine_enabled,
            "reason": STATUS_REASON + (" BEHAVIOR_ENGINE_ENABLED=true has no effect." if settings.behavior_engine_enabled else "")}
