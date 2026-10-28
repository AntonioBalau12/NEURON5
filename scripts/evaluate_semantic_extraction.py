"""Grouped, form-supervised comparison of P1 and P1.5 semantic extractors."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from foundation import compare_values, load_inputs
from core.graph.parsing import TextFactParser
from core.graph.semantic_extraction import (
    AttributeResolver,
    AttributeResolverExtractor,
    ExpandedDeterministicExtractor,
    HybridSemanticExtractor,
    P1ParserAdapter,
    SpacyAssistedExtractor,
    grouped_train_validation_split,
)


def _same_value(left, right, lexicon) -> bool:
    if left.value.kind != right.value.kind or left.value.op != right.value.op:
        return False
    a, b = left.value, right.value
    if a.kind == "name":
        left_entity, right_entity = lexicon.resolve(str(a.value)), lexicon.resolve(str(b.value))
        a = replace(a, value=left_entity.name if left_entity else a.value)
        b = replace(b, value=right_entity.name if right_entity else b.value)
    return compare_values(replace(a, op=None), replace(b, op=None), "eq") is True


def _fact_key(fact):
    return fact.subject.casefold(), fact.attribute, fact.value.key()


def _score(data, row_ids, extractor) -> dict:
    rows = [row for row in data.rows if row.row_id in row_ids]
    tp = fp = fn = 0
    pred_count = gold_count = exact_rows = exact_multi = multi_rows = 0
    by_kind: dict[str, dict[str, int]] = {}
    recovered, new_errors = [], []
    for row in rows:
        result = extractor.extract(row.text, row.row_id)
        predicted = list(result.facts)
        gold = list(row.facts)
        unmatched = list(gold)
        pred_count += len(predicted)
        gold_count += len(gold)
        row_tp = 0
        for fact in predicted:
            kind = fact.value.kind
            bucket = by_kind.setdefault(kind, {"gold": 0, "predicted": 0, "tp": 0, "fp": 0, "fn": 0})
            bucket["predicted"] += 1
            match = next((item for item in unmatched
                          if item.subject == fact.subject and item.attribute == fact.attribute
                          and _same_value(item, fact, data.lexicon)), None)
            if match is None:
                fp += 1
                bucket["fp"] += 1
                if extractor.method != "p1_regex" and len(new_errors) < 12:
                    new_errors.append({"row_id": row.row_id, "text": row.text,
                                       "candidate": f"{fact.subject}.{fact.attribute}={fact.value.key()}",
                                       "method": result.method})
            else:
                unmatched.remove(match)
                row_tp += 1
                tp += 1
                bucket["tp"] += 1
        for fact in gold:
            by_kind.setdefault(fact.value.kind, {"gold": 0, "predicted": 0, "tp": 0, "fp": 0, "fn": 0})["gold"] += 1
        for fact in unmatched:
            fn += 1
            by_kind[fact.value.kind]["fn"] += 1
        if len(gold) > 1:
            multi_rows += 1
        if not unmatched and len(predicted) == len(gold):
            exact_rows += 1
            if len(gold) > 1:
                exact_multi += 1
        if extractor.method != "p1_regex" and len(recovered) < 12:
            # The caller filters these against E0 below.
            for fact in gold:
                if any(item.subject == fact.subject and item.attribute == fact.attribute
                       and _same_value(item, fact, data.lexicon) for item in predicted):
                    recovered.append({"row_id": row.row_id, "text": row.text,
                                      "fact": f"{fact.subject}.{fact.attribute}={fact.value.key()}",
                                      "method": result.method})
    precision = tp / pred_count if pred_count else 0.0
    recall = tp / gold_count if gold_count else 0.0
    for values in by_kind.values():
        kind_precision = values["tp"] / values["predicted"] if values["predicted"] else 0.0
        kind_recall = values["tp"] / values["gold"] if values["gold"] else 0.0
        values["precision"] = kind_precision
        values["recall"] = kind_recall
        values["f1"] = (2 * kind_precision * kind_recall / (kind_precision + kind_recall)
                        if kind_precision + kind_recall else 0.0)
    return {
        "rows": len(rows), "gold": gold_count, "predicted": pred_count, "tp": tp,
        "fp": fp, "fn": fn, "precision": precision, "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "exact_full_row_accuracy": exact_rows / len(rows) if rows else 0.0,
        "exact_multi_fact_rows": exact_multi, "multi_fact_rows": multi_rows,
        "by_kind": by_kind, "examples_recovered_including_baseline": recovered,
        "examples_unmatched_candidates": new_errors,
    }


def _matched_gold_indices(data, gold, predictions):
    remaining = list(range(len(gold)))
    matched = set()
    for predicted in predictions:
        index = next((i for i in remaining
                      if gold[i].subject == predicted.subject
                      and gold[i].attribute == predicted.attribute
                      and _same_value(gold[i], predicted, data.lexicon)), None)
        if index is not None:
            remaining.remove(index)
            matched.add(index)
    return matched


def _same_fact(left, right, data):
    return (left.subject == right.subject and left.attribute == right.attribute
            and _same_value(left, right, data.lexicon))


def _delta(data, row_ids, baseline, candidate):
    new_correct = lost_correct = new_false_positive = removed_false_positive = 0
    recovered, errors = [], []
    for row in data.rows:
        if row.row_id not in row_ids:
            continue
        gold = list(row.facts)
        base = list(baseline.extract(row.text, row.row_id).facts)
        test = list(candidate.extract(row.text, row.row_id).facts)
        base_matches = _matched_gold_indices(data, gold, base)
        test_matches = _matched_gold_indices(data, gold, test)
        added_matches = test_matches - base_matches
        removed_matches = base_matches - test_matches
        new_correct += len(added_matches)
        lost_correct += len(removed_matches)
        for i in sorted(added_matches):
            if len(recovered) < 12:
                recovered.append({"row_id": row.row_id, "text": row.text,
                                  "fact": f"{gold[i].subject}.{gold[i].attribute}={gold[i].value.key()}"})
        base_fp = [fact for fact in base if not any(_same_fact(fact, item, data) for item in gold)]
        test_fp = [fact for fact in test if not any(_same_fact(fact, item, data) for item in gold)]
        removed_false_positive += sum(1 for fact in base_fp
                                      if not any(_same_fact(fact, item, data) for item in test_fp))
        for fact in test_fp:
            if not any(_same_fact(fact, item, data) for item in base_fp):
                new_false_positive += 1
                if len(errors) < 12:
                    errors.append({"row_id": row.row_id, "text": row.text,
                                   "candidate": f"{fact.subject}.{fact.attribute}={fact.value.key()}"})
    return {"additional_correct_matches": new_correct,
            "baseline_correct_matches_lost": lost_correct,
            "net_correct_match_change": new_correct - lost_correct,
            "new_unmatched_candidates": new_false_positive,
            "baseline_unmatched_candidates_removed": removed_false_positive,
            "net_unmatched_candidate_change": new_false_positive - removed_false_positive,
            "examples_recovered_only_by_candidate": recovered,
            "examples_new_unmatched_candidates": errors}


def _train_types(data, row_ids):
    kinds, units = {}, set()
    for row in data.rows:
        if row.row_id not in row_ids:
            continue
        for fact in row.facts:
            kinds.setdefault(fact.attribute, fact.value.kind)
            if fact.value.unit:
                units.add(fact.value.unit)
    return kinds, units


def main() -> int:
    data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
    if data.lexicon is None:
        raise SystemExit("invalid practice inputs: " + "; ".join(data.issues))
    split = grouped_train_validation_split(data, seed="neuron5-p15-confirm-v2")
    kinds, units = _train_types(data, split.train_row_ids)
    p1_parser = TextFactParser(data.lexicon, kinds, units)
    e0 = P1ParserAdapter(p1_parser)
    e1 = ExpandedDeterministicExtractor(data.lexicon, kinds, units)
    resolver = AttributeResolver().fit(data, split.train_row_ids)
    e3 = AttributeResolverExtractor(p1_parser, resolver)
    # Development-set evidence showed the resolver is useful for money only;
    # its all-type predictions add many quantity/date/boolean errors.
    e4 = HybridSemanticExtractor(e1, AttributeResolverExtractor(p1_parser, resolver,
                                                                 allowed_value_kinds={"money"}))
    e2 = SpacyAssistedExtractor(e0)
    results = {name: _score(data, split.validation_row_ids, extractor)
               for name, extractor in (("E0", e0), ("E1", e1), ("E3", e3), ("E4", e4))}
    # E2 runs its documented fallback only; this is not a spaCy score.
    e2_fallback = _score(data, split.validation_row_ids, e2)
    for name, result in results.items():
        result.pop("examples_recovered_including_baseline", None)
        result.pop("examples_unmatched_candidates", None)
    # Full-practice metrics are explicitly diagnostic and use all forms only for type/unit hints.
    full_kinds, full_units = _train_types(data, {row.row_id for row in data.rows})
    full_e0 = _score(data, {row.row_id for row in data.rows}, P1ParserAdapter(
        TextFactParser(data.lexicon, full_kinds, full_units)))
    full_e1 = _score(data, {row.row_id for row in data.rows},
                     ExpandedDeterministicExtractor(data.lexicon, full_kinds, full_units))
    full_e4 = _score(data, {row.row_id for row in data.rows}, e4)
    payload = {
        "split": {"method": "connected groups: shared canonical subject/attribute history OR normalized claim template",
                  "seed": "neuron5-p15-confirm-v2", "train_rows": len(split.train_row_ids),
                  "validation_rows": len(split.validation_row_ids), "group_count": split.group_count,
                  "validation_groups": split.validation_groups,
                  "resolver_training_examples": resolver.training_examples},
        "results_validation": results,
        "delta_vs_E0_validation": {"E1": _delta(data, split.validation_row_ids, e0, e1),
                                   "E3": _delta(data, split.validation_row_ids, e0, e3),
                                   "E4": _delta(data, split.validation_row_ids, e0, e4)},
        "E2": {"status": "unavailable: no spaCy package or English model installed",
               "reason": e2.reason,
               "fallback_metrics_not_spacy": {key: e2_fallback[key] for key in ("rows", "gold", "predicted", "tp", "fp", "fn", "precision", "recall", "f1")}},
        "full_practice_diagnostic_not_generalization": {
            "E0": {key: value for key, value in full_e0.items() if not key.startswith("examples_")},
            "E1": {key: value for key, value in full_e1.items() if not key.startswith("examples_")},
            "E4": {key: value for key, value in full_e4.items() if not key.startswith("examples_")},
            "delta_vs_E0": _delta(data, {row.row_id for row in data.rows},
                                  P1ParserAdapter(TextFactParser(data.lexicon, full_kinds, full_units)),
                                  ExpandedDeterministicExtractor(data.lexicon, full_kinds, full_units))},
        "model_artifact": "none; resolver is a runtime-fitted in-memory experimental model",
        "truth_label_use": "none; practice forms supply semantic attribute labels regardless of TRUE/FALSE/UNSURE",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
