"""Stable interface between the classification/CSV engine and the HTTP layer.

This module is owned by the contract: the engine implementation (labeler.py,
processor.py) and the FastAPI layer both code against it and neither may
change the dataclasses here without updating backend/docs/API_CONTRACT.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Protocol, Sequence

#: Labels the contract allows. "unsafe" from the architecture plan does not
#: exist in contracts/README.md and is never emitted; see docs/DECISIONS.md.
LABELS = ("true", "false", "unsure")

EventEmitter = Callable[[str, dict], None]
"""Called by the processor with (event_type, payload).

Allowed keys in payload: message (str), level (TRACE|DEBUG|INFO|WARN|ERROR|FATAL),
step (str), component (str), and the per-type fields documented below.

Allowed event types:
  step.started      step
  step.completed    step, durationMs (int)
  progress.updated  processedRows, totalRows (int|None), counts (dict)
  row.failed        rowId, lineNumber, code, message, column (str|None)
  log.recorded      message, level, step, component
"""


@dataclass(frozen=True)
class RowInput:
    """One dataset row handed to the classifier."""

    id: str
    text: str
    row_date: str | None = None  # ISO 8601 yyyy-mm-dd when the dataset has a date


@dataclass(frozen=True)
class FactClaim:
    """A fact the engine read out of a sentence (display/diagnostics only)."""

    subject: str
    attribute: str
    value: dict
    subject_spelling: str | None = None


@dataclass(frozen=True)
class RowDecision:
    """Classification result for one row.

    confidence is required for true/false (0.5..1.0) and must be None for
    unsure (the judged contract leaves unsure confidence empty).
    fallback=True means the label was assigned because the row could not be
    processed; error carries a stable machine code then.
    """

    id: str
    label: str
    confidence: float | None = None
    facts: tuple[FactClaim, ...] = ()
    fallback: bool = False
    error: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class MappingSpec:
    """Confirmed column mapping for one dataset snapshot."""

    text_column: str
    date_column: str | None = None
    id_column: str | None = None
    result_column: str = "label"


@dataclass
class ProcessOutcome:
    """Result of one processor run over a dataset snapshot."""

    output_path: Path
    total_rows: int
    processed_rows: int
    counts: dict[str, int]  # keys: true, false, unsure, fallback (always present)
    errors: list[dict]      # rowId, lineNumber, code, message, column
    duration_seconds: float
    timed_out: bool = False
    valid: bool = False


class Engine(Protocol):
    """Offline classifier. Must be usable without HTTP, browser or network."""

    def prepare(self, context_rows: Iterable[RowInput] = ()) -> None:
        """Build/refresh the inference context. Called once per job/CLI run."""

    def classify(self, row: RowInput) -> RowDecision:
        """Label one row. Must not raise for row-level problems."""

    def close(self) -> None:
        """Release resources."""


def create_engine(data_dir: str | Path | None = None) -> Engine:  # noqa: ARG001
    """Build the engine used by jobs: the teammates' HTTP classification service.

    data_dir is kept for interface stability; classification context lives in
    the remote service, not in this container.
    """
    from .remote_engine import create_remote_engine_from_settings

    return create_remote_engine_from_settings()


def process_csv(
    input_path: str | Path,
    output_path: str | Path,
    mapping: MappingSpec,
    engine: Engine,
    *,
    deadline_epoch: float | None = None,
    emit: EventEmitter | None = None,
    progress_every: int = 50,
    as_of: str | None = None,
) -> ProcessOutcome:
    """Stream input_path -> output_path, labelling every row.

    The processor owns CSV parsing/serialisation, row order/count integrity,
    deadline behaviour and per-row error containment. It never knows about
    sessions, jobs or WebSockets.
    """
    from .processor import process_csv as _process

    return _process(
        input_path,
        output_path,
        mapping,
        engine,
        deadline_epoch=deadline_epoch,
        emit=emit,
        progress_every=progress_every,
        as_of=as_of,
    )