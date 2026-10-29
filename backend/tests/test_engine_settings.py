"""The engine factory selects the configured local model artifact."""

from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

from app.config import get_settings
from app.engine.api import create_engine
from app.engine.local_engine import LocalModelEngine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = BACKEND_ROOT / "scripts" / "adapter.joblib"
FINAL_MODEL_PATH = BACKEND_ROOT.parent / "ml/classical/results_m2_v2/model.joblib"


def test_app_module_imports_when_started_from_backend_directory():
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_model_path_defaults_to_bundled_artifact(monkeypatch):
    monkeypatch.delenv("NEURON_MODEL_PATH", raising=False)

    assert get_settings().model_path == FINAL_MODEL_PATH


def test_model_path_can_be_configured_from_environment(monkeypatch, tmp_path):
    configured = tmp_path / "model.joblib"
    monkeypatch.setenv("NEURON_MODEL_PATH", str(configured))

    assert get_settings().model_path == configured.resolve()


def test_factory_uses_application_model_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("NEURON_MODEL_PATH", str(tmp_path / "missing.joblib"))
    configured = MODEL_PATH.resolve()
    engine = create_engine(settings=replace(get_settings(), model_path=configured))

    assert isinstance(engine, LocalModelEngine)
    assert engine.model_path == configured
    engine.close()
