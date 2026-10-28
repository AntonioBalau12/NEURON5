"""In-process DEMO classifier used when no teammates' service is configured.

Makes the whole frontend work with zero configuration: if NEURON_CLASSIFIER_URLS
is empty, jobs are classified locally by a tiny keyword heuristic instead of an
HTTP call. Labels are DEMO PLACEHOLDERS, not real classification: the job log
says so explicitly, and every result is reproducible offline.

The same helpers back app/mock_classifier.py, the standalone HTTP stand-in used
when you want to exercise the real HTTP client path (NEURON_CLASSIFIER_URLS
pointing at http://127.0.0.1:8010/classify).
"""

from __future__ import annotations

import csv
import io
import time
from pathlib import Path
from typing import Iterable

from .api import MappingSpec, RowDecision, RowInput, emit_event
from .remote_engine import RemoteResult

FALSE_CUES = (" not ", " never ", " no longer", "discontinu", "cancel", "drops ", "slashes ")
UNSURE_CUES = ("may ", "might ", "could ", "probably ", "rumour", "rumor", "reportedly")
TEXT_COLUMN_CANDIDATES = ("text", "sentence", "proposition", "claim", "content")

DEMO_WARNING = (
    "DEMO classifier: backend mock mode (no NEURON_CLASSIFIER_URLS). "
    "Labels are placeholders, not real classification."
)


def mock_label(text: str) -> tuple[str, float | None]:
    """Deterministic placeholder label for one sentence."""
    lowered = f" {text.strip().lower()} "
    if not text.strip():
        return "unsure", None
    if any(cue in lowered for cue in FALSE_CUES):
        return "false", 0.55
    if any(cue in lowered for cue in UNSURE_CUES):
        return "unsure", None
    return "true", 0.6


def _pick_text_index(header: list[str], text_column: str | None) -> int:
    if text_column:
        for index, name in enumerate(header):
            if name.strip() == text_column.strip():
                return index
    for index, name in enumerate(header):
        if name.strip().lower() in TEXT_COLUMN_CANDIDATES:
            return index
    return 1 if len(header) > 1 else 0


def fill_csv_with_mock_labels(
    data: bytes,
    result_column: str = "label",
    text_column: str | None = None,
) -> tuple[bytes, list[str], int, dict[str, int]]:
    """Return (labelled CSV bytes, columns, data rows, label counts)."""
    text = data.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise ValueError("empty CSV")
    header = [column for column in rows[0]]
    original_columns = len(header)
    text_index = _pick_text_index(header, text_column)
    lowered = [column.strip().lower() for column in header]
    try:
        result_index: int | None = lowered.index(result_column.strip().lower())
    except ValueError:
        result_index = None
        header = header + [result_column]
    counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    data_rows = 0
    for row in rows[1:]:
        if not row:
            continue
        row = list(row)
        if len(row) > original_columns:
            row = row[:original_columns]
        if len(row) < original_columns:
            row = row + [""] * (original_columns - len(row))
        sentence = row[text_index] if text_index < len(row) else ""
        label, _confidence = mock_label(sentence)
        counts[label] += 1
        if result_index is None:
            row = row + [label]
        else:
            if result_index >= len(row):
                row = row + [""] * (result_index - len(row) + 1)
            row[result_index] = label
        writer.writerow(row)
        data_rows += 1
    return output.getvalue().encode("utf-8"), header, data_rows, counts


class MockClassifierEngine:
    """Engine protocol object used when no remote classifier is configured."""

    def __init__(self, *, delay_seconds: float = 1.0) -> None:
        self.delay_seconds = max(0.0, float(delay_seconds))

    def prepare(self, context_rows: Iterable[RowInput] = ()) -> None:  # noqa: ARG002
        return None

    def classify(self, row: RowInput) -> RowDecision:  # pragma: no cover - defensive
        label, confidence = mock_label(row.text)
        return RowDecision(id=row.id, label=label, confidence=confidence, reason="mock")

    def close(self) -> None:
        return None

    def submit_dataset(
        self,
        input_path: str | Path,
        mapping: MappingSpec,
        *,
        as_of: str | None = None,  # noqa: ARG002
        deadline_epoch: float | None = None,  # noqa: ARG002
        emit=None,
    ) -> RemoteResult:
        started = time.time()
        emit_event(emit, "step.started", step="mock", component="mock-classifier",
                    message="Mock classifier: generating demo labels")
        content, columns, total_rows, counts = fill_csv_with_mock_labels(
            Path(input_path).read_bytes(),
            result_column=mapping.result_column or "label",
            text_column=mapping.text_column,
        )
        emit_event(emit, "log.recorded", level="WARN", component="mock-classifier", step="mock",
                    message=DEMO_WARNING)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        emit_event(emit, "step.completed", step="mock", component="mock-classifier",
                    durationMs=int((time.time() - started) * 1000),
                    message=f"Mock classifier labelled {total_rows} rows")
        return RemoteResult(
            content=content,
            columns=columns,
            total_rows=total_rows,
            counts=counts,
            errors=[],
            source="mock",
        )
