"""Train and evaluate fold-safe M2 LightGBM retrieval features."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
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
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support)

from core.graph.builder import build_graph
from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
from core.retrieval.hybrid import HybridEvidenceRetriever
from ml.classical.benchmark import LABELS, fact_group_key, make_feature_builder, transform_features

OUT = ROOT / "ml" / "classical" / "results_m2_v1"
SEED = 42


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
    counts = Counter(y.tolist()); n = len(y); k = len(counts)
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
    eligible = Counter(); category_count = Counter()
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
    actual = y == "false"; selected = pred == "false"
    tp = int(np.sum(actual & selected)); fp = int(np.sum(~actual & selected)); fn = int(np.sum(actual & ~selected))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"false_precision": precision, "false_recall": recall, "false_f1": f1,
            "false_true_positives": tp, "false_false_positives": fp, "false_false_negatives": fn}


def tune_false_threshold(y: np.ndarray, oof_probs: np.ndarray) -> float:
    scores = oof_probs[:, LABELS.index("false")]
    candidates = sorted(value for value in set(scores.tolist()) | {0.5, 1.0000001} if value >= 0.5)
    return max(candidates, key=lambda threshold: (
        false_metrics(y, oof_probs, threshold)["false_f1"],
        false_metrics(y, oof_probs, threshold)["false_precision"], threshold))


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
                # Each classifier-training feature uses only evidence inside its outer training partition.
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


def score(estimator: Any, x: Any, y: np.ndarray, rows: list[dict[str, str]], reference_rows: list[dict[str, str]]) -> dict[str, Any]:
    out = metrics(y, probabilities(estimator, x))
    groups = exact_signature_groups(rows, reference_rows)
    out["claim_groups"] = {}
    for name, indexes in groups.items():
        out["claim_groups"][name] = metrics(y[indexes], probabilities(estimator, x[indexes])) if indexes else {"rows": 0, "macro_f1": None}
    return out


def run(*, output: Path = OUT, max_configs: int | None = None) -> dict[str, Any]:
    require_lightgbm()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite populated results directory: {output}")
    rows, lexicon, splits, folds = load_inputs()
    train_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "train"]
    val_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "validation"]
    test_ix = [i for i, r in enumerate(rows) if splits[r["id"]] == "test"]
    train = [rows[i] for i in train_ix]; val = [rows[i] for i in val_ix]; test = [rows[i] for i in test_ix]
    y_train = np.asarray([r["label"].lower() for r in train]); y_val = np.asarray([r["label"].lower() for r in val]); y_test = np.asarray([r["label"].lower() for r in test])

    # Shared lexical builder follows P1. Retrieval evidence remains strictly fold-local.
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
        "m2": (estimator_matrix(x_train_base, oof_retr), estimator_matrix(x_val_base, val_retr), estimator_matrix(x_test_base, test_retr)),
    }
    configs = config_grid()[:max_configs] if max_configs is not None else config_grid()
    selected = {}
    test_scores = {}
    threshold_reports = {}
    for name, (xtr, xval, xtest) in feature_sets.items():
        candidates = []
        for cfg in configs:
            est = new_estimator(cfg, y_train).fit(xtr, y_train)
            validation = metrics(y_val, probabilities(est, xval))
            candidates.append((validation["macro_f1"], validation["balanced_accuracy"], cfg, validation))
        _, _, cfg, validation = max(candidates, key=lambda item: (item[0], item[1]))
        oof_probs, oof_fold_false = oof_probabilities(x_train_base, y_train, train, folds, cfg,
                                                       lexicon, name == "m2")
        threshold = tune_false_threshold(y_train, oof_probs)
        oof_fold_reports = []
        for fold in oof_fold_false:
            indexes = np.asarray(fold["indices"], dtype=int)
            fold_y, fold_probs = y_train[indexes], oof_probs[indexes]
            oof_fold_reports.append({
                "fold": fold["fold"],
                "before_threshold": metrics(fold_y, fold_probs),
                "after_threshold": metrics(fold_y, fold_probs, threshold),
                "false_before_threshold": false_metrics(fold_y, fold_probs),
                "false_after_threshold": false_metrics(fold_y, fold_probs, threshold),
            })
        final_y = np.concatenate((y_train, y_val))
        final_x = estimator_matrix(x_train_base, oof_retr) if name == "m2" else x_train_base
        val_x = estimator_matrix(x_val_base, val_retr) if name == "m2" else x_val_base
        final_x = vstack((final_x, val_x), format="csr")
        validation_estimator = new_estimator(cfg, y_train).fit(xtr, y_train)
        final = new_estimator(cfg, final_y).fit(final_x, final_y)
        val_probs = probabilities(validation_estimator, xval)
        test_probs = probabilities(final, xtest)
        selected[name] = {"configuration": cfg, "validation": validation,
                          "false_threshold_policy": {"threshold": threshold,
                              "selected_from": "OOF probabilities only; maximize false F1, tie-break precision then higher threshold",
                              "oof_before": false_metrics(y_train, oof_probs),
                              "oof_after": false_metrics(y_train, oof_probs, threshold),
                              "oof_fold_mean_std": mean_std(oof_fold_false, ("false_precision", "false_recall", "false_f1")),
                              "validation_before": false_metrics(y_val, val_probs),
                              "validation_after": false_metrics(y_val, val_probs, threshold),
                              "validation_precision_cost": false_metrics(y_val, val_probs)["false_precision"] - false_metrics(y_val, val_probs, threshold)["false_precision"]},
                          "validation_metrics_after_false_threshold": metrics(y_val, val_probs, threshold),
                          "oof_fold_metrics": oof_fold_reports,
                          "oof_fold_metric_mean_std": {
                              "before_threshold": mean_std([fold["before_threshold"] for fold in oof_fold_reports],
                                  ("accuracy", "balanced_accuracy", "macro_f1")),
                              "after_threshold": mean_std([fold["after_threshold"] for fold in oof_fold_reports],
                                  ("accuracy", "balanced_accuracy", "macro_f1")),
                              "false_before_threshold": mean_std([fold["false_before_threshold"] for fold in oof_fold_reports],
                                  ("false_precision", "false_recall", "false_f1")),
                              "false_after_threshold": mean_std([fold["false_after_threshold"] for fold in oof_fold_reports],
                                  ("false_precision", "false_recall", "false_f1")),
                          }}
        test_scores[name] = score(final, xtest, y_test, test, test_evidence)
        test_before = false_metrics(y_test, test_probs)
        test_after = false_metrics(y_test, test_probs, threshold)
        threshold_reports[name] = {"threshold": threshold, "selected_from": "OOF probabilities only",
                                   "outer_test_before": test_before, "outer_test_after": test_after,
                                   "outer_test_precision_cost": test_before["false_precision"] - test_after["false_precision"]}
        if name == "m2":
            output.mkdir(parents=True, exist_ok=True)
            joblib.dump({"estimator": final, "feature_builder": feature_builder,
                         "label_order": tuple(LABELS), "retrieval_feature_names": tuple(FEATURE_NAMES),
                         "feature_count": int(final_x.shape[1]), "minimum_confidence": 0.5,
                         "false_threshold": threshold}, output / "model.joblib", compress=3)
    report = {"status": "completed", "created_at": datetime.now(timezone.utc).isoformat(),
              "rows": {"train": len(train), "validation": len(val), "outer_test": len(test)},
              "selection": "validation macro-F1 then balanced accuracy; outer test was scored after selection and never used for tuning",
              "configs_evaluated": len(configs), "selected": selected, "outer_test": test_scores,
              "retrieval_features": list(FEATURE_NAMES), "oof_fold_count": len(set(folds.values())),
              "oof_retrieval_recall_by_fold": fold_retrieval,
              "oof_retrieval_recall_fold_mean_std": {
                  category: {str(k): mean_std([{"value": fold["recall"][category]["recall_at"][str(k)]}
                                               for fold in fold_retrieval], ("value",))["value"]
                             for k in (1, 3, 5, 10)}
                  for category in ("exact_shared_signature", "new_or_paraphrased_claim")},
              "validation_retrieval_recall": retrieval_recall(val_extractor, val, train),
              "outer_test_retrieval_recall": retrieval_recall(test_extractor, test, test_evidence),
              "false_threshold_policies": threshold_reports,
              "false_threshold_precision_cost_definition": "untuned false precision minus thresholded false precision; positive values indicate precision lost after thresholding",
              "evidence_policy": "OOF indexes/graphs use only the other nine train folds; validation evidence uses train; outer-test evidence uses train+validation after policy selection.",
              "outer_test_signature_policy": "Exact form signatures are used only to report exact shared-signature retrieval separately from new/paraphrased claims; forms never enter inference rows.",
              "split_sha256": hashlib.sha256((ROOT / "ml/shared/splits.csv").read_bytes()).hexdigest(),
              "fold_sha256": hashlib.sha256((ROOT / "ml/shared/cv10_folds.csv").read_bytes()).hexdigest()}
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-configs", type=int, help="bounded run for smoke benchmarking")
    parser.add_argument("--output", type=Path, default=OUT, help="new versioned output directory")
    args = parser.parse_args()
    report = run(output=args.output, max_configs=args.max_configs)
    print(json.dumps({"selected": report["selected"], "outer_test": report["outer_test"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
