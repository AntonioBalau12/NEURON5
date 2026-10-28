"""The in-process DEMO classifier: zero-config mock data for the frontend."""

from __future__ import annotations

import csv
import io
from dataclasses import replace
from pathlib import Path


from app.engine.api import MappingSpec, create_engine
from app.engine.mock_engine import (
    DEMO_WARNING,
    MockClassifierEngine,
    fill_csv_with_mock_labels,
    mock_label,
)
from app.engine.processor import process_csv
from app.engine.remote_engine import RemoteClassifierEngine

MAPPING = MappingSpec(text_column="text", date_column="date", id_column="id", result_column="label")


def test_mock_label_heuristic():
    assert mock_label("Hooly AI Pro costs 59 euros a month.") == ("true", 0.6)
    assert mock_label("Hooly no longer sells the tablet.") == ("false", 0.55)
    assert mock_label("Hooly might launch a server.") == ("unsure", None)
    assert mock_label("") == ("unsure", None)


def test_fill_overwrites_and_appends_result_column():
    existing = b"id,text,date,label\nx-1,plain sentence,2026-01-01,stale\nx-2,Hooly does not sell this.,2026-01-02,\n"
    content, columns, rows, counts = fill_csv_with_mock_labels(existing, "label", "text")
    parsed = list(csv.DictReader(io.StringIO(content.decode())))
    assert columns == ["id", "text", "date", "label"]
    assert rows == 2
    assert [row["label"] for row in parsed] == ["true", "false"]
    assert counts == {"true": 1, "false": 1, "unsure": 0, "fallback": 0}

    appended = b"id,text,date\nx-1,plain sentence,2026-01-01\n"
    content, columns, _rows, _counts = fill_csv_with_mock_labels(appended, "label")
    assert columns == ["id", "text", "date", "label"]
    parsed = list(csv.DictReader(io.StringIO(content.decode())))
    assert parsed[0]["label"] == "true"


def test_fill_handles_ragged_rows():
    ragged = b"id,text\nx-1\nx-2,plain sentence,extra\n"
    content, columns, rows, _counts = fill_csv_with_mock_labels(ragged)
    parsed = list(csv.reader(io.StringIO(content.decode())))
    assert columns == ["id", "text", "label"]
    assert rows == 2
    assert all(len(row) == 3 for row in parsed)


def test_mock_engine_runs_through_the_processor(tmp_path: Path):
    source = tmp_path / "in.csv"
    source.write_text(
        "id,text,date,label\n"
        "m-1,Hooly AI Pro costs 59 euros a month.,2026-04-20,\n"
        "m-2,Hooly no longer sells the tablet.,2026-05-10,\n"
        "m-3,Hooly might launch a server.,2026-06-01,\n",
        encoding="utf-8",
    )
    target = tmp_path / "out.csv"
    events: list[tuple[str, dict]] = []
    outcome = process_csv(
        source,
        target,
        MAPPING,
        MockClassifierEngine(delay_seconds=0),
        emit=lambda event_type, payload: events.append((event_type, payload)),
    )
    assert outcome.valid is True
    assert outcome.total_rows == 3
    assert outcome.counts == {"true": 1, "false": 1, "unsure": 1, "fallback": 0}
    rows = list(csv.DictReader(io.StringIO(target.read_text(encoding="utf-8"))))
    assert [row["label"] for row in rows] == ["true", "false", "unsure"]
    assert [row["id"] for row in rows] == ["m-1", "m-2", "m-3"]
    warnings = [payload.get("message") for event_type, payload in events if event_type == "log.recorded"]
    assert DEMO_WARNING in warnings


def test_create_engine_uses_mock_only_without_remote_urls(monkeypatch):
    monkeypatch.delenv("NEURON_CLASSIFIER_URLS", raising=False)
    monkeypatch.delenv("NEURON_CLASSIFIER_URL", raising=False)
    engine = create_engine()
    assert isinstance(engine, MockClassifierEngine)

    monkeypatch.setenv("NEURON_CLASSIFIER_URLS", "http://classifier.test/classify")
    engine = create_engine()
    assert isinstance(engine, RemoteClassifierEngine)


def test_api_serves_mock_data_end_to_end(monkeypatch, tmp_path: Path):
    """The frontend must work with a bare backend: no classifier service at all."""
    monkeypatch.delenv("NEURON_CLASSIFIER_URLS", raising=False)
    monkeypatch.delenv("NEURON_CLASSIFIER_URL", raising=False)
    import app.api.jobs as jobs_module
    from app.config import get_settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(jobs_module, "engine_factory", create_engine)
    settings = replace(get_settings(), temp_dir=tmp_path / "tmp")
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/v1/sessions").status_code in (200, 201)
        created = client.post(
            "/api/v1/datasets/manual",
            json={
                "columns": ["id", "text", "date"],
                "rows": [
                    ["m-1", "Hooly AI Pro costs 59 euros a month.", "2026-04-20"],
                    ["m-2", "Hooly no longer sells the tablet.", "2026-05-10"],
                ],
            },
        )
        assert created.status_code == 201, created.text
        dataset = created.json()
        confirmed = client.put(
            f"/api/v1/datasets/{dataset['id']}/mapping",
            json={"textColumn": "text", "dateColumn": "date", "idColumn": "id", "resultColumn": "label"},
        )
        assert confirmed.status_code == 200, confirmed.text
        started = client.post("/api/v1/jobs", json={"datasetId": dataset["id"]})
        assert started.status_code == 202, started.text
        job_id = started.json()["job"]["id"]
        import time

        deadline = time.time() + 30
        snapshot = {}
        while time.time() < deadline:
            snapshot = client.get(f"/api/v1/jobs/{job_id}").json()
            if snapshot["status"] in ("succeeded", "failed"):
                break
            time.sleep(0.1)
        assert snapshot["status"] == "succeeded", snapshot
        assert snapshot["counters"]["true"] == 1
        assert snapshot["counters"]["false"] == 1
        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert [row["label"] for row in rows] == ["true", "false"]
