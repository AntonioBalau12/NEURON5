"""Evidence lookup that preserves uncertainty, provenance, and self-exclusion."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import Any, Iterable, Mapping

from foundation import AtomicFact, TypedValue, compare_values
from .models import EvidenceQuery, EvidenceState, FactRecord, TemporalKnowledgeGraph


def _candidate_fact(candidate: AtomicFact | Mapping[str, Any]) -> AtomicFact | None:
    if isinstance(candidate, AtomicFact):
        return candidate
    try:
        value, error = TypedValue.parse(candidate.get("value"))
        subject, attribute = candidate.get("subject"), candidate.get("attribute")
        if error or value is None or not isinstance(subject, str) or not isinstance(attribute, str):
            return None
        return AtomicFact(subject, attribute, value)
    except (AttributeError, TypeError):
        return None


class EvidenceResolver:
    def __init__(self, graph: TemporalKnowledgeGraph):
        self.graph = graph

    def _normalize_candidate(self, fact: AtomicFact | None) -> AtomicFact | None:
        if fact is None:
            return None
        entity = self.graph.lexicon.resolve(fact.subject)
        if entity is None or fact.attribute not in entity.attributes:
            return fact
        value = fact.value
        if value.kind == "name" and isinstance(value.value, str):
            target = self.graph.lexicon.resolve(value.value)
            if target is not None:
                value = replace(value, value=target.name)
        return replace(fact, subject=entity.name, value=value)

    def find_supporting_evidence(
        self,
        candidate: AtomicFact | Mapping[str, Any],
        on_date: date | None = None,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> tuple[FactRecord, ...]:
        fact = self._normalize_candidate(_candidate_fact(candidate))
        if fact is None:
            return ()
        entity = self.graph.lexicon.resolve(fact.subject)
        if entity is None or fact.attribute not in entity.attributes:
            return ()
        excluded = set(exclude_evidence_ids)
        subject_key = self.graph.entity_key(entity.name)
        records = self.graph.facts_by_subject_attribute.get((subject_key, fact.attribute), ())
        return tuple(record for record in records
                     if record.evidence_status == EvidenceState.VERIFIED_SUPPORT
                     and record.source_row_id not in excluded
                     and self._date_applies(record, on_date)
                     and self._same_value(record.fact.value, fact.value))

    def find_contradicting_evidence(
        self,
        candidate: AtomicFact | Mapping[str, Any],
        on_date: date | None = None,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> tuple[FactRecord, ...]:
        fact = self._normalize_candidate(_candidate_fact(candidate))
        if fact is None:
            return ()
        entity = self.graph.lexicon.resolve(fact.subject)
        if entity is None:
            return ()
        excluded = set(exclude_evidence_ids)
        records = self.graph.facts_by_subject_attribute.get((self.graph.entity_key(entity.name), fact.attribute), ())
        return tuple(record for record in records
                     if record.evidence_status in {EvidenceState.VERIFIED_REFUTATION, EvidenceState.CONFLICTING}
                     and record.source_row_id not in excluded
                     and self._date_applies(record, on_date)
                     and (record.evidence_status == EvidenceState.CONFLICTING
                          or self._same_value(record.fact.value, fact.value)))

    def query(self, candidate: AtomicFact | Mapping[str, Any], on_date: date | None = None,
              exclude_evidence_ids: Iterable[str] = ()) -> EvidenceQuery:
        fact = self._normalize_candidate(_candidate_fact(candidate))
        if fact is None:
            return EvidenceQuery(EvidenceState.UNKNOWN, reason="candidate is not a valid atomic fact")
        entity = self.graph.lexicon.resolve(fact.subject)
        if entity is None or fact.attribute not in entity.attributes:
            return EvidenceQuery(EvidenceState.UNKNOWN, reason="unknown entity or attribute")
        excluded = set(exclude_evidence_ids)
        records = self.graph.facts_by_subject_attribute.get((self.graph.entity_key(entity.name), fact.attribute), ())
        relevant = tuple(r for r in records if r.source_row_id not in excluded and self._date_applies(r, on_date))
        support = tuple(r for r in relevant if r.evidence_status == EvidenceState.VERIFIED_SUPPORT and self._same_value(r.fact.value, fact.value))
        contradiction = tuple(r for r in relevant if r.evidence_status == EvidenceState.VERIFIED_REFUTATION and self._same_value(r.fact.value, fact.value))
        conflict = tuple(r for r in relevant if r.evidence_status == EvidenceState.CONFLICTING)
        candidates = tuple(r for r in relevant if r.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE and self._same_value(r.fact.value, fact.value))
        conflicting_values = tuple(r for r in conflict if not self._same_value(r.fact.value, fact.value))
        if contradiction and support:
            return EvidenceQuery(EvidenceState.CONFLICTING, support, contradiction, candidates,
                                 "independent support and refutation both apply")
        if contradiction:
            return EvidenceQuery(EvidenceState.VERIFIED_REFUTATION, support, contradiction, candidates, "explicit verified refutation")
        if conflict or (support and conflicting_values):
            return EvidenceQuery(EvidenceState.CONFLICTING, support, conflicting_values or conflict, candidates, "same-time evidence conflicts")
        if support:
            return EvidenceQuery(EvidenceState.VERIFIED_SUPPORT, support, (), candidates, "matching independent evidence")
        if candidates:
            return EvidenceQuery(EvidenceState.UNVERIFIED_CANDIDATE, (), (), candidates, "only unverified candidate evidence is available")
        return EvidenceQuery(EvidenceState.UNKNOWN, reason="no applicable evidence")

    def get_evidence(self, subject: str, attribute: str, on_date: date,
                     exclude_evidence_ids: Iterable[str] = ()) -> EvidenceQuery:
        entity = self.graph.lexicon.resolve(subject)
        if entity is None or attribute not in entity.attributes:
            return EvidenceQuery(EvidenceState.UNKNOWN, reason="unknown entity or attribute")
        excluded = set(exclude_evidence_ids)
        records = tuple(record for record in self.graph.facts_by_subject_attribute.get((self.graph.entity_key(entity.name), attribute), ())
                        if record.source_row_id not in excluded and (record.observed_on == on_date or (record.valid_from is not None and record.valid_from <= on_date and (record.valid_to is None or on_date <= record.valid_to))))
        supported = tuple(r for r in records if r.evidence_status == EvidenceState.VERIFIED_SUPPORT)
        candidates = tuple(r for r in records if r.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE)
        conflicts = tuple(r for r in records if r.evidence_status == EvidenceState.CONFLICTING)
        if conflicts:
            status = EvidenceState.CONFLICTING
        elif supported:
            status = EvidenceState.VERIFIED_SUPPORT
        elif candidates:
            status = EvidenceState.UNVERIFIED_CANDIDATE
        else:
            return EvidenceQuery(EvidenceState.UNKNOWN, reason="no evidence at requested date")
        return EvidenceQuery(status, supported, conflicts, candidates, "exact-date or explicit-interval evidence")

    @staticmethod
    def _date_applies(record: FactRecord, on_date: date | None) -> bool:
        if on_date is None:
            return True
        if record.observed_on == on_date:
            return True
        return record.valid_from is not None and record.valid_from <= on_date and (record.valid_to is None or on_date <= record.valid_to)

    @staticmethod
    def _same_value(left: TypedValue, right: TypedValue) -> bool:
        return compare_values(left, right, "eq") is True
