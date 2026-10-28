"""In-memory stores and record types for sessions, datasets, jobs and events.

Nothing here is persisted: the process owns all state, temporary CSV files
live under settings.temp_dir/neuron5/<run id>/, and the lifespan cleanup
task drops sessions and terminal jobs when their budgets expire.
"""

from __future__ import annotations

import asyncio
import secrets
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import Settings
from ..engine.api import MappingSpec, ProcessOutcome
from .utils import iso_utc, utcnow

ACTIVE_STATUSES = ("queued", "running", "finalizing")
TERMINAL_STATUSES = ("succeeded", "failed")
STAGES = ("queued", "parse", "classify", "write", "validate", "done", "failed")


@dataclass
class SessionRecord:
    id: str
    token: str
    created_at: datetime
    expires_at: datetime


@dataclass
class DatasetRecord:
    id: str
    mode: str
    session_id: str
    path: Path
    created_at: datetime
    byte_size: int
    encoding: str
    delimiter: str
    columns: list[str]
    row_count: int | None
    mapping: dict[str, Any] | None
    warnings: list[str]
    preview_rows: list[list[str]]
    preview_total: int | None = None
    mapping_frozen: bool = False


@dataclass
class JobRecord:
    id: str
    dataset_id: str
    session_id: str
    created_at: datetime
    deadline_at: datetime
    deadline_epoch: float
    input_path: Path
    output_path: Path
    mapping: MappingSpec
    expected_rows: int | None
    expected_columns: list[str]
    progress_every: int
    as_of: str | None = None
    status: str = "queued"
    stage: str = "queued"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    terminal_at: datetime | None = None
    processed_rows: int = 0
    total_rows: int | None = None
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "true": 0,
            "false": 0,
            "unsure": 0,
            "fallback": 0,
            "errors": 0,
        }
    )
    result_available: bool = False
    failure_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    outcome: ProcessOutcome | None = None
    task: asyncio.Task | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True)
class EventRecord:
    sequence_id: int
    job_id: str
    timestamp: datetime
    level: str
    event_type: str
    component: str
    step: str | None
    message: str
    data: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "sequenceId": self.sequence_id,
            "jobId": self.job_id,
            "timestamp": iso_utc(self.timestamp),
            "level": self.level,
            "type": self.event_type,
            "component": self.component,
            "step": self.step,
            "message": self.message,
            "data": dict(self.data),
        }


class JobEventLog:
    """Bounded per-job event history with live subscriber fan-out."""

    def __init__(self, capacity: int) -> None:
        self.capacity = max(1, int(capacity))
        self.events: deque[EventRecord] = deque(maxlen=self.capacity)
        self.last_sequence = 0
        self.dropped = 0
        self.started_emitted = False
        self.subscribers: set[asyncio.Queue[EventRecord]] = set()

    def append(
        self,
        *,
        job_id: str,
        level: str,
        event_type: str,
        component: str,
        step: str | None,
        message: str,
        data: dict[str, Any],
    ) -> EventRecord:
        if len(self.events) >= self.capacity:
            self.dropped += 1
        self.last_sequence += 1
        event = EventRecord(
            sequence_id=self.last_sequence,
            job_id=job_id,
            timestamp=utcnow(),
            level=level,
            event_type=event_type,
            component=component,
            step=step,
            message=message,
            data=dict(data),
        )
        self.events.append(event)
        return event

    def publish(self, event: EventRecord) -> None:
        for queue in list(self.subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - defensive
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover - defensive
                pass

    def events_after(self, sequence_id: int) -> list[EventRecord]:
        return [event for event in self.events if event.sequence_id > sequence_id]

    @property
    def oldest_sequence(self) -> int | None:
        return self.events[0].sequence_id if self.events else None

    def gap_for(self, requested: int) -> tuple[bool, int]:
        """Return (gap, replayFrom) for a client that saw sequence requested."""

        if not self.events:
            return False, max(0, requested) + 1
        oldest = self.events[0].sequence_id
        if requested < oldest - 1:
            return True, oldest
        return False, max(requested + 1, oldest)

    def truncated_for(self, requested: int) -> bool:
        if self.dropped <= 0 or not self.events:
            return False
        return requested < self.events[0].sequence_id - 1


@dataclass
class ApiState:
    settings: Settings
    run_dir: Path
    sessions: dict[str, SessionRecord] = field(default_factory=dict)
    tokens: dict[str, str] = field(default_factory=dict)
    datasets: dict[str, DatasetRecord] = field(default_factory=dict)
    jobs: dict[str, JobRecord] = field(default_factory=dict)
    event_logs: dict[str, JobEventLog] = field(default_factory=dict)
    idempotency: dict[tuple[str, str], str] = field(default_factory=dict)
    active_job_id: str | None = None

    @classmethod
    def create(cls, settings: Settings) -> "ApiState":
        run_dir = settings.temp_dir / "neuron5" / ("run_" + secrets.token_hex(8))
        return cls(settings=settings, run_dir=run_dir)

    def ensure_dirs(self) -> None:
        (self.run_dir / "datasets").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "jobs").mkdir(parents=True, exist_ok=True)

    def dataset_path(self, dataset_id: str) -> Path:
        return self.run_dir / "datasets" / f"{dataset_id}.csv"

    def job_output_path(self, job_id: str) -> Path:
        return self.run_dir / "jobs" / job_id / "result.csv"

    def event_log(self, job_id: str) -> JobEventLog:
        log = self.event_logs.get(job_id)
        if log is None:
            log = JobEventLog(self.settings.event_buffer_size)
            self.event_logs[job_id] = log
        return log

    def session_for_token(self, token: str | None) -> SessionRecord | None:
        if not token:
            return None
        session_id = self.tokens.get(token)
        if session_id is None:
            return None
        session = self.sessions.get(session_id)
        if session is None or session.expires_at <= utcnow():
            return None
        return session

    def active_job(self) -> JobRecord | None:
        if self.active_job_id is None:
            return None
        job = self.jobs.get(self.active_job_id)
        if job is None or job.status not in ACTIVE_STATUSES:
            self.active_job_id = None
            return None
        return job


def job_percent(job: JobRecord) -> int | None:
    total = job.total_rows
    if total is None:
        return None
    if total <= 0:
        return 100 if job.status == "succeeded" else 0
    if job.status == "succeeded":
        return 100
    return max(0, min(100, int(job.processed_rows * 100 / total)))


def job_json(job: JobRecord) -> dict[str, Any]:
    return {
        "id": job.id,
        "datasetId": job.dataset_id,
        "status": job.status,
        "createdAt": iso_utc(job.created_at),
        "startedAt": iso_utc(job.started_at),
        "deadlineAt": iso_utc(job.deadline_at),
        "finishedAt": iso_utc(job.finished_at),
        "progress": {
            "stage": job.stage,
            "processedRows": int(job.processed_rows),
            "totalRows": job.total_rows,
            "percent": job_percent(job),
        },
        "counters": {
            "true": int(job.counts.get("true", 0)),
            "false": int(job.counts.get("false", 0)),
            "unsure": int(job.counts.get("unsure", 0)),
            "fallback": int(job.counts.get("fallback", 0)),
            "errors": int(job.counts.get("errors", 0)),
        },
        "resultAvailable": bool(job.result_available),
        "failureReason": job.failure_reason,
        "warnings": list(job.warnings),
    }


def session_json(session: SessionRecord) -> dict[str, Any]:
    return {
        "sessionId": session.id,
        "createdAt": iso_utc(session.created_at),
        "expiresAt": iso_utc(session.expires_at),
    }
