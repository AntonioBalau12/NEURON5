"""Minimal offline contract runner. No unsupported claims are synthesized."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.sparse import csr_matrix, hstack

from foundation import OUTPUT_COLUMNS, InputData, evidence_audit, load_inputs, validate_output

IMMUTABLE_ATTRIBUTES = frozenset({
    "launched",
    "released",
    "published",
    "venue",
    "city",
    "screen_size",
    "weight",
    "battery_capacity",
})


def debias_probabilities(
    probs: np.ndarray,
    class_weights_map: dict[str, float] | None,
    label_order: tuple[str, ...] = ("false", "true", "unsure"),
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


def calibrate_claim_confidence(claim: dict[str, Any], as_of_date: str = "2026-10-29") -> float:
    """Calibrate confidence for generated claims based on immutability and recency."""
    form_raw = claim.get("form")
    attrs: set[str] = set()
    if isinstance(form_raw, str):
        try:
            parsed = json.loads(form_raw)
        except (TypeError, ValueError):
            parsed = None
    else:
        parsed = form_raw

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and "attribute" in item:
                attrs.add(str(item["attribute"]).casefold())
    elif isinstance(parsed, dict):
        for side in ("left", "right"):
            sub = parsed.get(side)
            if isinstance(sub, dict) and "attribute" in sub:
                attrs.add(str(sub["attribute"]).casefold())

    if attrs and attrs.issubset(IMMUTABLE_ATTRIBUTES):
        return 0.95

    # Mutable claim recency calculation
    claim_date_str = claim.get("date")
    if claim_date_str:
        try:
            import datetime
            as_of = datetime.date.fromisoformat(as_of_date)
            dt = datetime.date.fromisoformat(str(claim_date_str)[:10])
            days = max(0, (as_of - dt).days)
            recency = max(0.0, min(1.0, 1.0 - days / 365.0))
            return round(0.75 + 0.17 * recency, 4)
        except (ValueError, TypeError):
            pass
    return 0.88


def default_path(runtime: str, local: str) -> str:
    return runtime if Path(runtime).exists() else str(Path(__file__).resolve().parent / local)


def atomic_write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Write in the destination directory then atomically replace output.csv."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_candidates(path: str | Path) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
        raise ValueError("candidate file must be a JSON array of claim objects")
    return raw


def predict_unlabeled(
    data: InputData,
    model_path: str,
    practice_path: str,
    timing_breakdown: dict[str, float] | None = None,
) -> dict[str, tuple[str, float | None]]:
    """Run the serialized M2 model; inference rows need only id/text/date/label."""
    from core.graph.builder import build_graph
    from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
    from core.retrieval.hybrid import HybridEvidenceRetriever
    from ml.classical.benchmark import LABELS, transform_features

    t_mod0 = time.perf_counter()
    artifact = joblib.load(model_path)
    if timing_breakdown is not None:
        timing_breakdown["model_loading_seconds"] = time.perf_counter() - t_mod0

    if not isinstance(artifact, dict):
        raise ValueError("M2 model artifact must be a mapping")
    estimator = artifact["estimator"]
    feature_builder = artifact["feature_builder"]
    label_order = tuple(artifact["label_order"])
    if label_order != tuple(LABELS):
        raise ValueError(f"model label order mismatch: {label_order!r}")
    if tuple(artifact["retrieval_feature_names"]) != tuple(FEATURE_NAMES):
        raise ValueError("M2 retrieval feature schema mismatch")

    t_ref0 = time.perf_counter()
    reference = load_inputs(practice_path, str(Path(practice_path).with_name("lexicon.json")))
    if timing_breakdown is not None:
        timing_breakdown["reference_load_seconds"] = time.perf_counter() - t_ref0

    t_graph0 = time.perf_counter()
    graph = build_graph(reference)
    if timing_breakdown is not None:
        timing_breakdown["evidence_graph_construction_seconds"] = time.perf_counter() - t_graph0

    t_bm0 = time.perf_counter()
    retriever = HybridEvidenceRetriever(graph)
    extractor = RetrievalFeatureExtractor(retriever)
    if timing_breakdown is not None:
        timing_breakdown["bm25_indexing_seconds"] = time.perf_counter() - t_bm0

    pending = [row for row in data.rows if row.label is None]
    result: dict[str, tuple[str, float | None]] = {}
    usable: list[Any] = []
    model_rows: list[dict[str, str]] = []
    retrieval_rows: list[list[float]] = []

    t_feat0 = time.perf_counter()
    for row in pending:
        if not row.text.strip() or row.date is None:
            result[row.row_id] = ("unsure", None)
            continue
        model_rows.append({"id": row.row_id, "text": row.text, "date": row.date.isoformat()})
        retrieved_features = extractor.extract(
            row.text, row.date, exclude_evidence_ids=(row.row_id,)
        )
        retrieval_rows.append([retrieved_features[name] for name in FEATURE_NAMES])
        usable.append(row)

    if usable:
        base_matrix, _ = transform_features(model_rows, feature_builder)
        retrieval_matrix = csr_matrix(np.asarray(retrieval_rows, dtype=np.float32))
        features = hstack((base_matrix, retrieval_matrix), format="csr", dtype=np.float32)
        if timing_breakdown is not None:
            timing_breakdown["retrieval_feature_extraction_seconds"] = time.perf_counter() - t_feat0

        expected = artifact.get("feature_count")
        if expected is not None and features.shape[1] != int(expected):
            raise ValueError(f"M2 feature count mismatch: {features.shape[1]} != {expected}")

        t_lgb0 = time.perf_counter()
        probabilities = np.asarray(estimator.predict_proba(features), dtype=np.float64)
        classes = tuple(str(item) for item in estimator.classes_)
        aligned = np.zeros((len(usable), len(label_order)), dtype=np.float64)
        for column, label in enumerate(classes):
            if label in label_order:
                aligned[:, label_order.index(label)] = probabilities[:, column]
        if timing_breakdown is not None:
            timing_breakdown["lightgbm_inference_seconds"] = time.perf_counter() - t_lgb0

        t_pol0 = time.perf_counter()
        from ml.classical.decision_policy import CalibratedDecisionPolicy

        class_weights_map = artifact.get("class_weights_map")
        if not class_weights_map:
            class_weights_map = getattr(estimator, "class_weight", None)

        policy = artifact.get("decision_policy")
        if policy is None:
            default_mode = artifact.get("calibration_mode")
            if default_mode is None:
                default_mode = "debias" if class_weights_map else "none"
            policy = CalibratedDecisionPolicy(
                minimum_confidence=float(artifact.get("minimum_confidence", 0.50)),
                false_threshold=float(artifact.get("false_threshold", 0.52)),
                damping_graph=0.90,
                damping_fallback=0.75,
                calibration_mode=default_mode,
                class_weights_map=class_weights_map,
                temperature_scaler=artifact.get("temperature_scaler"),
                vector_scaler=artifact.get("vector_scaler"),
                label_order=label_order,
            )

        for index, row in enumerate(usable):
            rf = retrieval_rows[index]
            retrieved_dict = {FEATURE_NAMES[k]: rf[k] for k in range(len(FEATURE_NAMES))}
            pred_label, pred_conf, tier, reason = policy.decide_single(aligned[index], retrieved_dict)
            result[row.row_id] = (pred_label, pred_conf)

        if timing_breakdown is not None:
            timing_breakdown["calibration_and_decision_policy_seconds"] = time.perf_counter() - t_pol0
    elif timing_breakdown is not None:
        timing_breakdown["retrieval_feature_extraction_seconds"] = time.perf_counter() - t_feat0
        timing_breakdown["lightgbm_inference_seconds"] = 0.0
        timing_breakdown["calibration_and_decision_policy_seconds"] = 0.0

    return result
    return result


def run(
    universe: str,
    lexicon: str,
    output: str,
    contract_dir: str,
    candidates_path: str | None = None,
    model_path: str | None = None,
    practice_path: str | None = None,
) -> int:
    os.environ.setdefault("HOME", "/tmp")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/.cache")
    os.environ.setdefault("HF_HOME", "/tmp/huggingface")
    try:
        deadline = int(os.environ.get("ARENA_DEADLINE", "0"))
    except ValueError:
        print("ARENA_DEADLINE must be Unix seconds", file=sys.stderr)
        return 2
    if deadline and time.time() >= deadline:
        print("ARENA_DEADLINE has passed; stopping without writing output", file=sys.stderr)
        return 2
    data = load_inputs(universe, lexicon)
    if data.lexicon is None or any(x.startswith("lexicon:") for x in data.issues):
        print("input/lexicon validation failed:", *data.issues, sep="\n- ", file=sys.stderr)
        return 2
    if any(not row.row_id for row in data.rows) or len({row.row_id for row in data.rows}) != len(data.rows):
        print("input has missing or duplicate row IDs; cannot produce unambiguous label rows", file=sys.stderr)
        return 2
    audit = evidence_audit(data)
    print("evidence audit:", json.dumps(audit, sort_keys=True))
    # The P0 runner has no claim-generation model. It accepts externally
    # produced candidates only after the official schema and local checks pass.
    if not candidates_path:
        print("cannot meet exactly 1,000 claims: no verified candidate source is available", file=sys.stderr)
        print("no output written; unsupported claims will not be fabricated", file=sys.stderr)
        return 2
    try:
        claims = read_candidates(candidates_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"cannot load claim candidates: {exc}", file=sys.stderr)
        return 2
    if len(claims) != 1000:
        print(f"candidate count is {len(claims)}, not 1,000; no output written", file=sys.stderr)
        return 2
    packaged_practice = practice_path or str(Path(__file__).resolve().parent / "data" / "practice.csv")
    v2_model = Path(__file__).resolve().parent / "ml" / "classical" / "results_m2_v2" / "model.joblib"
    v1_model = Path(__file__).resolve().parent / "ml" / "classical" / "results_m2_v1" / "model.joblib"
    default_model = str(v2_model if v2_model.is_file() else v1_model)
    packaged_model = model_path or os.environ.get("NEURON_M2_MODEL", default_model)
    try:
        predictions = predict_unlabeled(data, packaged_model, packaged_practice)
    except Exception as exc:
        print(f"M2 inference failed: {exc}", file=sys.stderr)
        return 2
    rows: list[dict[str, Any]] = []
    for row in data.rows:
        if row.label is None:
            label, confidence = predictions.get(row.row_id, ("unsure", None))
            rows.append({
                "id": row.row_id,
                "type": "",
                "text": "",
                "form": "",
                "label": label,
                "confidence": "" if confidence is None else f"{confidence:g}",
            })
    for claim in claims:
        claim_conf = claim.get("confidence")
        if claim_conf is None or claim_conf == "":
            claim_conf = calibrate_claim_confidence(claim)
        elif isinstance(claim_conf, (int, float, str)):
            try:
                c_val = float(claim_conf)
                if not 0.5 <= c_val <= 1.0:
                    claim_conf = calibrate_claim_confidence(claim)
                else:
                    claim_conf = c_val
            except ValueError:
                claim_conf = calibrate_claim_confidence(claim)

        form_val = claim.get("form", {})
        if isinstance(form_val, str):
            try:
                parsed_f = json.loads(form_val)
                serialized_form = json.dumps(parsed_f, ensure_ascii=False, separators=(",", ":"))
            except (ValueError, TypeError):
                serialized_form = form_val
        else:
            serialized_form = json.dumps(form_val, ensure_ascii=False, separators=(",", ":"))

        rows.append({
            "id": claim.get("id", ""),
            "type": claim.get("type", ""),
            "text": claim.get("text", ""),
            "form": serialized_form,
            "label": claim.get("label", "true"),
            "confidence": f"{claim_conf:g}" if isinstance(claim_conf, float) else str(claim_conf),
        })
    # Validate a temporary candidate before replacing any previously complete output.
    dest = Path(output)
    staged = dest.with_name(dest.name + ".validate.tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(staged, rows)
        problems = validate_output(staged, data, contract_dir)
        if problems:
            print("output validation failed:", *problems[:40], sep="\n- ", file=sys.stderr)
            staged.unlink(missing_ok=True)
            return 2
        if deadline and time.time() >= deadline:
            print("deadline passed before output commit", file=sys.stderr)
            staged.unlink(missing_ok=True)
            return 2
        os.replace(staged, dest)
    except OSError as exc:
        print(f"cannot publish output: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
    print(f"wrote {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=default_path("/universe/universe.csv", "data/practice.csv"))
    parser.add_argument("--lexicon", default=default_path("/universe/lexicon.json", "data/lexicon.json"))
    parser.add_argument("--output", default=default_path("/output/output.csv", "output/output.csv"))
    parser.add_argument("--contract-dir", default=str(Path(__file__).resolve().parent / "contracts"))
    parser.add_argument("--candidates-json", help="JSON array of 1,000 precomputed verified claim candidates")
    parser.add_argument("--model", default=None, help="Path to the serialized M2 model")
    parser.add_argument("--practice", default=None, help="Path to packaged practice evidence with forms")
    args = parser.parse_args()
    return run(args.universe, args.lexicon, args.output, args.contract_dir, args.candidates_json, args.model, args.practice)


if __name__ == "__main__":
    raise SystemExit(main())
