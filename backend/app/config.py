"""Runtime settings for the offline classification API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


@dataclass(frozen=True)
class Settings:
    model_path: Path
    temp_dir: Path
    manual_max_bytes: int = 1_000_000
    bulk_max_bytes: int = 10_000_000
    job_deadline_seconds: int = 30 * 60
    session_ttl_seconds: int = 6 * 60 * 60
    result_grace_seconds: int = 10 * 60
    cleanup_interval_seconds: int = 60
    event_buffer_size: int = 5_000
    preview_default_rows: int = 50
    page_max_rows: int = 200
    progress_every_rows: int = 50
    as_of_date: str = "2026-10-29"
    cookie_name: str = "n5_session"
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def get_settings() -> Settings:
    return Settings(
        model_path=_env_path("NEURON_MODEL_PATH", BACKEND_ROOT.parent / "ml/classical/results_m2_v2/model.joblib"),
        temp_dir=_env_path("NEURON_TEMP_DIR", Path(os.environ.get("TMPDIR", "/tmp"))),
        manual_max_bytes=_env_int("NEURON_MANUAL_MAX_BYTES", 1_000_000),
        bulk_max_bytes=_env_int("NEURON_BULK_MAX_BYTES", 10_000_000),
        job_deadline_seconds=_env_int("NEURON_JOB_DEADLINE_SECONDS", 30 * 60),
        session_ttl_seconds=_env_int("NEURON_SESSION_TTL_SECONDS", 6 * 60 * 60),
        result_grace_seconds=_env_int("NEURON_RESULT_GRACE_SECONDS", 10 * 60),
        cleanup_interval_seconds=_env_int("NEURON_CLEANUP_INTERVAL_SECONDS", 60),
        event_buffer_size=_env_int("NEURON_EVENT_BUFFER_SIZE", 5_000),
        preview_default_rows=_env_int("NEURON_PREVIEW_DEFAULT_ROWS", 50),
        page_max_rows=_env_int("NEURON_PAGE_MAX_ROWS", 200),
        progress_every_rows=_env_int("NEURON_PROGRESS_EVERY_ROWS", 50),
        as_of_date=os.environ.get("NEURON_AS_OF", "2026-10-29"),
    )
