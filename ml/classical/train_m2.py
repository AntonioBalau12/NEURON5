"""Train and evaluate fold-safe M2 LightGBM retrieval features."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack, lil_matrix, vstack
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_fscore_support,
)
from sklearn.model_selection import StratifiedGroupKFold

from core.graph.builder import build_graph
from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
from core.retrieval.hybrid import HybridEvidenceRetriever
from ml.classical.benchmark import LABELS, fact_group_key, make_feature_builder, transform_features
from ml.classical.decision_policy import (
    CalibratedDecisionPolicy,
    TemperatureScaler,
    VectorScalingCalibrator,
    compute_ece,
    debias_probabilities,
    multiclass_brier_score,
)

OUT = ROOT / "ml" / "classical" / "results_m2_v2"
SEED = 42


def make_groups(rows: list[dict[str, str]]) -> list[str]:
    """Group rows by entity-fact families and text clusters to prevent leakage across folds."""
    groups = []
    for r in rows:
        form = r.get("form") or ""
        group_key = None
        try:
            facts = json.loads(form)
            if facts and isinstance(facts, list):
                keys = []
                for fact in facts:
                    subj = str(fact.get("subject", "")).casefold().strip()
                    attr = str(fact.get("attribute", "")).strip()
                    if subj and attr:
                        keys.append(subj + ":" + attr)
                if keys:
                    group_key = "fact_" + "_".join(sorted(keys))
        except Exception:
            pass
        if not group_key:
            text = r.get("text", "").casefold().strip()
            words = re.findall(r"[a-z0-9]+", text)
            if len(words) >= 4:
                group_key = "text_" + "_".join(words[:4])
            else:
                rid = r.get("id", "")
                group_key = f"row_{rid}"
        groups.append(group_key)
    return groups


def load_inputs() -> tuple[list[dict[str, str]], dict[str, Any], dict[str, str], dict[str, int]]:
    with (ROOT / "data" / "practice.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    lexicon = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8"))

    def csv_map(path: Path, field: str) -> dict[str, str]:
        with path.open(encoding="utf-8-sig", newline="") as f:
            return {r["id"]: r[field] for r in csv.DictReader(f)}

    splits = csv_map(ROOT / "ml/shared/splits.csv", "split")
    folds = {key: int(val) for key, val in csv_map(ROOT / "ml/shared/cv10_folds.csv", "fold").items()}
    ids = {r["id"] for r in rows}
    if set(splits) != ids or set(folds) != {r["id"] for r in rows if splits.get(r["id"]) == "train"}:
        raise ValueError("shared split/fold manifests do not match practice rows")
    return rows, lexicon, splits, folds


def inference_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Strip forms and labels before any claim is sent through a feature builder."""
    return [{"id": r["id"], "text": r["text"], "date": r["date"]} for r in rows]


def retrieval_matrix(index_rows: list[dict[str, str]], query_rows: list[dict[str, str]], lexicon: dict[str, Any]) -> csr_matrix:
    return extractor_matrix(build_retriever(index_rows, lexicon), query_rows)


def extractor_matrix(extractor: RetrievalFeatureExtractor, query_rows: list[dict[str, str]]) -> csr_matrix:
    values = []
    for row in inference_rows(query_rows):
        feats = extractor.extract(row["text"], row["date"], exclude_evidence_ids=(row["id"],))
        values.append([feats[name] for name in FEATURE_NAMES])
    return csr_matrix(np.asarray(values, dtype=np.float32).reshape(len(values), len(FEATURE_NAMES)))


def build_retriever(index_rows: list[dict[str, str]], lexicon: dict[str, Any]) -> RetrievalFeatureExtractor:
    """Build the graph and BM25 corpus from exactly the supplied evidence rows."""
    return RetrievalFeatureExtractor(HybridEvidenceRetriever(build_graph(index_rows, lexicon)))


def estimator_matrix(base: Any, retr: csr_matrix | None = None) -> Any:
    return base if retr is None else hstack((base, retr), format="csr", dtype=np.float32)


def config_grid() -> list[dict[str, Any]]:
    return [{"num_leaves": leaves, "reg_lambda": reg, "weighting": weight}
            for leaves in (7, 15) for reg in (1, 5) for weight in ("none", "moderate", "balanced")]


