"""Job orchestration, idempotency, state machine and event history tests."""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from test_api_helpers import (
    FakeProcessor,
    confirm_mapping,
    create_session,
    install_fake,
    make_app,
    manual_dataset,
    post_job,
    prepared_dataset,
    wait_for_terminal,
)

ROWS = [
    ["p-1", "This yes happened", "2026-01-01"],
    ["p-2", "This no happened", "2026-01-02"],
    ["p-3", "broken row", "2026-01-03"],
    ["p-4", "Maybe later", "2026-01-04"],
]
TERMINAL = ("succeeded", "failed")
ALLOWED_EVENT_TYPES = {
    "job.started",
    "step.started",
    "step.completed",
    "progress.updated",
    "row.failed",
    "log.recorded",
    "job.completed",
    "job.failed",
}


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    return body


def test_mapping_required_and_unknown_dataset(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        draft = manual_dataset(client, [["p-1", "yes", "2026-01-01"]])
        missing_mapping = post_job(client, draft["id"])
        body = assert_error(missing_mapping, 409, "MAPPING_REQUIRED")
        assert body["error"]["details"]["datasetId"] == draft["id"]
        assert_error(post_job(client, "ds_unknown"), 404, "NOT_FOUND")

        other = TestClient(app)
        try:
            create_session(other)
            foreign = confirm_mapping(
                other, manual_dataset(other, [["p-1", "yes", "2026-01-01"]])
            )
            assert_error(post_job(client, foreign["id"]), 404, "NOT_FOUND")
        finally:
            other.close()


def test_job_lifecycle_and_event_history(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        response = post_job(client, dataset["id"])
        assert response.status_code == 202, response.text
        created = response.json()
        assert created["replayed"] is False
        assert created["job"]["id"].startswith("job_")
        assert created["job"]["status"] == "queued"

        job = wait_for_terminal(client, created["job"]["id"])
        assert job["status"] == "succeeded"
        assert job["failureReason"] is None
        assert job["resultAvailable"] is True
        assert job["datasetId"] == dataset["id"]
        assert set(job) == {
            "id",
            "datasetId",
            "status",
            "createdAt",
            "startedAt",
            "deadlineAt",
            "finishedAt",
            "progress",
            "counters",
            "resultAvailable",
            "failureReason",
            "warnings",
        }
        assert set(job["progress"]) == {"stage", "processedRows", "totalRows", "percent"}
        assert job["progress"]["stage"] == "done"
        assert job["progress"]["processedRows"] == 4
        assert job["progress"]["totalRows"] == 4
        assert job["progress"]["percent"] == 100
        assert job["counters"] == {
            "true": 1,
            "false": 1,
            "unsure": 2,
            "fallback": 1,
            "errors": 1,
        }
        assert job["createdAt"].endswith("Z")
        assert job["startedAt"].endswith("Z")
        assert job["deadlineAt"].endswith("Z")
        assert job["finishedAt"].endswith("Z")
        assert job["warnings"] == []

        events_response = client.get(
            f"/api/v1/jobs/{job['id']}/events?afterSequenceId=0&limit=200"
        )
        assert events_response.status_code == 200, events_response.text
        history = events_response.json()
        assert set(history) == {"events", "lastSequenceId", "truncated", "total"}
        assert history["truncated"] is False
        assert history["total"] == len(history["events"])
        events = history["events"]
        assert events[0]["type"] == "job.started"
        assert events[-1]["type"] == "job.completed"
        assert [event["sequenceId"] for event in events] == list(
            range(1, len(events) + 1)
        )
        assert history["lastSequenceId"] == events[-1]["sequenceId"]
        assert {event["type"] for event in events} <= ALLOWED_EVENT_TYPES
        for event in events:
            assert event["jobId"] == job["id"]
            assert event["timestamp"].endswith("Z")
            assert event["level"] in {"TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"}
            assert isinstance(event["data"], dict)
        row_failed = [event for event in events if event["type"] == "row.failed"]
        assert len(row_failed) == 1
        assert row_failed[0]["data"]["rowId"] == "p-3"
        assert row_failed[0]["data"]["lineNumber"] == 4
        assert row_failed[0]["data"]["code"] == "FAKE_ROW_ERROR"
        assert row_failed[0]["level"] == "WARN"

        filtered = client.get(
            f"/api/v1/jobs/{job['id']}/events?type=row.failed&level=WARN"
        ).json()
        assert filtered["total"] == 1
        assert all(event["type"] == "row.failed" for event in filtered["events"])

        by_component = client.get(
            f"/api/v1/jobs/{job['id']}/events?component=orchestrator"
        ).json()
        assert by_component["total"] >= 2
        assert all(
            event["component"] == "orchestrator" for event in by_component["events"]
        )

        comma_filter = client.get(
            f"/api/v1/jobs/{job['id']}/events?type=job.started,job.completed"
        ).json()
        assert comma_filter["total"] == 2
        assert [event["type"] for event in comma_filter["events"]] == [
            "job.started",
            "job.completed",
        ]

        too_many = client.get(f"/api/v1/jobs/{job['id']}/events?limit=1001")
        assert_error(too_many, 400, "INVALID_REQUEST")

        page = client.get(
            f"/api/v1/jobs/{job['id']}/events?afterSequenceId=3&limit=2"
        ).json()
        assert [event["sequenceId"] for event in page["events"]] == [4, 5]
        assert page["total"] == len(events) - 3


def test_concurrent_second_job_conflict(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.5))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        first = prepared_dataset(client, ROWS)
        second = prepared_dataset(client, ROWS)
        response = post_job(client, first["id"])
        assert response.status_code == 202
        first_job = response.json()["job"]["id"]
        conflict = post_job(client, second["id"])
        body = assert_error(conflict, 409, "JOB_ALREADY_RUNNING")
        assert body["error"]["details"]["activeJobId"] == first_job
        wait_for_terminal(client, first_job)
        after = post_job(client, second["id"])
        assert after.status_code == 202, after.text
        wait_for_terminal(client, after.json()["job"]["id"])


def test_active_job_limit_is_global(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.5))
    app = make_app(tmp_path)
    with TestClient(app) as owner:
        create_session(owner)
        owner_dataset = prepared_dataset(owner, ROWS)
        owner_job = post_job(owner, owner_dataset["id"]).json()["job"]["id"]

        other = TestClient(app)
        try:
            create_session(other)
            other_dataset = prepared_dataset(other, ROWS)
            blocked = post_job(other, other_dataset["id"])
            body = assert_error(blocked, 409, "JOB_ALREADY_RUNNING")
            assert body["error"]["details"]["activeJobId"] == owner_job
        finally:
            other.close()
        wait_for_terminal(owner, owner_job)


