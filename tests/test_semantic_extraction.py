"""Regression checks for P1.5 experimental semantic extraction."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from core.graph import (
    AttributeResolver,
    AttributeResolverExtractor,
    EvidenceState,
    ExpandedDeterministicExtractor,
    P1ParserAdapter,
    SpacyAssistedExtractor,
    TextFactParser,
    build_graph,
)
from foundation import Lexicon, TypedValue


LEXICON_RAW = {
    "subjects": [
        {"name": "Alpha", "aliases": ["A"], "attributes": ["customers", "reliability_lead"]},
        {"name": "Beta", "aliases": [], "attributes": ["customers"]},
        {"name": "Holdan", "aliases": [], "attributes": []},
    ],
    "events": [],
}
LEXICON, _ = Lexicon.parse(LEXICON_RAW)


class SemanticExtractionTests(unittest.TestCase):
    def test_attribute_component_cue_recovers_paraphrase(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"reliability_lead": "name"})
        result = extractor.extract("Alpha's reliability group is managed by Holdan.", "r1")
        self.assertTrue(any(f.subject == "Alpha" and f.attribute == "reliability_lead"
                            and f.value == TypedValue("name", "Holdan") for f in result.facts))

    def test_passive_name_relationship_has_source_span_and_provenance(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"reliability_lead": "name"})
        result = extractor.extract("Holdan was appointed reliability lead by Alpha.", "r2")
        candidate = next(c for c in result.candidates if c.fact.subject == "Alpha")
        self.assertEqual(candidate.fact.attribute, "reliability_lead")
        self.assertEqual(candidate.source_row_id, "r2")
        self.assertEqual(candidate.method, "expanded_deterministic")
        self.assertIsNotNone(candidate.span_start)
        self.assertIsNotNone(candidate.span_end)

    def test_pronoun_without_unique_in_row_antecedent_abstains(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"customers": "quantity"}, ["customer"])
        self.assertEqual(extractor.extract("They have 12 customers.", "r3").facts, ())

    def test_two_subjects_and_values_stay_clause_local(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"customers": "quantity"}, ["customer"])
        result = extractor.extract("Alpha has 40 customers, and Beta has 12 customers.", "r4")
        by_subject = {fact.subject: fact.value.value for fact in result.facts}
        self.assertEqual(by_subject, {"Alpha": 40, "Beta": 12})

    def test_alias_subject_is_canonical_and_multiple_facts_are_decomposed(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"customers": "quantity"}, ["customer"])
        result = extractor.extract("A has 40 customers. Beta has 12 customers.", "r5")
        self.assertEqual({(fact.subject, fact.value.value) for fact in result.facts},
                         {("Alpha", 40), ("Beta", 12)})

    def test_builder_keeps_extractions_unverified_and_preserves_details(self):
        graph = build_graph([{"id": "u1", "text": "Alpha has 40 customers.",
                              "date": "2026-01-01", "label": "true"}], LEXICON_RAW)
        record = next(iter(graph.candidates_by_row["u1"]))
        detail = graph.evidence_by_id["u1"].extraction_candidates[0]
        self.assertEqual(record.evidence_status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(detail.source_row_id, "u1")
        self.assertTrue(record.provenance.startswith("semantic_extraction:"))
        if (Path(__file__).resolve().parents[1] / "core" / "graph" / "attribute_resolver.json").is_file():
            self.assertIn("hybrid_p1_plus_tfidf", record.provenance)
        self.assertEqual(detail.observed_on, date(2026, 1, 1))
        self.assertIsNotNone(detail.subject_span_start)
        self.assertIsNotNone(detail.subject_span_end)
        self.assertIsNotNone(detail.span_start)
        self.assertIsNotNone(detail.span_end)

    def test_spacy_adapter_falls_back_without_spacy(self):
        base = P1ParserAdapter(TextFactParser(LEXICON, {"customers": "quantity"}, ["customer"]))
        adapter = SpacyAssistedExtractor(base)
        result = adapter.extract("Alpha has 40 customers.", "r6")
        self.assertTrue(result.issues)
        self.assertEqual(result.facts[0].subject, "Alpha")
        self.assertTrue(result.method.startswith("spacy_unavailable_fallback"))

    def test_deterministic_extraction_is_repeatable(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"customers": "quantity"}, ["customer"])
        text = "Alpha has 40 customers, and Beta has 12 customers."
        self.assertEqual(extractor.extract(text, "r7"), extractor.extract(text, "r7"))

    def test_attribute_resolver_artifact_round_trips_without_external_dependencies(self):
        artifact = Path(__file__).resolve().parents[1] / "core" / "graph" / "attribute_resolver.json"
        if not artifact.is_file():
            self.skipTest("packaged selected resolver is not present")
        resolver = AttributeResolver.load(artifact)
        sample = "entity costs value per month"
        before = resolver.rank(sample, {"price", "customers"})
        with TemporaryDirectory() as temp:
            copy = Path(temp) / "resolver.json"
            resolver.save(copy)
            after = AttributeResolver.load(copy).rank(sample, {"price", "customers"})
        self.assertEqual(before, after)
        self.assertGreater(resolver.training_examples, 0)

    def test_attribute_word_inside_entity_name_is_not_an_attribute_cue(self):
        lexicon, _ = Lexicon.parse({"subjects": [
            {"name": "Alpha Photos", "aliases": [], "attributes": ["photos_stored", "customers"]},
        ], "events": []})
        extractor = ExpandedDeterministicExtractor(lexicon, {"photos_stored": "quantity", "customers": "quantity"}, ["customer"])
        result = extractor.extract("Alpha Photos has 40 customers.", "r8")
        self.assertTrue(any(f.attribute == "customers" for f in result.facts))
        self.assertFalse(any(f.attribute == "photos_stored" for f in result.facts))

    def test_written_date_day_is_not_a_quantity(self):
        extractor = ExpandedDeterministicExtractor(LEXICON, {"customers": "quantity"}, ["customer"])
        result = extractor.extract("Alpha has 12 customers since 18 October 2025.", "r9")
        self.assertFalse(any(f.value.unit == "October" for f in result.facts))

    def test_boolean_attribute_expansion_requires_explicit_baseline_cue(self):
        lexicon, _ = Lexicon.parse({"subjects": [
            {"name": "Alpha", "aliases": [], "attributes": ["memory_saver"]},
        ], "events": []})
        extractor = ExpandedDeterministicExtractor(lexicon, {"memory_saver": "boolean"})
        self.assertEqual(extractor.extract("Alpha saves memory.", "r10").facts, ())


if __name__ == "__main__":
    unittest.main()
