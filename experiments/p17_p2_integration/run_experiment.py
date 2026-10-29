"""Evaluate P1.7 candidate expansion with P2 graph/BM25 evidence and LightGBM."""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import platform
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import joblib
import numpy as np
import psutil
from scipy.sparse import csr_matrix, hstack
from threadpoolctl import threadpool_limits

from foundation import AtomicFact, EvidenceRecord, InputData, TypedValue, load_inputs
from core.graph.models import EvidenceState
from core.graph.evidence_resolver import EvidenceResolver
from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
from core.retrieval.hybrid import HybridEvidenceRetriever
from experiments.p17_recall.candidate_factory import Candidate, CandidateFactory, candidate_matches
from ml.classical.benchmark import make_feature_builder, transform_features
from ml.classical.train_m2 import LABELS, metrics as classification_metrics, new_estimator, probabilities
from r6 import (align_candidates, build_evidence_runtime, candidates_to_row_features,
                deterministic_name_version_boolean_spans, evidence_attribute_hints,
                evidence_guided_ranking, expand_candidates_with_evidence, p2_feature_values)

SEED = 42
VARIANTS = ("E0", "E1", "E2", "E3", "E4", "E5", "E6",
            "E2_p17_r5_ranked", "E5_evidence_ranked", "E6_evidence_ranked")
CLASSIFIER_VARIANTS = ("E2", "E5", "E6")
PROCESS = psutil.Process(os.getpid())


def read_csv_map(path: Path, key: str, value: str | None = None) -> dict[str, str | int]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if value is None:
        return {row[key]: row for row in rows}
    return {row[key]: row[value] for row in rows}


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def runtime_row(row: EvidenceRecord) -> dict[str, str]:
    return {"id": row.row_id, "text": row.text,
            "date": row.date.isoformat() if row.date else ""}


def gold_facts(row: EvidenceRecord) -> tuple:
    return tuple(row.facts)


def hit_relevant_ids(row: EvidenceRecord, graph, allowed_ids: set[str]) -> set[str]:
    relevant: set[str] = set()
    permitted = {EvidenceState.VERIFIED_SUPPORT, EvidenceState.VERIFIED_REFUTATION,
                 EvidenceState.CONFLICTING}
    resolver = EvidenceResolver(graph)
    for fact in row.facts:
        key = (graph.entity_key(fact.subject), fact.attribute)
        for record in graph.facts_by_subject_attribute.get(key, ()):
            if record.source_row_id not in allowed_ids or record.evidence_status not in permitted:
                continue
            if record.fact.value.kind != fact.value.kind:
                continue
            if resolver._date_applies(record, row.date):
                relevant.add(record.source_row_id)
    return relevant


def retrieval_score(row: EvidenceRecord, results, graph, allowed_ids: set[str], method: str) -> dict[str, Any]:
    relevant = hit_relevant_ids(row, graph, allowed_ids)
    ids = [item.evidence_id for item in results]
    row_records: dict[str, list[Any]] = defaultdict(list)
    target_pairs = {(graph.entity_key(f.subject), f.attribute) for f in row.facts}
    for key, records in graph.facts_by_subject_attribute.items():
        if key in target_pairs:
            for record in records:
                row_records[record.source_row_id].append(record)
    temporal = sum(any(EvidenceResolver._date_applies(record, row.date) for record in row_records.get(eid, ()))
                   for eid in ids)
    provenance = sum(eid in allowed_ids and eid in graph.evidence_by_id
                     and bool(graph.evidence_by_id[eid].provenance)
                     and item.provenance == graph.evidence_by_id[eid].provenance
                     for eid, item in zip(ids, results))
    result = {"partition": "", "retriever": method, "row_id": row.row_id,
              "queries": 1, "judged": bool(relevant), "relevant_reference_count": len(relevant),
              "evidence_coverage": bool(ids), "self_evidence_excluded": row.row_id not in ids,
              "temporal_compatibility": temporal / len(ids) if ids else 0.0,
              "provenance_correctness": provenance / len(ids) if ids else 0.0}
    for k in (5, 10):
        found = set(ids[:k]) & relevant
        result[f"recall_at_{k}"] = len(found) / len(relevant) if relevant else ""
    first = next((i for i, eid in enumerate(ids[:10], 1) if eid in relevant), None)
    result["mrr_at_10"] = (1 / first) if first else (0.0 if relevant else "")
    return result


def _candidate_matches_gold(candidates: Sequence[Candidate], gold: Sequence, lexicon,
                            limit: int | None = None) -> set[int]:
    remaining = set(range(len(gold)))
    matched: set[int] = set()
    for candidate in candidates[:limit]:
        index = next((i for i in sorted(remaining)
                      if candidate_matches(candidate.fact, gold[i], lexicon)), None)
        if index is not None:
            matched.add(index)
            remaining.remove(index)
    return matched


