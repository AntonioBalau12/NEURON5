"""Regression tests for verified, date-applicable retrieval fact features."""

from __future__ import annotations

import json
import unittest
from datetime import date

from foundation import Lexicon
from core.graph import build_graph
from core.graph.models import EvidenceState
from core.retrieval import HybridEvidenceRetriever, RetrievalFeatureExtractor, RetrievedEvidence


LEXICON = {
    "subjects": [
        {"name": "Holdan", "aliases": [], "attributes": ["joined"]},
        {"name": "Hooly", "aliases": [], "attributes": ["reliability_lead"]},
    ],
    "events": [],
}
DAY = "2026-01-12"
CLAIM = "Holdan joined Hooly on January 12, 2026."


def row(row_id: str, fact: dict, label: str = "true") -> dict:
    return {
        "id": row_id,
        "text": "Verified source.",
        "date": DAY,
        "label": label,
        "form": json.dumps([fact]),
    }


class RetrievalFactSignalTests(unittest.TestCase):
    def make_extractor(self, rows: list[dict]) -> RetrievalFeatureExtractor:
        lexicon, _ = Lexicon.parse(LEXICON)
        graph = build_graph(rows, lexicon, rows)
        return RetrievalFeatureExtractor(HybridEvidenceRetriever(graph))

    def test_same_date_on_unrelated_fact_does_not_match(self):
        extractor = self.make_extractor([
            row("joined", {"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": DAY}}),
            row("other", {"subject": "Hooly", "attribute": "reliability_lead", "value": {"kind": "name", "value": "Holdan"}}),
        ])
        evidence = extractor.retriever.graph.evidence_by_id["other"]
        other = RetrievedEvidence(
            evidence_id="other",
            bm25_score=1.0,
            source_date=date.fromisoformat(DAY),
            verification_status=EvidenceState.VERIFIED_SUPPORT,
            retrieval_method="graph",
            facts=evidence.facts,
        )

        feats = extractor.extract_from_results([other], CLAIM, DAY)

        self.assertEqual(feats["exact_fact_match"], 0)
        self.assertEqual(feats["temporal_evidence_match"], 0)

    def test_matching_verified_fact_sets_both_signals(self):
        extractor = self.make_extractor([
            row("joined", {"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": DAY}}),
        ])

        feats = extractor.extract(CLAIM, DAY)

        self.assertEqual(feats["exact_fact_match"], 1)
        self.assertEqual(feats["temporal_evidence_match"], 1)

    def test_unverified_matching_fact_preserves_unknown_signals(self):
        extractor = self.make_extractor([
            row("candidate", {"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": DAY}}, "unsure"),
        ])

        feats = extractor.extract(CLAIM, DAY)

        self.assertEqual(feats["exact_fact_match"], 0)
        self.assertEqual(feats["temporal_evidence_match"], 0)

    def test_excluded_claim_source_is_not_counted_as_independent_support(self):
        extractor = self.make_extractor([
            row("claim-row", {"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": DAY}}),
        ])

        feats = extractor.extract(CLAIM, DAY, exclude_evidence_ids=("claim-row",))

        self.assertEqual(feats["exact_fact_match"], 0)
        self.assertEqual(feats["temporal_evidence_match"], 0)

    def test_matching_fact_outside_observed_date_does_not_match(self):
        extractor = self.make_extractor([
            row("joined", {"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": DAY}}),
        ])

        feats = extractor.extract(CLAIM, "2026-01-13")

        self.assertEqual(feats["exact_fact_match"], 0)
        self.assertEqual(feats["temporal_evidence_match"], 0)


if __name__ == "__main__":
    unittest.main()
