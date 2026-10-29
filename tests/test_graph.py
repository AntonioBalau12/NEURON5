"""Regression tests for dynamic graph construction and evidence reasoning."""

from __future__ import annotations

import json
import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from core.graph import (
    EvidenceResolver,
    EvidenceState,
    FactRecord,
    ParseStatus,
    ReasoningEngine,
    TemporalIndex,
    build_graph,
    build_graph_from_paths,
    practice_extraction_metrics,
)


LEXICON = {
    "subjects": [
        {"name": "Alpha", "aliases": ["A"], "attributes": ["customers", "price", "owner", "founded", "storage"]},
        {"name": "Beta", "aliases": [], "attributes": ["customers", "price", "joined", "storage"]},
        {"name": "Event One", "aliases": ["E1"], "attributes": ["date"]},
        {"name": "Mira Vale", "aliases": ["Mira"], "attributes": ["joined"]},
    ],
    "events": ["Event One"],
}


def row(row_id, text, day, label, facts=None):
    item = {"id": row_id, "text": text, "date": day, "label": label}
    if facts is not None:
        item["form"] = json.dumps(facts)
    return item


def fact(subject, attribute, value):
    return {"subject": subject, "attribute": attribute, "value": value}


def quantity(value, unit="customer"):
    return {"kind": "quantity", "value": value, "unit": unit}


def money(value, per="month"):
    result = {"kind": "money", "value": value, "currency": "EUR"}
    if per is not None:
        result["per"] = per
    return result


def build(rows, reference=None):
    return build_graph(rows, LEXICON, reference)