def test_idempotency_replay_and_conflict(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.4))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        first = prepared_dataset(client, ROWS)
        second = prepared_dataset(client, ROWS)
        key = "click-attempt-1"
        original = post_job(client, first["id"], key=key)
        assert original.status_code == 202
        job_id = original.json()["job"]["id"]

        replay = post_job(client, first["id"], key=key)
        assert replay.status_code == 200, replay.text
        assert replay.json()["job"]["id"] == job_id
        assert replay.json()["job"]["status"] in ("queued", "running")
        assert replay.json()["replayed"] is True

        conflict = post_job(client, second["id"], key=key)
        assert_error(conflict, 409, "IDEMPOTENCY_CONFLICT")

        too_long = post_job(client, first["id"], key="x" * 129)
        assert_error(too_long, 400, "INVALID_REQUEST")

        wait_for_terminal(client, job_id)
        replay_after = post_job(client, first["id"], key=key)
        assert replay_after.status_code == 200
        assert replay_after.json()["job"]["id"] == job_id
        assert replay_after.json()["replayed"] is True


def test_job_not_ready_and_mapping_frozen(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(delay=0.5))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        response = post_job(client, dataset["id"])
        job_id = response.json()["job"]["id"]

        job = client.get(f"/api/v1/jobs/{job_id}").json()
        assert job["status"] in ("queued", "running")

        for path in (
            f"/api/v1/jobs/{job_id}/result/summary",
            f"/api/v1/jobs/{job_id}/result/preview",
            f"/api/v1/jobs/{job_id}/result/errors",
            f"/api/v1/jobs/{job_id}/result.csv",
        ):
            assert_error(client.get(path), 409, "JOB_NOT_READY")

        frozen = client.put(
            f"/api/v1/datasets/{dataset['id']}/mapping",
            json={"textColumn": "text", "resultColumn": "label"},
        )
        assert_error(frozen, 409, "INVALID_REQUEST")

        wait_for_terminal(client, job_id)
        assert (
            client.get(f"/api/v1/jobs/{job_id}/result/summary").status_code == 200
        )


def test_processor_error_fails_job(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(raise_error=True))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "failed"
        assert job["failureReason"] == "PROCESSOR_ERROR"
        assert job["resultAvailable"] is False
        assert job["progress"]["stage"] == "failed"

        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200
        assert summary.json()["status"] == "failed"
        assert summary.json()["output"] is None
        errors = client.get(f"/api/v1/jobs/{job_id}/result/errors")
        assert errors.status_code == 200
        assert errors.json()["total"] == 0
        assert_error(
            client.get(f"/api/v1/jobs/{job_id}/result.csv"), 409, "JOB_NOT_READY"
        )
        events = client.get(f"/api/v1/jobs/{job_id}/events").json()["events"]
        assert events[-1]["type"] == "job.failed"
        assert events[-1]["data"]["failureReason"] == "PROCESSOR_ERROR"


def test_invalid_output_fails_job(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(valid=False))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "failed"
        assert job["failureReason"] == "INVALID_OUTPUT"
        assert job["resultAvailable"] is False
        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary").json()
        assert summary["status"] == "failed"
        assert summary["errorsCount"] == 1
        assert client.get(f"/api/v1/jobs/{job_id}/result/errors").json()["total"] == 1
        assert_error(
            client.get(f"/api/v1/jobs/{job_id}/result/preview"), 409, "JOB_NOT_READY"
        )


