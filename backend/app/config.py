"""Runtime settings for the offline classification API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _env_urls() -> tuple[str, ...]:
    raw = os.environ.get("NEURON_CLASSIFIER_URLS") or os.environ.get("NEURON_CLASSIFIER_URL") or ""
    return tuple(u.strip() for u in raw.replace("\n", ",").split(",") if u.strip())


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    repo_root: Path
    data_dir: Path
    contracts_dir: Path
    temp_dir: Path
    manual_max_bytes: int = 1_000_000
    bulk_max_bytes: int = 10_000_000
    max_concurrent_jobs: int = 1
    job_deadline_seconds: int = 30 * 60
    session_ttl_seconds: int = 6 * 60 * 60
    result_grace_seconds: int = 10 * 60
    cleanup_interval_seconds: int = 60
    event_buffer_size: int = 5_000
    preview_default_rows: int = 50
    page_max_rows: int = 200
    progress_every_rows: int = 50
    as_of_date: str = os.environ.get("NEURON_AS_OF", "2026-10-29")
    # Classification is done by the teammates' HTTP services, not locally.
    classifier_urls: tuple[str, ...] = ()
    classifier_mode: str = "csv"  # csv (multipart CSV upload) | rows (JSON rows)
    classifier_field_name: str = "file"
    classifier_timeout_seconds: float = 30 * 60
    classifier_retries: int = 0
    classifier_token: str | None = None
    #: artificial delay of the in-process DEMO classifier (no URLs configured)
    mock_delay_seconds: float = 1.0
    cookie_name: str = "n5_session"
    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def get_settings() -> Settings:
    return Settings(
        repo_root=REPO_ROOT,
        data_dir=_env_path("NEURON_DATA_DIR", REPO_ROOT / "data"),
        contracts_dir=_env_path("NEURON_CONTRACTS_DIR", REPO_ROOT / "contracts"),
        temp_dir=_env_path("NEURON_TEMP_DIR", Path(os.environ.get("TMPDIR", "/tmp"))),
        manual_max_bytes=_env_int("NEURON_MANUAL_MAX_BYTES", 1_000_000),
        bulk_max_bytes=_env_int("NEURON_BULK_MAX_BYTES", 10_000_000),
        max_concurrent_jobs=_env_int("NEURON_MAX_CONCURRENT_JOBS", 1),
        job_deadline_seconds=_env_int("NEURON_JOB_DEADLINE_SECONDS", 30 * 60),
        session_ttl_seconds=_env_int("NEURON_SESSION_TTL_SECONDS", 6 * 60 * 60),
        result_grace_seconds=_env_int("NEURON_RESULT_GRACE_SECONDS", 10 * 60),
        cleanup_interval_seconds=_env_int("NEURON_CLEANUP_INTERVAL_SECONDS", 60),
        event_buffer_size=_env_int("NEURON_EVENT_BUFFER_SIZE", 5_000),
        preview_default_rows=_env_int("NEURON_PREVIEW_DEFAULT_ROWS", 50),
        page_max_rows=_env_int("NEURON_PAGE_MAX_ROWS", 200),
        progress_every_rows=_env_int("NEURON_PROGRESS_EVERY_ROWS", 50),
        classifier_urls=_env_urls(),
        classifier_mode=os.environ.get("NEURON_CLASSIFIER_MODE", "csv"),
        classifier_field_name=os.environ.get("NEURON_CLASSIFIER_FIELD_NAME", "file"),
        classifier_timeout_seconds=_env_float("NEURON_CLASSIFIER_TIMEOUT_SECONDS", 30 * 60),
        classifier_retries=_env_int("NEURON_CLASSIFIER_RETRIES", 0),
        classifier_token=os.environ.get("NEURON_CLASSIFIER_TOKEN") or None,
        mock_delay_seconds=_env_float("NEURON_MOCK_DELAY_SECONDS", 1.0),
    )