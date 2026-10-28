"""Runtime M2 inference contract checks."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

from foundation import load_inputs
from ml.classical.benchmark import LABELS, make_feature_builder
from runner import predict_unlabeled
from core.retrieval.features import FEATURE_NAMES


class FixedEstimator:
    classes_ = np.asarray(LABELS)

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.05, 0.9, 0.05]]), (matrix.shape[0], 1))


class RunnerM2Tests(unittest.TestCase):
    def test_runtime_input_needs_no_form_and_uses_model(self):
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
                writer.writerow({"id": "new-1", "text": "Holdan joined Hooly on January 12, 2026.",
                                 "date": "2026-01-12", "label": ""})

            data = load_inputs(universe, root / "lexicon.json")
            self.assertFalse(data.issues)
            model_rows = [{"id": f"p-{i}", "text": f"Holdan joined Hooly on 12 January 2026. Note {i}.",
                           "date": "2026-01-12"} for i in range(4)]
            artifact_path = root / "model.joblib"
            joblib.dump({
                "estimator": FixedEstimator(),
                "feature_builder": make_feature_builder(model_rows, lexicon),
                "label_order": tuple(LABELS),
                "retrieval_feature_names": tuple(FEATURE_NAMES),
            }, artifact_path)

            prediction = predict_unlabeled(data, str(artifact_path), str(practice))

            self.assertEqual(prediction["new-1"][0], "true")
            self.assertGreaterEqual(prediction["new-1"][1], 0.90)
            self.assertLessEqual(prediction["new-1"][1], 0.98)


if __name__ == "__main__":
    unittest.main()
