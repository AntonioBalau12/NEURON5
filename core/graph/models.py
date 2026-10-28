"""Typed records and indexes for the in-memory temporal evidence graph."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping

from foundation import AtomicFact, Lexicon, TypedValue


class EvidenceState(str, Enum):
    VERIFIED_SUPPORT = "VERIFIED_SUPPORT"
    VERIFIED_REFUTATION = "VERIFIED_REFUTATION"
    UNVERIFIED_CANDIDATE = "UNVERIFIED_CANDIDATE"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class ParseStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNPARSED = "unparsed"
    FORM_GROUNDED = "form_grounded"


@dataclass(frozen=True)
class EntityNode:
    identifier: str
    name: str
    aliases: tuple[str, ...]
    attributes: frozenset[str]
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FactRecord:
    fact: AtomicFact
    observed_on: date | None
    valid_from: date | None
    valid_to: date | None
    source_row_id: str
    evidence_status: EvidenceState
    parse_status: ParseStatus
    provenance: str
    confidence: float
    supporting_evidence: tuple[str, ...] = ()
    contradicting_evidence: tuple[str, ...] = ()

    @property
    def key(self) -> tuple[Any, ...]:
        return (self.fact.subject.casefold(), self.fact.attribute, self.fact.value.key())


@dataclass(frozen=True)
class ExtractionCandidate:
    fact: AtomicFact
    source_row_id: str
    method: str
    confidence: float
    span_start: int | None = None
    span_end: int | None = None
    ambiguous: bool = False
    observed_on: date | None = None
    subject_span_start: int | None = None
    subject_span_end: int | None = None


@dataclass(frozen=True)
class GraphEvidence:
    source_row_id: str
    text: str
    label: str | None
    observed_on: date | None
    facts: tuple[AtomicFact, ...]
    parse_status: ParseStatus
    coverage: float
    provenance: str
    issues: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()
    extraction_candidates: tuple[ExtractionCandidate, ...] = ()


@dataclass(frozen=True)
class EvidenceQuery:
    status: EvidenceState
    supporting: tuple[FactRecord, ...] = ()
    contradicting: tuple[FactRecord, ...] = ()
    candidates: tuple[FactRecord, ...] = ()
    reason: str = ""


@dataclass
class TemporalKnowledgeGraph:
    lexicon: Lexicon
    entities: dict[str, EntityNode]
    evidence_by_id: dict[str, GraphEvidence] = field(default_factory=dict)
    facts_by_subject_attribute: dict[tuple[str, str], list[FactRecord]] = field(default_factory=lambda: defaultdict(list))
    facts_by_date: dict[date, list[FactRecord]] = field(default_factory=lambda: defaultdict(list))
    facts_by_key: dict[tuple[Any, ...], list[FactRecord]] = field(default_factory=lambda: defaultdict(list))
    candidate_facts_by_key: dict[tuple[Any, ...], list[FactRecord]] = field(default_factory=lambda: defaultdict(list))
    relations_by_entity: dict[str, list[FactRecord]] = field(default_factory=lambda: defaultdict(list))
    candidates_by_row: dict[str, tuple[FactRecord, ...]] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @staticmethod
    def entity_key(subject: str) -> str:
        return Lexicon.normalize_name(subject)

    def add_fact(self, record: FactRecord) -> None:
        existing = self.facts_by_key.get(record.key, ())
        if any(item.source_row_id == record.source_row_id and item.fact.value.key() == record.fact.value.key()
               and item.evidence_status == record.evidence_status for item in existing):
            return
        subject_key = self.entity_key(record.fact.subject)
        self.facts_by_subject_attribute[(subject_key, record.fact.attribute)].append(record)
        self.facts_by_key[record.key].append(record)
        if record.observed_on is not None:
            self.facts_by_date[record.observed_on].append(record)
        if record.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE:
            self.candidate_facts_by_key[record.key].append(record)
            self.candidates_by_row[record.source_row_id] = (*self.candidates_by_row.get(record.source_row_id, ()), record)
        if record.evidence_status == EvidenceState.VERIFIED_SUPPORT and record.fact.value.kind == "name":
            target = self.lexicon.resolve(str(record.fact.value.value))
            if target is not None:
                self.relations_by_entity[subject_key].append(record)

    def sort_indexes(self) -> None:
        for values in self.facts_by_subject_attribute.values():
            values.sort(key=lambda item: (item.observed_on or date.min, item.source_row_id))
        for values in self.facts_by_date.values():
            values.sort(key=lambda item: (item.fact.subject, item.fact.attribute, item.source_row_id))


def entity_nodes(lexicon: Lexicon) -> dict[str, EntityNode]:
    """Create one canonical node per lexicon entity."""
    return {
        Lexicon.normalize_name(entity.name): EntityNode(
            identifier=Lexicon.normalize_name(entity.name),
            name=entity.name,
            aliases=entity.aliases,
            attributes=entity.attributes,
        )
        for entity in lexicon.entities
    }
