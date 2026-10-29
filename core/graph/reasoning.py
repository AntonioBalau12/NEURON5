"""Deterministic evidence reasoning with explicit abstention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from foundation import AtomicFact, TypedValue, compare_values
from .evidence_resolver import EvidenceResolver
from .models import EvidenceQuery, EvidenceState, TemporalKnowledgeGraph
from .temporal_index import TemporalIndex


@dataclass(frozen=True)
class ClaimResolution:
    status: EvidenceState
    confidence: float
    evidence_ids: tuple[str, ...]
    reason: str
    atomic_results: tuple[EvidenceQuery, ...] = ()


class ReasoningEngine:
    """Resolve claims only from independent, date-applicable graph evidence."""

    def __init__(self, graph: TemporalKnowledgeGraph):
        self.graph = graph
        self.resolver = EvidenceResolver(graph)
        self.temporal = TemporalIndex(graph)

    def evaluate_facts(self, facts: Sequence[AtomicFact], on_date: date | None,
                       exclude_evidence_ids: Sequence[str] = ()) -> ClaimResolution:
        if not facts:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "claim has no parsed atomic facts")
        results = tuple(self.resolver.query(fact, on_date, exclude_evidence_ids) for fact in facts)
        # A multi-fact sentence is false only when a specific atom is explicitly
        # refuted; false-labeled source rows never supply such atomic negation.
        if any(result.status == EvidenceState.VERIFIED_REFUTATION for result in results):
            status, reason = EvidenceState.VERIFIED_REFUTATION, "at least one atomic fact is explicitly refuted"
        elif all(result.status == EvidenceState.VERIFIED_SUPPORT for result in results):
            status, reason = EvidenceState.VERIFIED_SUPPORT, "all atomic facts have independent support"
        elif any(result.status == EvidenceState.CONFLICTING for result in results):
            status, reason = EvidenceState.CONFLICTING, "at least one atomic fact has conflicting evidence"
        elif any(result.status == EvidenceState.UNVERIFIED_CANDIDATE for result in results):
            status, reason = EvidenceState.UNVERIFIED_CANDIDATE, "only candidate evidence is available for at least one fact"
        else:
            status, reason = EvidenceState.UNKNOWN, "insufficient evidence for at least one fact"
        ids = tuple(dict.fromkeys(record.source_row_id for result in results
                                  for record in (*result.supporting, *result.contradicting, *result.candidates)))
        confidence = min((record.confidence for result in results for record in result.supporting), default=0.0) if status == EvidenceState.VERIFIED_SUPPORT else 0.0
        return ClaimResolution(status, confidence, ids, reason, results)

    def evaluate_evidence_row(self, source_row_id: str) -> ClaimResolution:
        """Evaluate one graph row while always excluding that row as evidence."""
        evidence = self.graph.evidence_by_id.get(source_row_id)
        if evidence is None:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "unknown evidence row")
        facts = tuple(dict.fromkeys(evidence.facts))
        return self.evaluate_facts(facts, evidence.observed_on, (source_row_id,))

    def evaluate_claim(self, claim_type: str, form: Mapping[str, Any], as_of: date = date(2026, 10, 29),
                       exclude_evidence_ids: Sequence[str] = ()) -> ClaimResolution:
        if claim_type == "fact":
            fact = _form_fact(form)
            return self.evaluate_facts((fact,) if fact else (), as_of, exclude_evidence_ids)
        if claim_type == "compare":
            return self._compare(form, as_of, exclude_evidence_ids)
        if claim_type == "change":
            return self._change(form, exclude_evidence_ids)
        if claim_type == "at_event":
            return self._at_event(form, exclude_evidence_ids)
        if claim_type == "relation":
            return self._relation(form, exclude_evidence_ids)
        return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), f"unsupported claim type {claim_type!r}")

    def _compare(self, form: Mapping[str, Any], on_date: date, excluded: Sequence[str]) -> ClaimResolution:
        left, right = form.get("left"), form.get("right")
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "invalid compare form")
        left_entity = self.graph.lexicon.resolve(str(left.get("subject", "")))
        right_entity = self.graph.lexicon.resolve(str(right.get("subject", "")))
        left_key = (left_entity.name if left_entity else str(left.get("subject", "")), left.get("attribute"))
        right_key = (right_entity.name if right_entity else str(right.get("subject", "")), right.get("attribute"))
        if left_key == right_key:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "a fact cannot be compared with itself")
        lquery = self.resolver.get_evidence(str(left.get("subject", "")), str(left.get("attribute", "")), on_date, excluded)
        rquery = self.resolver.get_evidence(str(right.get("subject", "")), str(right.get("attribute", "")), on_date, excluded)
        if lquery.status == EvidenceState.CONFLICTING or rquery.status == EvidenceState.CONFLICTING:
            return ClaimResolution(EvidenceState.CONFLICTING, 0.0, (), "one compared fact conflicts on the as-of date", (lquery, rquery))
        if lquery.status != EvidenceState.VERIFIED_SUPPORT or rquery.status != EvidenceState.VERIFIED_SUPPORT:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "both values need exact-date or explicit-interval support", (lquery, rquery))
        op = form.get("op")
        pairs: list[tuple[str, str]] = []
        for lrecord in lquery.supporting:
            for rrecord in rquery.supporting:
                comparison = compare_values(lrecord.fact.value, rrecord.fact.value, str(op))
                if comparison is True:
                    pairs.append((lrecord.source_row_id, rrecord.source_row_id))
        if not pairs:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "values are incomparable or do not establish the requested operator", (lquery, rquery))
        if any(eid in set(excluded) for pair in pairs for eid in pair):
            pairs = [pair for pair in pairs if not set(pair).intersection(excluded)]
        if not pairs:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "claim cannot use its own evidence", (lquery, rquery))
        evidence_ids = tuple(dict.fromkeys(eid for pair in pairs for eid in pair))
        return ClaimResolution(EvidenceState.VERIFIED_SUPPORT, 1.0, evidence_ids, "both compared values are date-grounded", (lquery, rquery))

    def _change(self, form: Mapping[str, Any], exclude_evidence_ids: Sequence[str]) -> ClaimResolution:
        from_value, from_error = TypedValue.parse(form.get("from"))
        to_value, to_error = TypedValue.parse(form.get("to"))
        if from_error or to_error or from_value is None or to_value is None:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "invalid change endpoint")
        changes = self.temporal.get_temporal_changes(str(form.get("subject", "")), str(form.get("attribute", "")))
        excluded = set(exclude_evidence_ids)
        for change in changes:
            if not set(change.evidence_ids).intersection(excluded) and compare_values(change.from_value, from_value, "eq") is True and compare_values(change.to_value, to_value, "eq") is True:
                return ClaimResolution(
                    EvidenceState.UNVERIFIED_CANDIDATE, 0.5, change.evidence_ids,
                    "different dated observations form a change candidate; observation dates do not establish a continuous validity interval or causal transition",
                )
        return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "no comparable ordered evidence supports this change")

    def _at_event(self, form: Mapping[str, Any], exclude_evidence_ids: Sequence[str]) -> ClaimResolution:
        value, error = TypedValue.parse(form.get("value"))
        if error or value is None:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "invalid event fact value")
        matches = [event for event in self.temporal.get_event_facts(str(form.get("event", "")))
                   if event.fact.fact.subject == str(form.get("subject", ""))
                   and event.fact.fact.attribute == form.get("attribute")
                   and not {event.event_date_evidence_id, event.fact.source_row_id}.intersection(exclude_evidence_ids)
                   and compare_values(event.fact.fact.value, value, "eq") is True]
        if matches:
            ids = tuple(dict.fromkeys(eid for event in matches for eid in (event.event_date_evidence_id, event.fact.source_row_id)))
            return ClaimResolution(EvidenceState.VERIFIED_SUPPORT, 1.0, ids, "fact is observed on the event date")
        return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "no exact-day event evidence supports the claim")

    def _relation(self, form: Mapping[str, Any], exclude_evidence_ids: Sequence[str]) -> ClaimResolution:
        value, error = TypedValue.parse(form.get("value"))
        if error or value is None:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "invalid relation value")
        link_entity = self.graph.lexicon.resolve(str(form.get("subject", "")))
        target_entity = self.graph.lexicon.resolve(str(form.get("target", "")))
        if link_entity is None or target_entity is None:
            return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "unknown relation subject or target")
        link_records = self.graph.facts_by_subject_attribute.get((self.graph.entity_key(link_entity.name), str(form.get("link", ""))), ())
        target_records = self.graph.facts_by_subject_attribute.get((self.graph.entity_key(target_entity.name), str(form.get("attribute", ""))), ())
        matches: list[tuple[str, str]] = []
        for link in link_records:
            named_target = self.graph.lexicon.resolve(str(link.fact.value.value)) if link.fact.value.kind == "name" else None
            if link.evidence_status != EvidenceState.VERIFIED_SUPPORT or named_target is None or named_target.name != target_entity.name:
                continue
            for target in target_records:
                if target.evidence_status == EvidenceState.VERIFIED_SUPPORT and target.observed_on == link.observed_on and target.observed_on is not None and not {link.source_row_id, target.source_row_id}.intersection(exclude_evidence_ids) and compare_values(target.fact.value, value, "eq") is True:
                    matches.append((link.source_row_id, target.source_row_id))
        if matches:
            ids = tuple(dict.fromkeys(eid for pair in matches for eid in pair))
            return ClaimResolution(EvidenceState.VERIFIED_SUPPORT, 1.0, ids, "link and target fact are observed on the same date")
        return ClaimResolution(EvidenceState.UNKNOWN, 0.0, (), "no co-temporal verified relation evidence")


def _form_fact(form: Mapping[str, Any]) -> AtomicFact | None:
    value, error = TypedValue.parse(form.get("value"))
    subject, attribute = form.get("subject"), form.get("attribute")
    if error or value is None or not isinstance(subject, str) or not isinstance(attribute, str):
        return None
    return AtomicFact(subject, attribute, value)
