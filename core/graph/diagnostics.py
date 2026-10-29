"""Practice-form extraction coverage diagnostics; never feed these labels into truth at runtime."""

from __future__ import annotations

from typing import Any

from dataclasses import replace

from foundation import AtomicFact, InputData, compare_values
from .parsing import TextFactParser


def practice_extraction_metrics(data: InputData) -> dict[str, Any]:
    """Report exact form-level precision/recall for deterministic parsing."""
    if data.lexicon is None:
        return {"rows": len(data.rows), "error": "lexicon unavailable"}
    attribute_kinds: dict[str, str] = {}
    known_units: set[str] = set()
    for row in data.rows:
        for fact in row.facts:
            attribute_kinds.setdefault(fact.attribute, fact.value.kind)
            if fact.value.kind in {"quantity", "duration"} and fact.value.unit:
                known_units.add(fact.value.unit)
    parser = TextFactParser(data.lexicon, attribute_kinds, known_units)
    true_positive = false_positive = false_negative = parsed_rows = 0
    gold_count = extracted_count = 0
    by_kind: dict[str, dict[str, int]] = {}
    for row in data.rows:
        gold = list(row.facts)
        extracted = list(parser.parse(row.text).facts)
        gold_count += len(gold)
        extracted_count += len(extracted)
        if extracted:
            parsed_rows += 1
        unmatched_gold = list(gold)
        for extracted_fact in extracted:
            kind = extracted_fact.value.kind
            bucket = by_kind.setdefault(kind, {"gold": 0, "extracted": 0, "exact_matches": 0})
            bucket["extracted"] += 1
            match = next((candidate for candidate in unmatched_gold
                          if candidate.subject == extracted_fact.subject
                          and candidate.attribute == extracted_fact.attribute
                          and candidate.value.kind == kind
                          and _same_fact_value(candidate, extracted_fact, data)), None)
            if match is None:
                false_positive += 1
            else:
                unmatched_gold.remove(match)
                true_positive += 1
                bucket["exact_matches"] += 1
        for missing in unmatched_gold:
            false_negative += 1
        for gold_fact in gold:
            by_kind.setdefault(gold_fact.value.kind, {"gold": 0, "extracted": 0, "exact_matches": 0})["gold"] += 1
    precision = true_positive / extracted_count if extracted_count else 0.0
    recall = true_positive / gold_count if gold_count else 0.0
    return {
        "rows": len(data.rows),
        "rows_with_candidates": parsed_rows,
        "gold_facts": gold_count,
        "extracted_candidates": extracted_count,
        "exact_matches": true_positive,
        "false_positive_candidates": false_positive,
        "missed_gold_facts": false_negative,
        "precision": precision,
        "recall": recall,
        "by_kind": by_kind,
    }


def _same_fact_value(left: AtomicFact, right: AtomicFact, data: InputData) -> bool:
    """Compare exact typed values while preserving operators and lexicon aliases."""
    if left.value.op != right.value.op:
        return False
    left_value, right_value = left.value, right.value
    if left_value.kind == "name" and isinstance(left_value.value, str) and data.lexicon is not None:
        entity = data.lexicon.resolve(left_value.value)
        if entity is not None:
            left_value = replace(left_value, value=entity.name)
    if right_value.kind == "name" and isinstance(right_value.value, str) and data.lexicon is not None:
        entity = data.lexicon.resolve(right_value.value)
        if entity is not None:
            right_value = replace(right_value, value=entity.name)
    # P0 comparison intentionally rejects operator-qualified values; here the
    # operator is checked separately and scalar/unit equivalence is compared.
    left_value, right_value = replace(left_value, op=None), replace(right_value, op=None)
    return compare_values(left_value, right_value, "eq") is True
