"""Reproducible grouped benchmark for P1.7 recall-first candidates."""
from __future__ import annotations

import csv
import copy
import json
import os
import platform
import re
import sys
import time
import tracemalloc
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from foundation import load_inputs
from core.graph.semantic_extraction import grouped_train_validation_split
from scripts.evaluate_semantic_extraction import _same_value
from candidate_factory import Candidate, CandidateFactory, ValueSpan

DEV_SEED = "neuron5-p15-confirm-v2"       # Published P1.6 development split.
CONFIRM_SEED = "neuron5-p17-confirm-v1"   # Predeclared new grouped holdout.
KS = (1, 3, 5, 10, 20)
RUNS = (("R0", None), ("R1", None),
        *(("R2", k) for k in KS), ("R3", 5),
        *(("R4", k) for k in KS), *(("R5", k) for k in KS))
BUDGETS = (200, 400, 800, 1600, 3200)


def _fact_dict(fact):
    v = fact.value
    return {"subject": fact.subject, "attribute": fact.attribute,
            "value": {k: x for k, x in (("kind", v.kind), ("value", v.value),
                       ("unit", v.unit), ("currency", v.currency),
                       ("per", v.per), ("op", v.op)) if x is not None}}


def _candidate_fact(c):
    return c.fact if isinstance(c, Candidate) else c


def _matches(pred, gold, lexicon):
    return pred.subject == gold.subject and pred.attribute == gold.attribute and _same_value(pred, gold, lexicon)


def _one_to_one(candidates, gold, lexicon):
    remaining = set(range(len(gold)))
    matched = set()
    for c in candidates:
        fact = _candidate_fact(c)
        i = next((i for i in sorted(remaining) if _matches(fact, gold[i], lexicon)), None)
        if i is not None:
            remaining.remove(i)
            matched.add(i)
    return matched


def _per_row_metrics(data, row_ids, row_candidates):
    rows = [row for row in data.rows if row.row_id in row_ids]
    gold_total = sum(len(r.facts) for r in rows)
    unique_gold = {(r.row_id, f.subject, f.attribute, f.value.key()) for r in rows for f in r.facts}
    tp = fp = exact = exact_multi = multi = 0
    per_kind = defaultdict(lambda: Counter())
    row_matches = {}
    for row in rows:
        candidates = row_candidates[row.row_id]
        gold = list(row.facts)
        matched = _one_to_one(candidates, gold, data.lexicon)
        row_matches[row.row_id] = matched
        tp += len(matched)
        fp += len(candidates) - len(matched)
        if len(matched) == len(gold) and len(candidates) == len(gold):
            exact += 1
            if len(gold) > 1:
                exact_multi += 1
        if len(gold) > 1:
            multi += 1
        for f in gold:
            per_kind[f.value.kind]["gold"] += 1
        for c in candidates:
            per_kind[_candidate_fact(c).value.kind]["predicted"] += 1
        for i in matched:
            per_kind[gold[i].value.kind]["tp"] += 1
    fn = gold_total - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / gold_total if gold_total else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_type = {}
    for kind, counts in sorted(per_kind.items()):
        counts["tp"] = counts.get("tp", 0)
        counts["predicted"] = counts.get("predicted", 0)
        counts["fn"] = counts["gold"] - counts["tp"]
        counts["precision"] = counts["tp"] / counts["predicted"] if counts["predicted"] else 0.0
        counts["recall"] = counts["tp"] / counts["gold"] if counts["gold"] else 0.0
        by_type[kind] = dict(counts)
    return {"rows": len(rows), "reference_facts": gold_total,
            "unique_row_scoped_gold_facts": len(unique_gold), "candidate_count": tp+fp,
            "gold_recovered": tp, "gold_missed": fn, "false_positive_diagnostic": fp,
            "oracle_candidate_recall": recall, "precision_diagnostic": precision,
            "f1_diagnostic": f1, "exact_full_rows": exact,
            "exact_full_row_coverage": exact / len(rows) if rows else 0.0,
            "multi_fact_rows": multi, "exact_multi_fact_rows": exact_multi,
            "by_type": by_type, "row_matches": row_matches}


