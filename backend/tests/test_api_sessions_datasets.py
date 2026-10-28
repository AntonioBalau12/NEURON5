"""Session, CORS/Origin and dataset endpoint tests."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from test_api_helpers import (
    confirm_mapping,
    create_session,
    make_app,
    manual_dataset,
)


def assert_error(response, status: int, code: str) -> dict:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert body["requestId"] == response.headers["x-request-id"]
    return body


def test_requires_session(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        assert_error(client.get("/api/v1/sessions/current"), 401, "SESSION_REQUIRED")
        assert_error(client.get("/api/v1/datasets/ds_missing"), 401, "SESSION_REQUIRED")
        assert_error(
            client.post("/api/v1/datasets/manual", json={"rows": []}),
            401,
            "SESSION_REQUIRED",
        )
        assert_error(
            client.post("/api/v1/jobs", json={"datasetId": "ds_missing"}),
            401,
            "SESSION_REQUIRED",
        )
        assert_error(
            client.get("/api/v1/jobs/job_missing/events"), 401, "SESSION_REQUIRED"
        )


def test_session_create_and_current(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/v1/sessions")
        assert response.status_code == 200, response.text
        session = response.json()
        assert session["sessionId"].startswith("sess_")
        assert session["createdAt"].endswith("Z")
        assert session["expiresAt"].endswith("Z")
        cookie = response.headers["set-cookie"]
        assert "n5_session=" in cookie
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie
        assert "Max-Age=21600" in cookie
        assert "Secure" not in cookie

        current = client.get("/api/v1/sessions/current")
        assert current.status_code == 200
        assert current.json()["sessionId"] == session["sessionId"]

        again = client.post("/api/v1/sessions")
        assert again.status_code == 200
        assert again.json()["sessionId"] == session["sessionId"]
        assert again.json()["createdAt"] == session["createdAt"]


def test_cors_and_origin_guard(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        foreign = client.post(
            "/api/v1/sessions", headers={"Origin": "http://evil.example"}
        )
        body = assert_error(foreign, 403, "INVALID_REQUEST")
        assert body["requestId"] == foreign.headers["x-request-id"]

        allowed = client.post(
            "/api/v1/sessions", headers={"Origin": "http://127.0.0.1:3000"}
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
        assert allowed.headers["access-control-allow-credentials"] == "true"

        # GET is not a state-changing method: a foreign Origin is not blocked.
        assert (
            client.get(
                "/api/v1/sessions/current",
                headers={"Origin": "http://evil.example"},
            ).status_code
            == 200
        )

        # Errors still carry the CORS headers for an allowed Origin.
        anonymous = TestClient(app)
        try:
            unauthorised = anonymous.get(
                "/api/v1/sessions/current",
                headers={"Origin": "http://localhost:3000"},
            )
            assert_error(unauthorised, 401, "SESSION_REQUIRED")
            assert (
                unauthorised.headers["access-control-allow-origin"]
                == "http://localhost:3000"
            )
            assert (
                unauthorised.headers["access-control-allow-credentials"] == "true"
            )
        finally:
            anonymous.close()

        preflight = client.options(
            "/api/v1/datasets/manual",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
        allow_headers = preflight.headers["access-control-allow-headers"].lower()
        assert "content-type" in allow_headers
        assert "idempotency-key" in allow_headers


def test_manual_dataset_mapping_and_preview(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        rows = [
            ["p-1", "Holdan yes started", "2026-01-12"],
            ["p-2", "Hooly no event", "2026-01-13"],
        ]
        dataset = manual_dataset(client, rows)
        assert dataset["id"].startswith("ds_")
        assert dataset["mode"] == "manual"
        assert dataset["byteSize"] > 0
        assert dataset["encoding"] == "utf-8"
        assert dataset["delimiter"] == ","
        assert dataset["hasHeader"] is True
        assert dataset["columns"] == ["id", "text", "date"]
        assert dataset["rowCount"] == 2
        assert dataset["mapping"] == {
            "textColumn": "text",
            "dateColumn": "date",
            "idColumn": "id",
            "resultColumn": "label",
            "confirmed": False,
            "autoDetected": True,
        }
        assert dataset["warnings"] == []
        assert dataset["preview"] == {
            "columns": ["id", "text", "date"],
            "rows": rows,
            "offset": 0,
            "limit": 5,
            "total": 2,
        }

        fetched = client.get(f"/api/v1/datasets/{dataset['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["id"] == dataset["id"]

        mapped = confirm_mapping(client, dataset)
        assert mapped["mapping"]["confirmed"] is True
        assert mapped["mapping"]["autoDetected"] is False

        bad = client.put(
            f"/api/v1/datasets/{dataset['id']}/mapping",
            json={"textColumn": "missing", "resultColumn": "label"},
        )
        assert_error(bad, 400, "INVALID_MAPPING")
        assert "textColumn" in bad.json()["error"]["details"]["issues"]


def test_dataset_preview_pagination_and_validation(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        rows = [[f"p-{i}", f"row {i} yes", "2026-01-01"] for i in range(12)]
        dataset = manual_dataset(client, rows)
        preview = client.get(f"/api/v1/datasets/{dataset['id']}/preview?offset=5&limit=3")
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["offset"] == 5
        assert body["limit"] == 3
        assert body["total"] == 12
        assert body["rows"] == rows[5:8]
        assert body["columns"] == ["id", "text", "date"]

        too_big = client.get(f"/api/v1/datasets/{dataset['id']}/preview?limit=500")
        assert_error(too_big, 400, "INVALID_REQUEST")
        negative = client.get(f"/api/v1/datasets/{dataset['id']}/preview?offset=-1")
        assert_error(negative, 400, "INVALID_REQUEST")


def test_manual_dataset_validation_and_size_limit(tmp_path):
    app = make_app(tmp_path, manual_max_bytes=100)
    with TestClient(app) as client:
        create_session(client)
        duplicate = client.post(
            "/api/v1/datasets/manual",
            json={"columns": ["a", "a"], "rows": []},
        )
        assert_error(duplicate, 400, "INVALID_REQUEST")
        blank = client.post(
            "/api/v1/datasets/manual",
            json={"columns": ["a", ""], "rows": []},
        )
        assert_error(blank, 400, "INVALID_REQUEST")
        unknown = client.post(
            "/api/v1/datasets/manual",
            json={"rows": [{"id": "p-1", "bogus": "x"}]},
        )
        assert_error(unknown, 400, "INVALID_REQUEST")
        too_long = client.post(
            "/api/v1/datasets/manual",
            json={"rows": [["p-1", "x" * 200, "2026-01-01"]]},
        )
        body = assert_error(too_long, 413, "DATASET_TOO_LARGE")
        assert body["error"]["details"]["maxBytes"] == 100


def test_empty_manual_dataset_and_missing_text_column(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        empty = manual_dataset(client, [])
        assert empty["rowCount"] == 0
        assert empty["preview"]["rows"] == []
        assert "EMPTY_FILE" in empty["warnings"]

        custom = manual_dataset(client, [["a", "b"]], columns=["alpha", "beta"])
        assert custom["mapping"] is None
        assert "HEADER_WITHOUT_TEXT_COLUMN" in custom["warnings"]
        mapped = confirm_mapping(
            client,
            custom,
            textColumn="alpha",
            dateColumn=None,
            idColumn=None,
            resultColumn="verdict",
        )
        assert mapped["mapping"]["textColumn"] == "alpha"
        assert mapped["mapping"]["resultColumn"] == "verdict"


def test_manual_dataset_accepts_row_objects(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = manual_dataset(
            client,
            [
                {"id": "p-1", "text": "yes", "date": "2026-01-01"},
                {"id": "p-2", "text": "no", "date": "2026-01-02"},
            ],
        )
        assert dataset["columns"] == ["id", "text", "date"]
        assert dataset["rowCount"] == 2
        assert dataset["preview"]["rows"] == [
            ["p-1", "yes", "2026-01-01"],
            ["p-2", "no", "2026-01-02"],
        ]


def test_dataset_ownership_isolation(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        dataset = manual_dataset(client, [["p-1", "yes", "2026-01-01"]])
        other = TestClient(app)
        try:
            other.post("/api/v1/sessions")
            for path in (
                f"/api/v1/datasets/{dataset['id']}",
                f"/api/v1/datasets/{dataset['id']}/preview",
            ):
                assert_error(other.get(path), 404, "NOT_FOUND")
            assert_error(
                other.put(
                    f"/api/v1/datasets/{dataset['id']}/mapping",
                    json={"textColumn": "text"},
                ),
                404,
                "NOT_FOUND",
            )
        finally:
            other.close()


def test_bulk_upload_quoted_csv_with_bom(tmp_path):
    app = make_app(tmp_path)
    content = (
        "\ufeffid,text,date\r\n"
        'p-1,"Hello, yes",2026-01-12\r\n'
        'p-2,"multi\nline no",2026-01-13\r\n'
    ).encode("utf-8")
    with TestClient(app) as client:
        create_session(client)
        response = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("practice.csv", content, "text/csv")},
        )
        assert response.status_code == 201, response.text
        dataset = response.json()
        assert dataset["mode"] == "bulk"
        assert dataset["encoding"] == "utf-8-sig"
        assert dataset["delimiter"] == ","
        assert dataset["columns"] == ["id", "text", "date"]
        assert dataset["rowCount"] == 2
        assert dataset["byteSize"] > 0  # snapshot is normalised to comma/UTF-8 without BOM
        assert "BOM_PRESENT" in dataset["warnings"]
        assert dataset["mapping"]["textColumn"] == "text"
        assert dataset["mapping"]["confirmed"] is False
        assert dataset["preview"]["rows"][0] == ["p-1", "Hello, yes", "2026-01-12"]
        assert dataset["preview"]["rows"][1][1] == "multi\nline no"


def test_bulk_delimiter_autodetect_explicit_and_ambiguous(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        create_session(client)
        explicit = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("data.csv", b"id;text;date\np-1;Hello;2026-01-01\n", "text/csv")},
            data={"delimiter": ";"},
        )
        assert explicit.status_code == 201, explicit.text
        explicit_dataset = explicit.json()
        assert explicit_dataset["delimiter"] == ";"
        assert explicit_dataset["rowCount"] == 1
        assert explicit_dataset["preview"]["rows"] == [
            ["p-1", "Hello", "2026-01-01"]
        ]
        explicit_preview = client.get(
            f"/api/v1/datasets/{explicit_dataset['id']}/preview?offset=0&limit=5"
        )
        assert explicit_preview.status_code == 200, explicit_preview.text
        assert explicit_preview.json() == {
            "columns": ["id", "text", "date"],
            "rows": [["p-1", "Hello", "2026-01-01"]],
            "offset": 0,
            "limit": 5,
            "total": 1,
        }

        ambiguous = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("data.csv", b"id,text;date\np-1,hello;x\n", "text/csv")},
        )
        assert ambiguous.status_code == 201, ambiguous.text
        assert ambiguous.json()["delimiter"] == ","
        assert "AMBIGUOUS_DELIMITER" in ambiguous.json()["warnings"]

        bad_delimiter = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("data.csv", b"id|text\np-1|hello\n", "text/csv")},
            data={"delimiter": "|"},
        )
        assert_error(bad_delimiter, 400, "INVALID_REQUEST")


def test_bulk_upload_errors_and_limits(tmp_path):
    app = make_app(tmp_path, bulk_max_bytes=100)
    with TestClient(app) as client:
        create_session(client)
        wrong_type = client.post("/api/v1/datasets/bulk", json={"file": "nope"})
        assert_error(wrong_type, 415, "UNSUPPORTED_MEDIA_TYPE")
        missing = client.post(
            "/api/v1/datasets/bulk",
            files={"other": ("x.txt", b"hello", "text/plain")},
        )
        assert_error(missing, 400, "INVALID_REQUEST")
        bad_encoding = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("bad.csv", b"\xff\xfe\x00bad", "text/csv")},
        )
        assert_error(bad_encoding, 400, "UNSUPPORTED_ENCODING")
        empty = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("empty.csv", b"", "text/csv")},
        )
        assert_error(empty, 400, "INVALID_CSV")
        no_header = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("blank.csv", b"\n\n", "text/csv")},
        )
        assert_error(no_header, 400, "INVALID_CSV")
        too_large = client.post(
            "/api/v1/datasets/bulk",
            files={"file": ("big.csv", b"id,text\n" + b"x" * 200, "text/csv")},
        )
        body = assert_error(too_large, 413, "DATASET_TOO_LARGE")
        assert body["error"]["details"]["maxBytes"] == 100