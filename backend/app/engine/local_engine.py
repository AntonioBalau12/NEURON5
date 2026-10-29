"""Local CPU inference using the team's fitted PredictionAdapter artifact."""

from datetime import date
from functools import lru_cache
import math
from pathlib import Path
from typing import Iterable
import warnings
import sys

import joblib
from sklearn.exceptions import InconsistentVersionWarning

from .api import ClassifierUnavailable, LABELS, RowDecision, RowInput

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@lru_cache(maxsize=1)
def _load_adapter(path: Path):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InconsistentVersionWarning)
            adapter = joblib.load(path)
        if isinstance(adapter, dict):
            from ml.classical.runtime import M2Runtime

            return M2Runtime(path, artifact=adapter)
        if adapter.family != "lightgbm" or tuple(adapter.label_order) != ("false", "true", "unsure"):
            raise ValueError("expected the team's three-class LightGBM PredictionAdapter")
        if adapter.feature_builder.get("feature_version") != "text-date-lexicon-v1":
            raise ValueError("unsupported model feature version")
        adapter.estimator.set_params(n_jobs=2)
        return adapter
    except Exception as exc:
        raise ClassifierUnavailable(f"Could not load local model {path}: {exc}") from exc


class LocalModelEngine:
    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path).expanduser().resolve()
        self.adapter = _load_adapter(self.model_path)

    def prepare(self, context_rows: Iterable[RowInput] = ()) -> None:
        """The artifact already contains its fitted text and lexicon features."""

    def classify(self, row: RowInput) -> RowDecision:
        if not row.text.strip():
            return RowDecision(row.id, "unsure", fallback=True, error="EMPTY_TEXT", reason="row has no sentence")
        if not row.row_date:
            return RowDecision(row.id, "unsure", fallback=True, error="MISSING_DATE", reason="the model requires an ISO row date")
        try:
            if len(row.row_date) != 10 or row.row_date[4] != "-" or row.row_date[7] != "-":
                raise ValueError("date must be yyyy-mm-dd")
            date.fromisoformat(row.row_date)
        except (TypeError, ValueError):
            return RowDecision(row.id, "unsure", fallback=True, error="INVALID_DATE", reason="date must be yyyy-mm-dd")

        predictions = self.adapter.predict([{"id": row.id, "text": row.text, "date": row.row_date}])
        if len(predictions) != 1:
            raise ValueError("model must return exactly one prediction for one row")
        prediction = predictions[0]
        label = prediction["label"]
        if label == "unsure" and prediction["confidence"] is None:
            return RowDecision(row.id, "unsure", reason=prediction.get("reason", "model uncertainty"))
        confidence = float(prediction["confidence"])
        if label not in LABELS or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("model returned an invalid label or confidence")
        if label == "unsure" or confidence < 0.5:
            return RowDecision(row.id, "unsure", reason="model uncertainty")
        return RowDecision(row.id, label, confidence=confidence, reason=prediction.get("reason", "local LightGBM prediction"))

    def close(self) -> None:
        """The cached, fitted adapter is shared by subsequent jobs."""