def class_weights(y: np.ndarray, mode: str) -> dict[str, float] | None:
    if mode == "none":
        return None
    counts = Counter(y.tolist())
    n = len(y)
    k = len(counts)
    exponent = 0.5 if mode == "moderate" else 1.0
    raw = {label: (n / (k * count)) ** exponent for label, count in counts.items()}
    mean = sum(raw[label] * counts[label] for label in counts) / n
    return {label: value / mean for label, value in raw.items()}


def new_estimator(config: dict[str, Any], y: np.ndarray):
    from lightgbm import LGBMClassifier
    return LGBMClassifier(objective="multiclass", num_class=len(LABELS), num_leaves=config["num_leaves"],
                          n_estimators=300, learning_rate=0.05, min_child_samples=20,
                          reg_lambda=config["reg_lambda"], n_jobs=2, random_state=SEED,
                          class_weight=class_weights(y, config["weighting"]), verbosity=-1)


def require_lightgbm() -> None:
    try:
        import lightgbm  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("LightGBM is required to train M2; install the existing benchmark dependency") from exc


def probabilities(estimator: Any, x: Any) -> np.ndarray:
    raw = estimator.predict_proba(x)
    aligned = np.zeros((len(raw), len(LABELS)), dtype=np.float64)
    for column, label in enumerate(estimator.classes_):
        aligned[:, LABELS.index(str(label))] = raw[:, column]
    return aligned


def decisions(probs: np.ndarray, false_threshold: float | None = None) -> np.ndarray:
    pred = np.asarray(LABELS)[probs.argmax(axis=1)]
    confidence = probs.max(axis=1)
    pred[confidence < 0.5] = "unsure"
    if false_threshold is not None:
        false_probability = probs[:, LABELS.index("false")]
        eligible = (pred != "false") & (false_probability >= max(0.5, false_threshold))
        pred[eligible] = "false"
    return pred


def metrics(y: np.ndarray, probs: np.ndarray, false_threshold: float | None = None) -> dict[str, Any]:
    pred = decisions(probs, false_threshold)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, pred, labels=LABELS, zero_division=0
    )
    return {"rows": len(y), "accuracy": float(accuracy_score(y, pred)),
            "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
            "macro_f1": float(f1_score(y, pred, labels=LABELS, average="macro", zero_division=0)),
            "classes": {label: {"precision": float(precision[i]), "recall": float(recall[i]),
                                "f1": float(f1[i]), "support": int(support[i])}
                        for i, label in enumerate(LABELS)},
            "confusion_matrix_labels": LABELS,
            "confusion_matrix": confusion_matrix(y, pred, labels=LABELS).tolist()}


def exact_signature_groups(rows: list[dict[str, str]], reference_rows: list[dict[str, str]]) -> dict[str, list[int]]:
    known = {fact_group_key(r.get("form", "")) for r in reference_rows}
    exact = [i for i, row in enumerate(rows) if fact_group_key(row.get("form", "")) and fact_group_key(row.get("form", "")) in known]
    return {"exact_shared_signature": exact, "new_or_paraphrased_claim": [i for i in range(len(rows)) if i not in set(exact)]}


def fact_signatures(row: dict[str, str]) -> set[str]:
    try:
        facts = json.loads(row.get("form", "[]") or "[]")
    except (TypeError, ValueError):
        return set()
    result = set()
    for fact in facts if isinstance(facts, list) else []:
        if not isinstance(fact, dict):
            continue
        value = fact.get("value", {})
        result.add(json.dumps((str(fact.get("subject", "")).casefold(), fact.get("attribute"),
                              value.get("kind"), value.get("value"), value.get("unit"),
                              value.get("currency"), value.get("per"), value.get("op")),
                             ensure_ascii=False, separators=(",", ":")))
    return result


