"""Comprehensive tests for BM25 retrieval, Hybrid Retriever, and ML features."""

from __future__ import annotations

import json
import unittest
from datetime import date

from foundation import AtomicFact, Lexicon, TypedValue
from core.graph import build_graph
from core.graph.models import EvidenceState, ParseStatus
from core.retrieval import (
    BM25Index,
    FEATURE_NAMES,
    HybridEvidenceRetriever,
    RetrievalFeatureExtractor,
    RetrievedEvidence,
    tokenize_evidence_text,
)

LEXICON_DATA = {
    "subjects": [
        {"name": "Holdan", "aliases": [], "attributes": ["joined", "previous_employer", "team_size"]},
        {"name": "Hooly", "aliases": ["Hooly Inc.", "Hooly AI"], "attributes": ["reliability_lead", "uptime_sla", "regions", "headquarters"]},
        {"name": "Mira Vale", "aliases": ["Mira"], "attributes": ["joined", "title"]},
        {"name": "Alpha", "aliases": ["A"], "attributes": ["customers", "price", "owner", "storage"]},
    ],
    "events": ["Gemini Launch Night"],
}


def make_row(row_id: str, text: str, day: str, label: str, facts: list[dict] | None = None) -> dict:
    item = {"id": row_id, "text": text, "date": day, "label": label}
    if facts is not None:
        item["form"] = json.dumps(facts)
    return item


class TokenizerTests(unittest.TestCase):
    def setUp(self):
        self.lexicon, _ = Lexicon.parse(LEXICON_DATA)

    def test_number_preservation(self):
        text = "Alpha has 40 customers and 1,200 active subscribers paying $49.99 with 99.9% SLA."
        tokens = tokenize_evidence_text(text, self.lexicon)
        self.assertIn("40", tokens)
        self.assertIn("1200", tokens)
        self.assertIn("num:49.99", tokens)
        self.assertIn("pct:99.9", tokens)
        self.assertIn("percent", tokens)

    def test_date_preservation_and_normalization(self):
        text1 = "Holdan started at Hooly on 12 January 2026."
        text2 = "Holdan joined Hooly on January 12, 2026."
        text3 = "Holdan joined on 2026-01-12."

        tokens1 = tokenize_evidence_text(text1, self.lexicon)
        tokens2 = tokenize_evidence_text(text2, self.lexicon)
        tokens3 = tokenize_evidence_text(text3, self.lexicon)

        # All 3 representations produce the normalized ISO date token
        self.assertIn("date:2026-01-12", tokens1)
        self.assertIn("date:2026-01-12", tokens2)
        self.assertIn("date:2026-01-12", tokens3)
        self.assertIn("2026", tokens1)
        self.assertIn("12", tokens1)

    def test_negation_preservation(self):
        text = "Hooly did not have an outage and was never without power."
        tokens = tokenize_evidence_text(text, self.lexicon)
        self.assertIn("neg:not", tokens)
        self.assertIn("not", tokens)
        self.assertIn("neg:never", tokens)
        self.assertIn("never", tokens)
        self.assertIn("neg:without", tokens)
        self.assertIn("without", tokens)

    def test_currency_preservation(self):
        text = "Plan costs €20 monthly or £15 in the UK and 100 EUR."
        tokens = tokenize_evidence_text(text, self.lexicon)
        self.assertIn("cur:eur", tokens)
        self.assertIn("money:eur:20", tokens)
        self.assertIn("cur:gbp", tokens)
        self.assertIn("money:gbp:15", tokens)

    def test_entity_alias_canonicalization(self):
        text1 = "Mira joined in 2025."
        text2 = "Hooly Inc. is based in Mountain View."
        tokens1 = tokenize_evidence_text(text1, self.lexicon)
        tokens2 = tokenize_evidence_text(text2, self.lexicon)
        self.assertIn("entity:miravale", tokens1)
        self.assertIn("entity:hooly", tokens2)

    def test_attribute_synonym_expansion(self):
        text1 = "Holdan started working at Hooly."
        text2 = "Holdan arrived from Nimbus Cloud, his previous employer."
        tokens1 = tokenize_evidence_text(text1, self.lexicon)
        tokens2 = tokenize_evidence_text(text2, self.lexicon)
        self.assertIn("attr:joined", tokens1)
        self.assertIn("attr:previous_employer", tokens2)


