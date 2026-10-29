"""Focused M2 checks for fold-local evidence and form-free inference rows."""
from __future__ import annotations

import json
import unittest

import numpy as np

from ml.classical.train_m2 import (LABELS, build_retriever, false_metrics, inference_rows,
                                  decisions, retrieval_matrix, retrieval_recall, tune_false_threshold)


LEXICON = {"subjects": [{"name": "Alpha", "aliases": [], "attributes": ["customers"]}], "events": []}


class M2FoldSafetyTests(unittest.TestCase):
    def test_graph_and_bm25_contain_only_training_fold_rows(self):
        train = {"id": "train-1", "text": "Alpha has 40 customers.", "date": "2026-01-01",
                 "label": "true", "form": json.dumps([{"subject": "Alpha", "attribute": "customers",
                     "value": {"kind": "quantity", "value": 40, "unit": "customer"}}])}
        held = {"id": "held-1", "text": "Alpha has 40 clients.", "date": "2026-01-02",
                "label": "true", "form": train["form"]}
        extractor = build_retriever([train], LEXICON)
        self.assertEqual(set(extractor.retriever.graph.evidence_by_id), {"train-1"})
        self.assertEqual(set(extractor.retriever.bm25.documents), {"train-1"})
        self.assertEqual(set(inference_rows([held])[0]), {"id", "text", "date"})
        features = retrieval_matrix([train], [held], LEXICON)
        self.assertEqual(features.shape, (1, 8))

    def test_validation_query_does_not_mutate_training_evidence(self):
        training = [{"id": "train-1", "text": "Alpha has 40 customers.", "date": "2026-01-01",
                     "label": "true", "form": json.dumps([{"subject": "Alpha", "attribute": "customers",
                         "value": {"kind": "quantity", "value": 40, "unit": "customer"}}])}]
        validation = [{"id": "validation-1", "text": "Alpha had 40 customers.", "date": "2026-01-02",
                       "label": "false", "form": "[]"}]
        _ = retrieval_matrix(training, validation, LEXICON)
        self.assertEqual([row["id"] for row in inference_rows(training)], ["train-1"])

    def test_retrieval_recall_is_separate_for_shared_and_new_signatures(self):
        evidence = [{"id": "e1", "text": "Alpha has 40 customers.", "date": "2026-01-01",
                     "label": "true", "form": json.dumps([{"subject": "Alpha", "attribute": "customers",
                         "value": {"kind": "quantity", "value": 40, "unit": "customer"}}])}]
        queries = [{"id": "q1", "text": "Alpha employed 40 customers.", "date": "2026-01-02",
                    "label": "true", "form": evidence[0]["form"]},
                   {"id": "q2", "text": "Alpha has 20 customers.", "date": "2026-01-02",
                    "label": "false", "form": json.dumps([{"subject": "Alpha", "attribute": "customers",
                        "value": {"kind": "quantity", "value": 20, "unit": "customer"}}])}]
        recall = retrieval_recall(build_retriever(evidence, LEXICON), queries, evidence)
        self.assertEqual(recall["exact_shared_signature"]["recall_at"]["1"], 1.0)
        self.assertIsNone(recall["new_or_paraphrased_claim"]["recall_at"]["1"])

    def test_false_threshold_is_chosen_from_oof_scores_and_reports_cost_metrics(self):
        y = np.asarray(["false", "false", "true", "true"])
        probs = np.asarray([[0.45, 0.4, 0.15], [0.35, 0.5, 0.15],
                            [0.25, 0.6, 0.15], [0.05, 0.8, 0.15]])
        probs = probs[:, [LABELS.index(label) for label in LABELS]]
        threshold = tune_false_threshold(y, probs)
        self.assertGreaterEqual(threshold, 0.5)
        self.assertIn("false_precision", false_metrics(y, probs, threshold))
        self.assertNotEqual(decisions(np.asarray([[0.45, 0.4, 0.15]]), 0.3)[0], "false")


if __name__ == "__main__":
    unittest.main()
