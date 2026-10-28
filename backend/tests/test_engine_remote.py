"""Tests for the teammates' HTTP classification integration (no network)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx
import pytest

from app.engine.api import MappingSpec
from app.engine.remote_engine import (
    ClassifierResponseError,
    ClassifierUnavailable,
    RemoteClassifierEngine,
)

MAPPING = MappingSpec(text_column="text", date_column="date", id_column="id", result_column="label")
ROWS = [
    ["x-1", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20", ""],
    ["x-2", "Holdan started at Hooly on 12 January 2026.", "2026-01-12", ""],
    ["x-3", "", "2026-02-01", ""],
]


def write_input(tmp_path: Path, rows=ROWS) -> Path:
    path = tmp_path / "input.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "text", "date", "label"])
        writer.writerows(rows)
    return path


def csv_response(rows, columns=("id", "text", "date", "label")) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def engine_for(handler, **kwargs) -> RemoteClassifierEngine:
    transport = httpx.MockTransport(handler)
    return RemoteClassifierEngine(["http://classifier.test/classify"], transport=transport, **kwargs)


def test_csv_response_becomes_output_table(tmp_path):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["content-type"]
        seen["body"] = request.content
        return httpx.Response(200, headers={"content-type": "text/csv"}, content=csv_response([
            ["x-1", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20", "true"],
            ["x-2", "Holdan started at Hooly on 12 January 2026.", "2026-01-12", "false"],
            ["x-3", "", "2026-02-01", "unsure"],
        ]))

    engine = engine_for(handler, mode="csv")
    result = engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert "multipart/form-data" in seen["content_type"]
    assert b"Hooly AI Pro" in seen["body"]
    assert result.source == "csv"
    assert result.columns == ["id", "text", "date", "label"]
    assert result.total_rows == 3
    assert result.counts == {"true": 1, "false": 1, "unsure": 1, "fallback": 0}
    text = result.content.decode()
    assert text.splitlines()[0] == "id,text,date,label"


def test_narrow_json_results_are_merged_preserving_schema(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["rows"][0]["id"] == "x-1"
        return httpx.Response(200, content=json.dumps({"results": [
            {"id": "x-1", "label": "true", "confidence": 0.9},
            {"id": "x-2", "label": "unsure"},
        ]}).encode())

    engine = engine_for(handler, mode="rows")
    result = engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert result.source == "merged"
    assert result.columns == ["id", "text", "date", "label"]
    parsed = list(csv.DictReader(io.StringIO(result.content.decode())))
    assert [row["id"] for row in parsed] == ["x-1", "x-2", "x-3"]
    assert [row["label"] for row in parsed] == ["true", "unsure", "unsure"]
    assert result.counts == {"true": 1, "false": 0, "unsure": 1, "fallback": 1}
    assert result.errors[0]["rowId"] == "x-3"
    assert result.errors[0]["code"] == "REMOTE_MISSING_RESULT"


def test_full_row_json_becomes_authoritative_table(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"rows": [
            {"id": "x-1", "text": "a", "date": "2026-01-01", "label": "true"},
            {"id": "x-2", "text": "b", "date": "2026-01-02", "label": "false"},
        ]}).encode())

    engine = engine_for(handler, mode="rows")
    result = engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert result.source == "json.rows"
    assert result.total_rows == 2
    assert result.columns[0] == "id"


def test_json_csv_string_and_columns_rows_are_accepted(tmp_path):
    def handler_csv_string(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"csv": "id,text,date,label\nx-1,a,2026-01-01,true\n"}).encode())

    result = engine_for(handler_csv_string).submit_dataset(write_input(tmp_path), MAPPING)
    assert result.total_rows == 1

    def handler_columns_rows(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"columns": ["id", "label"], "rows": [["x-1", "true"], ["x-2", "false"]]}).encode())

    result = engine_for(handler_columns_rows).submit_dataset(write_input(tmp_path), MAPPING)
    assert result.columns == ["id", "label"]
    assert result.total_rows == 2


def test_unreachable_service_raises_unavailable(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    engine = engine_for(handler)
    with pytest.raises(ClassifierUnavailable):
        engine.submit_dataset(write_input(tmp_path), MAPPING)


def test_http_error_raises_unavailable(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    engine = engine_for(handler)
    with pytest.raises(ClassifierUnavailable) as info:
        engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert "500" in str(info.value)


def test_fallback_url_is_used_when_first_fails(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "down" in str(request.url):
            return httpx.Response(503, text="down")
        return httpx.Response(200, headers={"content-type": "text/csv"}, content=csv_response([
            ["x-1", "a", "2026-01-01", "true"],
        ]))

    transport = httpx.MockTransport(handler)
    engine = RemoteClassifierEngine(["http://down.test/classify", "http://up.test/classify"], transport=transport)
    result = engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert result.total_rows == 1
    assert len(calls) == 2


def test_invalid_label_from_service_falls_back_to_unsure(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=json.dumps({"results": [
            {"id": "x-1", "label": "maybe"},
            {"id": "x-2", "label": "true", "confidence": 2.0},
        ]}).encode())

    engine = engine_for(handler, mode="rows")
    result = engine.submit_dataset(write_input(tmp_path), MAPPING)
    assert result.source == "merged"
    parsed = list(csv.DictReader(io.StringIO(result.content.decode())))
    assert parsed[0]["label"] == "unsure"
    assert parsed[1]["label"] == "true"
    assert result.counts["fallback"] == 2  # x-1 invalid label + x-3 missing


def test_garbage_response_is_rejected(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=b"<html>nope</html>")

    engine = engine_for(handler)
    with pytest.raises(ClassifierResponseError):
        engine.submit_dataset(write_input(tmp_path), MAPPING)


def test_no_urls_raises_clearly():
    with pytest.raises(ClassifierUnavailable):
        RemoteClassifierEngine([])