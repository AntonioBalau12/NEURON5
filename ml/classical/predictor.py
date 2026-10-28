"""Inference adapter for models trained by benchmark.py.

Rows require only ``text`` and ISO ``date``. The lexicon-aware feature builder
is serialized with the trained estimator; no practice form is read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    from .benchmark import LABELS, transform_features
except ImportError:  # direct script invocation: python ml/classical/benchmark.py
    from benchmark import LABELS, transform_features


@dataclass
class PredictionAdapter:
    estimator: Any
    feature_builder: dict[str, Any]
    label_order: tuple[str, ...] = tuple(LABELS)
    family: str = "unknown"

    def predict_proba(self, rows: list[dict[str, str]]) -> np.ndarray:
        x, _ = transform_features(rows, self.feature_builder)
        raw = self.estimator.predict_proba(x.toarray() if self.family == "catboost" else x)
        classes = list(getattr(self.estimator, "classes_", self.label_order))
        aligned = np.zeros((len(rows), len(self.label_order)), dtype=float)
        for col, label in enumerate(classes):
            aligned[:, self.label_order.index(str(label))] = raw[:, col]
        row_sums = aligned.sum(axis=1, keepdims=True)
        return np.divide(aligned, row_sums, out=np.zeros_like(aligned), where=row_sums != 0)

    def predict(self, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
        probs = self.predict_proba(rows)
        idx = probs.argmax(axis=1)
        return [{"label": self.label_order[int(j)], "confidence": float(probs[i, j]),
                 "probabilities": {label: float(probs[i, k]) for k, label in enumerate(self.label_order)}}
                for i, j in enumerate(idx)]