class BM25IndexTests(unittest.TestCase):
    def setUp(self):
        self.lexicon, _ = Lexicon.parse(LEXICON_DATA)
        self.index = BM25Index(lexicon=self.lexicon)
        self.index.add_document(
            evidence_id="p-1",
            text="Holdan started at Hooly on 12 January 2026.",
            source_date=date(2026, 1, 12),
            evidence_status=EvidenceState.VERIFIED_SUPPORT,
            entities=["Holdan", "Hooly"],
            attributes=["joined"],
        )
        self.index.add_document(
            evidence_id="p-2",
            text="From today, Hooly Cloud's reliability team answers to Holdan.",
            source_date=date(2026, 1, 12),
            evidence_status=EvidenceState.VERIFIED_SUPPORT,
            entities=["Hooly", "Holdan"],
            attributes=["reliability_lead"],
        )
        self.index.add_document(
            evidence_id="p-3",
            text="Alpha monthly price is €20.",
            source_date=date(2026, 1, 1),
            evidence_status=EvidenceState.VERIFIED_SUPPORT,
            entities=["Alpha"],
            attributes=["price"],
        )
        self.index.build()

    def test_index_properties(self):
        self.assertEqual(len(self.index.documents), 3)
        self.assertTrue(self.index.avgdl > 0)
        self.assertTrue(all(v >= 0 for v in self.index.idf.values()))

    def test_top_k_retrieval(self):
        for k in (1, 3, 5, 10):
            res = self.index.search("Holdan joined Hooly", top_k=k)
            self.assertLessEqual(len(res), min(k, 3))
            if res:
                self.assertEqual(res[0].evidence_id, "p-1")

    def test_self_exclusion(self):
        res = self.index.search("Holdan started at Hooly", top_k=5, exclude_evidence_ids=["p-1"])
        retrieved_ids = [r.evidence_id for r in res]
        self.assertNotIn("p-1", retrieved_ids)
        self.assertIn("p-2", retrieved_ids)


