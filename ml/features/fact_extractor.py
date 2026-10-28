"""Fact-Aware Feature Extractor.

Accepts:
- Claim text
- Claim publication date
- Lexicon
- Temporal Evidence Graph
- Optional claim ID for self-evidence exclusion

Extracts:
1. Parser features:
   - entity_detected
   - attribute_detected
   - value_detected
   - parse_coverage
   - parsed_fact_count
   - negation_detected

2. Knowledge Graph features:
   - entity_match
   - attribute_match
   - exact_value_match
   - value_difference
   - date_difference_days
   - verified_support_count
   - verified_refutation_count
   - candidate_evidence_count
   - conflict_count
   - temporal_compatibility
   - evidence_available

3. Evidence-quality features:
   - best_evidence_similarity
   - evidence_date_distance
   - independent_evidence_count

Missing values are represented as float('nan') along with explicit missing indicator flags.
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any, Mapping, Sequence

from foundation import (
    AtomicFact,
    Lexicon,
    TypedValue,
    compare_values,
    normalize_date,
)
from core.graph.models import (
    EvidenceState,
    FactRecord,
    ParseStatus,
    TemporalKnowledgeGraph,
)
from core.graph.parsing import (
    TextFactParser,
    _attribute_mentions,
    _entity_mentions,
    _value_spans,
)
from core.graph.evidence_resolver import EvidenceResolver

_NEGATION_RE = re.compile(
    r"\b(?:not|never|no|without|isn't|aren't|doesn't|didn't|hasn't|haven't|wasn't|weren't|won't|cannot|can't)\b",
    re.IGNORECASE,
)

PARSER_FEATURE_NAMES = (
    "entity_detected",
    "attribute_detected",
    "value_detected",
    "parse_coverage",
    "parsed_fact_count",
    "negation_detected",
)

GRAPH_FEATURE_NAMES = (
    "entity_match",
    "attribute_match",
    "exact_value_match",
    "value_difference",
    "date_difference_days",
    "verified_support_count",
    "verified_refutation_count",
    "candidate_evidence_count",
    "conflict_count",
    "temporal_compatibility",
    "evidence_available",
    "best_evidence_similarity",
    "evidence_date_distance",
    "independent_evidence_count",
    "value_difference_missing",
    "date_difference_missing",
    "temporal_compatibility_missing",
)

ALL_FEATURE_NAMES = PARSER_FEATURE_NAMES + GRAPH_FEATURE_NAMES


def _token_jaccard(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _numeric_value(val: TypedValue) -> float | None:
    if val.kind in {"quantity", "money", "percent", "duration"}:
        if isinstance(val.value, (int, float)):
            return float(val.value)
    return None


class FactAwareFeatureExtractor:
    """Reusable feature extractor combining TextFactParser and TemporalKnowledgeGraph."""

    def __init__(
        self,
        lexicon: Lexicon,
        graph: TemporalKnowledgeGraph | None = None,
        parser: TextFactParser | None = None,
        attribute_kinds: Mapping[str, str] | None = None,
        known_units: Sequence[str] = (),
    ):
        self.lexicon = lexicon
        self.graph = graph
        self.parser = parser or TextFactParser(
            lexicon=lexicon,
            attribute_kinds=attribute_kinds,
            known_units=known_units,
        )
        self.resolver = EvidenceResolver(graph) if graph is not None else None

    def set_graph(self, graph: TemporalKnowledgeGraph) -> None:
        self.graph = graph
        self.resolver = EvidenceResolver(graph)

    def extract_features(
        self,
        text: str,
        claim_date: str | date | None,
        lexicon: Lexicon | None = None,
        graph: TemporalKnowledgeGraph | None = None,
        exclude_claim_id: str | None = None,
    ) -> dict[str, float]:
        lex = lexicon or self.lexicon
        g = graph or self.graph
        parser = self.parser

        norm_date: date | None = None
        if claim_date is not None:
            norm_date, _ = normalize_date(claim_date)

        # 1. PARSER FEATURES
        # Entity detection
        entity_mentions = _entity_mentions(text, lex)
        entity_detected = 1.0 if entity_mentions else 0.0

        # Attribute detection
        attribute_detected = 0.0
        detected_entities = [ent for _, _, ent in entity_mentions]
        detected_attr_names: set[tuple[str, str]] = set()
        for ent in detected_entities:
            attr_spans = _attribute_mentions(text, ent)
            if attr_spans:
                attribute_detected = 1.0
                for _, _, attr_name, _ in attr_spans:
                    detected_attr_names.add((ent.name, attr_name))

        # Value detection
        value_spans = _value_spans(text, entity_mentions, parser.known_units)
        value_detected = 1.0 if value_spans else 0.0

        # Text parsing
        parsed = parser.parse(text)
        parse_coverage = float(parsed.confidence)
        parsed_fact_count = float(len(parsed.facts))

        # Negation detection
        negation_detected = 1.0 if bool(_NEGATION_RE.search(text)) else 0.0

        # 2. GRAPH & EVIDENCE FEATURES
        entity_match = 0.0
        attribute_match = 0.0
        exact_value_match = 0.0
        value_difference = float("nan")
        date_difference_days = float("nan")
        verified_support_count = 0.0
        verified_refutation_count = 0.0
        candidate_evidence_count = 0.0
        conflict_count = 0.0
        temporal_compatibility = float("nan")
        evidence_available = 0.0

        best_evidence_similarity = 0.0
        evidence_date_distance = float("nan")
        independent_evidence_count = 0.0

        if g is not None:
            # Check entity match in graph
            for ent in detected_entities:
                subj_k = g.entity_key(ent.name)
                if subj_k in g.entities:
                    entity_match = 1.0
                    break

            # Collect all relevant records from the graph for parsed facts or detected entity/attrs
            # Exclude self-evidence
            all_records: list[FactRecord] = []
            claimed_facts: list[AtomicFact] = list(parsed.facts)

            # If facts were parsed:
            if claimed_facts:
                for f in claimed_facts:
                    subj_k = g.entity_key(f.subject)
                    recs = [
                        r
                        for r in g.facts_by_subject_attribute.get((subj_k, f.attribute), [])
                        if r.source_row_id != exclude_claim_id
                    ]
                    if recs:
                        attribute_match = 1.0
                        evidence_available = 1.0
                        all_records.extend(recs)
            else:
                # Even if full facts were not parsed, check if any detected (entity, attribute) pair has evidence
                for ent_name, attr_name in detected_attr_names:
                    subj_k = g.entity_key(ent_name)
                    recs = [
                        r
                        for r in g.facts_by_subject_attribute.get((subj_k, attr_name), [])
                        if r.source_row_id != exclude_claim_id
                    ]
                    if recs:
                        attribute_match = 1.0
                        evidence_available = 1.0
                        all_records.extend(recs)

            # Deduplicate records by key and source_row_id
            seen_record_keys: set[tuple[str, str, Any, str]] = set()
            unique_records: list[FactRecord] = []
            for r in all_records:
                rec_sig = (r.fact.subject.casefold(), r.fact.attribute, r.fact.value.key(), r.source_row_id)
                if rec_sig not in seen_record_keys:
                    seen_record_keys.add(rec_sig)
                    unique_records.append(r)

            if unique_records:
                evidence_available = 1.0
                distinct_source_ids = {r.source_row_id for r in unique_records}
                independent_evidence_count = float(len(distinct_source_ids))

                # Count evidence states
                support_recs: list[FactRecord] = []
                refute_recs: list[FactRecord] = []
                cand_recs: list[FactRecord] = []
                conf_recs: list[FactRecord] = []

                for r in unique_records:
                    if r.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                        support_recs.append(r)
                    elif r.evidence_status == EvidenceState.VERIFIED_REFUTATION:
                        refute_recs.append(r)
                    elif r.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE:
                        cand_recs.append(r)
                    elif r.evidence_status == EvidenceState.CONFLICTING:
                        conf_recs.append(r)

                verified_support_count = float(len(support_recs))
                verified_refutation_count = float(len(refute_recs))
                candidate_evidence_count = float(len(cand_recs))
                conflict_count = float(len(conf_recs))

                # Check exact value match against verified support
                if claimed_facts:
                    for cf in claimed_facts:
                        for sr in support_recs:
                            if sr.fact.attribute == cf.attribute:
                                if compare_values(sr.fact.value, cf.value, "eq") is True:
                                    exact_value_match = 1.0
                                    break
                        if exact_value_match > 0.0:
                            break

                # Compute value difference (numeric or date)
                min_val_diff = float("inf")
                if claimed_facts:
                    for cf in claimed_facts:
                        cf_num = _numeric_value(cf.value)
                        for r in unique_records:
                            if r.fact.attribute == cf.attribute:
                                r_num = _numeric_value(r.fact.value)
                                if cf_num is not None and r_num is not None:
                                    rel_diff = abs(cf_num - r_num) / (abs(r_num) + 1e-6)
                                    if rel_diff < min_val_diff:
                                        min_val_diff = rel_diff
                if min_val_diff < float("inf"):
                    value_difference = float(min_val_diff)

                # Compute date difference
                if norm_date is not None:
                    min_date_diff = float("inf")
                    for r in unique_records:
                        if r.observed_on is not None:
                            d_diff = abs((norm_date - r.observed_on).days)
                            if d_diff < min_date_diff:
                                min_date_diff = float(d_diff)
                    if min_date_diff < float("inf"):
                        date_difference_days = float(min_date_diff)

                # Compute temporal compatibility
                if norm_date is not None and support_recs:
                    has_exact_date = any(r.observed_on == norm_date for r in support_recs if r.observed_on is not None)
                    if has_exact_date:
                        temporal_compatibility = 1.0
                    elif date_difference_days <= 30.0:
                        temporal_compatibility = 0.5
                    elif not math.isnan(date_difference_days):
                        temporal_compatibility = 0.0
                elif support_recs:
                    # No claim date provided, but support exists
                    temporal_compatibility = 0.5

                # Compute best evidence similarity and date distance
                claim_tokens = set(re.findall(r"\w+", text.casefold()))
                best_sim = 0.0
                best_ev_date: date | None = None
                for row_id in distinct_source_ids:
                    ev_obj = g.evidence_by_id.get(row_id)
                    if ev_obj and ev_obj.text:
                        ev_tokens = set(re.findall(r"\w+", ev_obj.text.casefold()))
                        sim = _token_jaccard(claim_tokens, ev_tokens)
                        if sim > best_sim:
                            best_sim = sim
                            best_ev_date = ev_obj.observed_on
                    elif ev_obj and ev_obj.observed_on is not None and best_ev_date is None:
                        best_ev_date = ev_obj.observed_on

                best_evidence_similarity = float(best_sim)
                if norm_date is not None and best_ev_date is not None:
                    evidence_date_distance = float(abs((norm_date - best_ev_date).days))

        return {
            "entity_detected": entity_detected,
            "attribute_detected": attribute_detected,
            "value_detected": value_detected,
            "parse_coverage": parse_coverage,
            "parsed_fact_count": parsed_fact_count,
            "negation_detected": negation_detected,
            "entity_match": entity_match,
            "attribute_match": attribute_match,
            "exact_value_match": exact_value_match,
            "value_difference": value_difference,
            "date_difference_days": date_difference_days,
            "verified_support_count": verified_support_count,
            "verified_refutation_count": verified_refutation_count,
            "candidate_evidence_count": candidate_evidence_count,
            "conflict_count": conflict_count,
            "temporal_compatibility": temporal_compatibility,
            "evidence_available": evidence_available,
            "best_evidence_similarity": best_evidence_similarity,
            "evidence_date_distance": evidence_date_distance,
            "independent_evidence_count": independent_evidence_count,
            "value_difference_missing": 1.0 if math.isnan(value_difference) else 0.0,
            "date_difference_missing": 1.0 if math.isnan(date_difference_days) else 0.0,
            "temporal_compatibility_missing": 1.0 if math.isnan(temporal_compatibility) else 0.0,
        }


def extract_fact_features(
    text: str,
    claim_date: str | date | None,
    lexicon: Lexicon,
    graph: TemporalKnowledgeGraph,
    exclude_claim_id: str | None = None,
    parser: TextFactParser | None = None,
) -> dict[str, float]:
    """Functional wrapper for extract_features."""
    extractor = FactAwareFeatureExtractor(lexicon=lexicon, graph=graph, parser=parser)
    return extractor.extract_features(
        text=text,
        claim_date=claim_date,
        exclude_claim_id=exclude_claim_id,
    )

