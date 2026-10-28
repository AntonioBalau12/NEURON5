"""Unit and integration tests for M2 confidence calibration, 3-tier abstention, and contract compliance."""

from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

from foundation import load_inputs
from core.retrieval.features import FEATURE_NAMES
from ml.classical.benchmark import LABELS, make_feature_builder
from runner import (
    atomic_write_csv,
    calibrate_claim_confidence,
    debias_probabilities,
    predict_unlabeled,
)


class DummyEstimator:
    def __init__(self, proba_map: dict[str, list[float]] | None = None, default_proba: list[float] | None = None):
        self.classes_ = np.asarray(LABELS)
        self.proba_map = proba_map or {}
        self.default_proba = default_proba or [0.1, 0.8, 0.1]

    def predict_proba(self, matrix):
        n = matrix.shape[0]
        row = np.asarray(self.default_proba, dtype=np.float64)
        return np.tile(row, (n, 1))


class TestConfidenceCalibration(unittest.TestCase):
    def test_debias_probabilities_reverses_weights_and_sums_to_one(self):
        class_weights_map = {"false": 2.285, "true": 0.400, "unsure": 16.257}
        # True prior: [0.15, 0.80, 0.05]
        true_prior = np.asarray([0.15, 0.80, 0.05], dtype=np.float64)
        # Weight-distorted probabilities:
        distorted_raw = true_prior * np.asarray([2.285, 0.400, 16.257])
        distorted = distorted_raw / distorted_raw.sum()

        debiased = debias_probabilities(distorted, class_weights_map)
        # Check sum to 1.0
        self.assertAlmostEqual(float(debiased.sum()), 1.0, places=6)
        # Check reversed back to true prior
        np.testing.assert_allclose(debiased, true_prior, rtol=1e-3, atol=1e-3)

        # Batch check
        batch = np.vstack([distorted, [0.3, 0.6, 0.1], [0.5, 0.3, 0.2]])
        debiased_batch = debias_probabilities(batch, class_weights_map)
        self.assertEqual(debiased_batch.shape, (3, 3))
        np.testing.assert_allclose(debiased_batch.sum(axis=1), np.ones(3), rtol=1e-5)

        # Identity check when class weights are None or uniform
        np.testing.assert_allclose(debias_probabilities(batch, None), batch)
        np.testing.assert_allclose(
            debias_probabilities(batch, {"false": 1.0, "true": 1.0, "unsure": 1.0}),
            batch,
        )

    def test_tiered_confidence_tier1_exact_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lexicon = {
                "subjects": [{"name": "Holdan", "aliases": [], "attributes": ["joined"]}],
                "events": [],
            }
            (root / "lexicon.json").write_text(json.dumps(lexicon), encoding="utf-8")
            practice = root / "practice.csv"
            with practice.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
                writer.writeheader()
                fact = json.dumps([{"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": "2026-01-12"}}])
                for i in range(4):
                    writer.writerow({"id": f"p-{i}", "text": f"Holdan joined Hooly on 12 January 2026. Note {i}.",
                                     "date": "2026-01-12", "label": "true", "form": fact})

            universe = root / "universe.csv"
            with universe.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                writer.writeheader()
                writer.writerow({"id": "row-exact", "text": "Holdan joined Hooly on January 12, 2026.",
                                 "date": "2026-01-12", "label": ""})

            data = load_inputs(universe, root / "lexicon.json")
            model_rows = [{"id": f"p-{i}", "text": f"Holdan joined Hooly on 12 January 2026. Note {i}.",
                           "date": "2026-01-12"} for i in range(4)]
            artifact_path = root / "model.joblib"
            joblib.dump({
                "estimator": DummyEstimator(default_proba=[0.05, 0.90, 0.05]),
                "feature_builder": make_feature_builder(model_rows, lexicon),
                "label_order": tuple(LABELS),
                "retrieval_feature_names": tuple(FEATURE_NAMES),
                "class_weights_map": {"false": 1.0, "true": 1.0, "unsure": 1.0},
                "minimum_confidence": 0.53,
                "false_threshold": 0.68,
            }, artifact_path)

            preds = predict_unlabeled(data, str(artifact_path), str(practice))
            label, conf = preds["row-exact"]
            self.assertEqual(label, "true")
            self.assertIsNotNone(conf)
            # Tier 1 exact match must be >= 0.90 and <= 0.98
            self.assertGreaterEqual(conf, 0.90)
            self.assertLessEqual(conf, 0.98)

    def test_tiered_confidence_tier2_false_guardrail_abstains(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lexicon = {
                "subjects": [{"name": "Holdan", "aliases": [], "attributes": ["joined"]}],
                "events": [],
            }
            (root / "lexicon.json").write_text(json.dumps(lexicon), encoding="utf-8")
            practice = root / "practice.csv"
            with practice.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
                writer.writeheader()
                writer.writerow({"id": "p-1", "text": "Something unrelated.", "date": "2026-01-01", "label": "true", "form": "[]"})

            universe = root / "universe.csv"
            with universe.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                writer.writeheader()
                writer.writerow({"id": "row-unverified-false", "text": "Unverified claim that triggers false.",
                                 "date": "2026-01-12", "label": ""})

            data = load_inputs(universe, root / "lexicon.json")
            model_rows = [{"id": f"p-{i}", "text": f"Something unrelated {i}.", "date": "2026-01-01"} for i in range(5)]
            artifact_path = root / "model.joblib"
            # Estimator predicts false with raw_conf = 0.60 (which is < false_threshold 0.68)
            joblib.dump({
                "estimator": DummyEstimator(default_proba=[0.60, 0.25, 0.15]),
                "feature_builder": make_feature_builder(model_rows, lexicon),
                "label_order": tuple(LABELS),
                "retrieval_feature_names": tuple(FEATURE_NAMES),
                "class_weights_map": {"false": 1.0, "true": 1.0, "unsure": 1.0},
                "minimum_confidence": 0.53,
                "false_threshold": 0.68,
            }, artifact_path)

            preds = predict_unlabeled(data, str(artifact_path), str(practice))
            label, conf = preds["row-unverified-false"]
            # Must abstain to unsure because retrieved_verified_count == 0 and conf < 0.68
            self.assertEqual(label, "unsure")
            self.assertIsNone(conf)

    def test_tiered_confidence_tier3_damping_and_bounds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            lexicon = {
                "subjects": [{"name": "Holdan", "aliases": [], "attributes": ["joined"]}],
                "events": [],
            }
            (root / "lexicon.json").write_text(json.dumps(lexicon), encoding="utf-8")
            practice = root / "practice.csv"
            with practice.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
                writer.writeheader()
                writer.writerow({"id": "p-1", "text": "Holdan joined Hooly on 12 January 2026.", "date": "2026-01-12", "label": "true", "form": "[]"})

            universe = root / "universe.csv"
            with universe.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                writer.writeheader()
                # Partial match (no exact fact match)
                writer.writerow({"id": "row-damped", "text": "Holdan visited the venue.",
                                 "date": "2026-01-12", "label": ""})

            data = load_inputs(universe, root / "lexicon.json")
            model_rows = [{"id": f"p-{i}", "text": f"Holdan joined Hooly on 12 January 2026. Note {i}.", "date": "2026-01-12"} for i in range(5)]
            artifact_path = root / "model.joblib"
            # Predict true with raw_conf = 0.80
            joblib.dump({
                "estimator": DummyEstimator(default_proba=[0.10, 0.80, 0.10]),
                "feature_builder": make_feature_builder(model_rows, lexicon),
                "label_order": tuple(LABELS),
                "retrieval_feature_names": tuple(FEATURE_NAMES),
                "class_weights_map": {"false": 1.0, "true": 1.0, "unsure": 1.0},
                "minimum_confidence": 0.53,
                "false_threshold": 0.68,
            }, artifact_path)

            preds = predict_unlabeled(data, str(artifact_path), str(practice))
            label, conf = preds["row-damped"]
            self.assertEqual(label, "true")
            self.assertIsNotNone(conf)
            # Tier 3 damped: 0.5 + (0.8 - 0.5) * damping <= 0.88
            self.assertGreaterEqual(conf, 0.5001)
            self.assertLessEqual(conf, 0.88)

    def test_calibrate_claim_confidence_immutable_vs_dynamic(self):
        immutable_claim = {
            "type": "fact",
            "form": json.dumps([{"subject": "Hooly Cloud", "attribute": "launched", "value": {"kind": "date", "value": "2025-11"}}]),
        }
        self.assertAlmostEqual(calibrate_claim_confidence(immutable_claim), 0.95)

        mutable_claim = {
            "type": "compare",
            "form": json.dumps({
                "left": {"subject": "Hooly AI Pro", "attribute": "customers"},
                "right": {"subject": "Hooly Free", "attribute": "customers"},
                "op": "gt",
            }),
            "date": "2026-10-20",
        }
        conf = calibrate_claim_confidence(mutable_claim)
        self.assertGreaterEqual(conf, 0.75)
        self.assertLessEqual(conf, 0.92)


if __name__ == "__main__":
    unittest.main()
