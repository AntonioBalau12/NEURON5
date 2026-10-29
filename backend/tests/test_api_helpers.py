"""Shared fakes and helpers for the API test-suite.

The engine package (labeler.py / processor.py) is built by another agent in
parallel; API tests therefore patch the module-level seams in
app.api.jobs (engine_factory and process_csv) with deterministic fakes.
The fake processor exercises the real orchestrator, event marshalling,
output validation and result endpoints -- it only replaces CSV labelling.
"""

from __future__ import annotations

import csv
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest
from fastapi.testclient import TestClient

from app.api import jobs as jobs_module
from app.config import get_settings
from app.engine.api import ProcessOutcome, RowDecision, RowInput
from app.main import create_app

TERMINAL = ("succeeded", "failed")


class FakeEngine:
    """Deterministic classifier used by the API tests."""

    def __init__(self) -> None:
        self.prepared = False
        self.prepared_context: tuple[RowInput, ...] = ()
        self.closed = False
        self.classified: list[RowInput] = []

    def prepare(self, context_rows: Iterable[RowInput] = ()) -> None:
        self.prepared = True
        self.prepared_context = tuple(context_rows)

    def classify(self, row: RowInput) -> RowDecision:
        self.classified.append(row)
        text = (row.text or "").casefold()
        if "broken" in text:
            return RowDecision(
                id=row.id,
                label="unsure",
                fallback=True,
                error="FAKE_ROW_ERROR",
                reason="This row is intentionally broken.",
            )
        if re.search(r"\byes\b", text):
            return RowDecision(id=row.id, label="true", confidence=0.9)
        if re.search(r"\bno\b", text):
            return RowDecision(id=row.id, label="false", confidence=0.75)
        return RowDecision(id=row.id, label="unsure")

    def close(self) -> None:
        self.closed = True


