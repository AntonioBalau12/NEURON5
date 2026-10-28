"""Processor tests for row-engine CSV handling."""

from __future__ import annotations

import csv
import time
from pathlib import Path

from app.engine.api import MappingSpec, RowDecision
from app.engine.processor import process_csv

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