def retrieval_recall(extractor: RetrievalFeatureExtractor, queries: list[dict[str, str]],
                     evidence_rows: list[dict[str, str]]) -> dict[str, Any]:
    evidence_facts = {row["id"]: fact_signatures(row) for row in evidence_rows}
    evidence_groups = {row["id"]: fact_group_key(row.get("form", "")) for row in evidence_rows}
    values: dict[str, dict[int, list[float]]] = {
        "exact_shared_signature": {k: [] for k in (1, 3, 5, 10)},
        "new_or_paraphrased_claim": {k: [] for k in (1, 3, 5, 10)},
    }
    eligible = Counter()
    category_count = Counter()
    for query in queries:
        signature = fact_group_key(query.get("form", ""))
        is_exact = bool(signature) and signature in set(evidence_groups.values())
        category = "exact_shared_signature" if is_exact else "new_or_paraphrased_claim"
        category_count[category] += 1
        target_facts = fact_signatures(query)
        if is_exact:
            relevant = {rid for rid, sig in evidence_groups.items() if sig == signature}
        else:
            relevant = {rid for rid, facts in evidence_facts.items() if target_facts and facts.intersection(target_facts)}
        if not relevant:
            continue
        eligible[category] += 1
        ranked = extractor.retriever.search(query["text"], query.get("date"), top_k=10,
                                            exclude_evidence_ids=(query["id"],), mode="hybrid")
        ranked_ids = [item.evidence_id for item in ranked]
        for k in values[category]:
            values[category][k].append(len(relevant.intersection(ranked_ids[:k])) / len(relevant))
    return {category: {"query_count": category_count[category], "queries_with_relevant_evidence": eligible[category],
                       "recall_at": {str(k): (float(np.mean(scores)) if scores else None)
                                     for k, scores in ks.items()}}
            for category, ks in values.items()}


def mean_std(fold_metrics: list[dict[str, Any]], keys: tuple[str, ...]) -> dict[str, dict[str, float | None]]:
    output = {}
    for key in keys:
        vals = [float(item[key]) for item in fold_metrics if item.get(key) is not None]
        output[key] = {"mean": float(np.mean(vals)) if vals else None,
                       "std": float(np.std(vals)) if vals else None, "folds": len(vals)}
    return output


def false_metrics(y: np.ndarray, probs: np.ndarray, threshold: float | None = None) -> dict[str, float | int]:
    pred = decisions(probs, threshold)
    actual = y == "false"
    selected = pred == "false"
    tp = int(np.sum(actual & selected))
    fp = int(np.sum(~actual & selected))
    fn = int(np.sum(actual & ~selected))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"false_precision": precision, "false_recall": recall, "false_f1": f1,
            "false_true_positives": tp, "false_false_positives": fp, "false_false_negatives": fn}


def oof_probabilities(base: Any, y: np.ndarray, train_rows: list[dict[str, str]],
                      fold_map: dict[str, int], config: dict[str, Any],
                      lexicon: dict[str, Any], include_retrieval: bool) -> tuple[np.ndarray, list[dict[str, Any]]]:
    result = np.zeros((len(y), len(LABELS)), dtype=np.float64)
    per_fold = []
    for fold in sorted(set(fold_map.values())):
        held = np.asarray([i for i, row in enumerate(train_rows) if fold_map[row["id"]] == fold])
        fit = np.asarray([i for i, row in enumerate(train_rows) if fold_map[row["id"]] != fold])
        x_fit, x_held = base[fit], base[held]
        if include_retrieval:
            fit_retr = lil_matrix((len(fit), len(FEATURE_NAMES)), dtype=np.float32)
            fit_rows_all = [train_rows[int(index)] for index in fit]
            for inner_fold in sorted(set(fold_map[row["id"]] for row in fit_rows_all)):
                inner_held_rel = [j for j, row_ix in enumerate(fit) if fold_map[train_rows[row_ix]["id"]] == inner_fold]
                inner_held_set = set(inner_held_rel)
                inner_fit = [int(row_ix) for j, row_ix in enumerate(fit) if j not in inner_held_set]
                inner_rows = [train_rows[i] for i in inner_fit]
                query_rows = [train_rows[int(fit[j])] for j in inner_held_rel]
                inner_x = extractor_matrix(build_retriever(inner_rows, lexicon), query_rows)
                fit_retr[inner_held_rel] = inner_x
            fit_rows = [train_rows[int(i)] for i in fit]
            held_rows = [train_rows[int(i)] for i in held]
            outer_extractor = build_retriever(fit_rows, lexicon)
            held_retr = extractor_matrix(outer_extractor, held_rows)
            fit_retr = fit_retr.tocsr()
            x_fit = estimator_matrix(x_fit, fit_retr)
            x_held = estimator_matrix(x_held, held_retr)
        estimator = new_estimator(config, y[fit]).fit(x_fit, y[fit])
        result[held] = probabilities(estimator, x_held)
        per_fold.append({"fold": fold, "indices": held.tolist()})
    return result, per_fold


