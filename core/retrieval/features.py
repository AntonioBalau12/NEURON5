"""Classical ML feature extraction from BM25 and hybrid evidence retrieval."""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from foundation import compare_values, normalize_date
from core.graph.models import EvidenceState
from core.retrieval.bm25 import RetrievedEvidence, _extract_dates
from core.retrieval.hybrid import HybridEvidenceRetriever


FEATURE_NAMES = (
    "bm25_top_score",
    "bm25_score_gap",
    "retrieved_verified_count",
    "retrieved_candidate_count",
    "graph_lookup_success",
    "retrieval_fallback_used",
    "exact_fact_match",
    "temporal_evidence_match",
)


class RetrievalFeatureExtractor:
    """Extract lightweight, reproducible tabular features for Classical ML (LightGBM/CatBoost)."""

    def __init__(self, retriever: HybridEvidenceRetriever):
        self.retriever = retriever

    def extract(
        self,
        claim_text: str,
        claim_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> dict[str, float | int]:
        """Run hybrid search and extract structured ML features."""
        results = self.retriever.search(
            claim_text=claim_text,
            claim_date=claim_date,
            top_k=top_k,
            exclude_evidence_ids=exclude_evidence_ids,
            mode="hybrid",
        )
        return self.extract_from_results(results, claim_text, claim_date)

    def extract_from_results(
        self,
        results: Sequence[RetrievedEvidence],
        claim_text: str,
        claim_date: date | str | None = None,
    ) -> dict[str, float | int]:
        """Extract ML features from precomputed retrieval results."""
        parsed_claim_date: date | None = None
        if isinstance(claim_date, str):
            parsed_claim_date, _ = normalize_date(claim_date)
        elif isinstance(claim_date, date):
            parsed_claim_date = claim_date

        if parsed_claim_date is None:
            extracted = _extract_dates(claim_text)
            if extracted:
                parsed_claim_date, _ = normalize_date(extracted[0])

        if not results:
            return {
                "bm25_top_score": 0.0,
                "bm25_score_gap": 0.0,
                "retrieved_verified_count": 0,
                "retrieved_candidate_count": 0,
                "graph_lookup_success": 0,
                "retrieval_fallback_used": 0,
                "exact_fact_match": 0,
                "temporal_evidence_match": 0,
            }

        # 1. Top score and score gap (sorted over non-zero BM25 scores)
        bm25_scores = sorted([float(r.bm25_score) for r in results if float(r.bm25_score) > 0.0], reverse=True)
        if bm25_scores:
            bm25_top_score = bm25_scores[0]
            bm25_score_gap = (
                max(0.0, bm25_scores[0] - bm25_scores[1])
                if len(bm25_scores) >= 2
                else bm25_scores[0]
            )
        else:
            bm25_top_score = 0.0
            bm25_score_gap = 0.0

        # 2. Counts by verification status
        retrieved_verified_count = sum(
            1 for r in results if r.verification_status == EvidenceState.VERIFIED_SUPPORT
        )
        retrieved_candidate_count = sum(
            1 for r in results if r.verification_status == EvidenceState.UNVERIFIED_CANDIDATE
        )

        # 3. Method indicators
        graph_lookup_success = 1 if any(r.retrieval_method in {"graph", "hybrid"} for r in results) else 0
        retrieval_fallback_used = 1 if (graph_lookup_success == 0 and any(r.retrieval_method == "bm25" for r in results)) else 0

        # 4. Exact fact match check against candidate facts
        exact_fact_match = 0
        candidate_facts: Sequence[AtomicFact] = ()
        if hasattr(self.retriever, "extract_candidate_facts"):
            candidate_facts = self.retriever.extract_candidate_facts(claim_text)
        elif hasattr(self.retriever, "parser"):
            candidate_facts = self.retriever.parser.parse(claim_text).facts

        if candidate_facts:
            for fact in candidate_facts:
                for r in results:
                    for ev_fact in r.facts:
                        if (
                            fact.subject.casefold() == ev_fact.subject.casefold()
                            and fact.attribute == ev_fact.attribute
                            and compare_values(fact.value, ev_fact.value, "eq") is True
                        ):
                            exact_fact_match = 1
                            break
                    if exact_fact_match:
                        break

        # 5. Temporal evidence match
        temporal_evidence_match = 0
        candidate_dates = set()
        if parsed_claim_date is not None:
            candidate_dates.add(parsed_claim_date)
        for ext_d in _extract_dates(claim_text):
            norm_ext, _ = normalize_date(ext_d)
            if norm_ext:
                candidate_dates.add(norm_ext)

        if candidate_dates:
            for r in results:
                if r.source_date is not None and r.source_date in candidate_dates:
                    temporal_evidence_match = 1
                    break
                for ev_fact in r.facts:
                    if ev_fact.value.kind == "date":
                        ev_d, _ = normalize_date(str(ev_fact.value.value))
                        if ev_d and ev_d in candidate_dates:
                            temporal_evidence_match = 1
                            break
                if temporal_evidence_match:
                    break

        return {
            "bm25_top_score": round(bm25_top_score, 4),
            "bm25_score_gap": round(bm25_score_gap, 4),
            "retrieved_verified_count": retrieved_verified_count,
            "retrieved_candidate_count": retrieved_candidate_count,
            "graph_lookup_success": graph_lookup_success,
            "retrieval_fallback_used": retrieval_fallback_used,
            "exact_fact_match": exact_fact_match,
            "temporal_evidence_match": temporal_evidence_match,
        }

    def extract_batch(
        self,
        claims: Iterable[Mapping[str, Any]],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Batch feature extraction for runtime or benchmark claim datasets."""
        rows: list[dict[str, Any]] = []
        for claim in claims:
            cid = str(claim.get("id", ""))
            text = str(claim.get("text", ""))
            date_val = claim.get("date")
            excluded = (cid,) if cid else ()
            feats = self.extract(
                claim_text=text,
                claim_date=date_val,
                top_k=top_k,
                exclude_evidence_ids=excluded,
            )
            row = {"id": cid, **feats}
            rows.append(row)
        return rows
