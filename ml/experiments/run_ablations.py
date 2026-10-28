"""Controlled Ablation Experiments for Classical ML + Parser + Temporal Evidence Graph.

Configurations:
  Config A: Text features baseline (Word TF-IDF + Char TF-IDF + surface stats)
  Config B: Text features + Parser-derived features
  Config C: Text features + Parser-derived features + Graph & Evidence features (Full Hybrid)
  Config D: Structured Graph & Parser features only (No text features)

Models:
  - LightGBM (num_leaves=15, reg_lambda=1.0, balanced & moderate class weights, 2 CPU threads)
  - CatBoost (for top configuration)

Leakage prevention:
  - Target claim's gold form is NEVER fed as an inference feature.
  - In 10-fold CV: each fold's evidence graph is built strictly out-of-fold from the other 9 folds.
  - In validation & test: the evidence graph is built strictly from outer train (1,328 rows).
  - Target row is always excluded from its own evidence (exclude_claim_id=row['id']).
"""

from __future__ import annotations

import os
import sys
import time
import tracemalloc
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
import lightgbm as lgb
from catboost import CatBoostClassifier

# Add repo root to python path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from foundation import Lexicon, load_inputs, normalize_date
from core.graph.builder import build_graph
from ml.features.fact_extractor import (
    ALL_FEATURE_NAMES,
    GRAPH_FEATURE_NAMES,
    PARSER_FEATURE_NAMES,
    FactAwareFeatureExtractor,
)
from ml.models.text_baseline import TextBaselinePipeline