def _ranked_at_k(data, rows, row_candidates, k):
    tp = gold_count = 0
    macro = []
    for row in rows:
        gold = list(row.facts)
        gold_count += len(gold)
        # R0-R4 use deterministic generation order; only R5 has been reranked.
        ranked = row_candidates[row.row_id][:k]
        matched = _one_to_one(ranked, gold, data.lexicon)
        tp += len(matched)
        macro.append(len(matched) / len(gold) if gold else 1.0)
    return {"gold_recovered": tp, "gold_total": gold_count,
            "micro_recall": tp / gold_count if gold_count else 0.0,
            "macro_claim_recall": sum(macro) / len(macro) if macro else 0.0}


def _budget_curve(data, rows, name, row_candidates):
    records = [(c.rank_score, row.row_id, c.key(), c) for row in rows for c in row_candidates[row.row_id]]
    records.sort(key=lambda x: (-x[0], x[1], x[2]))
    gold_by_row = {row.row_id: list(row.facts) for row in rows}
    total_gold = sum(len(v) for v in gold_by_row.values())
    budgets = list(BUDGETS) + [len(records)]
    result = []
    for budget in sorted(set(budgets)):
        used = defaultdict(set)
        recovered = 0
        for _score, row_id, _key, cand in records[:budget]:
            gold = gold_by_row[row_id]
            index = next((i for i, f in enumerate(gold) if i not in used[row_id]
                          and _matches(cand.fact, f, data.lexicon)), None)
            if index is not None:
                used[row_id].add(index)
                recovered += 1
        result.append({"configuration": name, "budget": budget,
                       "budget_available": budget <= len(records),
                       "actual_candidates": len(records), "gold_recovered": recovered,
                       "gold_total": total_gold,
                       "recall": recovered / total_gold if total_gold else 0.0})
    return result


def _component_stage(data, rows, factory, generated_candidates, stats_by_row, split_name):
    totals = Counter()
    for row in rows:
        gold = row.facts
        stats = stats_by_row[row.row_id]
        subjects = set(stats.get("subject_candidates", ()))
        attrs = {s: set(a) for s, a in stats.get("attribute_candidates", {}).items()}
        vals = stats.get("value_candidates", ())
        cands = generated_candidates[row.row_id]
        for fact in gold:
            totals["gold_facts"] += 1
            subject_ok = fact.subject in subjects
            value_ok = any(_matches_value(fact, item, data.lexicon) for item in vals)
            attr_ok = fact.attribute in attrs.get(fact.subject, set())
            triple_ok = any(_matches(c.fact, fact, data.lexicon) for c in cands)
            totals["subject"] += subject_ok
            totals["value"] += value_ok
            totals["attribute"] += attr_ok
            totals["triple"] += triple_ok
            totals["ranked_top20"] += fact in [x.fact for x in sorted(cands, key=lambda c: (-c.rank_score, c.key()))[:20]]
    n = totals["gold_facts"] or 1
    return {"split": split_name, "configuration": "R0" if generated_candidates and all(not x for x in generated_candidates.values()) else None,
            "reference_facts": totals["gold_facts"],
            "subject_candidate_recall": totals["subject"]/n,
            "attribute_candidate_recall": totals["attribute"]/n,
            "typed_value_candidate_recall": totals["value"]/n,
            "complete_triplet_oracle_recall": totals["triple"]/n,
            "complete_triplet_recall_at_20": totals["ranked_top20"]/n}


def _matches_value(fact, raw, lexicon):
    from foundation import AtomicFact
    v = raw["value"]
    candidate = AtomicFact(fact.subject, fact.attribute,
        __import__("foundation").TypedValue(v["kind"], v["value"], v.get("unit"),
                                             v.get("currency"), v.get("per"), v.get("op")))
    return _same_value(fact, candidate, lexicon)


def _memory_mb():
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            p = PMC(); p.cb = ctypes.sizeof(p)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            handle = kernel32.GetCurrentProcess()
            if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(p), p.cb):
                raise ctypes.WinError(ctypes.get_last_error())
            return p.PeakWorkingSetSize / (1024*1024), "Windows PeakWorkingSetSize"
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (1024 if platform.system() != "Darwin" else 1024*1024), "resource.ru_maxrss"
    except Exception as exc:
        return None, f"unavailable: {type(exc).__name__}"


