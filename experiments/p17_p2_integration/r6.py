"""Leakage-safe P1.7/P2 adapters for the R6 experiment.

P1.7 produces text-grounded, unverified claim hypotheses. P2 evidence may rank
compatible attributes for those hypotheses; it never supplies asserted values.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import date
from typing import Iterable, Mapping, Sequence

from foundation import AtomicFact, EvidenceRecord, InputData, Lexicon, TypedValue
from core.graph.builder import build_graph
from core.graph.evidence_resolver import EvidenceResolver
from core.graph.models import EvidenceState, TemporalKnowledgeGraph
from core.graph.parsing import _attribute_mentions, _entity_mentions
from core.graph.semantic_extraction import ExpandedDeterministicExtractor
from core.retrieval.features import FEATURE_NAMES, RetrievalFeatureExtractor
from core.retrieval.hybrid import HybridEvidenceRetriever
from experiments.p17_recall.candidate_factory import (Candidate, CandidateFactory, ValueSpan,
                                                      _kind_compatible)


def build_evidence_retriever(rows: Sequence[EvidenceRecord], lexicon: Lexicon
                             ) -> tuple[TemporalKnowledgeGraph, HybridEvidenceRetriever]:
    """Build P2 indexes/graph from exactly the supplied training evidence rows."""
    graph, retriever, _timings = build_evidence_runtime(rows, lexicon)
    return graph, retriever


def build_evidence_runtime(rows: Sequence[EvidenceRecord], lexicon: Lexicon
                           ) -> tuple[TemporalKnowledgeGraph, HybridEvidenceRetriever, dict[str, float]]:
    """Build P1.6 graph, then P2 BM25 indexes and report their times separately."""
    t0 = time.perf_counter()
    graph = build_graph(InputData(list(rows), lexicon),
                        extractor=ExpandedDeterministicExtractor(lexicon))
    graph_seconds = time.perf_counter() - t0
    t0 = time.perf_counter()
    retriever = HybridEvidenceRetriever(graph)
    index_seconds = time.perf_counter() - t0
    return graph, retriever, {"graph_construction_seconds": graph_seconds,
                              "p2_bm25_index_construction_seconds": index_seconds}


def _record_is_temporally_compatible(record, claim_date: date | None) -> bool:
    # Reuse P1.6's conservative date policy, especially exact-date refutations.
    return EvidenceResolver._date_applies(record, claim_date)


def evidence_attribute_hints(
    results,
    graph: TemporalKnowledgeGraph,
    allowed_reference_ids: set[str],
    query_id: str,
    query_date: date | None,
    candidate_subjects: Iterable[str],
) -> tuple[dict[tuple[str, str], dict[str, float]], dict[str, list[str]]]:
    """Suggest attributes only for subjects already hypothesized from query text.

    Returned facts contribute subject/attribute/type/provenance hints. Their
    values are never returned to CandidateFactory and cannot become candidates.
    """
    allowed_subjects = {graph.entity_key(s) for s in candidate_subjects}
    scores: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    sources: dict[str, list[str]] = defaultdict(list)
    permitted_states = {EvidenceState.VERIFIED_SUPPORT, EvidenceState.VERIFIED_REFUTATION,
                        EvidenceState.CONFLICTING}
    for rank, result in enumerate(results, start=1):
        eid = str(result.evidence_id)
        if eid == query_id or eid not in allowed_reference_ids or not result.provenance:
            continue
        evidence = graph.evidence_by_id.get(eid)
        if evidence is None:
            continue
        for fact in result.facts:
            key = (graph.entity_key(fact.subject), fact.attribute)
            records = graph.facts_by_subject_attribute.get(key, ())
            valid = [record for record in records if record.source_row_id == eid
                     and record.evidence_status in permitted_states
                     and _record_is_temporally_compatible(record, query_date)]
            if not valid or key[0] not in allowed_subjects:
                continue
            entity = graph.lexicon.resolve(fact.subject)
            if entity is None or fact.attribute not in entity.attributes:
                continue
            hint_key = (entity.name, fact.value.kind)
            score = 1.0 / (60.0 + rank)
            prior = scores[hint_key].get(fact.attribute, 0.0)
            if score > prior:
                scores[hint_key][fact.attribute] = score
            sources[f"{entity.name}\t{fact.value.kind}\t{fact.attribute}"].append(eid)
    return {key: dict(value) for key, value in scores.items()}, {
        key: sorted(set(value)) for key, value in sources.items()
    }


def expand_candidates_with_evidence(
    candidates: Sequence[Candidate],
    factory: CandidateFactory,
    attribute_hints: Mapping[tuple[str, str], Mapping[str, float]],
    hint_sources: Mapping[str, Sequence[str]],
) -> list[Candidate]:
    """Add compatible attribute hypotheses over existing text-grounded spans."""
    result = list(candidates)
    existing = {candidate.key() for candidate in result}
    for source in candidates:
        entity = factory.lexicon.resolve(source.fact.subject)
        if entity is None or source.value_span is None:
            continue
        hints = attribute_hints.get((entity.name, source.fact.value.kind), {})
        for attribute, score in sorted(hints.items()):
            if attribute not in entity.attributes:
                continue
            if not _kind_compatible(attribute, source.fact.value, factory.attribute_kinds):
                continue
            fact = AtomicFact(entity.name, attribute, source.fact.value, source.fact.subject)
            candidate = Candidate(source.row_id, fact, source.entity_span, source.value_span,
                                  source.clause_id, methods=set(source.methods),
                                  scores=dict(source.scores),
                                  matched_example_ids=set(source.matched_example_ids),
                                  ambiguous_entity=source.ambiguous_entity,
                                  evidence_state=source.evidence_state)
            # Scores attached to another attribute do not transfer. Keep the
            # text subject/value provenance, then attach only this hint's source.
            for method, score_key in (("attribute_cue", "attribute_cue"),
                                      ("tfidf_resolver_top20", "resolver"),
                                      ("bm25_multiview", "bm25_rrf")):
                candidate.methods.discard(method)
                candidate.scores.pop(score_key, None)
            for score_key in tuple(candidate.scores):
                if score_key.startswith("bm25_"):
                    candidate.scores.pop(score_key, None)
            candidate.methods.add("p2_evidence_attribute_link")
            candidate.scores["p2_evidence_attribute_link"] = float(score)
            source_key = f"{entity.name}\t{source.fact.value.kind}\t{attribute}"
            candidate.matched_example_ids.update(
                f"p2_evidence:{eid}" for eid in hint_sources.get(source_key, ())
            )
            if candidate.key() not in existing:
                result.append(candidate)
                existing.add(candidate.key())
    return result


def evidence_guided_ranking(candidates: Sequence[Candidate]) -> list[Candidate]:
    """Experimental evidence-first ordering; P1.7 R5 weights are not reused."""
    return sorted(candidates, key=lambda candidate: (
        -candidate.scores.get("p2_evidence_attribute_link", 0.0),
        -candidate.rank_score,
        candidate.key(),
    ))


def deterministic_name_version_boolean_spans(
    text: str, lexicon: Lexicon, attribute_kinds: Mapping[str, str]
) -> list[ValueSpan]:
    """Extract conservative name/version/polarity spans from the claim itself."""
    spans: dict[tuple[int, int, tuple], ValueSpan] = {}
    # Explicit quoted names are valid values only when a name-valued relation is
    # present in the same claim; the candidate factory still enforces schema.
    entity_mentions = _entity_mentions(text, lexicon)
    name_attributes = {attr for entity in lexicon.entities for attr in entity.attributes
                       if attribute_kinds.get(attr) == "name"}
    has_name_cue = False
    for _start, _end, entity in entity_mentions:
        for _a, _b, attr, _score in _attribute_mentions(text, entity, expanded=True):
            has_name_cue = has_name_cue or attr in name_attributes
    if has_name_cue:
        for match in re.finditer(r"[\"“]([^\"”]{1,80})[\"”]", text):
            start, end = match.start(1), match.end(1)
            value = text[start:end].strip()
            if value and value.casefold() not in {entity.name.casefold() for _, _, entity in entity_mentions}:
                value_start = start + len(text[start:end]) - len(text[start:end].lstrip())
                span = ValueSpan(TypedValue("name", value), value_start, value_start + len(value),
                                 "quoted_name_relation_span")
                spans[(span.start, span.end, span.value.key())] = span

        # Relationship grammar: a name follows a schema-recognized attribute
        # cue and a short copular/role connector. Only the captured text is used.
        for _a, _b, entity in entity_mentions:
            for cue_start, cue_end, attr, _score in _attribute_mentions(text, entity, expanded=True):
                if attr not in name_attributes or attr not in entity.attributes:
                    continue
                tail = text[cue_end:]
                match = re.match(
                    r"\s*(?:is|was|are|were|named|called|known\s+as|led\s+by|headed\s+by|reports\s+to|:)\s+"
                    r"([A-Z][\w'’.-]*(?:\s+[A-Z][\w'’.-]*){0,3})",
                    tail,
                )
                if match:
                    start, end = cue_end + match.start(1), cue_end + match.end(1)
                    value = text[start:end]
                    span = ValueSpan(TypedValue("name", value), start, end,
                                     "attribute_relation_name_span")
                    spans[(start, end, span.value.key())] = span

    # Version values are accepted when explicitly prefixed or attached to a
    # version-valued attribute cue. Do not reinterpret arbitrary decimals.
    version_attributes = {attr for entity in lexicon.entities for attr in entity.attributes
                          if attribute_kinds.get(attr) == "version"}
    version_prefix = re.compile(r"\b(?:v|version\s*)\s*(\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?)\b", re.I)
    version_ranges: list[tuple[int, int]] = [(m.start(1), m.end(1)) for m in version_prefix.finditer(text)]
    for _a, _b, entity in entity_mentions:
        for cue_start, cue_end, attr, _score in _attribute_mentions(text, entity, expanded=True):
            if attr not in version_attributes:
                continue
            local = text[cue_end:min(len(text), cue_end + 80)]
            for match in re.finditer(r"\b(\d+(?:\.\d+){1,3}(?:[-+][A-Za-z0-9.-]+)?)\b", local):
                version_ranges.append((cue_end + match.start(1), cue_end + match.end(1)))
    for start, end in version_ranges:
        value = text[start:end]
        span = ValueSpan(TypedValue("version", value), start, end, "version_relation_span")
        spans[(start, end, span.value.key())] = span

    # Improve scoped boolean negation while retaining an actual schema cue.
    negative = re.compile(r"\b(?:not|never|no\s+longer|without|lack(?:s|ed)?|isn't|aren't|wasn't|weren't|doesn't|didn't|hasn't|haven't)\b", re.I)
    positive = re.compile(r"\b(?:is|are|was|were|has|have|does|do|supports?|provides?|offers?|includes?|allows?|requires?)\b", re.I)
    for _a, _b, entity in entity_mentions:
        for cue_start, cue_end, attr, _score in _attribute_mentions(text, entity, expanded=True):
            if attribute_kinds.get(attr) != "boolean":
                continue
            left = max(0, cue_start - 64)
            right = min(len(text), cue_end + 64)
            context = text[left:right]
            neg = list(negative.finditer(context))
            pos = list(positive.finditer(context))
            if neg and (not pos or max(m.end() for m in neg) >= max(m.end() for m in pos)):
                value = False
            elif pos:
                value = True
            else:
                continue
            span = ValueSpan(TypedValue("boolean", value), cue_start, cue_end,
                             "boolean_relation_polarity_span")
            spans[(cue_start, cue_end, span.value.key())] = span
    return sorted(spans.values(), key=lambda item: (item.start, item.end, item.value.kind,
                                                    str(item.value.value)))


def candidates_to_row_features(candidates: Sequence[Candidate], stats: Mapping,
                               temporal_counts: Mapping[str, int]) -> dict[str, float]:
    kinds = ("quantity", "money", "percent", "date", "duration", "name", "boolean", "version")
    methods = {method for candidate in candidates for method in candidate.methods}
    result = {
        "candidate_count": float(len(candidates)),
        "candidate_subject_count": float(len({candidate.fact.subject for candidate in candidates})),
        "candidate_attribute_count": float(len({candidate.fact.attribute for candidate in candidates})),
        "ambiguous_candidate_count": float(sum(candidate.ambiguous_entity for candidate in candidates)),
        "mean_candidate_rank_score": float(sum(candidate.rank_score for candidate in candidates) / max(1, len(candidates))),
        "max_candidate_rank_score": float(max((candidate.rank_score for candidate in candidates), default=0.0)),
        "evidence_linked_candidate_count": float(sum("p2_evidence_attribute_link" in c.methods for c in candidates)),
        "implicit_subject_candidate_count": float(sum(bool({"same_row_pronoun_antecedent", "same_sentence_subject_carry"} & c.methods) for c in candidates)),
        "semantic_parser_candidate_count": float(len(candidates)),
        "p1_unparsed": float(bool(stats.get("deadline_exceeded", False))),
    }
    for kind in kinds:
        result[f"candidate_kind_{kind}"] = float(sum(c.fact.value.kind == kind for c in candidates))
    for state in ("VERIFIED_SUPPORT", "VERIFIED_REFUTATION", "UNVERIFIED_CANDIDATE", "CONFLICTING", "UNKNOWN"):
        result[f"alignment_{state.lower()}"] = float(temporal_counts.get(state, 0))
    return result


def align_candidates(candidates: Sequence[Candidate], graph: TemporalKnowledgeGraph,
                     query_id: str, query_date: date | None) -> dict[str, int]:
    resolver = EvidenceResolver(graph)
    counts = {state.value: 0 for state in EvidenceState}
    for candidate in candidates:
        result = resolver.query(candidate.fact, on_date=query_date,
                                exclude_evidence_ids=(query_id,))
        counts[result.status.value] += 1
    return counts


def p2_feature_values(extractor: RetrievalFeatureExtractor, results, text: str,
                      query_date: date | None) -> dict[str, float]:
    raw = extractor.extract_from_results(results, text, query_date)
    return {name: float(raw[name]) for name in FEATURE_NAMES}