def test_api_rejects_output_missing_result_column(monkeypatch, tmp_path):
    class MissingResultColumnProcessor(FakeProcessor):
        def __call__(self, *args, **kwargs):
            outcome = super().__call__(*args, **kwargs)
            with open(outcome.output_path, "r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            with open(outcome.output_path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                for row in rows:
                    writer.writerow(row[:-1])
            return outcome

    install_fake(monkeypatch, processor=MissingResultColumnProcessor())
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "failed"
        assert job["failureReason"] == "INVALID_OUTPUT"
        assert job["resultAvailable"] is False


def test_timed_out_fallback_still_succeeds(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(timed_out=True))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded"
        assert job["warnings"] == ["TIMED_OUT_FALLBACK"]
        assert job["resultAvailable"] is True
        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200
        assert summary.json()["warnings"] == ["TIMED_OUT_FALLBACK"]


def test_bulk_semicolon_snapshot_runs_job(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    content = (
        "id;text;date\n"
        "p-1;This yes happened;2026-01-01\n"
        "p-2;This no happened;2026-01-02\n"
    ).encode("utf-8")
    with TestClient(app) as client:
        create_session(client)
        uploaded = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("semicolon.csv", content, "text/csv")},
            data={"delimiter": ";"},
        )
        assert uploaded.status_code == 201, uploaded.text
        dataset = uploaded.json()
        assert dataset["delimiter"] == ";"
        assert dataset["columns"] == ["id", "text", "date"]
        confirmed = confirm_mapping(client, dataset)
        assert confirmed["mapping"]["textColumn"] == "text"
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded", job
        assert job["counters"]["true"] == 1
        assert job["counters"]["false"] == 1
        preview = client.get(f"/api/v1/jobs/{job_id}/result/preview").json()
        assert preview["columns"] == ["id", "text", "date", "label", "confidence"]
        assert [row[3] for row in preview["rows"]] == ["true", "false"]


def test_job_appends_new_result_column(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = manual_dataset(
            client,
            [["This yes happened", "2026-01-01"]],
            columns=["text", "date"],
        )
        confirmed = confirm_mapping(
            client,
            dataset,
            textColumn="text",
            dateColumn="date",
            idColumn=None,
            resultColumn="verdict",
        )
        assert confirmed["mapping"]["resultColumn"] == "verdict"
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded", job
        preview = client.get(f"/api/v1/jobs/{job_id}/result/preview").json()
        assert preview["columns"] == ["text", "date", "verdict", "confidence"]
        assert preview["rows"] == [["This yes happened", "2026-01-01", "true", "0.9"]]
        csv_response = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert csv_response.text.splitlines()[0] == "text,date,verdict,confidence"


def test_empty_dataset_produces_empty_result(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, [])
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded"
        assert job["progress"]["totalRows"] == 0
        assert job["progress"]["processedRows"] == 0
        assert job["counters"] == {
            "true": 0,
            "false": 0,
            "unsure": 0,
            "fallback": 0,
            "errors": 0,
        }
        assert job["resultAvailable"] is True
        preview = client.get(f"/api/v1/jobs/{job_id}/result/preview").json()
        assert preview["columns"] == ["id", "text", "date", "label", "confidence"]
        assert preview["rows"] == []
        assert preview["total"] == 0
        csv_response = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert csv_response.status_code == 200
        assert csv_response.text == "id,text,date,label,confidence\n"


def test_deadline_is_capped_by_arena_and_passed_to_processor(monkeypatch, tmp_path):
    engine, processor = install_fake(monkeypatch)
    arena_deadline = time.time() + 120
    monkeypatch.setenv("ARENA_DEADLINE", f"{arena_deadline:.3f}")
    app = make_app(tmp_path, job_deadline_seconds=3600)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        initial = client.get(f"/api/v1/jobs/{job_id}").json()
        deadline = datetime.fromisoformat(
            initial["deadlineAt"].replace("Z", "+00:00")
        ).astimezone(timezone.utc).timestamp()
        assert deadline <= arena_deadline + 1
        assert deadline > time.time()
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded"
        assert processor.deadline_epoch is not None
        assert processor.deadline_epoch <= arena_deadline + 0.01
        assert engine.prepared is True
        assert engine.closed is True


def test_job_ownership_isolation(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        wait_for_terminal(client, job_id)
        other = TestClient(app)
        try:
            create_session(other)
            assert_error(other.get(f"/api/v1/jobs/{job_id}"), 404, "NOT_FOUND")
            assert_error(
                other.get(f"/api/v1/jobs/{job_id}/events"), 404, "NOT_FOUND"
            )
            assert_error(
                other.get(f"/api/v1/jobs/{job_id}/result/summary"), 404, "NOT_FOUND"
            )
            assert_error(
                other.get(f"/api/v1/jobs/{job_id}/result.csv"), 404, "NOT_FOUND"
            )
        finally:
            other.close()