def _run_split(data, split_name, train_ids, validation_ids):
    rows = [row for row in data.rows if row.row_id in validation_ids]
    factory = CandidateFactory.fit(data, train_ids)
    baseline = factory.baseline()
    candidates_by_config = {}
    stats_by_config = {}
    timings = {}
    cpu_timings = {}
    previous_key = {"R1": "R0", "R3@5": "R2@5"}
    for k in KS:
        previous_key[f"R2@{k}"] = "R1"
        previous_key[f"R4@{k}"] = "R3@5"
        previous_key[f"R5@{k}"] = f"R4@{k}"
    for config, k in RUNS:
        config_key = f"{config}@{k}" if k is not None else config
        start = time.perf_counter()
        cpu_start = time.process_time()
        row_candidates = {}
        stats = {}
        if config == "R5":
            # R5 ranks the exact R4 set; no candidate generation is added.
            for row in rows:
                row_candidates[row.row_id] = sorted(
                    copy.deepcopy(candidates_by_config[previous_key[config_key]][row.row_id]),
                    key=lambda c: (-c.rank_score, c.row_id, c.key()))
                stats[row.row_id] = copy.deepcopy(stats_by_config[previous_key[config_key]][row.row_id])
        elif config == "R0":
            for row in rows:
                result = baseline.extract(row.text, row.row_id)
                converted = []
                for item in result.candidates:
                    c = Candidate(row.row_id, item.fact,
                                  (item.subject_span_start, item.subject_span_end) if item.subject_span_start is not None else None,
                                  (item.span_start, item.span_end) if item.span_start is not None else None,
                                  0, {item.method}, {"resolver": item.confidence,
                                  "exact_entity": 1.0 if item.subject_span_start is not None else 0.0,
                                  "value_compat": 1.0})
                    converted.append(c)
                row_candidates[row.row_id] = converted
                stats[row.row_id] = {"generated_before_caps": len(converted), "emitted": len(converted),
                    "subject_candidates": sorted({x.fact.subject for x in converted}),
                    "value_candidates": [{"value": _fact_dict(x.fact)["value"], "start": x.value_span[0], "end": x.value_span[1]}
                                         for x in converted if x.value_span],
                    "attribute_candidates": {s: sorted({x.fact.attribute for x in converted if x.fact.subject == s})
                                             for s in {x.fact.subject for x in converted}}}
        else:
            cumulative_global = 0
            for row in rows:
                added, add_stat = factory.generate(row.row_id, row.text, config=config, k=k or 5, collect_only=True)
                parent = previous_key[config_key]
                inherited = candidates_by_config[parent][row.row_id]
                merged = _merge_candidates(inherited, added)
                pre_cap = len(merged)
                if config == "R5":
                    merged.sort(key=lambda c: (-c.rank_score, c.row_id, c.key()))
                else:
                    merged = merged[:factory.per_row_cap]
                per_row_truncated = pre_cap > factory.per_row_cap
                room = max(0, factory.global_cap-cumulative_global)
                if len(merged) > room:
                    merged = merged[:room]
                global_truncated = len(merged) < min(pre_cap, factory.per_row_cap)
                cumulative_global += len(merged)
                row_candidates[row.row_id] = merged
                stat = _merge_component_stats(stats_by_config[parent][row.row_id], add_stat)
                stat.update({"generated_before_caps": pre_cap, "emitted": len(merged),
                             "per_row_truncated": per_row_truncated,
                             "global_truncated": global_truncated,
                             "skipped_after_global_cap": bool(cumulative_global >= factory.global_cap),
                             "deadline_exceeded": add_stat.get("deadline_exceeded", False),
                             "deadline_truncated": add_stat.get("deadline_truncated", False)})
                stats[row.row_id] = stat
        elapsed = time.perf_counter() - start
        timings[config_key] = elapsed
        cpu_timings[config_key] = time.process_time() - cpu_start
        candidates_by_config[config_key] = row_candidates
        stats_by_config[config_key] = stats
    return rows, factory, candidates_by_config, stats_by_config, timings, cpu_timings


