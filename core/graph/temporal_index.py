"""Date-scoped indexes and joins for changes, comparisons, events, and relations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from foundation import TypedValue, compare_values
from .models import EvidenceState, FactRecord, TemporalKnowledgeGraph


@dataclass(frozen=True)
class TemporalChange:
    subject: str
    attribute: str
    from_value: TypedValue
    to_value: TypedValue
    from_date: date
    to_date: date
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class RelationEvidence:
    subject: str
    link: str
    target: str
    target_attribute: str
    target_value: TypedValue
    observed_on: date
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class EventEvidence:
    event: str
    event_date: date
    fact: FactRecord
    event_date_evidence_id: str


class TemporalIndex:
    def __init__(self, graph: TemporalKnowledgeGraph):
        self.graph = graph
        self._change_cache: dict[tuple[str, str], tuple[TemporalChange, ...]] = {}

    def get_entity(self, identifier: str):
        entity = self.graph.lexicon.resolve(identifier)
        if entity is None:
            return None
        return self.graph.entities.get(self.graph.entity_key(entity.name))

    def get_fact_history(self, subject: str, attribute: str) -> tuple[FactRecord, ...]:
        entity = self.graph.lexicon.resolve(subject)
        if entity is None:
            return ()
        return tuple(self.graph.facts_by_subject_attribute.get((self.graph.entity_key(entity.name), attribute), ()))

    def get_temporal_changes(self, subject: str, attribute: str) -> tuple[TemporalChange, ...]:
        entity = self.graph.lexicon.resolve(subject)
        if entity is None:
            return ()
        cache_key = (self.graph.entity_key(entity.name), attribute)
        if cache_key in self._change_cache:
            return self._change_cache[cache_key]
        records = [r for r in self.get_fact_history(subject, attribute)
                   if r.evidence_status == EvidenceState.VERIFIED_SUPPORT
                   and r.observed_on is not None and r.fact.value.op is None]
        # Collapse repeated same-day/equivalent observations, then expose
        # differing observations as candidate pairs in O(n log n). Observation
        # dates alone do not establish a transition or continuous validity.
        ordered = sorted(records, key=lambda item: (item.observed_on, item.source_row_id))
        daily: list[FactRecord] = []
        for record in ordered:
            if daily and daily[-1].observed_on == record.observed_on:
                equality = compare_values(daily[-1].fact.value, record.fact.value, "eq")
                if equality is True:
                    continue
                # Same-day conflicts are usually flagged during construction;
                # remain conservative if the index was assembled manually.
                if equality is False:
                    daily.pop()
                    daily.append(record)
                    continue
            daily.append(record)
        changes: list[TemporalChange] = []
        previous: FactRecord | None = None
        for current in daily:
            if previous is not None:
                equality = compare_values(previous.fact.value, current.fact.value, "eq")
                if equality is False:
                    changes.append(TemporalChange(
                        current.fact.subject, attribute, previous.fact.value, current.fact.value,
                        previous.observed_on, current.observed_on,
                        tuple(dict.fromkeys((previous.source_row_id, current.source_row_id))),
                    ))
            previous = current
        result = tuple(changes)
        self._change_cache[cache_key] = result
        return result

    def get_comparable_facts(self, subject: str, attribute: str, on_date: date) -> tuple[FactRecord, ...]:
        entity = self.graph.lexicon.resolve(subject)
        if entity is None:
            return ()
        source = [r for r in self.graph.facts_by_date.get(on_date, ())
                  if r.fact.subject == entity.name and r.fact.attribute == attribute
                  and r.evidence_status == EvidenceState.VERIFIED_SUPPORT and r.fact.value.op is None]
        peers = [r for r in self.graph.facts_by_date.get(on_date, ())
                 if r.fact.subject != entity.name and r.fact.attribute == attribute
                 and r.evidence_status == EvidenceState.VERIFIED_SUPPORT and r.fact.value.op is None]
        comparable_ids = {r.source_row_id for left in source for r in peers
                          if compare_values(left.fact.value, r.fact.value, "eq") is not None}
        return tuple(r for r in peers if r.source_row_id in comparable_ids)

    def get_verified_relations(self, subject: str, on_date: date) -> tuple[RelationEvidence, ...]:
        entity = self.graph.lexicon.resolve(subject)
        if entity is None:
            return ()
        links = [r for r in self.graph.relations_by_entity.get(self.graph.entity_key(entity.name), ())
                 if r.observed_on == on_date and r.evidence_status == EvidenceState.VERIFIED_SUPPORT]
        result: list[RelationEvidence] = []
        for link in links:
            target = self.graph.lexicon.resolve(str(link.fact.value.value))
            if target is None:
                continue
            for fact in self.graph.facts_by_date.get(on_date, ()):
                if fact.fact.subject == target.name and fact.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                    result.append(RelationEvidence(entity.name, link.fact.attribute, target.name,
                                                   fact.fact.attribute, fact.fact.value, on_date,
                                                   tuple(dict.fromkeys((link.source_row_id, fact.source_row_id)))))
        return tuple(result)

    def get_event_facts(self, event: str) -> tuple[EventEvidence, ...]:
        entity = self.graph.lexicon.resolve(event)
        event_entities = {resolved.name for name in self.graph.lexicon.events
                          if (resolved := self.graph.lexicon.resolve(name)) is not None}
        if entity is None or entity.name not in event_entities:
            return ()
        event_dates = [r for r in self.graph.facts_by_subject_attribute.get((self.graph.entity_key(entity.name), "date"), ())
                       if r.fact.subject == entity.name
                       and r.fact.value.kind == "date" and r.fact.value.op is None
                       and r.evidence_status == EvidenceState.VERIFIED_SUPPORT]
        results: list[EventEvidence] = []
        for event_record in event_dates:
            raw = str(event_record.fact.value.value)
            try:
                if len(raw) == 10:
                    event_day = date.fromisoformat(raw)
                else:
                    continue  # Year/month precision is insufficient for a day-level event join.
            except ValueError:
                continue
            for fact in self.graph.facts_by_date.get(event_day, ()):
                if fact.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                    results.append(EventEvidence(entity.name, event_day, fact, event_record.source_row_id))
        return tuple(results)