LABELS = ["false", "true", "unsure"]
LABEL_TO_IDX = {l: i for i, l in enumerate(LABELS)}
IDX_TO_LABEL = {i: l for i, l in enumerate(LABELS)}


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray | None = None) -> dict[str, Any]:
    """Compute detailed evaluation metrics across classes."""
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
    p_per, r_per, f1_per, _ = precision_recall_fscore_support(y_true, y_pred, labels=[0, 1, 2], zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1, 2])

    pred_counts = pd.Series(y_pred).value_counts().to_dict()
    pred_dist = {IDX_TO_LABEL[k]: int(pred_counts.get(k, 0)) for k in range(3)}

    return {
        "accuracy": float(acc),
        "macro_f1": float(macro_f1),
        "false_precision": float(p_per[0]),
        "false_recall": float(r_per[0]),
        "false_f1": float(f1_per[0]),
        "true_precision": float(p_per[1]),
        "true_recall": float(r_per[1]),
        "true_f1": float(f1_per[1]),
        "unsure_precision": float(p_per[2]),
        "unsure_recall": float(r_per[2]),
        "unsure_f1": float(f1_per[2]),
        "confusion_matrix": cm.tolist(),
        "pred_dist": pred_dist,
    }


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print("=" * 80)
    print("NEURON5 Classical ML + Parser + Temporal Evidence Graph Ablation Suite")
    print("=" * 80)

    # 1. Load Data and Splits
    practice_csv = REPO_ROOT / "data" / "practice.csv"
    lexicon_json = REPO_ROOT / "data" / "lexicon.json"
    splits_csv = REPO_ROOT / "ml" / "shared" / "splits.csv"
    cv_folds_csv = REPO_ROOT / "ml" / "shared" / "cv10_folds.csv"

    universe = load_inputs(str(practice_csv), str(lexicon_json))
    lexicon = universe.lexicon
    if lexicon is None:
        raise ValueError("Could not load lexicon.")

    df_practice = pd.read_csv(practice_csv)
    df_splits = pd.read_csv(splits_csv)
    df_cv = pd.read_csv(cv_folds_csv)

    df_all = df_practice.merge(df_splits, on="id").merge(df_cv, on="id", how="left")
    print(f"Total dataset: {len(df_all)} rows.")
    print("Partition breakdown:")
    print(df_all["split"].value_counts())

    train_df = df_all[df_all["split"] == "train"].copy().reset_index(drop=True)
    val_df = df_all[df_all["split"] == "validation"].copy().reset_index(drop=True)
    test_df = df_all[df_all["split"] == "test"].copy().reset_index(drop=True)

    # 2. Precompute Structured Features Out-Of-Fold for CV
    cache_train = REPO_ROOT / "ml" / "experiments" / "df_train_struct.csv"
    cache_val = REPO_ROOT / "ml" / "experiments" / "df_val_struct.csv"
    cache_test = REPO_ROOT / "ml" / "experiments" / "df_test_struct.csv"

    if cache_train.exists() and cache_val.exists() and cache_test.exists():
        print("\n--- Loading Precomputed Structured Features from Cache ---")
        df_train_struct = pd.read_csv(cache_train)
        df_val_struct = pd.read_csv(cache_val)
        df_test_struct = pd.read_csv(cache_test)
    else:
        print("\n--- Step 1: Precomputing Out-Of-Fold Structured Features for Train (10 Folds) ---")
        oof_feat_rows: list[dict[str, float]] = [{}] * len(train_df)

        t_start_oof = time.time()
        for fold in range(10):
            t_f0 = time.time()
            tr_k_rows = train_df[train_df["fold"] != fold].to_dict("records")
            val_k_idx = train_df[train_df["fold"] == fold].index
            val_k_df = train_df.iloc[val_k_idx]

            # Build graph using ONLY training folds
            g_k = build_graph(tr_k_rows, lexicon, tr_k_rows)
            extractor = FactAwareFeatureExtractor(lexicon, g_k)

            for local_i, (_, row) in enumerate(val_k_df.iterrows()):
                global_idx = val_k_idx[local_i]
                feats = extractor.extract_features(
                    text=row["text"],
                    claim_date=row["date"],
                    exclude_claim_id=row["id"],
                )
                oof_feat_rows[global_idx] = feats

            t_f1 = time.time()
            print(f"  Fold {fold}: {len(val_k_df)} rows processed in {t_f1 - t_f0:.2f}s")
        print(f"OOF feature extraction complete in {time.time() - t_start_oof:.2f}s.")

        df_train_struct = pd.DataFrame(oof_feat_rows)
        df_train_struct.to_csv(cache_train, index=False)

        # 3. Precompute Structured Features for Outer Validation and Test
        print("\n--- Step 2: Precomputing Features for Outer Validation and Test from Train Graph ---")
        t_start_val = time.time()
        train_records = train_df.to_dict("records")
        g_train = build_graph(train_records, lexicon, train_records)
        extractor_train = FactAwareFeatureExtractor(lexicon, g_train)

        val_feat_rows = []
        for _, row in val_df.iterrows():
            f = extractor_train.extract_features(
                text=row["text"],
                claim_date=row["date"],
                exclude_claim_id=row["id"],
            )
            val_feat_rows.append(f)
        df_val_struct = pd.DataFrame(val_feat_rows)
        df_val_struct.to_csv(cache_val, index=False)

        test_feat_rows = []
        for _, row in test_df.iterrows():
            f = extractor_train.extract_features(
                text=row["text"],
                claim_date=row["date"],
                exclude_claim_id=row["id"],
            )
            test_feat_rows.append(f)
        df_test_struct = pd.DataFrame(test_feat_rows)
        df_test_struct.to_csv(cache_test, index=False)
        print(f"Val & Test feature extraction complete in {time.time() - t_start_val:.2f}s.")

    # 4. Coverage Statistics
    print("\n--- Coverage Statistics ---")
    def print_coverage(name: str, df_s: pd.DataFrame):
        n = len(df_s)
        n_parsed = (df_s["parsed_fact_count"] > 0).sum()
        n_ev = (df_s["evidence_available"] > 0).sum()
        n_exact = (df_s["exact_value_match"] > 0).sum()
        print(f"[{name}] Total: {n} | Parsed: {n_parsed} ({n_parsed/n*100:.1f}%) | "
              f"Evidence Available: {n_ev} ({n_ev/n*100:.1f}%) | "
              f"Exact Value Match: {n_exact} ({n_exact/n*100:.1f}%)")

    print_coverage("Train (OOF)", df_train_struct)
    print_coverage("Validation", df_val_struct)
    print_coverage("Test", df_test_struct)

    # 5. Build Feature Sets
    # Feature subsets:
    parser_cols = list(PARSER_FEATURE_NAMES)
    graph_cols = list(GRAPH_FEATURE_NAMES)
    struct_cols = parser_cols + graph_cols

    # Prepare labels
    y_train = np.array([LABEL_TO_IDX[l] for l in train_df["label"]])
    y_val = np.array([LABEL_TO_IDX[l] for l in val_df["label"]])
    y_test = np.array([LABEL_TO_IDX[l] for l in test_df["label"]])
    folds = train_df["fold"].values.astype(int)

    # 6. Ablation Experiment Matrix
    # Configs to run:
    # 1. Baseline Text (balanced)
    # 2. Baseline Text (moderate weight: false=2.0, true=1.0, unsure=3.0)
    # 3. Text + Parser (balanced)
    # 4. Text + Parser (moderate)
    # 5. Text + Parser + Graph (Full Hybrid - balanced)
    # 6. Text + Parser + Graph (Full Hybrid - moderate)
    # 7. Graph Only (balanced)
    # 8. Graph Only (moderate)
    # 9. Top CatBoost (Full Hybrid)

    experiment_definitions = [
        {"name": "A1: Text Baseline (Balanced)", "config": "A", "features": "text", "weighting": "balanced", "model": "lgb"},
        {"name": "A2: Text Baseline (Moderate)", "config": "A", "features": "text", "weighting": "moderate", "model": "lgb"},
        {"name": "B1: Text + Parser (Balanced)", "config": "B", "features": "text+parser", "weighting": "balanced", "model": "lgb"},
        {"name": "B2: Text + Parser (Moderate)", "config": "B", "features": "text+parser", "weighting": "moderate", "model": "lgb"},
        {"name": "C1: Text + Parser + Graph (Balanced)", "config": "C", "features": "text+parser+graph", "weighting": "balanced", "model": "lgb"},
        {"name": "C2: Text + Parser + Graph (Moderate)", "config": "C", "features": "text+parser+graph", "weighting": "moderate", "model": "lgb"},
        {"name": "D1: Graph Only (Balanced)", "config": "D", "features": "graph_only", "weighting": "balanced", "model": "lgb"},
        {"name": "D2: Graph Only (Moderate)", "config": "D", "features": "graph_only", "weighting": "moderate", "model": "lgb"},
        {"name": "C3: CatBoost Hybrid (Moderate)", "config": "C", "features": "text+parser+graph", "weighting": "moderate", "model": "catboost"},
    ]

    results_table = []
    all_oof_preds: dict[str, np.ndarray] = {}
    all_oof_probs: dict[str, np.ndarray] = {}
    all_val_preds: dict[str, np.ndarray] = {}
    all_val_probs: dict[str, np.ndarray] = {}
    all_test_preds: dict[str, np.ndarray] = {}
    all_test_probs: dict[str, np.ndarray] = {}

    print("\n--- Step 3: Running Controlled Ablations Across 10-Fold CV & Validation ---")

    for exp in experiment_definitions:
        exp_name = exp["name"]
        feat_type = exp["features"]
        weighting = exp["weighting"]
        model_type = exp["model"]
        print(f"\nRunning {exp_name}...")

        # Setup class weights
        if weighting == "balanced":
            class_weight = "balanced"
            cat_weights = [1328 / (3 * 194), 1328 / (3 * 1107), 1328 / (3 * 27)]
        elif weighting == "moderate":
            class_weight = {0: 2.0, 1: 1.0, 2: 3.0}
            cat_weights = [2.0, 1.0, 3.0]
        else:
            class_weight = None
            cat_weights = None

        oof_preds = np.zeros(len(train_df), dtype=int)
        oof_probs = np.zeros((len(train_df), 3), dtype=float)

        val_probs_folds = np.zeros((len(val_df), 3), dtype=float)
        test_probs_folds = np.zeros((len(test_df), 3), dtype=float)

        t_cv_start = time.time()
        tracemalloc.start()

        # 10-Fold CV
        for fold in range(10):
            val_idx = (folds == fold)
            tr_idx = ~val_idx

            train_texts_k = train_df.iloc[tr_idx]["text"].values
            val_texts_k = train_df.iloc[val_idx]["text"].values

            # Feature preparation per fold
            if feat_type == "text":
                text_pipe = TextBaselinePipeline(max_word_features=1000, max_char_features=1000)
                X_tr = text_pipe.fit_transform(train_texts_k)
                X_val = text_pipe.transform(val_texts_k)
                X_val_outer = text_pipe.transform(val_df["text"].values)
                X_test_outer = text_pipe.transform(test_df["text"].values)
            elif feat_type == "text+parser":
                text_pipe = TextBaselinePipeline(max_word_features=1000, max_char_features=1000)
                X_tr_txt = text_pipe.fit_transform(train_texts_k)
                X_val_txt = text_pipe.transform(val_texts_k)
                X_val_outer_txt = text_pipe.transform(val_df["text"].values)
                X_test_outer_txt = text_pipe.transform(test_df["text"].values)

                X_tr_p = csr_matrix(df_train_struct.iloc[tr_idx][parser_cols].values)
                X_val_p = csr_matrix(df_train_struct.iloc[val_idx][parser_cols].values)
                X_val_outer_p = csr_matrix(df_val_struct[parser_cols].values)
                X_test_outer_p = csr_matrix(df_test_struct[parser_cols].values)

                X_tr = hstack([X_tr_txt, X_tr_p], format="csr")
                X_val = hstack([X_val_txt, X_val_p], format="csr")
                X_val_outer = hstack([X_val_outer_txt, X_val_outer_p], format="csr")
                X_test_outer = hstack([X_test_outer_txt, X_test_outer_p], format="csr")
            elif feat_type == "text+parser+graph":
                text_pipe = TextBaselinePipeline(max_word_features=1000, max_char_features=1000)
                X_tr_txt = text_pipe.fit_transform(train_texts_k)
                X_val_txt = text_pipe.transform(val_texts_k)
                X_val_outer_txt = text_pipe.transform(val_df["text"].values)
                X_test_outer_txt = text_pipe.transform(test_df["text"].values)

                X_tr_s = csr_matrix(df_train_struct.iloc[tr_idx][struct_cols].values)
                X_val_s = csr_matrix(df_train_struct.iloc[val_idx][struct_cols].values)
                X_val_outer_s = csr_matrix(df_val_struct[struct_cols].values)
                X_test_outer_s = csr_matrix(df_test_struct[struct_cols].values)

                X_tr = hstack([X_tr_txt, X_tr_s], format="csr")
                X_val = hstack([X_val_txt, X_val_s], format="csr")
                X_val_outer = hstack([X_val_outer_txt, X_val_outer_s], format="csr")
                X_test_outer = hstack([X_test_outer_txt, X_test_outer_s], format="csr")
            elif feat_type == "graph_only":
                X_tr = csr_matrix(df_train_struct.iloc[tr_idx][struct_cols].values)
                X_val = csr_matrix(df_train_struct.iloc[val_idx][struct_cols].values)
                X_val_outer = csr_matrix(df_val_struct[struct_cols].values)
                X_test_outer = csr_matrix(df_test_struct[struct_cols].values)
            else:
                raise ValueError(f"Unknown feature type: {feat_type}")

            # Fit Model
            if model_type == "lgb":
                clf = lgb.LGBMClassifier(
                    num_leaves=15,
                    reg_lambda=1.0,
                    class_weight=class_weight,
                    n_estimators=100,
                    random_state=42 + fold,
                    n_jobs=2,
                    verbose=-1,
                )
                clf.fit(X_tr, y_train[tr_idx])
            elif model_type == "catboost":
                clf = CatBoostClassifier(
                    iterations=150,
                    depth=5,
                    l2_leaf_reg=3.0,
                    class_weights=cat_weights,
                    random_seed=42 + fold,
                    thread_count=2,
                    verbose=0,
                )
                clf.fit(X_tr, y_train[tr_idx])
            else:
                raise ValueError(f"Unknown model: {model_type}")

            raw_preds = clf.predict(X_val)
            oof_preds[val_idx] = np.squeeze(raw_preds).astype(int)
            oof_probs[val_idx] = clf.predict_proba(X_val)

            val_probs_folds += clf.predict_proba(X_val_outer) / 10.0
            test_probs_folds += clf.predict_proba(X_test_outer) / 10.0

        current_ram, peak_ram = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        t_cv_end = time.time()
        elapsed_sec = t_cv_end - t_cv_start

        val_preds = np.argmax(val_probs_folds, axis=1)
        test_preds = np.argmax(test_probs_folds, axis=1)

        # Measure single-thread latency per 100 inference calls
        t_infer_0 = time.time()
        if feat_type in ("text", "text+parser", "text+parser+graph"):
            sample_X = X_val_outer[:100]
        else:
            sample_X = X_val_outer[:100]
        _ = clf.predict(sample_X)
        latency_100 = (time.time() - t_infer_0) * 1000.0  # ms for 100 rows

        # Compute CV and Val metrics
        cv_metrics = compute_metrics(y_train, oof_preds, oof_probs)
        val_metrics = compute_metrics(y_val, val_preds, val_probs_folds)
        test_metrics = compute_metrics(y_test, test_preds, test_probs_folds)

        all_oof_preds[exp_name] = oof_preds
        all_oof_probs[exp_name] = oof_probs
        all_val_preds[exp_name] = val_preds
        all_val_probs[exp_name] = val_probs_folds
        all_test_preds[exp_name] = test_preds
        all_test_probs[exp_name] = test_probs_folds

        print(f"  --> CV Acc: {cv_metrics['accuracy']*100:.2f}% | CV Macro-F1: {cv_metrics['macro_f1']:.4f} | False Recall: {cv_metrics['false_recall']*100:.1f}%")
        print(f"  --> Val Acc: {val_metrics['accuracy']*100:.2f}% | Val Macro-F1: {val_metrics['macro_f1']:.4f} | False Recall: {val_metrics['false_recall']*100:.1f}%")
        print(f"  --> Test Acc: {test_metrics['accuracy']*100:.2f}% | Test Macro-F1: {test_metrics['macro_f1']:.4f} | False Recall: {test_metrics['false_recall']*100:.1f}%")
        print(f"  --> Peak RAM: {peak_ram / (1024*1024):.2f} MB | Latency (100 rows): {latency_100:.1f} ms")

        record = {
            "Experiment": exp_name,
            "Config": exp["config"],
            "Features": feat_type,
            "Weighting": weighting,
            "Model": model_type,
            "CV_Accuracy": cv_metrics["accuracy"],
            "CV_Macro_F1": cv_metrics["macro_f1"],
            "CV_False_Precision": cv_metrics["false_precision"],
            "CV_False_Recall": cv_metrics["false_recall"],
            "CV_False_F1": cv_metrics["false_f1"],
            "CV_True_F1": cv_metrics["true_f1"],
            "CV_Unsure_F1": cv_metrics["unsure_f1"],
            "Val_Accuracy": val_metrics["accuracy"],
            "Val_Macro_F1": val_metrics["macro_f1"],
            "Val_False_Precision": val_metrics["false_precision"],
            "Val_False_Recall": val_metrics["false_recall"],
            "Val_False_F1": val_metrics["false_f1"],
            "Val_True_F1": val_metrics["true_f1"],
            "Val_Unsure_F1": val_metrics["unsure_f1"],
            "Test_Accuracy": test_metrics["accuracy"],
            "Test_Macro_F1": test_metrics["macro_f1"],
            "Test_False_Precision": test_metrics["false_precision"],
            "Test_False_Recall": test_metrics["false_recall"],
            "Test_False_F1": test_metrics["false_f1"],
            "Test_True_F1": test_metrics["true_f1"],
            "Test_Unsure_F1": test_metrics["unsure_f1"],
            "Inference_Time_100rows_ms": latency_100,
            "Peak_RAM_MB": peak_ram / (1024 * 1024),
            "Total_Training_Sec": elapsed_sec,
            "Val_CM": str(val_metrics["confusion_matrix"]),
            "Val_Pred_Dist": str(val_metrics["pred_dist"]),
        }
        results_table.append(record)

    # 7. Save Comparison CSV
    results_df = pd.DataFrame(results_table)
    results_csv_path = REPO_ROOT / "ml" / "experiments" / "results_comparison.csv"
    results_df.to_csv(results_csv_path, index=False)
    print(f"\n[Artifact Saved] Comparison table written to: {results_csv_path}")

    # 8. Save Per-Row Predictions and Probabilities CSV
    # Assemble comprehensive predictions table
    pred_records = []
    # Train OOF
    for i, row in train_df.iterrows():
        rec = {
            "id": row["id"],
            "split": "train",
            "fold": int(row["fold"]),
            "text": row["text"],
            "date": row["date"],
            "gold_label": row["label"],
        }
        for exp in experiment_definitions:
            ename = exp["name"]
            pred_idx = all_oof_preds[ename][i]
            probs = all_oof_probs[ename][i]
            rec[f"{ename}_pred"] = IDX_TO_LABEL[pred_idx]
            rec[f"{ename}_prob_false"] = round(float(probs[0]), 4)
            rec[f"{ename}_prob_true"] = round(float(probs[1]), 4)
            rec[f"{ename}_prob_unsure"] = round(float(probs[2]), 4)
        pred_records.append(rec)

    # Validation
    for i, row in val_df.iterrows():
        rec = {
            "id": row["id"],
            "split": "validation",
            "fold": -1,
            "text": row["text"],
            "date": row["date"],
            "gold_label": row["label"],
        }
        for exp in experiment_definitions:
            ename = exp["name"]
            pred_idx = all_val_preds[ename][i]
            probs = all_val_probs[ename][i]
            rec[f"{ename}_pred"] = IDX_TO_LABEL[pred_idx]
            rec[f"{ename}_prob_false"] = round(float(probs[0]), 4)
            rec[f"{ename}_prob_true"] = round(float(probs[1]), 4)
            rec[f"{ename}_prob_unsure"] = round(float(probs[2]), 4)
        pred_records.append(rec)

    # Test
    for i, row in test_df.iterrows():
        rec = {
            "id": row["id"],
            "split": "test",
            "fold": -1,
            "text": row["text"],
            "date": row["date"],
            "gold_label": row["label"],
        }
        for exp in experiment_definitions:
            ename = exp["name"]
            pred_idx = all_test_preds[ename][i]
            probs = all_test_probs[ename][i]
            rec[f"{ename}_pred"] = IDX_TO_LABEL[pred_idx]
            rec[f"{ename}_prob_false"] = round(float(probs[0]), 4)
            rec[f"{ename}_prob_true"] = round(float(probs[1]), 4)
            rec[f"{ename}_prob_unsure"] = round(float(probs[2]), 4)
        pred_records.append(rec)

    preds_df = pd.DataFrame(pred_records)
    preds_csv_path = REPO_ROOT / "ml" / "experiments" / "predictions_oof_and_val.csv"
    preds_df.to_csv(preds_csv_path, index=False)
    print(f"[Artifact Saved] Predictions & probabilities written to: {preds_csv_path}")

    print("\n" + "=" * 80)
    print("Ablation Run Completed Successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
