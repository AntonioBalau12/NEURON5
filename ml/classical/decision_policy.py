"""Unified Decision Policy, Probability Calibration, and Abstention Engine.

Shared by both training evaluation (OOF, validation, test) and production inference (runner.py).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence
import numpy as np
import scipy.optimize
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)

LABELS = ["false", "true", "unsure"]


def compute_ece(probs: np.ndarray, y_true_indices: np.ndarray, n_bins: int = 10) -> float:
    """Compute top-1 Expected Calibration Error."""
    confidences = np.max(probs, axis=1)
    predictions = np.argmax(probs, axis=1)
    accuracies = (predictions == y_true_indices).astype(float)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0

    for i in range(n_bins):
        bin_lower, bin_upper = bin_boundaries[i], bin_boundaries[i + 1]
        in_bin = (
            (confidences > bin_lower) & (confidences <= bin_upper)
            if i > 0
            else (confidences >= bin_lower) & (confidences <= bin_upper)
        )
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(accuracies[in_bin])
            avg_confidence_in_bin = np.mean(confidences[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin

    return float(ece)


def multiclass_brier_score(probs: np.ndarray, y_true_indices: np.ndarray) -> float:
    """Compute multiclass Brier score."""
    n, k = probs.shape
    one_hot = np.zeros((n, k), dtype=float)
    one_hot[np.arange(n), y_true_indices] = 1.0
    return float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))


def debias_probabilities(
    probs: np.ndarray,
    class_weights_map: dict[str, float] | None,
    label_order: Sequence[str] = tuple(LABELS),
) -> np.ndarray:
    """Reverse class-weight prior distortion so probabilities reflect the true prior."""
    if not class_weights_map:
        return np.asarray(probs, dtype=np.float64)
    probs_arr = np.asarray(probs, dtype=np.float64)
    orig_shape = probs_arr.shape
    if probs_arr.ndim == 1:
        probs_arr = probs_arr.reshape(1, -1)
    weights = np.asarray([float(class_weights_map.get(lbl, 1.0)) for lbl in label_order], dtype=np.float64)
    weights = np.maximum(weights, 1e-12)
    unweighted = probs_arr / weights
    sums = unweighted.sum(axis=1, keepdims=True)
    debiased = np.divide(unweighted, sums, out=np.zeros_like(unweighted), where=sums != 0)
    return debiased.reshape(orig_shape)


class TemperatureScaler:
    """Multiclass temperature scaling via negative log-likelihood minimization."""

    def __init__(self, temperature: float = 1.0):
        self.temperature = float(temperature)

    def fit(self, probs: np.ndarray, y_true_indices: np.ndarray) -> TemperatureScaler:
        eps = 1e-12
        clipped = np.clip(probs, eps, 1.0 - eps)
        logits = np.log(clipped)

        def loss_fn(t):
            t_val = max(1e-4, float(t[0]))
            scaled = logits / t_val
            exp_scaled = np.exp(scaled - np.max(scaled, axis=1, keepdims=True))
            p = exp_scaled / np.sum(exp_scaled, axis=1, keepdims=True)
            p = np.clip(p, eps, 1.0 - eps)
            return log_loss(y_true_indices, p, labels=[0, 1, 2])

        res = scipy.optimize.minimize(loss_fn, x0=[1.0], bounds=[(0.05, 10.0)], method="L-BFGS-B")
        self.temperature = float(res.x[0])
        return self

    def predict_proba(self, probs: np.ndarray) -> np.ndarray:
        eps = 1e-12
        clipped = np.clip(probs, eps, 1.0 - eps)
        logits = np.log(clipped)
        scaled = logits / max(1e-4, self.temperature)
        exp_scaled = np.exp(scaled - np.max(scaled, axis=1, keepdims=True))
        return exp_scaled / np.sum(exp_scaled, axis=1, keepdims=True)


class VectorScalingCalibrator:
    """Multiclass Platt / Vector scaling on logits with L2 regularization."""

    def __init__(self, c: float = 1.0):
        self.c = c
        self.model = LogisticRegression(C=self.c, solver="lbfgs", max_iter=500)
        self.classes_ = np.asarray([0, 1, 2])

    def fit(self, probs: np.ndarray, y_true_indices: np.ndarray) -> VectorScalingCalibrator:
        eps = 1e-12
        logits = np.log(np.clip(probs, eps, 1.0 - eps))
        self.model.fit(logits, y_true_indices)
        self.classes_ = np.asarray(self.model.classes_)
        return self

    def predict_proba(self, probs: np.ndarray) -> np.ndarray:
        eps = 1e-12
        logits = np.log(np.clip(probs, eps, 1.0 - eps))
        raw = self.model.predict_proba(logits)
        aligned = np.zeros((len(raw), len(LABELS)), dtype=float)
        for idx, cls in enumerate(self.classes_):
            if cls < len(LABELS):
                aligned[:, cls] = raw[:, idx]
        return aligned


class CalibratedDecisionPolicy:
    """Production decision policy unifying training evaluation and runtime inference.

    Applies:
    1. Prior debiasing or temperature/Platt probability calibration.
    2. Factual confidence safety (Tier 1 boosts TRUE only on verified positive support).
    3. FALSE Precision Guardrail (Tier 2 abstaining unverified false predictions to unsure).
    4. Damped ML confidence and selective minimum-confidence abstention (Tier 3).
    """

    def __init__(
        self,
        minimum_confidence: float = 0.50,
        false_threshold: float = 0.65,
        damping_graph: float = 0.90,
        damping_fallback: float = 0.75,
        calibration_mode: str = "debias",
        class_weights_map: dict[str, float] | None = None,
        temperature_scaler: TemperatureScaler | None = None,
        vector_scaler: VectorScalingCalibrator | None = None,
        label_order: Sequence[str] = tuple(LABELS),
    ):
        self.minimum_confidence = float(minimum_confidence)
        self.false_threshold = float(false_threshold)
        self.damping_graph = float(damping_graph)
        self.damping_fallback = float(damping_fallback)
        self.calibration_mode = calibration_mode
        self.class_weights_map = class_weights_map
        self.temperature_scaler = temperature_scaler
        self.vector_scaler = vector_scaler
        self.label_order = tuple(label_order)

    def calibrate_probabilities(self, probs: np.ndarray) -> np.ndarray:
        """Apply the chosen probability calibration method."""
        p = np.asarray(probs, dtype=np.float64)
        if self.calibration_mode == "debias":
            return debias_probabilities(p, self.class_weights_map, self.label_order)
        elif self.calibration_mode == "temperature" and self.temperature_scaler is not None:
            return self.temperature_scaler.predict_proba(p)
        elif self.calibration_mode == "debias_temperature":
            deb = debias_probabilities(p, self.class_weights_map, self.label_order)
            if self.temperature_scaler is not None:
                return self.temperature_scaler.predict_proba(deb)
            return deb
        elif self.calibration_mode == "vector" and self.vector_scaler is not None:
            return self.vector_scaler.predict_proba(p)
        return p

    def decide_single(
        self,
        raw_prob_row: np.ndarray,
        retrieval_features: Mapping[str, Any],
    ) -> tuple[str, float | None, str, str]:
        """Classify a single claim and assign calibrated confidence.

        Returns: (label, confidence, tier_applied, reason)
        """
        # 1. Calibrate probabilities
        p_row = self.calibrate_probabilities(raw_prob_row.reshape(1, -1))[0]

        false_idx = self.label_order.index("false")
        true_idx = self.label_order.index("true")
        unsure_idx = self.label_order.index("unsure")

        raw_pred = self.label_order[int(np.argmax(p_row))]
        raw_conf = float(p_row[self.label_order.index(raw_pred)])
        false_conf = float(p_row[false_idx])

        # Feature signals
        exact_match = int(retrieval_features.get("exact_fact_match", 0))
        temporal_match = int(retrieval_features.get("temporal_evidence_match", 0))
        ret_verified = int(retrieval_features.get("retrieved_verified_count", 0))
        graph_success = int(retrieval_features.get("graph_lookup_success", 0))
        verified_refutation = int(retrieval_features.get("verified_refutation", 0))

        # Tier 1 (Deterministic Factual Safety):
        # Only boost TRUE when positive evidence supports it!
        # Positive evidence must NEVER boost FALSE!
        if raw_pred == "true" and exact_match == 1 and temporal_match == 1:
            safe_conf = round(min(0.98, max(0.90, raw_conf + 0.02 * ret_verified)), 4)
            return "true", safe_conf, "tier_1_verified_support", "Exact temporal match in verified graph evidence"

        if raw_pred == "false" and verified_refutation == 1:
            safe_conf = round(min(0.98, max(0.90, raw_conf + 0.02 * ret_verified)), 4)
            return "false", safe_conf, "tier_1_verified_refutation", "Explicit verified refutation in graph evidence"

        # Tier 2 (FALSE Precision Guardrail):
        # Low-confidence false predictions without verified evidence abstain to unsure.
        if raw_pred == "false" and exact_match == 0 and raw_conf < self.false_threshold:
            return (
                "unsure",
                None,
                "tier_2_false_guardrail",
                f"Unverified false prediction (conf {raw_conf:.3f} < {self.false_threshold:.3f}) abstained to unsure",
            )

        # Tier 3 (Retrieval-Damped ML Confidence):
        damping = self.damping_graph if graph_success == 1 else self.damping_fallback
        safe_conf = 0.5 + (raw_conf - 0.5) * damping

        if raw_pred == "unsure" or safe_conf < self.minimum_confidence:
            return (
                "unsure",
                None,
                "tier_3_abstention",
                f"Confidence below minimum threshold ({safe_conf:.3f} < {self.minimum_confidence:.3f})",
            )

        safe_conf = round(float(np.clip(safe_conf, 0.5001, 0.88)), 4)
        return raw_pred, safe_conf, "tier_3_damped_confidence", f"Calibrated {raw_pred} with damped confidence {safe_conf}"

    def decide_batch(
        self,
        probs_matrix: np.ndarray,
        retrieval_data: Sequence[Mapping[str, Any]] | np.ndarray,
        feature_names: Sequence[str] = (
            "bm25_top_score", "bm25_score_gap", "retrieved_verified_count",
            "retrieved_candidate_count", "graph_lookup_success", "retrieval_fallback_used",
            "exact_fact_match", "temporal_evidence_match",
        ),
    ) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
        """Run batch decision policy.

        Returns: (predictions_array, confidences_array, diagnostics_list)
        """
        n = len(probs_matrix)
        preds = []
        confs = []
        diagnostics = []

        is_matrix = isinstance(retrieval_data, np.ndarray) or hasattr(retrieval_data, "toarray")
        if is_matrix and hasattr(retrieval_data, "toarray"):
            retrieval_data = retrieval_data.toarray()

        for i in range(n):
            if is_matrix:
                rf = {feature_names[k]: float(retrieval_data[i, k]) for k in range(min(len(feature_names), retrieval_data.shape[1]))}
            elif retrieval_data is None:
                rf = {}
            else:
                rf = retrieval_data[i]

            label, conf, tier, reason = self.decide_single(probs_matrix[i], rf)
            preds.append(label)
            confs.append(conf)
            diagnostics.append({"index": i, "label": label, "confidence": conf, "tier": tier, "reason": reason})

        return np.asarray(preds), np.asarray(confs, dtype=object), diagnostics

    def evaluate(
        self,
        y_true: Sequence[str],
        probs_matrix: np.ndarray,
        retrieval_data: Sequence[Mapping[str, Any]] | np.ndarray,
        feature_names: Sequence[str] = (
            "bm25_top_score", "bm25_score_gap", "retrieved_verified_count",
            "retrieved_candidate_count", "graph_lookup_success", "retrieval_fallback_used",
            "exact_fact_match", "temporal_evidence_match",
        ),
        row_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Compute complete classification, calibration, payoff, and prediction-change metrics."""
        y_true_arr = np.asarray([lbl.lower() for lbl in y_true])
        raw_preds = np.asarray([self.label_order[int(np.argmax(p))] for p in probs_matrix])
        raw_confs = np.asarray([float(np.max(p)) for p in probs_matrix])

        policy_preds, policy_confs, diagnostics = self.decide_batch(probs_matrix, retrieval_data, feature_names)

        # Raw metrics
        raw_prec, raw_rec, raw_f1, raw_sup = precision_recall_fscore_support(
            y_true_arr, raw_preds, labels=self.label_order, zero_division=0
        )
        raw_acc = float(accuracy_score(y_true_arr, raw_preds))
        raw_bal_acc = float(balanced_accuracy_score(y_true_arr, raw_preds))
        raw_macro_f1 = float(f1_score(y_true_arr, raw_preds, labels=self.label_order, average="macro", zero_division=0))

        # Calibrated policy metrics
        pol_prec, pol_rec, pol_f1, pol_sup = precision_recall_fscore_support(
            y_true_arr, policy_preds, labels=self.label_order, zero_division=0
        )
        pol_acc = float(accuracy_score(y_true_arr, policy_preds))
        pol_bal_acc = float(balanced_accuracy_score(y_true_arr, policy_preds))
        pol_macro_f1 = float(f1_score(y_true_arr, policy_preds, labels=self.label_order, average="macro", zero_division=0))

        # Competition payoff
        payoff = 0.0
        for i in range(len(y_true_arr)):
            pred = policy_preds[i]
            act = y_true_arr[i]
            c = policy_confs[i]
            if pred == "unsure" or c is None:
                continue
            if pred == act:
                payoff += c
            else:
                payoff -= c
        avg_payoff = float(payoff / max(1, len(y_true_arr)))

        # Tier usage
        tier_counts = {}
        for d in diagnostics:
            tier_counts[d["tier"]] = tier_counts.get(d["tier"], 0) + 1

        # Prediction-level comparison
        changes = []
        for i in range(len(y_true_arr)):
            if raw_preds[i] != policy_preds[i]:
                rid = row_ids[i] if row_ids is not None else f"row-{i}"
                changes.append({
                    "id": rid,
                    "actual": y_true_arr[i],
                    "raw_pred": raw_preds[i],
                    "raw_conf": round(float(raw_confs[i]), 4),
                    "policy_pred": policy_preds[i],
                    "policy_conf": policy_confs[i],
                    "tier": diagnostics[i]["tier"],
                    "reason": diagnostics[i]["reason"],
                })

        return {
            "rows": len(y_true_arr),
            "raw_performance": {
                "accuracy": raw_acc,
                "balanced_accuracy": raw_bal_acc,
                "macro_f1": raw_macro_f1,
                "classes": {
                    lbl: {
                        "precision": float(raw_prec[k]),
                        "recall": float(raw_rec[k]),
                        "f1": float(raw_f1[k]),
                        "support": int(raw_sup[k]),
                    }
                    for k, lbl in enumerate(self.label_order)
                },
                "confusion_matrix": confusion_matrix(y_true_arr, raw_preds, labels=self.label_order).tolist(),
            },
            "calibrated_performance": {
                "accuracy": pol_acc,
                "balanced_accuracy": pol_bal_acc,
                "macro_f1": pol_macro_f1,
                "classes": {
                    lbl: {
                        "precision": float(pol_prec[k]),
                        "recall": float(pol_rec[k]),
                        "f1": float(pol_f1[k]),
                        "support": int(pol_sup[k]),
                    }
                    for k, lbl in enumerate(self.label_order)
                },
                "confusion_matrix": confusion_matrix(y_true_arr, policy_preds, labels=self.label_order).tolist(),
            },
            "competition_confidence_payoff": avg_payoff,
            "tier_counts": tier_counts,
            "prediction_changes_count": len(changes),
            "prediction_changes": changes,
            "policy_parameters": {
                "minimum_confidence": self.minimum_confidence,
                "false_threshold": self.false_threshold,
                "damping_graph": self.damping_graph,
                "damping_fallback": self.damping_fallback,
                "calibration_mode": self.calibration_mode,
            },
        }