def _merge_candidates(parent, additions):
    merged = {}
    for candidate in [*parent, *additions]:
        candidate = copy.deepcopy(candidate)
        key = candidate.key()
        existing = merged.get(key)
        if existing is None:
            merged[key] = candidate
        else:
            existing.methods.update(candidate.methods)
            existing.matched_example_ids.update(candidate.matched_example_ids)
            for name, value in candidate.scores.items():
                existing.scores[name] = max(existing.scores.get(name, 0.0), value)
            existing.ambiguous_entity = existing.ambiguous_entity or candidate.ambiguous_entity
    return list(merged.values())


def _merge_component_stats(parent, child):
    result = copy.deepcopy(parent)
    result["subject_candidates"] = sorted(set(parent.get("subject_candidates", ())) |
                                          set(child.get("subject_candidates", ())))
    values = {(x.get("start"), x.get("end"), json.dumps(x.get("value"), sort_keys=True)):x
              for x in [*parent.get("value_candidates", ()), *child.get("value_candidates", ())]}
    result["value_candidates"] = list(values.values())
    attrs = defaultdict(set)
    for source in (parent, child):
        for subject, names in source.get("attribute_candidates", {}).items():
            attrs[subject].update(names)
    result["attribute_candidates"] = {name:sorted(values) for name,values in sorted(attrs.items())}
    result["entity_hypotheses"] = max(parent.get("entity_hypotheses",0),child.get("entity_hypotheses",0))
    result["value_spans"] = max(parent.get("value_spans",0),child.get("value_spans",0))
    return result


