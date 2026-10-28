"""Application settings must reach the classifier without rereading the environment."""

import csv
import io
import json
from dataclasses import replace

import httpx
from fastapi.testclient import TestClient

from app.config import get_settings
from app.engine import remote_engine
from app.engine.api import create_engine
from app.engine.mock_engine import MockClassifierEngine
from app.main import create_app
from test_api_helpers import create_session, post_job, prepared_dataset, wait_for_terminal


def test_explicit_demo_settings_override_remote_environment(monkeypatch):
    monkeypatch.setenv("NEURON_CLASSIFIER_URLS", "http://environment.test/classify")
    settings = replace(get_settings(), classifier_urls=(), mock_delay_seconds=0.25)

    engine = create_engine(settings=settings)

    assert isinstance(engine, MockClassifierEngine)
    assert engine.delay_seconds == 0.25


def test_job_uses_application_classifier_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("NEURON_CLASSIFIER_URLS", "http://environment.test/classify")
    settings = replace(
        get_settings(),
        temp_dir=tmp_path,
        classifier_urls=("http://configured.test/classify",),
        classifier_mode="rows",
        classifier_field_name="dataset",
        classifier_timeout_seconds=13,
        classifier_retries=2,
        classifier_token="test-token",
        as_of_date="2026-01-23",
    )
    requests = []
    engines = []

    def respond(request):
        requests.append(request)
        assert str(request.url) == settings.classifier_urls[0]
        assert request.headers["authorization"] == "Bearer test-token"
        payload = json.loads(request.content)
        assert payload["asOf"] == settings.as_of_date
        assert payload["rows"][0]["id"] == "row-1"
        return httpx.Response(200, json={"results": [{"id": "row-1", "label": "false"}]})

    constructor = remote_engine.RemoteClassifierEngine

    def create_with_transport(*args, **kwargs):
        engine = constructor(*args, transport=httpx.MockTransport(respond), **kwargs)
        engines.append(engine)
        return engine

    monkeypatch.setattr(remote_engine, "RemoteClassifierEngine", create_with_transport)
    with TestClient(create_app(settings)) as client:
        create_session(client)
        dataset = prepared_dataset(client, [["row-1", "A plain sentence.", "2026-01-01"]])
        response = post_job(client, dataset["id"])
        assert response.status_code == 202, response.text
        job_id = response.json()["job"]["id"]
        job = wait_for_terminal(client, job_id)
        assert job["status"] == "succeeded", job
        output = client.get(f"/api/v1/jobs/{job_id}/result.csv")
        assert output.status_code == 200
        rows = list(csv.DictReader(io.StringIO(output.text)))
        assert rows[0]["label"] == "false"

    assert len(requests) == len(engines) == 1
    engine = engines[0]
    assert engine.urls == settings.classifier_urls
    assert engine.mode == settings.classifier_mode
    assert engine.field_name == settings.classifier_field_name
    assert engine.timeout == settings.classifier_timeout_seconds
    assert engine.retries == settings.classifier_retries
    assert engine.token == settings.classifier_token
    assert engine.as_of == settings.as_of_date


def test_reference_date_is_read_when_settings_are_loaded(monkeypatch):
    monkeypatch.setenv("NEURON_AS_OF", "2026-02-11")
    assert get_settings().as_of_date == "2026-02-11"