def tune_false_threshold(y: np.ndarray, oof_probs: np.ndarray) -> float:
    scores = oof_probs[:, LABELS.index("false")]
    candidates = sorted(value for value in set(scores.tolist()) | {0.5, 1.0000001} if value >= 0.5)
    return max(candidates, key=lambda threshold: (
        false_metrics(y, oof_probs, threshold)["false_f1"],
        false_metrics(y, oof_probs, threshold)["false_precision"], threshold))


def audit_calibration_methods(
    y_str: list[str],
    raw_probs: np.ndarray,
    cw_map: dict[str, float] | None,
) -> dict[str, Any]:
    """Audit probability calibration methods across LogLoss, Brier, ECE, and competition payoff."""
    y_idx = np.asarray([LABELS.index(lbl) for lbl in y_str])
    eps = 1e-12

    # 1. Raw LightGBM
    p_raw = np.clip(raw_probs, eps, 1.0 - eps)
    raw_loss = float(log_loss(y_idx, p_raw, labels=[0, 1, 2]))
    raw_brier = multiclass_brier_score(p_raw, y_idx)
    raw_ece = compute_ece(p_raw, y_idx)

    # 2. Debiased
    p_deb = debias_probabilities(raw_probs, cw_map, LABELS)
    p_deb_clipped = np.clip(p_deb, eps, 1.0 - eps)
    deb_loss = float(log_loss(y_idx, p_deb_clipped, labels=[0, 1, 2]))
    deb_brier = multiclass_brier_score(p_deb, y_idx)
    deb_ece = compute_ece(p_deb, y_idx)

    # 3. Temperature Scaling
    temp_scaler = TemperatureScaler().fit(raw_probs, y_idx)
    p_temp = temp_scaler.predict_proba(raw_probs)
    p_temp_clipped = np.clip(p_temp, eps, 1.0 - eps)
    temp_loss = float(log_loss(y_idx, p_temp_clipped, labels=[0, 1, 2]))
    temp_brier = multiclass_brier_score(p_temp, y_idx)
    temp_ece = compute_ece(p_temp, y_idx)

    # 4. Debiased + Temperature Scaling
    deb_temp_scaler = TemperatureScaler().fit(p_deb, y_idx)
    p_deb_temp = deb_temp_scaler.predict_proba(p_deb)
    p_deb_temp_clipped = np.clip(p_deb_temp, eps, 1.0 - eps)
    deb_temp_loss = float(log_loss(y_idx, p_deb_temp_clipped, labels=[0, 1, 2]))
    deb_temp_brier = multiclass_brier_score(p_deb_temp, y_idx)
    deb_temp_ece = compute_ece(p_deb_temp, y_idx)

    # 5. Platt / Vector Scaling
    vec_scaler = VectorScalingCalibrator().fit(raw_probs, y_idx)
    p_vec = vec_scaler.predict_proba(raw_probs)
    p_vec_clipped = np.clip(p_vec, eps, 1.0 - eps)
    vec_loss = float(log_loss(y_idx, p_vec_clipped, labels=[0, 1, 2]))
    vec_brier = multiclass_brier_score(p_vec, y_idx)
    vec_ece = compute_ece(p_vec, y_idx)

    return {
        "raw_lightgbm": {"log_loss": raw_loss, "brier_score": raw_brier, "ece": raw_ece},
        "class_weight_debias": {"log_loss": deb_loss, "brier_score": deb_brier, "ece": deb_ece},
        "temperature_scaling": {"log_loss": temp_loss, "brier_score": temp_brier, "ece": temp_ece, "temperature": temp_scaler.temperature},
        "debias_plus_temperature": {"log_loss": deb_temp_loss, "brier_score": deb_temp_brier, "ece": deb_temp_ece, "temperature": deb_temp_scaler.temperature},
        "vector_scaling_platt": {"log_loss": vec_loss, "brier_score": vec_brier, "ece": vec_ece},
    }