def parse_metrics(rows: Sequence[EvidenceRecord], results: Mapping[str, Mapping[str, Any]],
                  lexicon) -> list[dict[str, Any]]:
    output = []
    for name in VARIANTS:
        all_gold = recovered = fp = exact = 0
        subject = attribute = value = 0
        kind_counts: dict[str, Counter] = defaultdict(Counter)
        cand_total = 0; per_row_counts = []; newly_vs_e2 = 0
        top_hits = Counter()
        for row in rows:
            candidates, stats = results[row.row_id][name]
            gold = gold_facts(row)
            matches = _candidate_matches_gold(candidates, gold, lexicon)
            baseline_matches = (_candidate_matches_gold(results[row.row_id]["E2"][0], gold, lexicon)
                                if name != "E2" else set())
            newly_vs_e2 += len(matches - baseline_matches)
            all_gold += len(gold); recovered += len(matches)
            fp += len(candidates) - len(matches); cand_total += len(candidates)
            per_row_counts.append(len(candidates))
            exact += int(len(matches) == len(gold) and len(candidates) == len(gold))
            subjects = set(stats.get("subject_candidates", ()))
            attrs = {s: set(items) for s, items in stats.get("attribute_candidates", {}).items()}
            raw_values = []
            for item in stats.get("value_candidates", ()):
                raw = item.get("value", {})
                try:
                    typed, _issue = TypedValue.parse(raw)
                    if typed is not None:
                        raw_values.append(typed)
                except (TypeError, ValueError):
                    pass
            for fact in gold:
                kind_counts[fact.value.kind]["gold"] += 1
                subject += int(fact.subject in subjects)
                attribute += int(fact.attribute in attrs.get(fact.subject, set()))
                value_found = any(candidate_matches(AtomicFact(fact.subject, fact.attribute, item), fact, lexicon)
                                  for item in raw_values)
                value += int(value_found)
                kind_counts[fact.value.kind]["subject"] += int(fact.subject in subjects)
                kind_counts[fact.value.kind]["attribute"] += int(fact.attribute in attrs.get(fact.subject, set()))
                kind_counts[fact.value.kind]["value"] += int(value_found)
            for k in (1, 3, 5, 10, 20):
                top_hits[k] += len(_candidate_matches_gold(candidates, gold, lexicon, k))
        output.append({"partition": "", "configuration": name, "rows": len(rows),
                       "gold_facts": all_gold, "gold_recovered": recovered,
                       "oracle_triplet_recall": recovered / all_gold if all_gold else 0.0,
                       "subject_availability": subject / all_gold if all_gold else 0.0,
                       "attribute_availability": attribute / all_gold if all_gold else 0.0,
                       "typed_value_availability": value / all_gold if all_gold else 0.0,
                       "candidate_count": cand_total,
                       "mean_candidates_per_claim": cand_total / max(1, len(rows)),
                       "median_candidates_per_claim": float(np.median(per_row_counts)) if per_row_counts else 0.0,
                       "p95_candidates_per_claim": float(np.quantile(per_row_counts, 0.95)) if per_row_counts else 0.0,
                       "newly_recovered_gold_vs_E2": newly_vs_e2,
                       "false_positive_candidates": fp,
                       "false_positive_growth_vs_E2": "",
                       "full_row_accuracy": exact / max(1, len(rows)),
                       **{f"oracle_recall_at_{k}": top_hits[k] / all_gold if all_gold else 0.0
                          for k in (1, 3, 5, 10, 20)},
                       "per_value_kind": json.dumps({kind: {**dict(counts),
                           "recall": counts.get("gold", 0) and counts.get("gold", 0) and
                           (counts.get("gold", 0) and counts.get("value", 0) / counts["gold"])}
                           for kind, counts in sorted(kind_counts.items())}, ensure_ascii=False)})
    e2 = next(row for row in output if row["configuration"] == "E2")
    for row in output:
        row["false_positive_growth_vs_E2"] = row["false_positive_candidates"] - e2["false_positive_candidates"]
    return output


def new_facts_vs(candidates: Sequence[Candidate], baseline: Sequence[Candidate], gold: Sequence,
                 lexicon) -> int:
    base_matches = _candidate_matches_gold(baseline, gold, lexicon)
    current_matches = _candidate_matches_gold(candidates, gold, lexicon)
    return len(current_matches - base_matches)


