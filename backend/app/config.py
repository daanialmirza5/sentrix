"""Environment-driven configuration for TETHER.

All tunables that the TRD names (weights, thresholds, TTLs) live here so they can be
overridden per deployment without code changes. Values default to the TRD numbers.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    env: str = field(default_factory=lambda: _env("TETHER_ENV", "development"))
    data_dir: Path = field(default_factory=lambda: Path(_env("TETHER_DATA_DIR", str(REPO_DIR / "data"))))
    database_url: str = field(default_factory=lambda: _env("TETHER_DATABASE_URL", ""))
    redis_url: str = field(default_factory=lambda: _env("TETHER_REDIS_URL", ""))
    cors_origins: list[str] = field(
        default_factory=lambda: [o.strip() for o in _env(
            "TETHER_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080").split(",") if o.strip()]
    )
    max_request_bytes: int = field(default_factory=lambda: _env_int("TETHER_MAX_REQUEST_BYTES", 2 * 1024 * 1024))

    # Operator auth (dashboard users). Separate secret from agent credentials.
    operator_jwt_secret: str = field(default_factory=lambda: _env("TETHER_OPERATOR_JWT_SECRET", ""))
    demo_password: str = field(default_factory=lambda: _env("TETHER_DEMO_PASSWORD", "tether-demo"))
    operator_session_minutes: int = field(default_factory=lambda: _env_int("TETHER_OPERATOR_SESSION_MINUTES", 480))

    # Task-bound credentials (TRD 2: TTL 5-15 min)
    token_ttl_seconds: int = field(default_factory=lambda: _env_int("TETHER_TOKEN_TTL_SECONDS", 600))
    token_ttl_min_seconds: int = 300
    token_ttl_max_seconds: int = 900
    restricted_ttl_seconds: int = field(default_factory=lambda: _env_int("TETHER_RESTRICTED_TTL_SECONDS", 300))
    max_delegation_depth: int = field(default_factory=lambda: _env_int("TETHER_MAX_DELEGATION_DEPTH", 3))
    delegation_ttl_factor: float = 0.8  # child TTL <= parent remaining * factor

    # Role-fit (TRD 4.1)
    f_lo: float = field(default_factory=lambda: _env_float("TETHER_FIT_LO", 0.15))
    f_hi: float = field(default_factory=lambda: _env_float("TETHER_FIT_HI", 0.55))
    embedding_model: str = field(default_factory=lambda: _env("TETHER_EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    embeddings_enabled: bool = field(default_factory=lambda: _env_bool("TETHER_EMBEDDINGS", True))

    # Behavior (TRD 4.2) - NOT IMPLEMENTED in this build (docs/BLOCKERS.md #2). The stub returns 0.
    behavior_engine_enabled: bool = field(default_factory=lambda: _env_bool("BEHAVIOR_ENGINE_ENABLED", False))

    # Provenance (TRD 4.3)
    taint_n_half: float = field(default_factory=lambda: _env_float("TETHER_TAINT_N_HALF", 5.0))
    taint_floor: float = 0.05
    content_retention_hours: int = field(default_factory=lambda: _env_int("TETHER_CONTENT_RETENTION_HOURS", 24))

    # Drift (TRD 4.4)
    cusum_k: float = field(default_factory=lambda: _env_float("TETHER_CUSUM_K", 0.5))
    cusum_h: float = field(default_factory=lambda: _env_float("TETHER_CUSUM_H", 5.0))
    drift_window: int = 10
    drift_enroll_windows: int = 20  # 12 gave unstable anchors in tests (see docs/decisions.md ADR-005)
    rolling_alpha: float = 0.15

    # Fusion (TRD 4.8)
    w_r: float = 0.55
    w_b: float = 0.35
    w_p: float = 0.60
    w_s: float = 0.60
    deception_floor: float = 0.95

    # Trust ladder (TRD 5)
    clean_window_actions: int = 5
    l1_clean_windows: int = 3
    l2_clean_windows: int = 5
    contagion_lambda: float = 0.5
    contagion_cooldown_seconds: int = 900
    probation_actions: int = field(default_factory=lambda: _env_int("TETHER_PROBATION_ACTIONS", 40))

    # Async / bus
    async_mode: str = field(default_factory=lambda: _env("TETHER_ASYNC_MODE", "thread"))  # thread | inline
    bus_max_queue: int = 10000

    # Feature flags for ablation (benchmark only flips these on an isolated instance)
    pillars: dict[str, bool] = field(default_factory=lambda: {
        "role_fit": True, "task_tokens": True, "provenance": True, "deception": True,
        "drift": True, "delegation": True, "heartbeat": True,
    })

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        if not self.database_url:
            self.database_url = f"sqlite:///{(self.data_dir / 'tether.db').as_posix()}"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"


settings = Settings()


def reload_settings(**overrides) -> Settings:
    """Rebuild the global settings object (used by tests and the isolated benchmark)."""
    global settings
    new = Settings()
    for k, v in overrides.items():
        setattr(new, k, v)
    new.__post_init__()
    settings.__dict__.update(new.__dict__)
    return settings
