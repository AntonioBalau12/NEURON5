"""Result endpoints: summary, preview, errors and CSV streaming."""

from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from test_api_helpers import (
    FakeProcessor,
    create_session,
    install_fake,
    make_app,
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


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    return body


def _finished_job(monkeypatch, tmp_path, processor=None):
    install_fake(monkeypatch, processor=processor or FakeProcessor())
    app = make_app(tmp_path)
    client = TestClient(app)
    return app, client


def test_result_summary_preview_errors_and_csv(monkeypatch, tmp_path):
    install_fake(monkeypatch)
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        wait_for_terminal(client, job_id)

        summary_response = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary_response.status_code == 200, summary_response.text
        summary = summary_response.json()
        assert set(summary) == {
            "jobId",
            "status",
            "totalRows",
            "counts",
            "durationSeconds",
            "warnings",
            "failureReason",
            "output",
            "errorsCount",
        }
        assert summary["jobId"] == job_id
        assert summary["status"] == "succeeded"
        assert summary["totalRows"] == 4
        assert summary["counts"] == {
            "true": 1,
            "false": 1,
            "unsure": 2,
            "fallback": 1,
            "errors": 1,
        }
        assert summary["durationSeconds"] == 0.02
        assert summary["warnings"] == []
        assert summary["failureReason"] is None
        assert summary["errorsCount"] == 1
        output = summary["output"]
        assert output["fileName"] == "result.csv"
        assert output["bytes"] > 0
        assert output["contentType"] == "text/csv; charset=utf-8"

        preview = client.get(
            f"/api/v1/jobs/{job_id}/result/preview?offset=0&limit=10"
        )
        assert preview.status_code == 200, preview.text
        page = preview.json()
        assert page["columns"] == ["id", "text", "date", "label"]
        assert page["total"] == 4
        assert page["offset"] == 0
        assert page["limit"] == 10
        assert [row[3] for row in page["rows"]] == ["true", "false", "unsure", "unsure"]

        second_page = client.get(
            f"/api/v1/jobs/{job_id}/result/preview?offset=1&limit=2"
        ).json()
        assert second_page["rows"] == page["rows"][1:3]
        assert second_page["total"] == 4
        assert_error(
            client.get(f"/api/v1/jobs/{job_id}/result/preview?limit=500"),
            400,
            "INVALID_REQUEST",
        )

        errors_response = client.get(
            f"/api/v1/jobs/{job_id}/result/errors?offset=0&limit=50"
        )
        assert errors_response.status_code == 200, errors_response.text
        errors = errors_response.json()
        assert errors["total"] == 1
        assert errors["offset"] == 0
        assert errors["limit"] == 50
        item = errors["items"][0]
        assert set(item) == {"rowId", "lineNumber", "column", "code", "message"}
        assert item["rowId"] == "p-3"
        assert item["lineNumber"] == 4
        assert item["column"] == "text"
        assert item["code"] == "FAKE_ROW_ERROR"

        csv_response = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert csv_response.status_code == 200, csv_response.text
        assert csv_response.headers["content-type"] == "text/csv; charset=utf-8"
        assert (
            csv_response.headers["content-disposition"]
            == f'attachment; filename="result-{job_id}.csv"'
        )
        parsed = list(csv.reader(io.StringIO(csv_response.text)))
        assert parsed[0] == ["id", "text", "date", "label"]
        assert len(parsed) == 5
        assert [row[3] for row in parsed[1:]] == ["true", "false", "unsure", "unsure"]
        assert [row[0] for row in parsed[1:]] == ["p-1", "p-2", "p-3", "p-4"]


def test_failed_job_exposes_summary_and_errors_but_not_csv(monkeypatch, tmp_path):
    install_fake(monkeypatch, processor=FakeProcessor(valid=False))
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = prepared_dataset(client, ROWS)
        job_id = post_job(client, dataset["id"]).json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "failed"
        assert job["failureReason"] == "INVALID_OUTPUT"

        summary = client.get(f"/api/v1/jobs/{job_id}/result/summary")
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert body["status"] == "failed"
        assert body["output"] is None
        assert body["failureReason"] == "INVALID_OUTPUT"
        assert body["counts"]["errors"] == 1

        errors = client.get(f"/api/v1/jobs/{job_id}/result/errors")
        assert errors.status_code == 200
        assert errors.json()["total"] == 1
        assert_error(
            client.get(f"/api/v1/jobs/{job_id}/result/preview"), 409, "JOB_NOT_READY"
        )
        assert_error(
            client.get(f"/api/v1/jobs/{job_id}/result.csv"), 409, "JOB_NOT_READY"
        )


def test_result_ownership_isolation(monkeypatch, tmp_path):
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
            for path in (
                f"/api/v1/jobs/{job_id}/result/summary",
                f"/api/v1/jobs/{job_id}/result/preview",
                f"/api/v1/jobs/{job_id}/result/errors",
                f"/api/v1/jobs/{job_id}/result.csv",
            ):
                assert_error(other.get(path), 404, "NOT_FOUND")
        finally:
            other.close()