def _examples_jsonl(data, rows, candidates, stats, split_name):
    categories = defaultdict(list)
    for row in rows:
        cs = candidates[row.row_id]
        value_types = {f.value.kind for f in row.facts}
        if len(row.facts) > 1: categories["multi_fact"].append(row)
        if "date" in value_types: categories["temporal"].append(row)
        if "name" in value_types: categories["name_relation"].append(row)
        if any(re.search(r"\d", e.name) for e in data.lexicon.entities if e.name in row.text): categories["numeric_entity_name"].append(row)
        if stats[row.row_id].get("entity_hypotheses", 1) > 1: categories["ambiguous_entities"].append(row)
        if any(c.scores.get("bm25_rrf", 0) for c in cs): categories["value_alignment_bm25"].append(row)
    path = OUT / "candidate_examples.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for category, examples in sorted(categories.items()):
            for row in examples[:8]:
                obj = {"split": split_name, "category": category, "row_id": row.row_id,
                       "text": row.text, "expected_form_for_audit_only": [_fact_dict(x) for x in row.facts],
                       "candidates": [c.as_dict() for c in candidates[row.row_id][:30]]}
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
    dev = grouped_train_validation_split(data, seed=DEV_SEED)
    confirm = grouped_train_validation_split(data, seed=CONFIRM_SEED)
    split_specs = [("dev_reproduction", dev.train_row_ids, dev.validation_row_ids),
                   ("new_grouped_confirmation", confirm.train_row_ids, confirm.validation_row_ids)]
    summary_rows, type_rows, stage_rows, budget_rows, new_rows, missed_rows = [], [], [], [], [], []
    split_payload = {}
    for split_name, train_ids, val_ids in split_specs:
        rows, factory, per_config, stats_per_config, timings, cpu_timings = _run_split(data, split_name, train_ids, val_ids)
        split_payload[split_name] = {"train_rows": len(train_ids), "validation_rows": len(val_ids),
                                     "BM25_train_examples": {k: len(v.records) for k,v in factory.indexes.items()},
                                     "BM25_k": list(KS), "per_row_cap": factory.per_row_cap,
                                     "global_cap": factory.global_cap}
        results = {}
        for config, retrieval_k in RUNS:
            config_key = f"{config}@{retrieval_k}" if retrieval_k is not None else config
            row_candidates = per_config[config_key]
            metrics = _per_row_metrics(data, val_ids, row_candidates)
            results[config_key] = metrics
            counts = [len(row_candidates[r.row_id]) for r in rows]
            mem, mem_method = _memory_mb()
            all_candidates = [c for row in rows for c in row_candidates[row.row_id]]
            implicit_subject_hypotheses = sum(bool({"same_row_pronoun_antecedent", "same_sentence_subject_carry"} & c.methods)
                                              for c in all_candidates)
            unknown_subjects = sum(data.lexicon.resolve(c.fact.subject) is None for c in all_candidates)
            summary_rows.append({"split": split_name, "configuration": config, "retrieval_k": retrieval_k,
                "reference_facts": metrics["reference_facts"],
                "unique_row_scoped_gold_facts": metrics["unique_row_scoped_gold_facts"],
                "gold_recovered": metrics["gold_recovered"], "oracle_candidate_recall": metrics["oracle_candidate_recall"],
                "candidate_count": metrics["candidate_count"],
                "mean_candidates_per_row": sum(counts)/len(counts) if counts else 0,
                "median_candidates_per_row": sorted(counts)[len(counts)//2] if counts else 0,
                "p95_candidates_per_row": sorted(counts)[min(len(counts)-1, int(.95*len(counts)))] if counts else 0,
                "max_candidates_per_row": max(counts, default=0),
                "newly_recovered_vs_R0": "", "precision_diagnostic": metrics["precision_diagnostic"],
                "f1_diagnostic": metrics["f1_diagnostic"], "exact_full_rows": metrics["exact_full_rows"],
                "multi_fact_rows": metrics["multi_fact_rows"], "exact_multi_fact_rows": metrics["exact_multi_fact_rows"],
                "generation_wall_seconds": timings[config_key],
                "generation_cpu_seconds": cpu_timings[config_key],
                "rows_per_second": len(rows)/timings[config_key] if timings[config_key] else 0,
                "rows_per_cpu_second": len(rows)/cpu_timings[config_key] if cpu_timings[config_key] else 0,
                "peak_process_memory_mb": mem, "memory_measurement": mem_method,
                "implicit_subject_hypothesis_candidates": implicit_subject_hypotheses,
                "subjects_outside_lexicon": unknown_subjects,
                "values_without_text_spans": 0,
                "truncated_rows": sum(stats_per_config[config_key][r.row_id].get("per_row_truncated", False) or
                                       stats_per_config[config_key][r.row_id].get("global_truncated", False) for r in rows)})
            for kind, vals in metrics["by_type"].items():
                type_rows.append({"split": split_name, "configuration": config, "retrieval_k": retrieval_k, "value_type": kind,
                                  "gold": vals["gold"], "predicted": vals["predicted"], "recovered": vals["tp"],
                                  "missed": vals["fn"], "oracle_candidate_recall": vals["recall"],
                                  "precision_diagnostic": vals["precision"]})
            for budget in _budget_curve(data, rows, config_key, row_candidates):
                budget_rows.append({"split": split_name, "retrieval_k": retrieval_k, **budget})
            for kk in KS:
                result_k = _ranked_at_k(data, rows, row_candidates, kk)
                # A separate CSV row carries per-claim Recall@K values.
                budget_rows.append({"split": split_name, "configuration": config, "retrieval_k": retrieval_k,
                    "budget": f"per_claim@{kk}", "budget_available": True,
                    "actual_candidates": metrics["candidate_count"],
                    "gold_recovered": result_k["gold_recovered"], "gold_total": result_k["gold_total"],
                    "recall": result_k["micro_recall"], "macro_claim_recall": result_k["macro_claim_recall"]})
            # Stage coverage from generator component inventories.
            st = _stage_metrics(data, rows, row_candidates, stats_per_config[config_key])
            stage_rows.append({"split": split_name, "configuration": config, "retrieval_k": retrieval_k, **st})
        r0_matches = results["R0"]["row_matches"]
        for config, retrieval_k in RUNS[1:]:
            config_key = f"{config}@{retrieval_k}" if retrieval_k is not None else config
            current = results[config_key]["row_matches"]
            for row in rows:
                gold = list(row.facts)
                for i, fact in enumerate(gold):
                    if i not in r0_matches[row.row_id] and i in current[row.row_id]:
                        candidate = next((c for c in per_config[config_key][row.row_id]
                                          if _matches(c.fact, fact, data.lexicon)), None)
                        new_rows.append({"split": split_name, "configuration": config, "retrieval_k": retrieval_k, "row_id": row.row_id,
                                         "text": row.text, "expected_form": json.dumps(_fact_dict(fact), ensure_ascii=False),
                                         "candidate_provenance": json.dumps(candidate.as_dict() if candidate else {}, ensure_ascii=False)})
        final = per_config["R5@5"]
        final_stats = stats_per_config["R5@5"]
        for row in rows:
            matched = results["R5@5"]["row_matches"][row.row_id]
            for i, fact in enumerate(row.facts):
                if i in matched: continue
                st = final_stats[row.row_id]
                subject_ok = fact.subject in st.get("subject_candidates", ())
                attr_ok = fact.attribute in st.get("attribute_candidates", {}).get(fact.subject, ())
                value_ok = any(_matches_value(fact, v, data.lexicon) for v in st.get("value_candidates", ()))
                stage = "entity" if not subject_ok else "value" if not value_ok else "attribute" if not attr_ok else "binding_or_cap"
                missed_rows.append({"split": split_name, "row_id": row.row_id, "text": row.text,
                                    "expected_form": json.dumps(_fact_dict(fact), ensure_ascii=False),
                                    "first_identifiable_missing_stage": stage,
                                    "subject_candidate_present": subject_ok,
                                    "typed_value_candidate_present": value_ok,
                                    "attribute_candidate_present": attr_ok,
                                    "candidate_generation_truncated": bool(st.get("per_row_truncated") or st.get("global_truncated"))})
        if split_name == "new_grouped_confirmation":
            _examples_jsonl(data, rows, per_config["R5@5"], stats_per_config["R5@5"], split_name)
        split_payload[split_name]["results"] = {name: {k:v for k,v in result.items() if k != "row_matches" and k != "by_type"}
                                                 for name, result in results.items()}
        split_payload[split_name]["per_type"] = {name: result["by_type"] for name, result in results.items()}
        split_payload[split_name]["relative_to_R0"] = {
            name: {"net_gold_recovered_delta": result["gold_recovered"]-results["R0"]["gold_recovered"],
                   "newly_recovered_gold_facts": sum(len(result["row_matches"][rid]-results["R0"]["row_matches"][rid]) for rid in val_ids),
                   "candidate_count_delta": result["candidate_count"]-results["R0"]["candidate_count"]}
            for name, result in results.items() if name != "R0"}
        split_payload[split_name]["generation_seconds"] = timings
        split_payload[split_name]["generation_cpu_seconds"] = cpu_timings
    _write_csv(OUT / "benchmark_recall.csv", summary_rows)
    _write_csv(OUT / "recall_by_type.csv", type_rows)
    _write_csv(OUT / "stage_recall.csv", stage_rows)
    _write_csv(OUT / "candidate_budget_curve.csv", budget_rows)
    _write_csv(OUT / "newly_recovered_facts.csv", new_rows)
    _write_csv(OUT / "missed_gold_facts.csv", missed_rows)
    report = {"protocol": {"dev_seed": DEV_SEED, "confirmation_seed_predeclared": CONFIRM_SEED,
                "grouping": "connected shared subject-attribute histories OR normalized claim template",
                "forms_used_for_generation": "training rows only; validation forms are passed only to scorer",
                "labels_used_for_generation": False, "evidence_state": "UNVERIFIED_CANDIDATE",
                "candidate_caps": {"per_row": 512, "global": 1_000_000,
                                    "deadline_seconds": "configurable; not set for evaluation"},
                "platform": platform.platform()},
             "schema_inventory": _schema_inventory(data),
             "leakage_audit": {name: _leakage_audit(data, train_ids, val_ids)
                               for name, train_ids, val_ids in split_specs},
             "splits": split_payload}
    (OUT / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({name: info["results"] for name, info in split_payload.items()}, indent=2))


def _stage_metrics(data, rows, candidates, stats):
    totals = Counter()
    for row in rows:
        st = stats[row.row_id]
        subjects = set(st.get("subject_candidates", ()))
        attrs = {s:set(a) for s,a in st.get("attribute_candidates", {}).items()}
        vals = st.get("value_candidates", ())
        for gold in row.facts:
            totals["gold"] += 1
            s_ok = gold.subject in subjects
            a_ok = gold.attribute in attrs.get(gold.subject, set())
            v_ok = any(_matches_value(gold, raw, data.lexicon) for raw in vals)
            t_ok = any(_matches(c.fact, gold, data.lexicon) for c in candidates[row.row_id])
            totals["subject"] += s_ok; totals["attribute"] += a_ok
            totals["value"] += v_ok; totals["triplet"] += t_ok
            rank20 = sorted(candidates[row.row_id], key=lambda c:(-c.rank_score,c.key()))[:20]
            totals["triplet_top20"] += any(_matches(c.fact, gold, data.lexicon) for c in rank20)
    n = totals["gold"] or 1
    return {"reference_facts": totals["gold"], "subject_candidate_recall": totals["subject"]/n,
            "attribute_candidate_recall": totals["attribute"]/n, "typed_value_candidate_recall": totals["value"]/n,
            "complete_triplet_oracle_recall": totals["triplet"]/n,
            "complete_triplet_recall_at_20": totals["triplet_top20"]/n}


def _write_csv(path, rows):
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _schema_inventory(data):
    pair_count = sum(len(entity.attributes) for entity in data.lexicon.entities)
    kinds_by_attribute = defaultdict(set)
    for row in data.rows:
        for fact in row.facts:
            kinds_by_attribute[fact.attribute].add(fact.value.kind)
    pair_kind_count = sum(len(kinds_by_attribute[attr]) for entity in data.lexicon.entities
                           for attr in entity.attributes)
    attrs_per_entity = [len(e.attributes) for e in data.lexicon.entities]
    return {"canonical_entities": len(data.lexicon.entities),
            "unique_attribute_names": len({a for e in data.lexicon.entities for a in e.attributes}),
            "compatible_subject_attribute_pairs": pair_count,
            "compatible_subject_attribute_value_kind_triples_observed_in_practice": pair_kind_count,
            "lexicon_events": len(data.lexicon.events), "min_attributes_per_entity": min(attrs_per_entity),
            "median_attributes_per_entity": sorted(attrs_per_entity)[len(attrs_per_entity)//2],
            "max_attributes_per_entity": max(attrs_per_entity),
            "practice_semantic_fact_count_all_labels": sum(len(r.facts) for r in data.rows),
            "value_kinds_observed": dict(sorted(Counter(f.value.kind for row in data.rows for f in row.facts).items()))}


def _leakage_audit(data, train_ids, validation_ids):
    from core.graph.semantic_extraction import _template
    train = [row for row in data.rows if row.row_id in train_ids]
    valid = [row for row in data.rows if row.row_id in validation_ids]
    train_templates = {_template(row.text, data.lexicon) for row in train}
    validation_templates = {_template(row.text, data.lexicon) for row in valid}
    train_pairs = {(fact.subject.casefold(), fact.attribute) for row in train for fact in row.facts}
    valid_pairs = {(fact.subject.casefold(), fact.attribute) for row in valid for fact in row.facts}
    # Audit near-duplicate surface forms after masking known entity names and digits.
    def tokens(text):
        value = text.casefold()
        names = [(spelling, entity) for entity in data.lexicon.entities
                 for spelling in (entity.name, *entity.aliases)]
        for spelling, _entity in sorted(names, key=lambda x: -len(x[0])):
            value = re.sub(r"(?<!\w)"+re.escape(spelling)+r"(?!\w)", " entity ", value)
        value = re.sub(r"\d+(?:[.,]\d+)?", " number ", value)
        return set(re.findall(r"[a-z]+|entity|number", value))
    train_sets = [(row.row_id, tokens(row.text)) for row in train]
    near = []
    for row in valid:
        current = tokens(row.text)
        for train_id, other in train_sets:
            union = current | other
            score = len(current & other) / len(union) if union else 1.0
            if score >= 0.85:
                near.append({"validation_row_id": row.row_id, "training_row_id": train_id,
                             "token_jaccard": round(score, 5)})
    return {"training_rows": len(train), "validation_rows": len(valid),
            "shared_subject_attribute_histories": len(train_pairs & valid_pairs),
            "shared_normalized_templates": len(train_templates & validation_templates),
            "near_duplicate_pairs_token_jaccard_ge_0_85": len(near),
            "near_duplicate_examples": near[:20],
            "generation_fit_row_ids": "training IDs only; validation forms accessed only by scorer"}


if __name__ == "__main__":
    main()
