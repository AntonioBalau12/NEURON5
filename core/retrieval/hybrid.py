"""Hybrid Evidence Retriever combining Temporal Graph lookups and BM25 lexical search."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import re
from typing import Any, Iterable, Mapping, Sequence

from foundation import AtomicFact, TypedValue, compare_values, normalize_date
from core.graph.evidence_resolver import EvidenceResolver
from core.graph.models import EvidenceState, GraphEvidence, ParseStatus, TemporalKnowledgeGraph
from core.graph.parsing import TextFactParser, _entity_mentions, _attribute_mentions
from core.graph.reasoning import ClaimResolution, ReasoningEngine
from core.retrieval.bm25 import ATTRIBUTE_SYNONYMS, BM25Index, RetrievedEvidence, _extract_dates


class HybridEvidenceRetriever:
    """Hybrid evidence retrieval over a TemporalKnowledgeGraph using graph structures and BM25."""

    def __init__(
        self,
        graph: TemporalKnowledgeGraph,
        bm25_index: BM25Index | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        include_attribute_synonyms: bool = True,
    ):
        self.graph = graph
        self.resolver = EvidenceResolver(graph)
        self.reasoning = ReasoningEngine(graph)
        # Prepare TextFactParser using graph lexicon
        attribute_kinds: dict[str, str] = {}
        known_units: set[str] = set()
        for ev in graph.evidence_by_id.values():
            for fact in ev.facts:
                attribute_kinds.setdefault(fact.attribute, fact.value.kind)
                if fact.value.kind in {"quantity", "duration"} and fact.value.unit:
                    known_units.add(fact.value.unit)
        self.parser = TextFactParser(graph.lexicon, attribute_kinds, known_units)
        self.bm25 = (
            bm25_index
            if bm25_index is not None
            else BM25Index.from_graph(
                graph,
                k1=k1,
                b=b,
                include_attribute_synonyms=include_attribute_synonyms,
            )
        )

    def search(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
        mode: str = "hybrid",
    ) -> list[RetrievedEvidence]:
        """Unified search interface supporting mode='hybrid', mode='bm25', mode='graph'."""
        if mode == "bm25":
            return self.search_bm25(
                claim_text=claim_text,
                claim_date=claim_date,
                top_k=top_k,
                exclude_evidence_ids=exclude_evidence_ids,
            )
        elif mode == "graph":
            return self.search_graph(
                claim_text=claim_text,
                claim_date=claim_date,
                top_k=top_k,
                exclude_evidence_ids=exclude_evidence_ids,
            )
        else:
            return self.search_hybrid(
                claim_text=claim_text,
                claim_date=claim_date,
                top_k=top_k,
                exclude_evidence_ids=exclude_evidence_ids,
            )

    def search_bm25(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> list[RetrievedEvidence]:
        """Retrieve evidence using BM25 lexical search only."""
        return self.bm25.search(
            query_text=claim_text,
            query_date=claim_date,
            top_k=top_k,
            exclude_evidence_ids=exclude_evidence_ids,
        )

    def search_graph(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> list[RetrievedEvidence]:
        """Retrieve evidence using canonical entity/attribute lookups in the temporal graph."""
        if top_k <= 0:
            return []
        parsed_date: date | None = None
        if isinstance(claim_date, str):
            parsed_date, _ = normalize_date(claim_date)
        elif isinstance(claim_date, date):
            parsed_date = claim_date

        if parsed_date is None:
            # Attempt to extract date from text
            extracted_dates = _extract_dates(claim_text)
            if extracted_dates:
                parsed_date, _ = normalize_date(extracted_dates[0])

        excluded = set(exclude_evidence_ids or ())
        parsed = self.parser.parse(claim_text)
        evidence_scores: dict[str, float] = {}

        # 1. Fact-level lookup via EvidenceResolver
        for fact in parsed.facts:
            entity = self.graph.lexicon.resolve(fact.subject)
            if entity is None or fact.attribute not in entity.attributes:
                continue
            subject_key = self.graph.entity_key(entity.name)
            records = self.graph.facts_by_subject_attribute.get((subject_key, fact.attribute), ())
            for r in records:
                if r.source_row_id in excluded:
                    continue
                score = 0.5
                if r.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                    score = 1.0
                    # Date bonus
                    if parsed_date is not None and r.observed_on == parsed_date:
                        score += 0.5
                    # Value equality bonus
                    if compare_values(r.fact.value, fact.value, "eq") is True:
                        score += 0.5
                elif r.evidence_status in {EvidenceState.CONFLICTING, EvidenceState.VERIFIED_REFUTATION}:
                    score = 0.8
                current = evidence_scores.get(r.source_row_id, 0.0)
                if score > current:
                    evidence_scores[r.source_row_id] = score

        # 2. Entity and attribute mention fallback if no facts or weak hits
        if not evidence_scores:
            mentions = _entity_mentions(claim_text, self.graph.lexicon)
            for _, _, entity in mentions:
                subject_key = self.graph.entity_key(entity.name)
                for _, _, attr, _ in _attribute_mentions(claim_text, entity):
                    records = self.graph.facts_by_subject_attribute.get((subject_key, attr), ())
                    for r in records:
                        if r.source_row_id in excluded:
                            continue
                        score = 0.4
                        if r.evidence_status == EvidenceState.VERIFIED_SUPPORT:
                            score = 0.8
                            if parsed_date is not None and r.observed_on == parsed_date:
                                score += 0.2
                        current = evidence_scores.get(r.source_row_id, 0.0)
                        if score > current:
                            evidence_scores[r.source_row_id] = score

        if not evidence_scores:
            return []

        ranked_ids = sorted(
            evidence_scores.keys(),
            key=lambda eid: evidence_scores[eid],
            reverse=True,
        )[:top_k]

        results: list[RetrievedEvidence] = []
        for eid in ranked_ids:
            ev = self.graph.evidence_by_id.get(eid)
            score = evidence_scores[eid]
            if ev is not None:
                idx_doc = self.bm25.documents.get(eid)
                if idx_doc is not None:
                    status = idx_doc.evidence_status
                else:
                    status = (
                        EvidenceState.VERIFIED_SUPPORT
                        if ev.label == "true" and ev.parse_status == ParseStatus.FORM_GROUNDED
                        else EvidenceState.UNVERIFIED_CANDIDATE
                    )
                results.append(
                    RetrievedEvidence(
                        evidence_id=eid,
                        bm25_score=0.0,
                        source_date=ev.observed_on,
                        verification_status=status,
                        retrieval_method="graph",
                        text=ev.text,
                        entities=tuple(f.subject for f in ev.facts),
                        attributes=tuple(f.attribute for f in ev.facts),
                        facts=ev.facts,
                        provenance=ev.provenance,
                        graph_score=score,
                        combined_score=score,
                    )
                )
        return results

    def search_hybrid(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> list[RetrievedEvidence]:
        """Combine direct graph lookup with BM25 retrieval into a ranked, deduplicated Top-K list using RRF."""
        if top_k <= 0:
            return []
        pool_k = max(top_k * 2, 20)
        graph_results = self.search_graph(
            claim_text=claim_text,
            claim_date=claim_date,
            top_k=pool_k,
            exclude_evidence_ids=exclude_evidence_ids,
        )
        bm25_results = self.search_bm25(
            claim_text=claim_text,
            claim_date=claim_date,
            top_k=pool_k,
            exclude_evidence_ids=exclude_evidence_ids,
        )

        graph_map = {r.evidence_id: r for r in graph_results}
        bm25_map = {r.evidence_id: r for r in bm25_results}
        all_ids = list(dict.fromkeys((*graph_map.keys(), *bm25_map.keys())))

        if not all_ids:
            return []

        # Reciprocal Rank Fusion (RRF) with k=10
        k_rrf = 10.0
        graph_ranks = {r.evidence_id: rank for rank, r in enumerate(graph_results, 1)}
        bm25_ranks = {r.evidence_id: rank for rank, r in enumerate(bm25_results, 1)}

        scored_items: list[RetrievedEvidence] = []
        for eid in all_ids:
            g_item = graph_map.get(eid)
            b_item = bm25_map.get(eid)

            rrf_score = 0.0
            if eid in graph_ranks:
                rrf_score += 1.0 / (k_rrf + graph_ranks[eid])
            if eid in bm25_ranks:
                rrf_score += 1.2 / (k_rrf + bm25_ranks[eid])
            if eid in graph_ranks and eid in bm25_ranks:
                rrf_score += 0.1

            base_item = b_item if b_item is not None else g_item
            assert base_item is not None

            retrieval_method = (
                "hybrid"
                if (g_item is not None and b_item is not None)
                else ("graph" if g_item is not None else "bm25")
            )
            g_score = g_item.graph_score if g_item is not None else 0.0
            b_score = b_item.bm25_score if b_item is not None else 0.0

            scored_items.append(
                replace(
                    base_item,
                    retrieval_method=retrieval_method,
                    graph_score=g_score,
                    bm25_score=b_score,
                    combined_score=rrf_score,
                )
            )

        scored_items.sort(key=lambda item: item.combined_score, reverse=True)
        return scored_items[:top_k]

    def extract_candidate_facts(self, claim_text: str) -> list[AtomicFact]:
        """Extract candidate facts from claim text using parser and conservative attribute synonyms."""
        candidate_facts: list[AtomicFact] = []
        parsed = self.parser.parse(claim_text)
        extracted_dates = _extract_dates(claim_text)

        for fact in parsed.facts:
            # Refine partial dates (e.g. '2026') to full ISO dates if available
            if fact.value.kind == "date" and len(str(fact.value.value)) < 10 and extracted_dates:
                candidate_facts.append(replace(fact, value=TypedValue("date", extracted_dates[0])))
            else:
                candidate_facts.append(fact)

        # If parser extracted nothing (e.g. paraphrase like "Holdan started working at Hooly"),
        # extract candidate facts using entity resolution and conservative attribute synonyms.
        if not candidate_facts:
            mentions = _entity_mentions(claim_text, self.graph.lexicon)
            text_lower = claim_text.casefold()
            for _, _, entity in mentions:
                for attr in entity.attributes:
                    synonyms = ATTRIBUTE_SYNONYMS.get(attr, ())
                    matched_syn = None
                    for syn in synonyms:
                        pattern = r"\b" + r"\s+".join(re.escape(w) for w in syn.split()) + r"\b"
                        if re.search(pattern, text_lower):
                            matched_syn = syn
                            break
                    if matched_syn:
                        kind = self.parser.attribute_kinds.get(attr)
                        val = None
                        if kind == "date" or extracted_dates:
                            if extracted_dates:
                                val = TypedValue("date", extracted_dates[0])
                        if val is not None:
                            candidate_facts.append(AtomicFact(entity.name, attr, val, entity.name))

        return candidate_facts

    def verify_claim(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> ClaimResolution:
        """Verify claim against retrieved evidence, strictly preserving UNKNOWN on doubt.

        NEVER marks an unverified sentence as TRUE just because BM25 retrieved it.
        """
        parsed_date: date | None = None
        if isinstance(claim_date, str):
            parsed_date, _ = normalize_date(claim_date)
        elif isinstance(claim_date, date):
            parsed_date = claim_date

        extracted_dates = _extract_dates(claim_text)
        if parsed_date is None and extracted_dates:
            parsed_date, _ = normalize_date(extracted_dates[0])

        retrieved = self.search_hybrid(
            claim_text=claim_text,
            claim_date=parsed_date,
            top_k=top_k,
            exclude_evidence_ids=exclude_evidence_ids,
        )

        if not retrieved:
            return ClaimResolution(
                status=EvidenceState.UNKNOWN,
                confidence=0.0,
                evidence_ids=(),
                reason="no relevant evidence retrieved",
            )

        candidate_facts = self.extract_candidate_facts(claim_text)
        if candidate_facts:
            resolution = self.reasoning.evaluate_facts(
                candidate_facts,
                on_date=parsed_date,
                exclude_evidence_ids=tuple(exclude_evidence_ids or ()),
            )
            if resolution.status in {
                EvidenceState.VERIFIED_SUPPORT,
                EvidenceState.VERIFIED_REFUTATION,
                EvidenceState.CONFLICTING,
            }:
                return resolution

        return ClaimResolution(
            status=EvidenceState.UNKNOWN,
            confidence=0.0,
            evidence_ids=tuple(r.evidence_id for r in retrieved),
            reason="retrieved evidence cannot verify claim without ambiguity",
        )
