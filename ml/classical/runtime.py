"""Shared calibrated M2 inference for the offline runner and the web API."""

from pathlib import Path

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack

from core.graph.reference import load_reference_graph
from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
from core.retrieval.hybrid import HybridEvidenceRetriever
from .benchmark import LABELS, transform_features
from .decision_policy import CalibratedDecisionPolicy

ROOT = Path(__file__).resolve().parents[2]


class M2Runtime:
    def __init__(self, model_path, practice_path=None, artifact=None):
        artifact = joblib.load(model_path) if artifact is None else artifact
        if not isinstance(artifact, dict):
            raise ValueError("M2 model artifact must be a mapping")
        self.estimator = artifact["estimator"]
        self.feature_builder = artifact["feature_builder"]
        self.label_order = tuple(artifact["label_order"])
        self.policy = artifact.get("decision_policy")
        self.feature_count = artifact.get("feature_count")
        if self.label_order != tuple(LABELS):
            raise ValueError("M2 label order mismatch")
        if tuple(artifact["retrieval_feature_names"]) != tuple(FEATURE_NAMES):
            raise ValueError("M2 retrieval feature schema mismatch")
        if not isinstance(self.policy, CalibratedDecisionPolicy):
            raise ValueError("M2 v2 artifact is missing its serialized CalibratedDecisionPolicy")
        if tuple(self.policy.label_order) != self.label_order:
            raise ValueError("M2 decision policy label order mismatch")
        if hasattr(self.estimator, "set_params"):
            self.estimator.set_params(n_jobs=2)
        practice = Path(practice_path or ROOT / "data/practice.csv").resolve()
        graph = load_reference_graph(str(practice), str(practice.with_name("lexicon.json")))
        self.extractor = RetrievalFeatureExtractor(HybridEvidenceRetriever(graph))

    def predict(self, rows):
        if not rows:
            return []
        retrieved = [self.extractor.extract(row["text"], row["date"],
                     exclude_evidence_ids=(row.get("id", ""),)) for row in rows]
        base, _ = transform_features(rows, self.feature_builder)
        extra = csr_matrix(np.asarray([[item[name] for name in FEATURE_NAMES] for item in retrieved], dtype=np.float32))
        features = hstack((base, extra), format="csr", dtype=np.float32)
        if self.feature_count is not None and features.shape[1] != int(self.feature_count):
            raise ValueError("M2 feature count mismatch")
        probabilities = np.asarray(self.estimator.predict_proba(features), dtype=np.float64)
        aligned = np.zeros((len(rows), len(self.label_order)), dtype=np.float64)
        for column, label in enumerate(self.estimator.classes_):
            if str(label) in self.label_order:
                aligned[:, self.label_order.index(str(label))] = probabilities[:, column]
        results = []
        for index, evidence in enumerate(retrieved):
            label, confidence, tier, reason = self.policy.decide_single(aligned[index], evidence)
            results.append({"label": label, "confidence": confidence, "tier": tier, "reason": reason})
        return results