def tune_policy_thresholds(
    y_str: list[str],
    raw_probs: np.ndarray,
    retrieval_retr: csr_matrix,
    cw_map: dict[str, float] | None,
) -> tuple[float, float, str, float]:
    """Sweep threshold combinations on OOF data to optimize competition payoff while preserving FALSE recall."""
    best_mc = 0.50
    best_ft = 0.52
    best_mode = "none"
    best_score = -float("inf")

    # Evaluate candidates
    min_conf_grid = [0.50, 0.52, 0.55]
    false_thresh_grid = [0.50, 0.52, 0.55, 0.58, 0.60]

    for mc in min_conf_grid:
        for ft in false_thresh_grid:
            pol = CalibratedDecisionPolicy(
                minimum_confidence=mc,
                false_threshold=ft,
                calibration_mode="none",
                class_weights_map=cw_map,
            )
            eval_res = pol.evaluate(y_str, raw_probs, retrieval_retr)
            payoff = eval_res["competition_confidence_payoff"]
            mf1 = eval_res["calibrated_performance"]["macro_f1"]
            f_rec = eval_res["calibrated_performance"]["classes"]["false"]["recall"]
            f_prec = eval_res["calibrated_performance"]["classes"]["false"]["precision"]

            # Payoff primary, false recall floor >= 0.08
            score = payoff if f_rec >= 0.08 else payoff - 0.5
            if score > best_score:
                best_score = score
                best_mc = mc
                best_ft = ft
                best_mode = "none"

    return best_mc, best_ft, best_mode, best_score