class HybridRetrieverAndReasoningTests(unittest.TestCase):
    def setUp(self):
        lexicon, _ = Lexicon.parse(LEXICON_DATA)
        self.reference = [
            make_row(
                "p-1",
                "Holdan started at Hooly on 12 January 2026.",
                "2026-01-12",
                "true",
                [{"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": "2026-01-12"}}],
            ),
            make_row(
                "p-2",
                "From today, Hooly Cloud's reliability team answers to Holdan.",
                "2026-01-12",
                "true",
                [{"subject": "Hooly", "attribute": "reliability_lead", "value": {"kind": "name", "value": "Holdan"}}],
            ),
            make_row(
                "p-3",
                "Alpha has 40 customers.",
                "2026-01-01",
                "true",
                [{"subject": "Alpha", "attribute": "customers", "value": {"kind": "quantity", "value": 40, "unit": "customer"}}],
            ),
        ]
        self.graph = build_graph(self.reference, lexicon, self.reference)
        self.retriever = HybridEvidenceRetriever(self.graph)

    def test_section_4_holdan_claim_1_verified(self):
        # Claim 1: Holdan joined Hooly on January 12, 2026.
        claim = "Holdan joined Hooly on January 12, 2026."
        results = self.retriever.search(claim, top_k=3, mode="hybrid")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].evidence_id, "p-1")

        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertEqual(ver.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertIn("p-1", ver.evidence_ids)

    def test_section_4_holdan_claim_2_paraphrase_handled_by_bm25(self):
        # Claim 2: Holdan started working at Hooly on January 12, 2026.
        # Graph parsing fails for this paraphrase, but BM25 succeeds!
        claim = "Holdan started working at Hooly on January 12, 2026."
        graph_results = self.retriever.search(claim, top_k=3, mode="graph")
        self.assertEqual(len(graph_results), 0)

        bm25_results = self.retriever.search(claim, top_k=3, mode="bm25")
        self.assertTrue(len(bm25_results) > 0)
        self.assertEqual(bm25_results[0].evidence_id, "p-1")

        hybrid_results = self.retriever.search(claim, top_k=3, mode="hybrid")
        self.assertEqual(hybrid_results[0].evidence_id, "p-1")
        self.assertEqual(hybrid_results[0].retrieval_method, "bm25")

        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertEqual(ver.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertIn("p-1", ver.evidence_ids)

    def test_section_4_holdan_claim_3_wrong_date_remains_unknown(self):
        # Claim 3: Holdan joined Hooly on January 13, 2026.
        # Must retrieve p-1 as relevant evidence, but NEVER mark it TRUE!
        claim = "Holdan joined Hooly on January 13, 2026."
        results = self.retriever.search(claim, top_k=3, mode="hybrid")
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0].evidence_id, "p-1")

        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertEqual(ver.status, EvidenceState.UNKNOWN)
        self.assertNotEqual(ver.status, EvidenceState.VERIFIED_SUPPORT)

    def test_unverified_sentence_never_marked_true_by_retrieval(self):
        # Candidate claim with no verified graph support
        claim = "Alpha has 500 customers."
        results = self.retriever.search(claim, top_k=3, mode="hybrid")
        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertNotEqual(ver.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(ver.status, EvidenceState.UNKNOWN)

    def test_target_self_exclusion(self):
        claim = "Holdan started at Hooly on 12 January 2026."
        results = self.retriever.search(claim, top_k=3, exclude_evidence_ids=["p-1"])
        retrieved_ids = [r.evidence_id for r in results]
        self.assertNotIn("p-1", retrieved_ids)

    def test_different_subject_same_date_never_verified_as_support(self):
        # A claim about another person must NOT be verified by Holdan's joined fact
        claim = "Dinesh started working at Hooly on January 12, 2026."
        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertEqual(ver.status, EvidenceState.UNKNOWN)

    def test_unrelated_attribute_same_date_never_verified(self):
        claim = "Holdan left Hooly on January 12, 2026."
        ver = self.retriever.verify_claim(claim, top_k=3)
        self.assertEqual(ver.status, EvidenceState.UNKNOWN)

    def test_none_exclude_evidence_ids_safe(self):
        res = self.retriever.search("Holdan joined Hooly", top_k=3, exclude_evidence_ids=None)
        self.assertTrue(len(res) > 0)

    def test_retrieved_evidence_mapping_protocol(self):
        res = self.retriever.search("Holdan joined Hooly", top_k=1)
        self.assertTrue(len(res) > 0)
        item = res[0]
        self.assertEqual(item["evidence_id"], "p-1")
        self.assertEqual(item.get("evidence_id"), "p-1")
        self.assertIsNone(item.get("unknown_key"))
        self.assertEqual(item.get("unknown_key", "default"), "default")
        d = dict(item)
        self.assertIn("evidence_id", d)
        self.assertIn("combined_score", d)


class MLFeatureExtractorTests(unittest.TestCase):
    def setUp(self):
        lexicon, _ = Lexicon.parse(LEXICON_DATA)
        self.reference = [
            make_row(
                "p-1",
                "Holdan started at Hooly on 12 January 2026.",
                "2026-01-12",
                "true",
                [{"subject": "Holdan", "attribute": "joined", "value": {"kind": "date", "value": "2026-01-12"}}],
            ),
            make_row(
                "p-2",
                "From today, Hooly Cloud's reliability team answers to Holdan.",
                "2026-01-12",
                "true",
                [{"subject": "Hooly", "attribute": "reliability_lead", "value": {"kind": "name", "value": "Holdan"}}],
            ),
        ]
        self.graph = build_graph(self.reference, lexicon, self.reference)
        self.retriever = HybridEvidenceRetriever(self.graph)
        self.extractor = RetrievalFeatureExtractor(self.retriever)

    def test_features_contract(self):
        feats = self.extractor.extract("Holdan joined Hooly on January 12, 2026.", "2026-01-12")
        for name in FEATURE_NAMES:
            self.assertIn(name, feats)
            self.assertIsInstance(feats[name], (float, int))

        self.assertGreater(feats["bm25_top_score"], 0.0)
        self.assertGreaterEqual(feats["bm25_score_gap"], 0.0)
        self.assertGreaterEqual(feats["retrieved_verified_count"], 1)
        self.assertEqual(feats["temporal_evidence_match"], 1)
        self.assertEqual(feats["exact_fact_match"], 1)

    def test_date_mismatch_feature(self):
        feats = self.extractor.extract("Holdan joined Hooly on January 13, 2026.", "2026-01-13")
        self.assertEqual(feats["temporal_evidence_match"], 0)

    def test_fallback_indicator_on_paraphrase(self):
        feats = self.extractor.extract("Holdan started working at Hooly on January 12, 2026.", "2026-01-12")
        self.assertEqual(feats["graph_lookup_success"], 0)
        self.assertEqual(feats["retrieval_fallback_used"], 1)
        self.assertGreater(feats["bm25_top_score"], 0.0)

    def test_grouped_thousands_tokenization(self):
        text1 = "The bounty tops out at €50,000."
        text2 = "The bounty tops out at 50,000 EUR."
        tokens1 = tokenize_evidence_text(text1)
        tokens2 = tokenize_evidence_text(text2)
        self.assertIn("50000", tokens1)
        self.assertIn("money:eur:50000", tokens1)
        self.assertIn("50000", tokens2)
        self.assertIn("money:eur:50000", tokens2)


if __name__ == "__main__":
    unittest.main()
