"""P1.6 regressions for exact negative evidence and semantic value alignment."""

from __future__ import annotations

import json
import unittest
from datetime import date

from core.graph import (
    EvidenceResolver,
    EvidenceState,
    ExpandedDeterministicExtractor,
    ReasoningEngine,
    TextFactParser,
    build_graph,
)
from core.graph.parsing import _entity_mentions, _value_spans
from foundation import Lexicon


LEXICON_RAW = {
    "subjects": [
        {"name": "Alpha", "aliases": ["A"], "attributes": ["customers", "price", "storage"]},
        {"name": "Hooly Pixel 10", "aliases": ["Pixel 10"], "attributes": ["price", "screen_size"]},
        {"name": "Hooly Cloud", "aliases": [], "attributes": [
            "opened", "data_centres", "availability_zones", "regions", "newest_region",
        ]},
    ],
    "events": [],
}
LEXICON, _ = Lexicon.parse(LEXICON_RAW)


def row(row_id, text, day, label, facts):
    return {"id": row_id, "text": text, "date": day, "label": label,
            "form": json.dumps(facts)}


def fact(subject, attribute, kind, value, **extra):
    return {"subject": subject, "attribute": attribute,
            "value": {"kind": kind, "value": value, **extra}}


class VerifiedNegativeEvidenceTests(unittest.TestCase):
    def test_single_exact_false_atom_is_date_scoped_refutation(self):
        graph = build_graph([row("f-40", "Alpha has 40 customers.", "2026-01-01", "false",
                                 [fact("Alpha", "customers", "quantity", 40, unit="customer")])], LEXICON_RAW)
        records = graph.facts_by_subject_attribute[(graph.entity_key("Alpha"), "customers")]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.evidence_status, EvidenceState.VERIFIED_REFUTATION)
        self.assertEqual(record.provenance, "practice.false_single_atom_exact_refutation")
        self.assertEqual(record.source_row_id, "f-40")
        self.assertEqual(record.observed_on, date(2026, 1, 1))
        resolver = EvidenceResolver(graph)
        exact = fact("A", "customers", "quantity", 40, unit="customer")
        self.assertEqual(resolver.query(exact, date(2026, 1, 1)).status, EvidenceState.VERIFIED_REFUTATION)
        self.assertEqual(resolver.query(exact, date(2026, 1, 2)).status, EvidenceState.UNKNOWN)
        self.assertEqual(resolver.query(exact, None).status, EvidenceState.UNKNOWN)
        alternative = fact("Alpha", "customers", "quantity", 50, unit="customer")
        self.assertEqual(resolver.query(alternative, date(2026, 1, 1)).status, EvidenceState.UNKNOWN)

    def test_false_multi_fact_row_does_not_refute_any_atom(self):
        graph = build_graph([row("f-many", "Alpha has 40 customers and costs €30 per month.",
                                 "2026-01-01", "false", [
                                     fact("Alpha", "customers", "quantity", 40, unit="customer"),
                                     fact("Alpha", "price", "money", 30, currency="EUR", per="month"),
                                 ])], LEXICON_RAW)
        records = [record for values in graph.facts_by_subject_attribute.values() for record in values]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(item.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE for item in records))
        resolver = EvidenceResolver(graph)
        self.assertEqual(resolver.query(fact("Alpha", "customers", "quantity", 40, unit="customer"),
                                        date(2026, 1, 1)).status, EvidenceState.UNVERIFIED_CANDIDATE)

    def test_negated_operator_approximate_and_undated_false_forms_are_not_refutations(self):
        cases = [
            row("neg", "Alpha does not have 40 customers.", "2026-01-01", "false",
                [fact("Alpha", "customers", "quantity", 40, unit="customer")]),
            row("op", "Alpha has over 40 customers.", "2026-01-01", "false",
                [fact("Alpha", "customers", "quantity", 40, unit="customer", op="gt")]),
            row("approx", "Alpha has about 40 customers.", "2026-01-01", "false",
                [fact("Alpha", "customers", "quantity", 40, unit="customer")]),
            row("no-date", "Alpha has 40 customers.", "", "false",
                [fact("Alpha", "customers", "quantity", 40, unit="customer")]),
        ]
        graph = build_graph(cases, LEXICON_RAW)
        records = [record for values in graph.facts_by_subject_attribute.values() for record in values]
        self.assertEqual(len(records), 4)
        self.assertTrue(all(item.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE for item in records))

    def test_same_date_positive_and_negative_preserve_both_sources_and_conflict(self):
        claim = fact("Alpha", "customers", "quantity", 40, unit="customer")
        graph = build_graph([
            row("positive", "Alpha has 40 customers.", "2026-01-01", "true", [claim]),
            row("negative", "Alpha has 40 customers.", "2026-01-01", "false", [claim]),
        ], LEXICON_RAW)
        result = EvidenceResolver(graph).query(claim, date(2026, 1, 1))
        self.assertEqual(result.status, EvidenceState.CONFLICTING)
        self.assertEqual({record.source_row_id for record in result.supporting}, {"positive"})
        self.assertEqual({record.source_row_id for record in result.contradicting}, {"negative"})
        self.assertEqual(set(graph.evidence_by_id["positive"].contradicting_evidence_ids), {"negative"})
        self.assertEqual(set(graph.evidence_by_id["negative"].contradicting_evidence_ids), {"positive"})
        row_result = ReasoningEngine(graph).evaluate_evidence_row("negative")
        self.assertEqual(row_result.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(row_result.evidence_ids, ("positive",))

    def test_unlabeled_candidate_cannot_verify_or_refute_itself(self):
        graph = build_graph([{"id": "candidate", "text": "Alpha has 40 customers.",
                              "date": "2026-01-01", "label": ""}], LEXICON_RAW)
        query = EvidenceResolver(graph).query(fact("Alpha", "customers", "quantity", 40, unit="customer"),
                                               date(2026, 1, 1), ["candidate"])
        self.assertEqual(query.status, EvidenceState.UNKNOWN)

    def test_get_evidence_does_not_extend_refutation_beyond_observation_date(self):
        claim = fact("Alpha", "customers", "quantity", 40, unit="customer")
        graph = build_graph([
            row("negative", "Alpha has 40 customers.", "2026-01-01", "false", [claim]),
        ], LEXICON_RAW)
        resolver = EvidenceResolver(graph)
        self.assertEqual(resolver.get_evidence("Alpha", "customers", date(2026, 1, 1)).status,
                         EvidenceState.VERIFIED_REFUTATION)
        self.assertEqual(resolver.get_evidence("Alpha", "customers", date(2026, 1, 2)).status,
                         EvidenceState.UNKNOWN)

    def test_cross_date_positive_observation_is_not_linked_as_contradiction(self):
        claim = fact("Alpha", "customers", "quantity", 40, unit="customer")
        graph = build_graph([
            row("positive", "Alpha has 40 customers.", "2026-01-01", "true", [claim]),
            row("negative", "Alpha has 40 customers.", "2026-01-02", "false", [claim]),
        ], LEXICON_RAW)
        self.assertEqual(graph.evidence_by_id["positive"].contradicting_evidence_ids, ())
        self.assertEqual(graph.evidence_by_id["negative"].contradicting_evidence_ids, ())


class ValueAlignmentTests(unittest.TestCase):
    def extractor(self, kinds, units=(), **options):
        return ExpandedDeterministicExtractor(LEXICON, kinds, units, **options)

    def test_numeric_entity_name_span_is_protected_without_losing_price(self):
        parser = TextFactParser(LEXICON, {"price": "money"}, protect_entity_numbers=True)
        text = "Hooly Pixel 10 price is €799."
        mentions = _entity_mentions(text, LEXICON)
        spans = _value_spans(text, mentions, {}, protect_entity_numbers=True)
        self.assertNotIn(10, [span.value.value for span in spans])
        self.assertTrue(any(span.value.kind == "money" and span.value.value == 799 for span in spans))
        result = self.extractor({"price": "money"}, protect_entity_numbers=True).extract(text, "p10")
        self.assertIn(("Hooly Pixel 10", "price", 799),
                      {(item.subject, item.attribute, item.value.value) for item in result.facts})

    def test_month_day_year_is_one_complete_full_precision_date(self):
        result = self.extractor({"opened": "date"}, complete_date_spans=True).extract(
            "Hooly Cloud opened on November 4, 2025.", "date-1")
        dates = [item.value.value for item in result.facts if item.attribute == "opened"]
        self.assertEqual(dates, ["2025-11-04"])

    def test_count_unit_can_follow_two_modifier_words(self):
        result = self.extractor({"data_centres": "quantity"}, ["centre", "site"],
                                complete_date_spans=True, complete_unit_spans=True).extract(
            "Hooly Cloud occupies 4 data centre sites.", "unit-1")
        self.assertIn(("data_centres", 4, "site"),
                      {(item.attribute, item.value.value, item.value.unit) for item in result.facts})
        self.assertNotIn(("data_centres", 4, "data"),
                         {(item.attribute, item.value.value, item.value.unit) for item in result.facts})

    def test_count_noun_cue_aligns_value_to_matching_attribute_and_abstains_on_equal_ambiguity(self):
        parser = self.extractor({"availability_zones": "quantity", "regions": "quantity",
                                 "newest_region": "name"}, ["zone"],
                                complete_date_spans=True, align_attribute_values=True)
        result = parser.extract("Every Hooly Cloud region is divided into zones, 9 zones across the platform.", "zone-1")
        matched = [item for item in result.facts if item.value.value == 9]
        self.assertEqual([(item.attribute, item.value.unit) for item in matched], [("availability_zones", "zone")])

    def test_existing_money_hybrid_example_remains_available(self):
        from pathlib import Path
        import json
        lexicon = json.loads(Path("data/lexicon.json").read_text(encoding="utf-8"))
        graph = build_graph([{"id": "money", "text": "Hooly AI Pro costs €59 per month.",
                              "date": "2026-01-01", "label": ""}], lexicon)
        candidates = graph.candidates_by_row.get("money", ())
        self.assertTrue(any(item.fact.attribute == "price" and item.fact.value.kind == "money"
                            and item.fact.value.value == 59 for item in candidates))

    def test_selected_graph_builder_uses_protection_and_complete_value_spans(self):
        from pathlib import Path
        from foundation import load_inputs
        references = load_inputs(Path("data/practice.csv"), Path("data/lexicon.json"))
        graph = build_graph([
            {"id": "selected-product", "text": "Hooly Pixel 10 price is €799.",
             "date": "2026-01-01", "label": ""},
            {"id": "selected-date", "text": "Hooly Cloud launched on November 4, 2025.",
             "date": "2026-01-01", "label": ""},
            {"id": "selected-temporal-clause", "text":
             "The region list has been the same since Hooly Cloud opened on November 4, 2025.",
             "date": "2026-01-01", "label": ""},
            {"id": "selected-unit", "text": "Physically, Hooly Cloud occupies 4 data centre sites.",
             "date": "2026-01-01", "label": ""},
        ], references.lexicon, reference_evidence=references)
        product = graph.candidates_by_row.get("selected-product", ())
        self.assertTrue(any(item.fact.attribute == "price" and item.fact.value.kind == "money"
                            and item.fact.value.value == 799 for item in product))
        self.assertFalse(any(item.fact.value.value == 10 for item in product))
        dates = [item.fact.value.value for item in graph.candidates_by_row.get("selected-date", ())
                 if item.fact.attribute == "launched"]
        self.assertIn("2025-11-04", dates)
        self.assertNotIn("2025", dates)
        temporal = graph.candidates_by_row.get("selected-temporal-clause", ())
        self.assertFalse(any(item.fact.attribute in {"newest_region", "regions"}
                            and item.fact.value.kind == "date" for item in temporal))
        units = graph.candidates_by_row.get("selected-unit", ())
        self.assertTrue(any(item.fact.attribute == "data_centres" and item.fact.value.value == 4
                            and item.fact.value.unit == "site" for item in units))
        self.assertTrue(all(item.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE
                            for row_id in ("selected-product", "selected-date", "selected-temporal-clause", "selected-unit")
                            for item in graph.candidates_by_row.get(row_id, ())))


if __name__ == "__main__":
    unittest.main()