def run(*, output: Path = OUT, max_configs: int | None = None, overwrite: bool = True) -> dict[str, Any]:
    require_lightgbm()
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise FileExistsError(f"refusing to overwrite populated results directory: {output}")
    rows, lexicon, splits, folds = load_inputs()
    train_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "train"]
    val_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "validation"]
    test_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "test"]
    train = [rows[i] for i in train_ix]
    val = [rows[i] for i in val_ix]
    test = [rows[i] for i in test_ix]
    y_train = np.asarray([r["label"].lower() for r in train])
    y_val = np.asarray([r["label"].lower() for r in val])
    y_test = np.asarray([r["label"].lower() for r in test])

    # Shared lexical builder. Retrieval evidence remains strictly fold-local.
    feature_builder = make_feature_builder(train, lexicon)
    x_train_base, _ = transform_features(inference_rows(train), feature_builder)
    x_val_base, _ = transform_features(inference_rows(val), feature_builder)
    x_test_base, _ = transform_features(inference_rows(test), feature_builder)

    oof_retr = lil_matrix((len(train), len(FEATURE_NAMES)), dtype=np.float32)
    fold_retrieval = []
    for fold in sorted(set(folds.values())):
        held = [i for i, r in enumerate(train) if folds[r["id"]] == fold]
        fit_rows = [r for i, r in enumerate(train) if folds[r["id"]] != fold]
        extractor = build_retriever(fit_rows, lexicon)
        held_rows = [train[i] for i in held]
        oof_retr[held] = extractor_matrix(extractor, held_rows)
        fold_retrieval.append({"fold": fold, "recall": retrieval_recall(extractor, held_rows, fit_rows)})
    oof_retr = oof_retr.tocsr()

    val_extractor = build_retriever(train, lexicon)
    val_retr = extractor_matrix(val_extractor, val)
    test_evidence = train + val
    test_extractor = build_retriever(test_evidence, lexicon)
    test_retr = extractor_matrix(test_extractor, test)

    feature_sets = {
        "reference": (x_train_base, x_val_base, x_test_base),
        "m2": (
            estimator_matrix(x_train_base, oof_retr),
            estimator_matrix(x_val_base, val_retr),
            estimator_matrix(x_test_base, test_retr),
        ),
    }
    configs = config_grid()[:max_configs] if max_configs is not None else config_grid()
    selected = {}
    test_scores = {}
    threshold_reports = {}
    calibration_audits = {}

    for name, (xtr, xval, xtest) in feature_sets.items():
        candidates = []
        for cfg in configs:
            est = new_estimator(cfg, y_train).fit(xtr, y_train)
            validation = metrics(y_val, probabilities(est, xval))
            candidates.append((validation["macro_f1"], validation["balanced_accuracy"], cfg, validation))
        _, _, cfg, validation = max(candidates, key=lambda item: (item[0], item[1]))

        oof_probs, oof_fold_false = oof_probabilities(
            x_train_base, y_train, train, folds, cfg, lexicon, name == "m2"
        )
        cw_map = class_weights(y_train, cfg["weighting"])

        # Calibration audit
        cal_audit = audit_calibration_methods(list(y_train), oof_probs, cw_map)
        calibration_audits[name] = cal_audit

        # Tune policy thresholds on OOF
        min_conf, false_thresh, cal_mode, best_payoff = tune_policy_thresholds(
            list(y_train), oof_probs, oof_retr if name == "m2" else None, cw_map
        )

        # Build policy
        policy = CalibratedDecisionPolicy(
            minimum_confidence=min_conf,
            false_threshold=false_thresh,
            damping_graph=0.90,
            damping_fallback=0.75,
            calibration_mode=cal_mode,
            class_weights_map=cw_map,
        )

        oof_eval = policy.evaluate(
            list(y_train),
            oof_probs,
            oof_retr if name == "m2" else None,
            row_ids=[r["id"] for r in train],
        )

        final_y = np.concatenate((y_train, y_val))
        final_x = estimator_matrix(x_train_base, oof_retr) if name == "m2" else x_train_base
        val_x = estimator_matrix(x_val_base, val_retr) if name == "m2" else x_val_base
        final_x = vstack((final_x, val_x), format="csr")

        validation_estimator = new_estimator(cfg, y_train).fit(xtr, y_train)
        final_est = new_estimator(cfg, final_y).fit(final_x, final_y)

        val_probs = probabilities(validation_estimator, xval)
        test_probs = probabilities(final_est, xtest)

        val_eval = policy.evaluate(
            list(y_val),
            val_probs,
            val_retr if name == "m2" else None,
            row_ids=[r["id"] for r in val],
        )

        test_eval = policy.evaluate(
            list(y_test),
            test_probs,
            test_retr if name == "m2" else None,
            row_ids=[r["id"] for r in test],
        )

        selected[name] = {
            "configuration": cfg,
            "validation_raw": validation,
            "validation_policy": val_eval,
            "oof_evaluation": oof_eval,
            "policy_parameters": {
                "minimum_confidence": min_conf,
                "false_threshold": false_thresh,
                "calibration_mode": cal_mode,
            },
            "calibration_audit": cal_audit,
        }

        test_scores[name] = test_eval

        if name == "m2":
            output.mkdir(parents=True, exist_ok=True)
            # --- Full-Universe Production Fit on 100% of data/practice.csv (1,897 rows) ---
            all_rows = rows
            y_all = np.asarray([r["label"].lower() for r in all_rows])
            prod_feature_builder = make_feature_builder(all_rows, lexicon)
            x_prod_base, _ = transform_features(inference_rows(all_rows), prod_feature_builder)

            # 10-fold fold-safe OOF retrieval features across all 1,897 rows using StratifiedGroupKFold
            prod_groups = make_groups(all_rows)
            sgkf = StratifiedGroupKFold(n_splits=10, shuffle=True, random_state=SEED)
            prod_folds: dict[str, int] = {}
            for fold_idx, (fit_idx, held_idx) in enumerate(sgkf.split(all_rows, y_all, prod_groups)):
                for idx in held_idx:
                    prod_folds[all_rows[idx]["id"]] = fold_idx

            # Verify 0 group leakage
            for f_idx in range(10):
                f_held_ids = {all_rows[i]["id"] for i in range(len(all_rows)) if prod_folds[all_rows[i]["id"]] == f_idx}
                f_fit_ids = {all_rows[i]["id"] for i in range(len(all_rows)) if prod_folds[all_rows[i]["id"]] != f_idx}
                f_held_grps = {prod_groups[i] for i, r in enumerate(all_rows) if r["id"] in f_held_ids}
                f_fit_grps = {prod_groups[i] for i, r in enumerate(all_rows) if r["id"] in f_fit_ids}
                assert len(f_held_grps.intersection(f_fit_grps)) == 0, f"Leaking groups in fold {f_idx}"

            prod_retr = lil_matrix((len(all_rows), len(FEATURE_NAMES)), dtype=np.float32)
            for p_fold in sorted(set(prod_folds.values())):
                p_held = [i for i, r in enumerate(all_rows) if prod_folds[r["id"]] == p_fold]
                p_fit_rows = [r for i, r in enumerate(all_rows) if prod_folds[r["id"]] != p_fold]
                p_extractor = build_retriever(p_fit_rows, lexicon)
                p_held_rows = [all_rows[i] for i in p_held]
                prod_retr[p_held] = extractor_matrix(p_extractor, p_held_rows)
            prod_retr = prod_retr.tocsr()
            x_prod_full = estimator_matrix(x_prod_base, prod_retr)

            # Compute full 1,897-row grouped OOF probabilities for calibrator fitting
            prod_oof_probs = np.zeros((len(all_rows), len(LABELS)), dtype=np.float64)
            for p_fold in sorted(set(prod_folds.values())):
                p_held = np.asarray([i for i, r in enumerate(all_rows) if prod_folds[r["id"]] == p_fold])
                p_fit = np.asarray([i for i, r in enumerate(all_rows) if prod_folds[r["id"]] != p_fold])
                p_est = new_estimator(cfg, y_all[p_fit]).fit(x_prod_full[p_fit], y_all[p_fit])
                prod_oof_probs[p_held] = probabilities(p_est, x_prod_full[p_held])

            prod_estimator = new_estimator(cfg, y_all).fit(x_prod_full, y_all)
            cw_all = class_weights(y_all, cfg["weighting"])
            prod_y_idx = np.asarray([LABELS.index(lbl) for lbl in y_all])

            prod_temp_scaler = TemperatureScaler().fit(prod_oof_probs, prod_y_idx)
            prod_vec_scaler = VectorScalingCalibrator().fit(prod_oof_probs, prod_y_idx)

            prod_policy = CalibratedDecisionPolicy(
                minimum_confidence=float(min_conf),
                false_threshold=float(false_thresh),
                damping_graph=0.90,
                damping_fallback=0.75,
                calibration_mode=cal_mode,
                class_weights_map=cw_all,
                temperature_scaler=prod_temp_scaler,
                vector_scaler=prod_vec_scaler,
                label_order=tuple(LABELS),
            )

            joblib.dump({
                "estimator": prod_estimator,
                "feature_builder": prod_feature_builder,
                "decision_policy": prod_policy,
                "temperature_scaler": prod_temp_scaler,
                "vector_scaler": prod_vec_scaler,
                "label_order": tuple(LABELS),
                "retrieval_feature_names": tuple(FEATURE_NAMES),
                "feature_count": int(x_prod_full.shape[1]),
                "class_weights_map": cw_all,
                "minimum_confidence": float(min_conf),
                "false_threshold": float(false_thresh),
                "calibration_mode": cal_mode,
                "production_universe_rows": len(all_rows),
                "grouped_folds": 10,
                "group_leakage": 0,
            }, output / "model.joblib", compress=3)

    report = {
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "rows": {"train": len(train), "validation": len(val), "outer_test": len(test)},
        "selection": "validation macro-F1 then balanced accuracy; outer test was scored after selection and never used for tuning",
        "configs_evaluated": len(configs),
        "selected": selected,
        "outer_test": test_scores,
        "calibration_audits": calibration_audits,
        "retrieval_features": list(FEATURE_NAMES),
        "oof_fold_count": len(set(folds.values())),
        "oof_retrieval_recall_by_fold": fold_retrieval,
        "oof_retrieval_recall_fold_mean_std": {
            category: {
                str(k): mean_std(
                    [{"value": fold["recall"][category]["recall_at"][str(k)]} for fold in fold_retrieval],
                    ("value",),
                )["value"]
                for k in (1, 3, 5, 10)
            }
            for category in ("exact_shared_signature", "new_or_paraphrased_claim")
        },
        "validation_retrieval_recall": retrieval_recall(val_extractor, val, train),
        "outer_test_retrieval_recall": retrieval_recall(test_extractor, test, test_evidence),
        "production_fit": {
            "rows": 1897,
            "grouped_folds": 10,
            "group_leakage": 0,
            "distinct_groups": len(set(prod_groups)),
        },
        "evidence_policy": "OOF indexes/graphs use only the other nine train folds; validation evidence uses train; outer-test evidence uses train+validation after policy selection.",
        "split_sha256": hashlib.sha256((ROOT / "ml/shared/splits.csv").read_bytes()).hexdigest(),
        "fold_sha256": hashlib.sha256((ROOT / "ml/shared/cv10_folds.csv").read_bytes()).hexdigest(),
    }

    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-configs", type=int, help="bounded run for smoke benchmarking")
    parser.add_argument("--output", type=Path, default=OUT, help="new versioned output directory")
    parser.add_argument("--no-overwrite", action="store_true", help="refuse to overwrite existing directory")
    args = parser.parse_args()
    report = run(output=args.output, max_configs=args.max_configs, overwrite=not args.no_overwrite)
    print(json.dumps({"selected": report["selected"]["m2"]["configuration"],
                      "validation_policy_f1": report["selected"]["m2"]["validation_policy"]["calibrated_performance"]["macro_f1"],
                      "test_policy_f1": report["outer_test"]["m2"]["calibrated_performance"]["macro_f1"],
                      "test_payoff": report["outer_test"]["m2"]["competition_confidence_payoff"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
