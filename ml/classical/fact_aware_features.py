"""Leakage-safe numerical features from claim text and a training-only graph."""
from __future__ import annotations

import re
import sys
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from core.graph import EvidenceState, TemporalKnowledgeGraph, TextFactParser
from foundation import Lexicon, compare_values


NEGATION_RE = re.compile(r"\b(?:not|never|no|without|neither|nor|isn't|wasn't|aren't|weren't|doesn't|didn't|hasn't|haven't|won't|can't|cannot)\b", re.I)
EVENT_ATTR_RE = re.compile(r"(?:join|start|found|born|launch|release|acquir|appoint|create|establish|begin|open|close|occur|date)", re.I)
NUMERIC_RE = re.compile(r"(?<!\w)\d+(?:[,.]\d+)?(?:%|\s*(?:million|billion|thousand|km|m|kg|gb|mb|hz|usd|eur))?", re.I)
DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b", re.I)
MONTH_DAY_DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b", re.I)


FEATURE_NAMES = (
    "entity_detected", "attribute_detected", "value_detected", "parse_coverage",
    "parsed_fact_count", "negation_detected", "entity_match", "attribute_match",
    "exact_value_match", "value_difference", "date_difference_days",
    "verified_support_count", "verified_refutation_count", "candidate_evidence_count",
    "conflict_count", "temporal_compatibility", "evidence_available",
    "best_evidence_similarity", "best_value_compatibility", "evidence_date_distance", "independent_evidence_count",
)


class FactAwareFeatureExtractor:
    """Extract target text-only facts and compare them to graph evidence.

    The target form is never accepted. Only graph facts with their original provenance
    and status can contribute. `claim_id` is excluded before every evidence query.
    """

    def __init__(self, lexicon: Lexicon, graph: TemporalKnowledgeGraph):
        self.lexicon, self.graph = lexicon, graph
        kinds: dict[str, str] = {}
        units: set[str] = set()
        for history in graph.facts_by_subject_attribute.values():
            for record in history:
                if record.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                    kinds.setdefault(record.fact.attribute, record.fact.value.kind)
                    if record.fact.value.unit:
                        units.add(record.fact.value.unit)
        self.parser = TextFactParser(lexicon, kinds, units)

    def transform(self, claim_text: str, claim_date: str | date | None,
                  claim_id: str | None = None) -> tuple[dict[str, float], dict[str, Any]]:
        # The shared parser accepts day-month-year but not month-day-year with an
        # optional comma. Normalize this surface form without adding semantics.
        parser_text = MONTH_DAY_DATE_RE.sub(lambda m: f"{m.group(2)} {m.group(1)} {m.group(3)}", claim_text or "")
        parsed = self.parser.parse(parser_text)
        when = _as_date(claim_date)
        entities = _entity_mentions(claim_text, self.lexicon)
        attrs = _attribute_mentions(claim_text, self.lexicon)
        negation = bool(NEGATION_RE.search(claim_text or ""))
        values_mentioned = bool(NUMERIC_RE.search(claim_text or "") or DATE_RE.search(claim_text or ""))
        support_ids: set[str] = set(); candidate_ids: set[str] = set(); conflict_ids: set[str] = set()
        refutation_ids: set[str] = set(); used_ids: set[str] = set()
        exact = 0; diff: list[float] = []; date_diffs: list[float] = []; date_distances: list[float] = []
        similarity: list[float] = []; value_compatibility: list[float] = []; temporal: list[float] = []
        retrieved: list[dict[str, Any]] = []
        for fact in parsed.facts:
            key = self.graph.entity_key(fact.subject)
            history = self.graph.facts_by_subject_attribute.get((key, fact.attribute), ())
            if not history:
                continue
            relevant = [r for r in history if r.source_row_id != str(claim_id or "")]
            is_event = bool(EVENT_ATTR_RE.search(fact.attribute))
            # Mutable values require exact observation or explicit validity at claim date.
            applicable = [r for r in relevant if is_event or _date_applies(r, when)]
            exact_records = [r for r in applicable if compare_values(r.fact.value, fact.value, "eq") is True]
            exact += bool(exact_records)
            for record in applicable:
                used_ids.add(record.source_row_id)
                status = record.evidence_status
                if status == EvidenceState.VERIFIED_SUPPORT: support_ids.add(record.source_row_id)
                elif status == EvidenceState.VERIFIED_REFUTATION: refutation_ids.add(record.source_row_id)
                elif status == EvidenceState.UNVERIFIED_CANDIDATE: candidate_ids.add(record.source_row_id)
                elif status == EvidenceState.CONFLICTING: conflict_ids.add(record.source_row_id)
                if status in {EvidenceState.VERIFIED_SUPPORT, EvidenceState.CONFLICTING}:
                    evidence = self.graph.evidence_by_id.get(record.source_row_id)
                    if evidence and evidence.text:
                        similarity.append(_text_similarity(claim_text, evidence.text))
                    value_compatibility.append(_typed_similarity(record.fact.value, fact.value))
                    difference = _value_difference(record.fact.value, fact.value)
                    if difference is not None:
                        diff.append(difference)
                        if fact.value.kind == "date": date_diffs.append(difference)
                if when and record.observed_on:
                    date_distances.append(abs((when - record.observed_on).days))
                # Temporal compatibility means a relevant exact observation/interval;
                # event-like attributes compare their typed event values across dates.
                temporal.append(float(_date_applies(record, when) or (is_event and record.fact.value.kind == fact.value.kind)))
                retrieved.append({"evidence_id": record.source_row_id, "attribute": fact.attribute,
                                  "status": status.value, "observed_on": record.observed_on.isoformat() if record.observed_on else None,
                                  "value_kind": record.fact.value.kind, "value": record.fact.value.value})
        usable = bool(used_ids)
        coverage = min(1.0, len(parsed.facts) / max(1, len(entities), len(attrs)))
        features = {
            "entity_detected": float(bool(entities)), "attribute_detected": float(bool(attrs)),
            "value_detected": float(bool(parsed.facts) or values_mentioned),
            "parse_coverage": coverage, "parsed_fact_count": float(len(parsed.facts)),
            "negation_detected": float(negation), "entity_match": float(bool(entities) and bool(used_ids)),
            "attribute_match": float(bool(attrs) and bool(used_ids)), "exact_value_match": float(exact > 0),
            "value_difference": min(diff) if diff else np.nan,
            "date_difference_days": min(date_diffs) if date_diffs else np.nan,
            "verified_support_count": float(len(support_ids)), "verified_refutation_count": float(len(refutation_ids)),
            "candidate_evidence_count": float(len(candidate_ids)), "conflict_count": float(len(conflict_ids)),
            "temporal_compatibility": max(temporal, default=0.0), "evidence_available": float(usable),
            "best_evidence_similarity": max(similarity) if similarity else np.nan,
            "best_value_compatibility": max(value_compatibility) if value_compatibility else np.nan,
            "evidence_date_distance": min(date_distances) if date_distances else np.nan,
            "independent_evidence_count": float(len(used_ids)),
        }
        diagnostics = {"parsed_facts": [{"subject": f.subject, "attribute": f.attribute,
                                           "value_kind": f.value.kind, "value": f.value.value,
                                           "unit": f.value.unit, "currency": f.value.currency}
                                          for f in parsed.facts],
                      "parser_status": parsed.status.value, "parser_issues": list(parsed.issues),
                      "retrieved_evidence": retrieved}
        return features, diagnostics


