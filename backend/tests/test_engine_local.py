"""Contract tests against the bundled local model artifact."""

import csv
from pathlib import Path

import pytest

from app.engine.api import ClassifierUnavailable, RowInput
from app.engine.local_engine import LocalModelEngine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = BACKEND_ROOT / "scripts" / "adapter.joblib"


@pytest.fixture(scope="module")
def engine():
    local = LocalModelEngine(MODEL_PATH)
    local.prepare()
    yield local
    local.close()


def test_classification_matches_artifact_predictions(engine):
    rows = [
        RowInput("r-1", "Hooly AI Pro costs EUR 59 a month.", "2026-04-20"),
        RowInput("r-2", "Holdan started at Hooly on 12 January 2026.", "2026-01-12"),
        RowInput("r-3", "The Hooly Gemini launch happened in 2026.", "2026-02-01"),
    ]
    raw = engine.adapter.predict(
        [{"text": row.text, "date": row.row_date} for row in rows]
    )

    for row, prediction in zip(rows, raw, strict=True):
        decision = engine.classify(row)
        expected_label = prediction["label"]
        expected_confidence = prediction["confidence"]
        if expected_label in ("true", "false") and expected_confidence < 0.5:
            expected_label = "unsure"
            expected_confidence = None
        elif expected_label == "unsure":
            expected_confidence = None

        assert decision.id == row.id
        assert decision.label == expected_label
        assert decision.confidence == expected_confidence
        assert decision.fallback is False


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (RowInput("missing", "A sentence.", None), "MISSING_DATE"),
        (RowInput("invalid", "A sentence.", "2026-13-40"), "INVALID_DATE"),
        (RowInput("empty", "  ", "2026-01-01"), "EMPTY_TEXT"),
    ],
)
def test_invalid_rows_return_fallbacks(engine, row, code):
    decision = engine.classify(row)

    assert decision.id == row.id
    assert decision.label == "unsure"
    assert decision.confidence is None
    assert decision.fallback is True
    assert decision.error == code


def test_missing_artifact_raises_classifier_unavailable(tmp_path):
    with pytest.raises(ClassifierUnavailable):
        LocalModelEngine(tmp_path / "missing.joblib")


def test_low_confidence_true_or_false_is_reported_as_unsure(engine):
    with (BACKEND_ROOT.parent / "data" / "practice.csv").open(encoding="utf-8-sig", newline="") as handle:
        source = next(row for row in csv.DictReader(handle) if row["id"] == "p-428")
    prediction = engine.adapter.predict([{"text": source["text"], "date": source["date"]}])[0]
    assert prediction["label"] in ("true", "false")
    assert prediction["confidence"] < 0.5

    decision = engine.classify(RowInput(source["id"], source["text"], source["date"]))
    assert decision.label == "unsure"
    assert decision.confidence is None
    assert decision.fallback is False
