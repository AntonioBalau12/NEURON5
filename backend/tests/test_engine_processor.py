"""Processor tests: both remote (whole-dataset HTTP) and row-engine modes."""

from __future__ import annotations

import csv
import time
from pathlib import Path

import httpx
import pytest

from app.engine.api import MappingSpec, RowDecision
from app.engine.processor import process_csv
from app.engine.remote_engine import ClassifierUnavailable, RemoteClassifierEngine

MAPPING = MappingSpec(text_column="text", date_column="date", id_column="id", result_column="label")


def write_csv(path: Path, columns, rows) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
    return path


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


class FakeEngine:
    def __init__(self, fail_texts: tuple[str, ...] = ("boom",)):
        self.calls: list = []
        self.fail_texts = fail_texts

    def prepare(self, context_rows=()):
        return None

    def classify(self, row):
        self.calls.append(row)
        if any(token in row.text for token in self.fail_texts):
            raise RuntimeError("row exploded")
        if "false" in row.text:
            return RowDecision(id=row.id, label="false", confidence=0.8)
        if row.text.startswith("unsure"):
            return RowDecision(id=row.id, label="unsure")
        return RowDecision(id=row.id, label="true", confidence=0.9)

    def close(self):
        return None


def test_row_mode_appends_result_column_and_preserves_order(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date"], [
        ["r-1", "true sentence", "2026-01-01"],
        ["r-2", "false sentence", "2026-01-02"],
        ["r-3", "unsure sentence", "2026-01-03"],
    ])
    target = tmp_path / "out.csv"
    outcome = process_csv(source, target, MAPPING, FakeEngine())
    assert outcome.valid is True
    assert outcome.total_rows == 3
    assert outcome.counts == {"true": 1, "false": 1, "unsure": 1, "fallback": 0}
    columns, rows = read_csv(target)
    assert columns == ["id", "text", "date", "label"]
    assert [row["id"] for row in rows] == ["r-1", "r-2", "r-3"]
    assert [row["label"] for row in rows] == ["true", "false", "unsure"]


def test_row_mode_overwrites_existing_result_column(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date", "label"], [
        ["r-1", "true sentence", "2026-01-01", "stale"],
    ])
    target = tmp_path / "out.csv"
    process_csv(source, target, MAPPING, FakeEngine())
    columns, rows = read_csv(target)
    assert columns == ["id", "text", "date", "label"]
    assert rows[0]["label"] == "true"


def test_quoted_newline_and_comma_values_survive(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date"], [
        ["r-1", "line one,\nline two", "2026-01-01"],
    ])
    target = tmp_path / "out.csv"
    process_csv(source, target, MAPPING, FakeEngine())
    _, rows = read_csv(target)
    assert rows[0]["text"] == "line one,\nline two"


def test_row_errors_do_not_stop_the_job(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date"], [
        ["r-1", "true sentence", "2026-01-01"],
        ["r-2", "boom", "2026-01-02"],
        ["r-3", "false sentence", "2026-01-03"],
        ["r-4", "", "2026-01-04"],
    ])
    target = tmp_path / "out.csv"
    events: list = []
    outcome = process_csv(source, target, MAPPING, FakeEngine(), emit=lambda event_type, payload: events.append((event_type, payload)))
    assert outcome.valid is True
    assert outcome.counts["fallback"] == 2
    _, rows = read_csv(target)
    assert [row["label"] for row in rows] == ["true", "unsure", "false", "unsure"]
    codes = {error["code"] for error in outcome.errors}
    assert {"ROW_ERROR", "EMPTY_TEXT"} <= codes
    assert any(event_type == "row.failed" for event_type, _ in events)
    assert any(event_type == "progress.updated" for event_type, _ in events)


def test_invalid_date_is_reported_and_the_row_still_classifies(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date"], [
        ["r-1", "true sentence", "not-a-date"],
    ])
    target = tmp_path / "out.csv"
    engine = FakeEngine()
    outcome = process_csv(source, target, MAPPING, engine)
    assert outcome.counts["true"] == 1
    assert outcome.errors[0]["code"] == "INVALID_DATE"
    assert engine.calls[0].row_date is None


def test_deadline_writes_fallback_rows_instead_of_hanging(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date"], [
        ["r-1", "true sentence", "2026-01-01"],
        ["r-2", "true sentence", "2026-01-02"],
    ])
    target = tmp_path / "out.csv"
    engine = FakeEngine()
    outcome = process_csv(source, target, MAPPING, engine, deadline_epoch=time.time() - 1)
    assert outcome.valid is True
    assert outcome.timed_out is True
    assert outcome.counts["fallback"] == 2
    assert engine.calls == []
    _, rows = read_csv(target)
    assert [row["label"] for row in rows] == ["unsure", "unsure"]


def test_remote_mode_stores_the_service_table(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date", "label"], [
        ["r-1", "true sentence", "2026-01-01", ""],
        ["r-2", "false sentence", "2026-01-02", ""],
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        body = "id,text,date,label\nr-1,true sentence,2026-01-01,true\nr-2,false sentence,2026-01-02,false\n"
        return httpx.Response(200, headers={"content-type": "text/csv"}, content=body.encode())

    engine = RemoteClassifierEngine(["http://classifier.test/classify"], transport=httpx.MockTransport(handler))
    target = tmp_path / "out.csv"
    outcome = process_csv(source, target, MAPPING, engine)
    assert outcome.valid is True
    assert outcome.total_rows == 2
    assert outcome.counts == {"true": 1, "false": 1, "unsure": 0, "fallback": 0}
    _, rows = read_csv(target)
    assert [row["label"] for row in rows] == ["true", "false"]


def test_remote_mode_propagates_unavailable_service(tmp_path):
    source = write_csv(tmp_path / "in.csv", ["id", "text", "date", "label"], [["r-1", "a", "2026-01-01", ""]])

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    engine = RemoteClassifierEngine(["http://classifier.test/classify"], transport=httpx.MockTransport(handler))
    with pytest.raises(ClassifierUnavailable):
        process_csv(source, tmp_path / "out.csv", MAPPING, engine)
    assert not (tmp_path / "out.csv").exists()