def _as_date(value: str | date | None) -> date | None:
    if isinstance(value, date): return value
    try: return date.fromisoformat(str(value)) if value else None
    except ValueError: return None


def _date_applies(record: Any, when: date | None) -> bool:
    if when is None: return False
    return record.observed_on == when or (record.valid_from is not None and record.valid_from <= when and (record.valid_to is None or when <= record.valid_to))


def _entity_mentions(text: str, lexicon: Lexicon) -> list[str]:
    found = []
    for entity in lexicon.entities:
        if any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or "", re.I) for name in (entity.name, *entity.aliases)):
            found.append(entity.name)
    return found


def _attribute_mentions(text: str, lexicon: Lexicon) -> list[str]:
    words = (text or "").casefold()
    found = set()
    for entity in lexicon.entities:
        if entity.name not in _entity_mentions(text, lexicon): continue
        for attribute in entity.attributes:
            cue = attribute.replace("_", " ").casefold()
            if cue and re.search(r"(?<!\w)" + re.escape(cue) + r"(?!\w)", words): found.add(attribute)
            elif cue and len(cue.split()) > 1 and cue.split()[-1] in words.split(): found.add(attribute)
    return sorted(found)


def _typed_similarity(left: Any, right: Any) -> float:
    if compare_values(left, right, "eq") is True: return 1.0
    if left.kind != right.kind: return 0.0
    if left.kind in {"quantity", "duration"} and left.unit != right.unit: return 0.25
    if left.kind == "money" and (left.currency != right.currency or left.per != right.per): return 0.0
    return 0.5


def _text_similarity(left: str, right: str) -> float:
    """Cosine similarity of lowercase token-frequency vectors."""
    a=Counter(re.findall(r"[a-z0-9]+",(left or "").casefold()))
    b=Counter(re.findall(r"[a-z0-9]+",(right or "").casefold()))
    if not a or not b:return 0.0
    dot=sum(value*b.get(token,0) for token,value in a.items())
    norm_a=math.sqrt(sum(value*value for value in a.values()));norm_b=math.sqrt(sum(value*value for value in b.values()))
    return dot/(norm_a*norm_b) if norm_a and norm_b else 0.0


def _value_difference(left: Any, right: Any) -> float | None:
    if left.kind != right.kind: return None
    try:
        if left.kind == "date":
            return float(abs((date.fromisoformat(str(left.value)) - date.fromisoformat(str(right.value))).days))
        if left.kind in {"quantity", "money", "percent", "duration", "version"} and left.unit == right.unit and left.currency == right.currency and left.per == right.per:
            return float(abs(float(left.value) - float(right.value)))
    except (ValueError, TypeError): pass
    return None
