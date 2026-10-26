"""Behavioral clock. The simulator runs thousands of actions per second, so rate features use a
virtual timestamp the simulator sets per action. Live HTTP traffic uses wall-clock time.
Credential expiry always uses real time (never virtual).
"""
from __future__ import annotations

import contextvars
import time

_virtual: contextvars.ContextVar[float | None] = contextvars.ContextVar("sentrix_virtual_time", default=None)


def now() -> float:
    v = _virtual.get()
    return time.time() if v is None else v


def set_virtual(ts: float | None):
    return _virtual.set(ts)


def reset(token) -> None:
    _virtual.reset(token)
