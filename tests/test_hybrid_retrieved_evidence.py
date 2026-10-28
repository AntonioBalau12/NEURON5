"""Regression tests for the evidence set consumed by hybrid verification."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from foundation import Lexicon
from core.graph import build_graph
from core.graph.models import EvidenceState
from core.retrieval import HybridEvidenceRetriever, RetrievedEvidence


LEXICON_DATA = {
    "subjects": [
        {"name": "Alpha", "aliases": [], "attributes": ["customers", "price"]},
        {"name": "Beta", "aliases": [], "attributes": ["customers"]},
    ],
    "events": [],
}


def row(row_id: str, text: str, fact: dict) -> dict:
    return {
        "id": row_id,
        "text": text,
        "date": "2026-01-12",
        "label": "true",
        "form": json.dumps([fact]),
    }


class RetrievedEvidenceVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        lexicon, _ = Lexicon.parse(LEXICON_DATA)
        self.rows = [
            row("alpha-40", "Alpha has 40 customers.", {
                "subject": "Alpha", "attribute": "customers",
                "value": {"kind": "quantity", "value": 40, "unit": "customer"},
            }),
            row("beta-40", "Beta has 40 customers.", {
                "subject": "Beta", "attribute": "customers",
                "value": {"kind": "quantity", "value": 40, "unit": "customer"},
            }),
        ]
        self.graph = build_graph(self.rows, lexicon, self.rows)
        self.retriever = HybridEvidenceRetriever(self.graph)

    def retrieved(self, evidence_id: str, status: EvidenceState) -> RetrievedEvidence:
        evidence = self.graph.evidence_by_id[evidence_id]
        return RetrievedEvidence(
            evidence_id=evidence_id,
            bm25_score=1.0,
            source_date=evidence.observed_on,
            verification_status=status,
            retrieval_method="bm25",
            text=evidence.text,
            facts=evidence.facts,
        )

    def test_global_match_outside_retrieved_set_does_not_verify(self) -> None:
        with patch.object(self.retriever, "search_hybrid", return_value=[
            self.retrieved("beta-40", EvidenceState.UNVERIFIED_CANDIDATE),
        ]):
            result = self.retriever.verify_claim("Alpha has 40 customers.")

        self.assertEqual(result.status, EvidenceState.UNKNOWN)
        self.assertEqual(result.evidence_ids, ("beta-40",))

    def test_retrieved_matching_fact_must_have_verified_retrieval_status(self) -> None:
        with patch.object(self.retriever, "search_hybrid", return_value=[
            self.retrieved("alpha-40", EvidenceState.UNVERIFIED_CANDIDATE),
        ]):
            result = self.retriever.verify_claim("Alpha has 40 customers.")

        self.assertEqual(result.status, EvidenceState.UNKNOWN)

    def test_decisive_ids_are_actual_retrieved_contributors(self) -> None:
        result = self.retriever.verify_claim("Alpha has 40 customers.")

        self.assertEqual(result.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(result.evidence_ids, ("alpha-40",))


if __name__ == "__main__":
    unittest.main()