class FakeProcessor:
    """Minimal stand-in for process_csv that honours the frozen signature."""

    def __init__(
        self,
        *,
        delay: float = 0.0,
        valid: bool = True,
        timed_out: bool = False,
        raise_error: bool = False,
    ) -> None:
        self.delay = delay
        self.valid = valid
        self.timed_out = timed_out
        self.raise_error = raise_error
        self.deadline_epoch: float | None = None
        self.as_of: str | None = None
        self.calls = 0

    def __call__(
        self,
        input_path,
        output_path,
        mapping,
        engine,
        *,
        deadline_epoch: float | None = None,
        emit: Callable[[str, dict], None] | None = None,
        progress_every: int = 50,
        as_of: str | None = None,
    ) -> ProcessOutcome:
        self.calls += 1
        self.deadline_epoch = deadline_epoch
        self.as_of = as_of
        emit = emit or (lambda event_type, payload: None)
        if self.delay:
            time.sleep(self.delay)
        emit("job.started", {"message": "Job started.", "step": "parse", "component": "processor"})
        emit("step.started", {"step": "parse", "component": "processor"})
        if self.raise_error:
            raise RuntimeError("fake processor exploded")
        with open(input_path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            rows = list(reader)
        text_index = header.index(mapping.text_column) if mapping.text_column in header else 0
        id_index = header.index(mapping.id_column) if mapping.id_column in header else None
        date_index = header.index(mapping.date_column) if mapping.date_column in header else None
        result_index = (
            header.index(mapping.result_column)
            if mapping.result_column in header
            else None
        )
        out_header = list(header) if result_index is not None else list(header) + [mapping.result_column]
        engine.prepare(())
        emit("step.completed", {"step": "parse", "durationMs": 1, "component": "processor"})
        emit("step.started", {"step": "classify", "component": "processor"})
        counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
        errors: list[dict[str, Any]] = []
        out_rows: list[list[str]] = []
        for index, row in enumerate(rows):
            row_id = (
                row[id_index]
                if id_index is not None and id_index < len(row)
                else f"r-{index + 1}"
            )
            text = row[text_index] if text_index < len(row) else ""
            row_date = row[date_index] if date_index is not None and date_index < len(row) else None
            decision = engine.classify(RowInput(id=row_id, text=text, row_date=row_date))
            if decision.label in counts:
                counts[decision.label] += 1
            if decision.fallback:
                counts["fallback"] += 1
                error = {
                    "rowId": row_id,
                    "lineNumber": index + 2,
                    "column": mapping.text_column,
                    "code": decision.error or "ROW_ERROR",
                    "message": decision.reason or "Row failed.",
                }
                errors.append(error)
                emit(
                    "row.failed",
                    {
                        **error,
                        "level": "WARN",
                        "step": "classify",
                        "component": "processor",
                    },
                )
            out_row = list(row)
            if result_index is not None:
                while len(out_row) <= result_index:
                    out_row.append("")
                out_row[result_index] = decision.label
            else:
                out_row.append(decision.label)
            out_rows.append(out_row)
            processed = index + 1
            if processed % max(1, progress_every) == 0:
                emit(
                    "progress.updated",
                    {
                        "processedRows": processed,
                        "totalRows": len(rows),
                        "counts": dict(counts),
                        "step": "classify",
                        "component": "processor",
                    },
                )
        emit(
            "progress.updated",
            {
                "processedRows": len(rows),
                "totalRows": len(rows),
                "counts": dict(counts),
                "step": "classify",
                "component": "processor",
            },
        )
        emit("step.completed", {"step": "classify", "durationMs": 1, "component": "processor"})
        emit("step.started", {"step": "write", "component": "processor"})
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(out_header)
            writer.writerows(out_rows)
        emit("step.completed", {"step": "write", "durationMs": 1, "component": "processor"})
        emit("step.started", {"step": "validate", "component": "processor"})
        emit("step.completed", {"step": "validate", "durationMs": 1, "component": "processor"})
        return ProcessOutcome(
            output_path=output,
            total_rows=len(rows),
            processed_rows=len(rows),
            counts=counts,
            errors=errors,
            duration_seconds=0.02,
            timed_out=self.timed_out,
            valid=self.valid,
        )


def make_app(tmp_path: Path, **overrides: Any):
    settings = replace(get_settings(), temp_dir=Path(tmp_path), **overrides)
    return create_app(settings)


def test_app_preloads_and_retains_reference_graph_during_lifespan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    graph = object()
    calls = []
    monkeypatch.setattr("app.main.preload_reference_graph", lambda: calls.append(graph) or graph)
    with TestClient(make_app(tmp_path)) as client:
        assert client.app.state.reference_graph is graph
        assert client.get("/openapi.json").status_code == 200
    assert calls == [graph]


def install_fake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    engine: FakeEngine | None = None,
    processor: FakeProcessor | None = None,
) -> tuple[FakeEngine, FakeProcessor]:
    classifier = engine or FakeEngine()
    fake_processor = processor or FakeProcessor()
    monkeypatch.setattr(jobs_module, "engine_factory", lambda *, settings=None: classifier)
    monkeypatch.setattr(jobs_module, "process_csv", fake_processor)
    return classifier, fake_processor


def create_session(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/v1/sessions")
    assert response.status_code == 200, response.text
    return response.json()


def manual_dataset(
    client: TestClient,
    rows: list[Any],
    columns: list[str] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"rows": rows}
    if columns is not None:
        body["columns"] = columns
    response = client.post("/api/v1/datasets/manual", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def confirm_mapping(client: TestClient, dataset: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    mapping = dataset.get("mapping") or {}
    body = {
        "textColumn": mapping.get("textColumn") or "text",
        "dateColumn": mapping.get("dateColumn"),
        "idColumn": mapping.get("idColumn"),
        "resultColumn": "label",
    }
    body.update(overrides)
    response = client.put(f"/api/v1/datasets/{dataset['id']}/mapping", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def prepared_dataset(client: TestClient, rows: list[Any]) -> dict[str, Any]:
    return confirm_mapping(client, manual_dataset(client, rows))


def post_job(client: TestClient, dataset_id: str, key: str | None = None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post("/api/v1/jobs", json={"datasetId": dataset_id}, headers=headers)


def wait_for_terminal(client: TestClient, job_id: str, timeout: float = 6.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/jobs/{job_id}")
        if response.status_code == 200:
            last = response.json()
            if last["status"] in TERMINAL:
                return last
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish; last state: {last!r}")


def wait_until(predicate: Callable[[], bool], timeout: float = 4.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition was not met before the timeout")