class GraphConstructionTests(unittest.TestCase):
    def test_runtime_rows_without_forms_get_candidates_and_keep_true_label_unverified(self):
        reference = [row("p1", "Alpha has 40 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(40))])]
        graph = build([row("u1", "Alpha has 55 customers.", "2026-02-01", "true")], reference)
        candidates = graph.candidates_by_row.get("u1", ())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].fact.value.value, 55)
        self.assertEqual(candidates[0].evidence_status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(graph.evidence_by_id["p1"].provenance, "practice.form")

    def test_parser_handles_multiple_facts_and_explicit_operators_as_candidates(self):
        reference = [
            row("p1", "Alpha has 40 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(40))]),
            row("p2", "Beta has 20 customers.", "2026-01-01", "true", [fact("Beta", "customers", quantity(20))]),
            row("p3", "Alpha monthly price is €20.", "2026-01-01", "true", [fact("Alpha", "price", money(20, None))]),
        ]
        graph = build([
            row("u1", "Alpha has over 55 customers, and Beta has 12 customers.", "2026-02-01", ""),
            row("u2", "Alpha has 1.2 million customers, and Beta has 40 or more customers.", "2026-02-02", ""),
            row("u3", "Alpha has about 50 customers.", "2026-02-03", ""),
            row("u4", "Alpha monthly price is €49,99.", "2026-02-04", ""),
        ], reference)
        candidates = graph.candidates_by_row["u1"]
        keyed = {(item.fact.subject, item.fact.attribute): item for item in candidates}
        self.assertEqual(keyed[("Alpha", "customers")].fact.value.value, 55)
        self.assertEqual(keyed[("Alpha", "customers")].fact.value.op, "gt")
        self.assertEqual(keyed[("Beta", "customers")].fact.value.value, 12)
        self.assertTrue(all(item.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE for item in candidates))
        more = {(item.fact.subject, item.fact.attribute): item for item in graph.candidates_by_row["u2"]}
        self.assertEqual(more[("Alpha", "customers")].fact.value.value, 1_200_000)
        self.assertEqual(more[("Beta", "customers")].fact.value.op, "ge")
        self.assertNotIn("u3", graph.candidates_by_row)
        price = next(item for item in graph.candidates_by_row["u4"] if item.fact.attribute == "price")
        self.assertEqual(price.fact.value.value, 49.99)
        self.assertEqual(price.fact.value.currency, "EUR")

    def test_duplicate_reference_row_is_merged_once_only_when_identity_matches(self):
        f = [fact("A", "customers", quantity(40))]
        base = row("p1", "Alpha has 40 customers.", "2026-01-01", "true")
        ref = row("p1", "Alpha has 40 customers.", "2026-01-01", "true", f)
        graph = build([base], [ref])
        records = graph.facts_by_subject_attribute[(graph.entity_key("Alpha"), "customers")]
        self.assertEqual(len([r for r in records if r.source_row_id == "p1"]), 1)
        self.assertEqual(records[0].evidence_status, EvidenceState.VERIFIED_SUPPORT)

    def test_mismatched_reference_text_is_not_merged(self):
        base = row("p1", "Alpha has 40 customers.", "2026-01-01", "true")
        ref = row("p1", "Alpha has 999 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(999))])
        graph = build([base], [ref])
        self.assertTrue(any("did not match runtime row" in issue for issue in graph.issues))
        records = graph.facts_by_subject_attribute[(graph.entity_key("Alpha"), "customers")]
        self.assertTrue(all(r.fact.value.value != 999 for r in records))

    def test_duplicate_reference_id_is_counted_once(self):
        reference = row("p1", "Alpha has 40 customers.", "2026-01-01", "true",
                        [fact("Alpha", "customers", quantity(40))])
        graph = build([], [reference, reference])
        records = graph.facts_by_subject_attribute[(graph.entity_key("Alpha"), "customers")]
        self.assertEqual(len(records), 1)
        self.assertTrue(any("duplicate row id" in issue for issue in graph.issues))

    def test_false_multifact_rows_do_not_supply_refutation(self):
        false_form = [fact("Alpha", "customers", quantity(40)), fact("Beta", "customers", quantity(20))]
        graph = build([row("f1", "Alpha has 40 and Beta has 20 customers.", "2026-01-01", "false", false_form)])
        statuses = [r.evidence_status for records in graph.facts_by_subject_attribute.values() for r in records]
        self.assertTrue(statuses)
        self.assertTrue(all(status == EvidenceState.UNVERIFIED_CANDIDATE for status in statuses))

    def test_repeated_unlabeled_candidates_do_not_promote_themselves_to_truth(self):
        graph = build([
            row("u1", "Alpha has 40 customers.", "2026-01-01", ""),
            row("u2", "Alpha has 40 customers.", "2026-01-01", ""),
        ])
        from foundation import AtomicFact, TypedValue
        result = EvidenceResolver(graph).query(
            AtomicFact("Alpha", "customers", TypedValue("quantity", 40, unit="customer")),
            date(2026, 1, 1),
        )
        self.assertEqual(result.status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(len(result.candidates), 2)

    def test_unknown_subject_attribute_and_bad_rows_are_reported(self):
        graph = build([row("x", "Ghost has 4 customers.", "2026-01-01", "true"),
                       row("x", "duplicate", "2026-01-02", "true")])
        self.assertTrue(any("duplicate row id" in issue for issue in graph.issues))
        self.assertIn("Alpha", [entity.name for entity in graph.entities.values()])

    def test_path_builder_reads_runtime_csv_without_form_and_supports_local_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            lexicon_path = folder / "lexicon.json"
            universe_path = folder / "universe.csv"
            lexicon_path.write_text(json.dumps(LEXICON), encoding="utf-8")
            with universe_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "text", "date", "label"])
                writer.writeheader()
                writer.writerow(row("u", "Alpha has 55 customers.", "2026-02-01", ""))
            graph = build_graph_from_paths(universe_path, lexicon_path, use_packaged_practice=False)
            self.assertIn("u", graph.candidates_by_row)
            self.assertEqual(graph.evidence_by_id["u"].label, None)

    def test_practice_metric_matches_operator_values_and_name_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            lexicon_path = folder / "lexicon.json"
            csv_path = folder / "practice.csv"
            lexicon = {"subjects": [
                {"name": "Alpha", "aliases": [], "attributes": ["customers", "owner"]},
                {"name": "Beta", "aliases": ["B"], "attributes": []},
            ], "events": []}
            lexicon_path.write_text(json.dumps(lexicon), encoding="utf-8")
            forms = [
                fact("Alpha", "customers", {"kind": "quantity", "value": 40, "unit": "customer", "op": "gt"}),
                fact("Alpha", "owner", {"kind": "name", "value": "B"}),
            ]
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["id", "text", "date", "label", "form"])
                writer.writeheader()
                writer.writerow(row("p", "Alpha has over 40 customers. Alpha's owner is Beta.", "2026-01-01", "true", forms))
            from foundation import load_inputs
            metrics = practice_extraction_metrics(load_inputs(csv_path, lexicon_path))
            self.assertEqual(metrics["gold_facts"], 2)
            self.assertEqual(metrics["exact_matches"], 2)
            self.assertEqual(metrics["false_positive_candidates"], 0)


class TemporalAndReasoningTests(unittest.TestCase):
    def test_exact_date_support_does_not_extrapolate_and_self_evidence_is_excluded(self):
        graph = build([row("p1", "Alpha has 40 customers.", "2026-01-01", "true",
                            [fact("Alpha", "customers", quantity(40))])])
        resolver = EvidenceResolver(graph)
        candidate = fact("Alpha", "customers", quantity(40))
        parsed = __import__("foundation").AtomicFact("Alpha", "customers", __import__("foundation").TypedValue("quantity", 40, unit="customer"))
        self.assertEqual(resolver.query(parsed, date(2026, 1, 1)).status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(resolver.query(parsed, date(2026, 1, 2)).status, EvidenceState.UNKNOWN)
        self.assertEqual(resolver.query(parsed, date(2026, 1, 1), ["p1"]).status, EvidenceState.UNKNOWN)
        self.assertEqual(resolver.find_supporting_evidence(candidate, date(2026, 1, 1), ["p1"]), ())
        self.assertEqual(ReasoningEngine(graph).evaluate_evidence_row("p1").status, EvidenceState.UNKNOWN)

    def test_row_evaluation_can_use_independent_duplicate_evidence_but_not_itself(self):
        form = [fact("Alpha", "customers", quantity(40))]
        graph = build([
            row("p1", "Alpha has 40 customers.", "2026-01-01", "true", form),
            row("p2", "Alpha serves 40 customers.", "2026-01-01", "true", form),
        ])
        result = ReasoningEngine(graph).evaluate_evidence_row("p1")
        self.assertEqual(result.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(result.evidence_ids, ("p2",))
        self.assertEqual(graph.evidence_by_id["p1"].supporting_evidence_ids, ("p2",))

    def test_same_day_non_equivalent_true_facts_are_conflicting(self):
        graph = build([
            row("a", "Alpha has 40 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(40))]),
            row("b", "Alpha has 45 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(45))]),
        ])
        query = EvidenceResolver(graph).get_evidence("A", "customers", date(2026, 1, 1))
        self.assertEqual(query.status, EvidenceState.CONFLICTING)
        self.assertEqual(set(graph.evidence_by_id["a"].contradicting_evidence_ids), {"b"})

    def test_equivalent_units_are_not_reported_as_a_conflict(self):
        graph = build([
            row("a", "Alpha has 1 GB storage.", "2026-01-01", "true", [fact("Alpha", "customers", {"kind": "quantity", "value": 1, "unit": "GB"})]),
            row("b", "Alpha has 1000 MB storage.", "2026-01-01", "true", [fact("Alpha", "customers", {"kind": "quantity", "value": 1000, "unit": "MB"})]),
        ])
        query = EvidenceResolver(graph).get_evidence("Alpha", "customers", date(2026, 1, 1))
        self.assertEqual(query.status, EvidenceState.VERIFIED_SUPPORT)

    def test_temporal_change_uses_ordered_comparable_true_observations(self):
        graph = build([
            row("a", "Alpha price was EUR 10 monthly.", "2026-01-01", "true", [fact("Alpha", "price", money(10))]),
            row("b", "Alpha price is EUR 15 monthly.", "2026-03-01", "true", [fact("Alpha", "price", money(15))]),
            row("c", "Alpha has 5 customers.", "2026-04-01", "true", [fact("Alpha", "customers", quantity(5))]),
        ])
        changes = TemporalIndex(graph).get_temporal_changes("A", "price")
        self.assertEqual(len(changes), 1)
        self.assertEqual((changes[0].from_value.value, changes[0].to_value.value), (10, 15))
        result = ReasoningEngine(graph).evaluate_claim("change", {
            "subject": "Alpha", "attribute": "price", "from": money(10), "to": money(15),
        })
        self.assertEqual(result.status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(len(result.evidence_ids), 2)
        self.assertEqual(ReasoningEngine(graph).evaluate_claim("change", {
            "subject": "Alpha", "attribute": "price", "from": money(10), "to": money(15),
        }, exclude_evidence_ids=["a"]).status, EvidenceState.UNKNOWN)

    def test_same_day_conflict_does_not_reclassify_unrelated_candidate(self):
        graph = build([
            row("a", "Alpha has 40 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(40))]),
            row("b", "Alpha has 45 customers.", "2026-01-01", "true", [fact("Alpha", "customers", quantity(45))]),
            row("c", "Alpha has 40 customers.", "2026-01-01", "unsure", [fact("Alpha", "customers", quantity(40))]),
        ])
        candidate = next(record for record in graph.candidates_by_row["c"] if record.fact.value.value == 40)
        self.assertEqual(candidate.evidence_status, EvidenceState.UNVERIFIED_CANDIDATE)

    def test_primary_fact_provenance_does_not_claim_self_support(self):
        graph = build([row("a", "Alpha has 40 customers.", "2026-01-01", "true",
                            [fact("Alpha", "customers", quantity(40))])])
        record = graph.facts_by_subject_attribute[(graph.entity_key("Alpha"), "customers")][0]
        self.assertEqual(record.source_row_id, "a")
        self.assertEqual(record.supporting_evidence, ())

    def test_incompatible_or_partial_date_precision_is_not_a_change(self):
        graph = build([
            row("a", "Alpha was founded in 2025.", "2025-01-01", "true", [fact("Alpha", "founded", {"kind": "date", "value": "2025"})]),
            row("b", "Alpha was founded on 2025-03-01.", "2026-01-01", "true", [fact("Alpha", "founded", {"kind": "date", "value": "2025-03-01"})]),
        ])
        self.assertEqual(TemporalIndex(graph).get_temporal_changes("Alpha", "founded"), ())

    def test_multi_fact_claim_requires_each_atom_and_preserves_unknown(self):
        graph = build([row("a", "Alpha has 40 customers.", "2026-01-01", "true",
                           [fact("Alpha", "customers", quantity(40))])])
        engine = ReasoningEngine(graph)
        known = __import__("foundation").AtomicFact("Alpha", "customers", __import__("foundation").TypedValue("quantity", 40, unit="customer"))
        unknown = __import__("foundation").AtomicFact("Beta", "customers", __import__("foundation").TypedValue("quantity", 20, unit="customer"))
        self.assertEqual(engine.evaluate_facts([known], date(2026, 1, 1)).status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(engine.evaluate_facts([known, unknown], date(2026, 1, 1)).status, EvidenceState.UNKNOWN)

    def test_multi_fact_claim_is_false_only_with_explicit_atomic_refutation(self):
        from foundation import AtomicFact, TypedValue

        graph = build([row("a", "Alpha has 40 customers.", "2026-01-01", "true",
                           [fact("Alpha", "customers", quantity(40))])])
        graph.add_fact(FactRecord(AtomicFact("Beta", "customers", TypedValue("quantity", 20, unit="customer")),
                                  date(2026, 1, 1), None, None, "refutation-1",
                                  EvidenceState.VERIFIED_REFUTATION, ParseStatus.FORM_GROUNDED,
                                  "independent_verified_refutation", 1.0))
        known = AtomicFact("Alpha", "customers", TypedValue("quantity", 40, unit="customer"))
        refuted = AtomicFact("Beta", "customers", TypedValue("quantity", 20, unit="customer"))
        result = ReasoningEngine(graph).evaluate_facts([known, refuted], date(2026, 1, 1))
        self.assertEqual(result.status, EvidenceState.VERIFIED_REFUTATION)

    def test_relation_requires_same_day_link_and_target_fact(self):
        graph = build([row("link", "Alpha's owner is Mira.", "2026-01-01", "true",
                            [fact("Alpha", "owner", {"kind": "name", "value": "Mira"})]),
                       row("joined", "Mira Vale joined on 2025-12-01.", "2026-01-01", "true",
                           [fact("Mira", "joined", {"kind": "date", "value": "2025-12-01"})])])
        form = {"subject": "Alpha", "link": "owner", "target": "Mira", "attribute": "joined",
                "value": {"kind": "date", "value": "2025-12-01"}}
        result = ReasoningEngine(graph).evaluate_claim("relation", form)
        self.assertEqual(result.status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(set(result.evidence_ids), {"link", "joined"})
        self.assertEqual(ReasoningEngine(graph).evaluate_claim("relation", form, exclude_evidence_ids=["link"]).status, EvidenceState.UNKNOWN)

    def test_event_fact_requires_exact_event_day_evidence(self):
        graph = build([row("event", "Event One took place on 2026-03-24.", "2026-03-24", "true",
                            [fact("Event One", "date", {"kind": "date", "value": "2026-03-24"})]),
                       row("fact", "Alpha has 40 customers.", "2026-03-24", "true",
                           [fact("Alpha", "customers", quantity(40))])])
        form = {"event": "E1", "subject": "Alpha", "attribute": "customers", "value": quantity(40)}
        self.assertEqual(ReasoningEngine(graph).evaluate_claim("at_event", form).status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(ReasoningEngine(graph).evaluate_claim("at_event", form, exclude_evidence_ids=["fact"]).status, EvidenceState.UNKNOWN)

    def test_compare_requires_both_values_on_the_as_of_date(self):
        graph = build([
            row("a", "Alpha has 40 customers.", "2026-10-29", "true", [fact("Alpha", "customers", quantity(40))]),
            row("b", "Beta has 20 customers.", "2026-10-29", "true", [fact("Beta", "customers", quantity(20))]),
        ])
        form = {"left": {"subject": "Alpha", "attribute": "customers"},
                "right": {"subject": "Beta", "attribute": "customers"}, "op": "gt"}
        engine = ReasoningEngine(graph)
        self.assertEqual(engine.evaluate_claim("compare", form).status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(engine.evaluate_claim("compare", form, exclude_evidence_ids=["a"]).status, EvidenceState.UNKNOWN)
        self_compare = {"left": {"subject": "A", "attribute": "customers"},
                        "right": {"subject": "Alpha", "attribute": "customers"}, "op": "eq"}
        self.assertEqual(engine.evaluate_claim("compare", self_compare).status, EvidenceState.UNKNOWN)

    def test_comparable_fact_index_uses_date_and_unit_compatibility(self):
        graph = build([
            row("a", "Alpha has 1 GB storage.", "2026-10-29", "true",
                [fact("Alpha", "storage", {"kind": "quantity", "value": 1, "unit": "GB"})]),
            row("b", "Beta has 1000 MB storage.", "2026-10-29", "true",
                [fact("Beta", "storage", {"kind": "quantity", "value": 1000, "unit": "MB"})]),
        ])
        peers = TemporalIndex(graph).get_comparable_facts("A", "storage", date(2026, 10, 29))
        self.assertEqual([item.fact.subject for item in peers], ["Beta"])


if __name__ == "__main__":
    unittest.main()