def collect_one(row: EvidenceRecord, factory: CandidateFactory, retriever: HybridEvidenceRetriever,
                feature_extractor: RetrievalFeatureExtractor, graph, baseline, allowed_ids: set[str],
                partition: str) -> tuple[dict[str, tuple[list[Candidate], dict]], dict[str, Any], dict[str, float], dict[str, float], dict[str, Any]]:
    text = row.text
    query_date = row.date
    times: dict[str, float] = {}
    t0 = time.perf_counter()
    bm25 = retriever.search(text, query_date, top_k=20, exclude_evidence_ids=(row.row_id,), mode="bm25")
    hybrid = retriever.search(text, query_date, top_k=20, exclude_evidence_ids=(row.row_id,), mode="hybrid")
    times["p2_retrieval"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    base_result = baseline.extract(text, row.row_id)
    r0 = [Candidate(row.row_id, item.fact,
                    (item.subject_span_start, item.subject_span_end) if item.subject_span_start is not None else None,
                    (item.span_start, item.span_end) if item.span_start is not None else None,
                    0, {item.method}, {"resolver": item.confidence,
                    "exact_entity": 1.0 if item.subject_span_start is not None else 0.0,
                    "value_compat": 1.0}) for item in base_result.candidates]
    s0 = {"generated_before_caps": len(r0), "emitted": len(r0),
          "subject_candidates": sorted({item.fact.subject for item in r0}),
          "value_candidates": [{"value": {"kind": c.fact.value.kind, "value": c.fact.value.value,
                                             "unit": c.fact.value.unit, "currency": c.fact.value.currency,
                                             "per": c.fact.value.per, "op": c.fact.value.op},
                                 "start": c.value_span[0], "end": c.value_span[1]}
                                for c in r0 if c.value_span],
          "attribute_candidates": {s: sorted({c.fact.attribute for c in r0 if c.fact.subject == s})
                                    for s in {c.fact.subject for c in r0}}}
    r1_add, s1_add = factory.generate(row.row_id, text, config="R1", collect_only=True)
    r1 = merge_candidates(r0, r1_add)
    s1 = merge_stats(s0, s1_add)
    r4_add, s4_add = factory.generate(row.row_id, text, config="R4", k=5, collect_only=True)
    r4 = merge_candidates(r0, r4_add)
    s4 = merge_stats(s0, s4_add)
    extra_spans = deterministic_name_version_boolean_spans(text, factory.lexicon, factory.attribute_kinds)
    r6_add, s6_add = factory.generate(row.row_id, text, config="R4", k=5, collect_only=True,
                                      value_span_hints=extra_spans)
    r6_base = merge_candidates(r0, r6_add)
    s6 = merge_stats(s0, s6_add)
    times["p17_candidate_extraction"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    hints, sources = evidence_attribute_hints(hybrid, graph, allowed_ids, row.row_id,
                                              query_date, s4.get("subject_candidates", ()))
    e5 = expand_candidates_with_evidence(r4, factory, hints, sources)
    e6 = expand_candidates_with_evidence(r6_base, factory, hints, sources)
    for candidate in [*e5, *e6]:
        if "p2_evidence_attribute_link" in candidate.methods:
            candidate.evidence_state = "UNVERIFIED_CANDIDATE"
    times["r6_evidence_guided_expansion"] = time.perf_counter() - t0

    e5_stats = expanded_stats(s4, e5)
    e6_stats = expanded_stats(s6, e6)
    variants = {
        "E0": (r0, s0), "E1": (r1, s1), "E2": (r4, s4),
        "E3": (r4, s4), "E4": (r4, s4), "E5": (e5, e5_stats), "E6": (e6, e6_stats),
        "E2_p17_r5_ranked": (sorted(r4, key=lambda c: (-c.rank_score, c.row_id, c.key())), s4),
    }
    variants["E5_evidence_ranked"] = (evidence_guided_ranking(e5), variants["E5"][1])
    variants["E6_evidence_ranked"] = (evidence_guided_ranking(e6), variants["E6"][1])
    t0 = time.perf_counter()
    temporal = {name: align_candidates(variants[name][0], graph, row.row_id, query_date)
                for name in ("E2", "E5", "E6")}
    times["temporal_alignment"] = time.perf_counter() - t0
    p2_features = p2_feature_values(feature_extractor, hybrid, text, query_date)
    feature_rows = {}
    for name in CLASSIFIER_VARIANTS:
        feature_rows[name] = {**p2_features,
                              **candidates_to_row_features(*variants[name], temporal[name])}
    retrieval_rows = {
        "P2_BM25": retrieval_score(row, bm25, graph, allowed_ids, "P2_BM25"),
        "P2_Hybrid": retrieval_score(row, hybrid, graph, allowed_ids, "P2_Hybrid"),
    }
    for record in retrieval_rows.values():
        record["partition"] = partition
    return variants, feature_rows, p2_features, times, retrieval_rows


def expanded_stats(base: Mapping[str, Any], candidates: Sequence[Candidate]) -> dict[str, Any]:
    result = dict(base)
    subjects = set(result.get("subject_candidates", ()))
    values = list(result.get("value_candidates", ()))
    attrs: dict[str, set[str]] = defaultdict(set)
    for subject, names in result.get("attribute_candidates", {}).items():
        attrs[subject].update(names)
    for candidate in candidates:
        subjects.add(candidate.fact.subject)
        attrs[candidate.fact.subject].add(candidate.fact.attribute)
        if candidate.value_span:
            value = candidate.fact.value
            values.append({"value": {"kind": value.kind, "value": value.value,
                                     "unit": value.unit, "currency": value.currency,
                                     "per": value.per, "op": value.op},
                           "start": candidate.value_span[0], "end": candidate.value_span[1]})
    unique_values = {(x.get("start"), x.get("end"), json.dumps(x.get("value"), sort_keys=True)): x for x in values}
    result["subject_candidates"] = sorted(subjects)
    result["attribute_candidates"] = {subject: sorted(names) for subject, names in sorted(attrs.items())}
    result["value_candidates"] = list(unique_values.values())
    result["generated_before_caps"] = len(candidates)
    result["emitted"] = len(candidates)
    return result


def merge_candidates(parent: Sequence[Candidate], additions: Sequence[Candidate]) -> list[Candidate]:
    merged: dict[tuple, Candidate] = {}
    for source in (*parent, *additions):
        candidate = Candidate(source.row_id, source.fact, source.entity_span, source.value_span,
                              source.clause_id, set(source.methods), dict(source.scores),
                              set(source.matched_example_ids), source.ambiguous_entity, source.evidence_state)
        prior = merged.get(candidate.key())
        if prior is None:
            merged[candidate.key()] = candidate
            continue
        prior.methods.update(candidate.methods)
        prior.matched_example_ids.update(candidate.matched_example_ids)
        for key, value in candidate.scores.items():
            prior.scores[key] = max(prior.scores.get(key, 0.0), value)
        prior.ambiguous_entity = prior.ambiguous_entity or candidate.ambiguous_entity
    return list(merged.values())


def merge_stats(parent: Mapping[str, Any], child: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(parent)
    result["subject_candidates"] = sorted(set(parent.get("subject_candidates", ())) |
                                          set(child.get("subject_candidates", ())))
    values = {(item.get("start"), item.get("end"), json.dumps(item.get("value"), sort_keys=True)): item
              for item in [*parent.get("value_candidates", ()), *child.get("value_candidates", ())]}
    result["value_candidates"] = list(values.values())
    attrs: dict[str, set[str]] = defaultdict(set)
    for source in (parent, child):
        for subject, names in source.get("attribute_candidates", {}).items():
            attrs[subject].update(names)
    result["attribute_candidates"] = {subject: sorted(names) for subject, names in sorted(attrs.items())}
    result["generated_before_caps"] = max(int(parent.get("generated_before_caps", 0) or 0),
                                           int(child.get("generated_before_caps", 0) or 0))
    result["emitted"] = result["generated_before_caps"]
    result["deadline_exceeded"] = bool(child.get("deadline_exceeded", False))
    return result


def evaluate_rows(data: InputData, allowed_ids: set[str], targets: Sequence[EvidenceRecord],
                  split_name: str) -> dict[str, Any]:
    start = time.perf_counter()
    allowed_rows = [row for row in data.rows if row.row_id in allowed_ids]
    fit_start = time.perf_counter()
    factory = CandidateFactory.fit(data, allowed_ids)
    resolver_fit_seconds = time.perf_counter() - fit_start
    graph, retriever, graph_timings = build_evidence_runtime(allowed_rows, data.lexicon)
    feature_extractor = RetrievalFeatureExtractor(retriever)
    baseline = factory.baseline()
    per_row: dict[str, Any] = {}
    feature_rows: dict[str, dict[str, float]] = {}
    retrieval_rows: list[dict[str, Any]] = []
    timings: Counter = Counter()
    errors: list[dict[str, Any]] = []
    for i, row in enumerate(targets, start=1):
        variants, row_features, _p2, elapsed, retrieval = collect_one(
            row, factory, retriever, feature_extractor, graph, baseline, allowed_ids, split_name)
        per_row[row.row_id] = variants
        feature_rows[row.row_id] = row_features
        for key, value in elapsed.items():
            timings[key] += value
        retrieval_rows.extend(retrieval.values())
        for name in VARIANTS:
            candidates, _stats = variants[name]
            matched = _candidate_matches_gold(candidates, row.facts, data.lexicon)
            if len(matched) != len(row.facts):
                errors.append({"partition": split_name, "row_id": row.row_id,
                               "configuration": name, "text": row.text,
                               "date": row.date.isoformat() if row.date else "",
                               "gold_form_post_generation": json.dumps([
                                   {"subject": f.subject, "attribute": f.attribute,
                                    "value": f.value.to_dict() if hasattr(f.value, "to_dict") else str(f.value)}
                                   for f in row.facts], ensure_ascii=False),
                               "candidate_count": len(candidates),
                               "recovered_gold": len(matched),
                               "unrecovered_facts": json.dumps([
                                   {"subject": row.facts[j].subject, "attribute": row.facts[j].attribute,
                                    "value_kind": row.facts[j].value.kind,
                                    "value": row.facts[j].value.value}
                                   for j in range(len(row.facts)) if j not in matched], ensure_ascii=False),
                               "candidate_provenance": json.dumps([
                                   c.as_dict() for c in candidates[:20]], ensure_ascii=False)})
        if i % 100 == 0:
            write_json(OUT / "progress.json", {"phase": split_name, "completed_rows": i,
                                                 "planned_rows": len(targets), "status": "running",
                                                 "elapsed_seconds": time.perf_counter()-start,
                                                 "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    metrics_by_variant = parse_metrics(targets, per_row, data.lexicon)
    for row in metrics_by_variant:
        row["partition"] = split_name
    for record in retrieval_rows:
        record["partition"] = split_name
    return {"metrics": metrics_by_variant, "features": feature_rows,
            "per_row": per_row, "retrieval": retrieval_rows, "errors": errors,
            "timings": dict(timings), "candidate_resolver_fit_seconds": resolver_fit_seconds,
            **graph_timings,
            "total_seconds": time.perf_counter()-start,
            "peak_rss_mb": PROCESS.memory_info().rss / (1024 ** 2),
            "factory": factory, "graph": graph, "retriever": retriever}


def feature_matrix(row_features: Mapping[str, Mapping[str, float]], ids: Sequence[str]) -> tuple[csr_matrix, list[str]]:
    p2_names = list(FEATURE_NAMES)
    candidate_names = sorted({name for row in row_features.values() for name in row if name not in p2_names})
    names = p2_names + candidate_names
    dense = np.asarray([[float(row_features[row_id].get(name, 0.0)) for name in names]
                        for row_id in ids], dtype=np.float32)
    return csr_matrix(dense), names


def classification_rows(train_rows: Sequence[EvidenceRecord], val_rows: Sequence[EvidenceRecord],
                         train_feature_rows: Mapping[str, Mapping[str, Mapping[str, float]]],
                         val_feature_rows: Mapping[str, Mapping[str, Mapping[str, float]]],
                         lexicon_json: dict[str, Any], legacy_config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], Any, dict[str, Any]]:
    train_runtime = [runtime_row(row) for row in train_rows]
    val_runtime = [runtime_row(row) for row in val_rows]
    builder = make_feature_builder(train_runtime, lexicon_json)
    base_train, _ = transform_features(train_runtime, builder)
    base_val, _ = transform_features(val_runtime, builder)
    y_train = np.asarray([row.label.lower() for row in train_rows])
    y_val = np.asarray([row.label.lower() for row in val_rows])
    train_ids = [row.row_id for row in train_rows]; val_ids = [row.row_id for row in val_rows]
    rows_out: list[dict[str, Any]] = []
    models = {}
    feature_names = {}
    for name in CLASSIFIER_VARIANTS:
        x_train_meta, names = feature_matrix(train_feature_rows[name], train_ids)
        x_val_meta, _ = feature_matrix(val_feature_rows[name], val_ids)
        x_train = hstack((base_train, x_train_meta), format="csr", dtype=np.float32)
        x_val = hstack((base_val, x_val_meta), format="csr", dtype=np.float32)
        model = new_estimator(legacy_config, y_train)
        model.fit(x_train, y_train)
        probs = probabilities(model, x_val)
        score = classification_metrics(y_val, probs)
        rows_out.append({"partition": "validation", "configuration": name,
                         "feature_count": x_train.shape[1], "training_rows": len(y_train), **score})
        models[name] = model
        feature_names[name] = names
    return rows_out, builder, base_train, {"models": models, "feature_names": feature_names,
                                           "y_train": y_train, "x_base_val": base_val}


def model_selection_key(row: Mapping[str, Any]) -> tuple:
    classes = row.get("classes", {})
    return (row.get("macro_f1", 0.0), row.get("balanced_accuracy", 0.0),
            classes.get("false", {}).get("recall", 0.0),
            classes.get("unsure", {}).get("recall", 0.0))


def _resource_metrics() -> dict[str, Any]:
    try:
        return {"peak_rss_mb": round(PROCESS.memory_info().rss / (1024 ** 2), 2),
                "cpu_affinity": PROCESS.cpu_affinity()}
    except Exception:
        return {"peak_rss_mb": round(PROCESS.memory_info().rss / (1024 ** 2), 2),
                "cpu_affinity": "unavailable"}


def run(*, runtime_rows: int = 18000) -> dict[str, Any]:
    started = time.perf_counter()
    input_data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
    rows_by_id = {row.row_id: row for row in input_data.rows}
    split_map = read_csv_map(ROOT / "ml" / "shared" / "splits.csv", "id", "split")
    fold_map = {key: int(value) for key, value in read_csv_map(ROOT / "ml" / "shared" / "cv10_folds.csv", "id", "fold").items()}
    if set(split_map) != set(rows_by_id) or set(fold_map) != {rid for rid, split in split_map.items() if split == "train"}:
        raise ValueError("P2 shared manifests do not match current P1.7 practice IDs")
    train_rows = [row for row in input_data.rows if split_map[row.row_id] == "train"]
    val_rows = [row for row in input_data.rows if split_map[row.row_id] == "validation"]
    test_rows = [row for row in input_data.rows if split_map[row.row_id] == "test"]
    lexicon_json = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8"))
    legacy_report_path = ROOT / "ml" / "classical" / "results_m2_v1" / "report.json"
    legacy_report = json.loads(legacy_report_path.read_text(encoding="utf-8"))
    legacy_config = legacy_report["selected"]["m2"]["configuration"]

    write_json(OUT / "progress.json", {"phase": "grouped_cv", "status": "running",
                                        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                        "planned_folds": 10, "completed_folds": 0})
    cv_variant_results: dict[str, dict[str, Any]] = {name: {} for name in VARIANTS}
    cv_feature_rows: dict[str, dict[str, dict[str, float]]] = {name: {} for name in CLASSIFIER_VARIANTS}
    cv_retrieval: list[dict[str, Any]] = []
    cv_errors: list[dict[str, Any]] = []
    cv_timings: list[dict[str, Any]] = []
    for fold in sorted(set(fold_map.values())):
        allowed_ids = {rid for rid in fold_map if fold_map[rid] != fold}
        held_rows = [row for row in train_rows if fold_map[row.row_id] == fold]
        fold_start = time.perf_counter()
        evaluated = evaluate_rows(input_data, allowed_ids, held_rows, f"cv_fold_{fold}")
        for row in held_rows:
            variants = evaluated["per_row"][row.row_id]
            for name in VARIANTS:
                cv_variant_results[name][row.row_id] = variants[name]
            for name in CLASSIFIER_VARIANTS:
                cv_feature_rows[name][row.row_id] = evaluated["features"][row.row_id][name]
        cv_retrieval.extend(evaluated["retrieval"])
        cv_errors.extend(evaluated["errors"])
        cv_timings.append({"phase": "grouped_cv", "fold": fold,
                           "rows": len(held_rows), "elapsed_seconds": time.perf_counter()-fold_start,
                           "candidate_resolver_fit_seconds": evaluated["candidate_resolver_fit_seconds"],
                           "graph_construction_seconds": evaluated["graph_construction_seconds"],
                           "p2_bm25_index_construction_seconds": evaluated["p2_bm25_index_construction_seconds"],
                           **evaluated["timings"], "peak_rss_mb": evaluated["peak_rss_mb"]})
        write_json(OUT / "progress.json", {"phase": "grouped_cv", "status": "running",
                                             "started_at": started, "planned_folds": 10,
                                             "completed_folds": fold + 1,
                                             "last_fold_seconds": time.perf_counter()-fold_start,
                                             "elapsed_seconds": time.perf_counter()-started,
                                             "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    cv_by_row = {
        row.row_id: {name: cv_variant_results[name][row.row_id] for name in VARIANTS}
        for row in train_rows
    }
    cv_metrics = parse_metrics(train_rows, cv_by_row, input_data.lexicon)
    for row in cv_metrics:
        row["partition"] = "grouped_oof_cv"
    cv_retrieval_aggregate = aggregate_retrieval(cv_retrieval)

    validation = evaluate_rows(input_data, {row.row_id for row in train_rows}, val_rows, "validation")
    validation_metrics = validation["metrics"]
    validation_features_by_variant = {
        name: {row.row_id: validation["features"][row.row_id][name] for row in val_rows}
        for name in CLASSIFIER_VARIANTS
    }
    classification_validation, feature_builder, _base_train, trained = classification_rows(
        train_rows, val_rows, cv_feature_rows, validation_features_by_variant,
        lexicon_json, legacy_config)
    for row in validation_metrics:
        row["partition"] = "validation"
    selected_parse = max((row for row in validation_metrics if row["configuration"] in ("E2", "E5", "E6")),
                         key=lambda row: (row["oracle_triplet_recall"], row["oracle_recall_at_5"],
                                          row["subject_availability"], row["attribute_availability"]))["configuration"]
    selected_classifier = max(classification_validation, key=model_selection_key)["configuration"]
    selected_model = trained["models"][selected_classifier]

    # Test references are added only after validation-based selection. The test
    # labels/forms are used solely for the final diagnostic score.
    final_fit_rows = [*train_rows, *val_rows]
    test_eval = evaluate_rows(input_data, {row.row_id for row in final_fit_rows}, test_rows, "test_post_selection")
    for row in test_eval["metrics"]:
        row["partition"] = "test_post_selection"
    final_runtime = [runtime_row(row) for row in final_fit_rows]
    final_labels = np.asarray([row.label.lower() for row in final_fit_rows])
    train_oof_meta, selected_feature_names = feature_matrix(cv_feature_rows[selected_classifier],
                                                              [row.row_id for row in train_rows])
    val_meta, _ = feature_matrix(validation_features_by_variant[selected_classifier],
                                 [row.row_id for row in val_rows])
    final_base_train, _ = transform_features(final_runtime, feature_builder)
    final_meta = __import__("scipy").sparse.vstack((train_oof_meta, val_meta), format="csr")
    final_x = hstack((final_base_train, final_meta), format="csr", dtype=np.float32)
    final_model = new_estimator(legacy_config, final_labels).fit(final_x, final_labels)
    test_runtime = [runtime_row(row) for row in test_rows]
    test_base, _ = transform_features(test_runtime, feature_builder)
    test_features_by_variant = {
        row.row_id: test_eval["features"][row.row_id][selected_classifier]
        for row in test_rows
    }
    test_meta, _ = feature_matrix(test_features_by_variant, [row.row_id for row in test_rows])
    test_x = hstack((test_base, test_meta), format="csr", dtype=np.float32)
    test_y = np.asarray([row.label.lower() for row in test_rows])
    test_probs = probabilities(final_model, test_x)
    test_classifier_metrics = classification_metrics(test_y, test_probs)
    model_path = OUT / "models" / f"lightgbm_{selected_classifier.lower()}.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": final_model, "feature_builder": feature_builder,
                 "label_order": tuple(LABELS), "candidate_configuration": selected_parse,
                 "candidate_feature_names": selected_feature_names,
                 "p2_retrieval_feature_names": tuple(FEATURE_NAMES),
                 "legacy_m2_configuration": legacy_config,
                 "feature_count": int(final_x.shape[1])}, model_path, compress=3)

    parse_ablation = [*cv_metrics, *validation_metrics, *test_eval["metrics"]]
    classification_ablation = [{"partition": "validation", "configuration": row["configuration"],
                                 "classification": json.dumps(row, ensure_ascii=False)}
                                for row in classification_validation]
    write_csv(OUT / "ablation.csv", [*parse_ablation, *classification_ablation])
    write_csv(OUT / "retrieval_metrics.csv", cv_retrieval_aggregate +
              aggregate_retrieval(validation["retrieval"]) + aggregate_retrieval(test_eval["retrieval"]))
    write_csv(OUT / "error_analysis.csv", [*validation["errors"][:400], *test_eval["errors"][:200]])
    write_csv(OUT / "timings.csv", cv_timings + [
        {"phase": "validation", "rows": len(val_rows), "elapsed_seconds": validation["total_seconds"],
         "candidate_resolver_fit_seconds": validation["candidate_resolver_fit_seconds"],
         "graph_construction_seconds": validation["graph_construction_seconds"],
         "p2_bm25_index_construction_seconds": validation["p2_bm25_index_construction_seconds"], **validation["timings"]},
        {"phase": "test_post_selection", "rows": len(test_rows), "elapsed_seconds": test_eval["total_seconds"],
         "candidate_resolver_fit_seconds": test_eval["candidate_resolver_fit_seconds"],
         "graph_construction_seconds": test_eval["graph_construction_seconds"],
         "p2_bm25_index_construction_seconds": test_eval["p2_bm25_index_construction_seconds"], **test_eval["timings"]}])
    legacy_validation = legacy_report["selected"]["m2"]["validation"]
    legacy_test = legacy_report.get("outer_test", {}).get("m2", {})
    report = {"status": "completed", "branch_base": "origin/feat/p1-7-recall-candidate-expansion",
              "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "splits": {"train": len(train_rows), "validation": len(val_rows), "test": len(test_rows),
                         "grouped_cv_folds": len(set(fold_map.values()))},
              "protocol": {"seed": SEED, "p2_split_manifest": "ml/shared/splits.csv",
                           "p2_cv_manifest": "ml/shared/cv10_folds.csv",
                           "training_forms_used_only_inside_each_allowed_training_partition": True,
                           "validation_test_forms_are_features": False,
                           "query_self_evidence_excluded": True,
                           "p1_attribute_resolver_json_used": False,
                           "candidate_evidence_state": "UNVERIFIED_CANDIDATE",
                           "retrieved_values_copied_to_claim_candidates": False,
                           "test_used_for_selection": False,
                           "shared_subject_attribute_history_cross_split": 0,
                           "near_duplicate_audit": "reported from P1.7 reproduction artifacts"},
              "selection": {"parse_configuration": selected_parse,
                            "parse_criterion": "validation oracle triplet recall, then Recall@5, subject/attribute availability",
                            "classifier_configuration": selected_classifier,
                            "classifier_criterion": "validation Macro-F1, then balanced accuracy, FALSE recall, UNSURE recall",
                            "lightgbm_hyperparameters": legacy_config},
              "p1_7_reproduction": "p17_reproduction/metrics.json",
              "cv_parse_metrics": cv_metrics,
              "validation_parse_metrics": validation_metrics,
              "cv_retrieval_metrics": cv_retrieval_aggregate,
              "validation_retrieval_metrics": aggregate_retrieval(validation["retrieval"]),
              "classification": {"legacy_p2_m2_validation": legacy_validation,
                                 "legacy_p2_m2_test_post_selection": legacy_test,
                                 "integrated_validation": classification_validation,
                                 "integrated_test_post_selection": test_classifier_metrics,
                                 "integrated_test_confusion_matrix": test_classifier_metrics["confusion_matrix"]},
              "test_parse_metrics_post_selection": test_eval["metrics"],
              "model_artifact": str(model_path.relative_to(OUT)),
              "model_bytes": model_path.stat().st_size,
              "elapsed_seconds_before_runtime_benchmark": time.perf_counter()-started,
              "runtime_benchmark_pending": True,
              "caveats": ["The legacy M2 result is read from the preserved P2 branch artifact and is labeled separately.",
                          "Test metrics are diagnostics after validation-only selection.",
                          "Runtime of the 1,000 TRUE-claim generator is not part of this model-only benchmark yet."]}
    write_json(OUT / "metrics.json", report)

    runtime = benchmark_runtime(input_data, final_fit_rows, test_rows, feature_builder,
                                final_model, selected_classifier, selected_parse,
                                selected_feature_names, runtime_rows)
    write_json(OUT / "runtime.json", runtime)
    report["runtime"] = runtime
    report["runtime_benchmark_pending"] = False
    write_json(OUT / "metrics.json", report)
    write_json(OUT / "progress.json", {"phase": "complete", "status": "complete",
                                        "elapsed_seconds": time.perf_counter()-started,
                                        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                        "selected_parse": selected_parse,
                                        "selected_classifier": selected_classifier})
    return report


def aggregate_retrieval(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["retriever"])].append(row)
    output = []
    for name, group in sorted(grouped.items()):
        judged = [row for row in group if row.get("judged")]
        item = {"partition": group[0].get("partition", ""), "retriever": name,
                "queries": len(group), "judged_queries": len(judged),
                "evidence_coverage": sum(bool(row["evidence_coverage"]) for row in group) / max(1, len(group)),
                "self_evidence_excluded": all(bool(row["self_evidence_excluded"]) for row in group),
                "temporal_compatibility": float(np.mean([row["temporal_compatibility"] for row in group])) if group else 0.0,
                "provenance_correctness": float(np.mean([row["provenance_correctness"] for row in group])) if group else 0.0}
        for metric in ("recall_at_5", "recall_at_10", "mrr_at_10"):
            values = [float(row[metric]) for row in judged if row.get(metric) != ""]
            item[metric] = float(np.mean(values)) if values else None
        output.append(item)
    return output


def benchmark_runtime(data: InputData, allowed_rows: Sequence[EvidenceRecord], seed_rows: Sequence[EvidenceRecord],
                      feature_builder: dict[str, Any], estimator: Any, classifier_variant: str,
                      candidate_config: str, candidate_feature_names: Sequence[str], target_rows: int) -> dict[str, Any]:
    """Full synthetic label-free inference replay with per-stage measurements."""
    if target_rows <= 0:
        return {"status": "skipped", "reason": "target row count is zero"}
    affinity = "unavailable"
    try:
        PROCESS.cpu_affinity([0, 1]); affinity = PROCESS.cpu_affinity()
    except Exception as exc:
        affinity = f"unavailable: {type(exc).__name__}: {exc}"
    allowed_ids = {row.row_id for row in allowed_rows}
    p1_start = time.perf_counter(); factory = CandidateFactory.fit(data, allowed_ids)
    p1_fit = time.perf_counter() - p1_start
    graph, retriever, retrieval_build_times = build_evidence_runtime(allowed_rows, data.lexicon)
    graph_seconds = retrieval_build_times["graph_construction_seconds"]
    bm25_index_seconds = retrieval_build_times["p2_bm25_index_construction_seconds"]
    feature_extractor = RetrievalFeatureExtractor(retriever)
    seed = list(seed_rows) or list(allowed_rows)
    raw_rows = []
    for index in range(target_rows):
        source = seed[index % len(seed)]
        raw_rows.append({"id": f"runtime-{index:05d}", "text": source.text,
                         "date": source.date.isoformat() if source.date else ""})
    # Strip all labels/forms by construction.
    transform_start = time.perf_counter()
    base_matrix, _ = transform_features(raw_rows, feature_builder)
    base_transform = time.perf_counter() - transform_start
    candidate_seconds = retrieval_seconds = expansion_seconds = alignment_seconds = feature_seconds = 0.0
    meta_rows: dict[str, dict[str, float]] = {}
    output_predictions = []
    by_id = {row.row_id: row for row in data.rows}
    for i, runtime in enumerate(raw_rows):
        query_date, _ = __import__("foundation").normalize_date(runtime["date"])
        t0 = time.perf_counter()
        spans = (deterministic_name_version_boolean_spans(runtime["text"], data.lexicon, factory.attribute_kinds)
                 if classifier_variant == "E6" else ())
        base_candidates, stats = factory.generate(runtime["id"], runtime["text"], config="R4", k=5,
                                                  collect_only=True, value_span_hints=spans)
        candidate_seconds += time.perf_counter() - t0
        t0 = time.perf_counter()
        hits = retriever.search(runtime["text"], query_date, top_k=20,
                                exclude_evidence_ids=(runtime["id"],), mode="hybrid")
        retrieval_seconds += time.perf_counter() - t0
        t0 = time.perf_counter()
        if classifier_variant in {"E5", "E6"}:
            hints, sources = evidence_attribute_hints(hits, graph, allowed_ids, runtime["id"], query_date,
                                                      stats.get("subject_candidates", ()))
            candidates = expand_candidates_with_evidence(base_candidates, factory, hints, sources)
        else:
            candidates = list(base_candidates)
        if classifier_variant in {"E5", "E6"}:
            candidates = evidence_guided_ranking(candidates)
        expansion_seconds += time.perf_counter() - t0
        t0 = time.perf_counter()
        alignment = align_candidates(candidates, graph, runtime["id"], query_date)
        alignment_seconds += time.perf_counter() - t0
        t0 = time.perf_counter()
        p2 = p2_feature_values(feature_extractor, hits, runtime["text"], query_date)
        cand = candidates_to_row_features(candidates, stats, alignment)
        meta_rows[runtime["id"]] = {**p2, **cand}
        feature_seconds += time.perf_counter() - t0
        if i % 1000 == 0 or i + 1 == target_rows:
            write_json(OUT / "progress.json", {"phase": "runtime_18k", "status": "running",
                                                 "completed_rows": i + 1, "planned_rows": target_rows,
                                                 "elapsed_seconds": candidate_seconds+retrieval_seconds+expansion_seconds+alignment_seconds+feature_seconds+base_transform,
                                                 "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()})
    meta_matrix, names = feature_matrix(meta_rows, [row["id"] for row in raw_rows])
    model_matrix = hstack((base_matrix, meta_matrix), format="csr", dtype=np.float32)
    predict_start = time.perf_counter()
    with threadpool_limits(limits=2):
        probs = probabilities(estimator, model_matrix)
    prediction_seconds = time.perf_counter() - predict_start
    for i, row in enumerate(raw_rows):
        label_index = int(np.argmax(probs[i])); label = LABELS[label_index]
        output_predictions.append({"id": row["id"], "label": label,
                                   "confidence": float(probs[i, label_index]),
                                   "probability_false": float(probs[i, LABELS.index("false")]),
                                   "probability_true": float(probs[i, LABELS.index("true")]),
                                   "probability_unsure": float(probs[i, LABELS.index("unsure")])})
    csv_start = time.perf_counter()
    write_csv(OUT / "runtime_predictions_18k.csv", output_predictions)
    csv_seconds = time.perf_counter() - csv_start
    total = p1_fit + graph_seconds + bm25_index_seconds + base_transform + candidate_seconds + retrieval_seconds + expansion_seconds + alignment_seconds + feature_seconds + prediction_seconds + csv_seconds
    return {"status": "measured", "rows": target_rows, "workload": "repeated P2 test claim text, unique IDs; runtime input rows contain id/text/date only",
            "wall_seconds": {"candidate_factory_fit_semantic_resolver_and_bm25": p1_fit,
                             "graph_construction": graph_seconds,
                             "p2_bm25_index_construction": bm25_index_seconds,
                             "tfidf_feature_transform": base_transform,
                             "p1_7_candidate_extraction": candidate_seconds,
                             "p2_hybrid_retrieval": retrieval_seconds,
                             "r6_evidence_guided_expansion_and_ranking": expansion_seconds,
                             "p1_6_temporal_alignment": alignment_seconds,
                             "structured_feature_extraction": feature_seconds,
                             "lightgbm_prediction": prediction_seconds,
                             "csv_output": csv_seconds,
                             "end_to_end_sum": total},
            "throughput_claims_per_second": target_rows / max(total, 1e-12),
            "projected_seconds_18000": total * 18000 / target_rows,
            "projected_minutes_18000": total * 18000 / target_rows / 60,
            "peak_rss_mb": PROCESS.memory_info().rss / (1024 ** 2),
            "cpu_affinity": affinity, "cpu_threads": 2,
            "classifier_variant": classifier_variant, "candidate_configuration": candidate_config,
            "feature_count": int(model_matrix.shape[1]), "candidate_feature_count": len(names),
            "prediction_csv": "runtime_predictions_18k.csv",
            "generator_1000_true_claims_included": False,
            "full_competition_30_minute_claim": False,
            "total_duration_note": "Does not include generating and verifying the separate 1,000 TRUE claims."}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-rows", type=int, default=18000)
    parser.add_argument("--skip-runtime", action="store_true")
    args = parser.parse_args()
    report = run(runtime_rows=0 if args.skip_runtime else args.runtime_rows)
    print(json.dumps({"status": "completed", "selected": report["selection"],
                      "runtime": report.get("runtime")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
