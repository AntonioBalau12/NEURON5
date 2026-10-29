from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.claims.best_k import BestKPool
from core.claims.checkpoint import CheckpointManager
from core.claims.factory import ClaimFactory
from core.claims.ranker import RankedClaim, reported_confidence, score_candidate
from core.claims.scheduler import AnytimeScheduler
from foundation import Lexicon, load_inputs, validate_claim_text
from foundation import TypedValue
from core.claims.p3.observations import Obs
from core.claims.p3.rules import gen_change, gen_relation, verify_change_endpoints
from core.claims.p3.store import Params, Store
from core.claims.p3 import render, textcheck
from core.claims.p3.textcheck import Names


ROOT = Path(__file__).resolve().parents[1]


class ClaimRuntimeTests(unittest.TestCase):
    def test_semantic_replacement_and_deterministic_best_k(self):
        pool = BestKPool(5)
        key = ("fact", "Example", "size")
        weak = RankedClaim({"id": "p3-weak", "type": "fact"}, key, ("r1",), (), 0.55, "asof_rule")
        strong = RankedClaim({"id": "p3-strong", "type": "fact"}, key, ("r1", "r2"), (), 0.8, "asof_rule")
        self.assertTrue(pool.add(weak))
        self.assertTrue(pool.add(strong))
        self.assertFalse(pool.add(weak))
        self.assertEqual([x.claim["id"] for x in pool.selected()], ["p3-strong"])

    def test_ranker_does_not_report_heuristic_score_as_probability(self):
        candidate = SimpleNamespace(
            evidence={"support": [{"row_id": "r1", "role": "support"}, {"row_id": "r2", "role": "support"}]},
            flags=[], rule="asof_rule", engine={"status": "VERIFIED_SUPPORT"}, verified=True, status="accepted",
        )
        score, flags, ids = score_candidate(candidate)
        self.assertGreater(score, 0.5)
        self.assertEqual(ids, ("r1", "r2"))
        self.assertEqual(reported_confidence(candidate), 0.58)
        candidate.flags = ["cross_attribute_compare"]
        self.assertLess(score_candidate(candidate)[0], score)
        self.assertEqual(reported_confidence(candidate), 0.5)

    def test_scheduler_stops_for_deadline_and_signal(self):
        clock = SimpleNamespace(now=100.0)
        stop = SimpleNamespace(is_set=lambda: False)
        scheduler = AnytimeScheduler(deadline=110, clock=lambda: clock.now, stop_event=stop)
        self.assertTrue(scheduler.can_start("fact"))
        clock.now = 109.9
        self.assertFalse(scheduler.can_start("compare"))
        clock.now = 100
        stop.is_set = lambda: True
        self.assertFalse(scheduler.can_start("fact"))

    def test_unverified_candidate_is_never_eligible(self):
        candidate = SimpleNamespace(verified=False, status="pending")
        self.assertEqual(ClaimFactory._eligible(candidate, None), (False, "not_verified_by_p3"))

    def test_current_fact_uses_final_p3_asof_acceptance_policy(self):
        from core.claims.p3.store import AsOf
        store = SimpleNamespace(params=SimpleNamespace(as_of=date(2026, 10, 29)))
        store.asof_fact = lambda _key: AsOf(
            ("Example", "status"), True, last=SimpleNamespace(on=date(2026, 10, 15), clean=True), immutable=False,
        )
        self.assertTrue(ClaimFactory._is_asof_grounded(store, ("Example", "status")))
        store.asof_fact = lambda _key: AsOf(("Example", "status"), False)
        self.assertFalse(ClaimFactory._is_asof_grounded(store, ("Example", "status")))
        store.asof_fact = lambda _key: AsOf(
            ("Example", "joined"), True, last=SimpleNamespace(on=date(2022, 1, 1), clean=True), immutable=True,
        )
        self.assertTrue(ClaimFactory._is_asof_grounded(store, ("Example", "joined")))
        store.asof_fact = lambda _key: AsOf(
            ("Example", "status"), True, last=SimpleNamespace(on=date(2026, 10, 29), clean=True), immutable=False,
        )
        self.assertTrue(ClaimFactory._is_asof_grounded(store, ("Example", "status")))

    def test_event_date_precision_equivalence_is_not_a_reschedule_conflict(self):
        store = SimpleNamespace(support=lambda _key: [
            SimpleNamespace(value=TypedValue("date", "2026")),
            SimpleNamespace(value=TypedValue("date", "2026-05-12")),
        ])
        self.assertFalse(ClaimFactory._event_has_date_conflict(store, "Event"))
        store.support = lambda _key: [
            SimpleNamespace(value=TypedValue("date", "2026-05-12")),
            SimpleNamespace(value=TypedValue("date", "2026-05-13")),
        ]
        self.assertTrue(ClaimFactory._event_has_date_conflict(store, "Event"))

    def test_checkpoint_is_atomic_and_preserves_previous_valid_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lexicon = {"subjects": [{"name": "Example", "aliases": [], "attributes": ["size"]}], "events": []}
            (root / "lexicon.json").write_text(__import__("json").dumps(lexicon), encoding="utf-8")
            source = root / "universe.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                writer.writeheader()
                writer.writerow({"id": "u1", "text": "Example was discussed.", "date": "2026-01-01", "label": ""})
            data = load_inputs(source, root / "lexicon.json")
            output = root / "out.csv"
            manager = CheckpointManager(output, data, ROOT / "contracts")
            self.assertTrue(manager.publish({"u1": ("unsure", None)}, []))
            previous = output.read_bytes()
            bad = [{"id": "bad/id", "type": "fact", "text": "bad", "form": {}, "label": "true", "confidence": 0.4}]
            self.assertFalse(manager.publish({"u1": ("unsure", None)}, bad))
            self.assertEqual(output.read_bytes(), previous)
            self.assertTrue(any("invalid id" in issue or "confidence" in issue for issue in manager.last_validation))

    def test_partial_checkpoint_does_not_replace_existing_complete_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lexicon = {"subjects": [], "events": []}
            (root / "lexicon.json").write_text(__import__("json").dumps(lexicon), encoding="utf-8")
            source = root / "universe.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                writer.writeheader()
                writer.writerow({"id": "u1", "text": "A sentence.", "date": "2026-01-01", "label": ""})
            data = load_inputs(source, root / "lexicon.json")
            output = root / "out.csv"
            output.write_text("previous complete output", encoding="utf-8")
            manager = CheckpointManager(output, data, ROOT / "contracts")
            with patch("core.claims.checkpoint.validate_output", return_value=[]):
                self.assertTrue(manager.publish({"u1": ("unsure", None)}, []))
            self.assertTrue(manager.preserved_complete)
            self.assertEqual(output.read_text(encoding="utf-8"), "previous complete output")


class TargetedEvidenceRecoveryTests(unittest.TestCase):
    @staticmethod
    def _change_store(from_value, to_value, *, from_day="2026-01-01", to_day="2026-02-01",
                      from_id="r-from", to_id="r-to", from_kind="support", to_kind="support",
                      extra=()):
        lexicon, issues = Lexicon.parse({
            "subjects": [{"name": "Example", "aliases": [], "attributes": ["price"]}],
            "events": [],
        })
        if issues or lexicon is None:
            raise AssertionError(issues)
        key = ("Example", "price")

        def observation(row_id, day, value, kind, provenance="practice.form", label="true", clean=True):
            return Obs("Example", "price", value, date.fromisoformat(day), row_id, label, kind,
                       provenance, clean, (), "Example's price was observed.")

        records = [observation(from_id, from_day, from_value, from_kind),
                   observation(to_id, to_day, to_value, to_kind)]
        records.extend(extra)
        return SimpleNamespace(lexicon=lexicon, obs={key: records}), key, records[:2]

    def test_change_requires_independent_strictly_ordered_true_endpoints(self):
        store, key, (before, after) = self._change_store(TypedValue("money", 49, currency="EUR"),
                                                         TypedValue("money", 59, currency="EUR"))
        self.assertIsNone(verify_change_endpoints(store, key, before, after))
        self.assertEqual(verify_change_endpoints(store, key, after, before),
                         "change_endpoints_not_strictly_ordered")
        same_row_store, same_key, (same_a, same_b) = self._change_store(
            TypedValue("money", 49, currency="EUR"), TypedValue("money", 59, currency="EUR"), to_id="r-from")
        self.assertEqual(verify_change_endpoints(same_row_store, same_key, same_a, same_b),
                         "change_endpoints_not_independent_rows")

    def test_change_rejects_conflicting_and_candidate_only_endpoint_evidence(self):
        conflict = Obs("Example", "price", TypedValue("money", 45, currency="EUR"), date(2026, 1, 1),
                       "r-conflict", "true", "conflict", "practice.form", False, (), "conflicting value")
        store, key, (before, after) = self._change_store(
            TypedValue("money", 49, currency="EUR"), TypedValue("money", 59, currency="EUR"), extra=(conflict,))
        self.assertEqual(verify_change_endpoints(store, key, before, after),
                         "ambiguous_endpoint_observation(2026-01-01)")
        candidate_store, key, (before, after) = self._change_store(
            TypedValue("money", 49, currency="EUR"), TypedValue("money", 59, currency="EUR"), to_kind="text_candidate")
        self.assertEqual(verify_change_endpoints(candidate_store, key, before, after),
                         "endpoint_not_verified_true_support")

    def test_change_rejects_incompatible_kinds_currencies_periods_and_operators(self):
        pairs = [
            (TypedValue("money", 49, currency="EUR"), TypedValue("quantity", 59, unit="seat"),
             "change_endpoint_value_kinds_differ"),
            (TypedValue("money", 49, currency="EUR"), TypedValue("money", 59, currency="USD"),
             "change_endpoint_values_incompatible"),
            (TypedValue("money", 49, currency="EUR", per="month"), TypedValue("money", 59, currency="EUR", per="year"),
             "change_endpoint_values_incompatible"),
            (TypedValue("money", 49, currency="EUR", op="gt"), TypedValue("money", 59, currency="EUR"),
             "change_endpoint_has_comparison_operator"),
        ]
        for before_value, after_value, expected in pairs:
            with self.subTest(expected=expected, before=before_value, after=after_value):
                store, key, (before, after) = self._change_store(before_value, after_value)
                self.assertEqual(verify_change_endpoints(store, key, before, after), expected)

    def test_boolean_change_text_is_deterministic_and_checks_each_endpoint(self):
        lexicon_raw = {
            "subjects": [
                {"name": "Example", "aliases": [], "attributes": [
                    "end_to_end_encrypted_backups", "gemini_formula_assist"]},
                {"name": "Gemini", "aliases": [], "attributes": []},
            ],
            "events": [],
        }
        lexicon, issues = Lexicon.parse(lexicon_raw)
        self.assertFalse(issues)
        form = {"subject": "Example", "attribute": "end_to_end_encrypted_backups",
                "from": {"kind": "boolean", "value": False},
                "to": {"kind": "boolean", "value": True}}
        text = render.boolean_change_text("Example", form["attribute"], False, True)
        self.assertEqual(text, render.boolean_change_text("Example", form["attribute"], False, True))
        with tempfile.TemporaryDirectory() as tmp:
            lex_path = Path(tmp) / "lexicon.json"
            lex_path.write_text(json.dumps(lexicon_raw), encoding="utf-8")
            names = Names(lex_path)
            self.assertEqual(textcheck.check_text("change", text, form, names), [])
            self.assertEqual(validate_claim_text("change", text, form, lexicon), [])
            reversed_form = {**form, "from": form["to"], "to": form["from"]}
            self.assertTrue(textcheck.check_text("change", text, reversed_form, names))
            overlap_form = {"subject": "Example", "attribute": "gemini_formula_assist",
                            "from": {"kind": "boolean", "value": False},
                            "to": {"kind": "boolean", "value": True}}
            overlap_text = render.boolean_change_text("Example", overlap_form["attribute"], False, True)
            self.assertEqual(textcheck.check_text("change", overlap_text, overlap_form, names), [])
            self.assertEqual(validate_claim_text("change", overlap_text, overlap_form, lexicon), [])

    def test_final_money_endpoint_before_period_is_read_as_a_value(self):
        lexicon, issues = Lexicon.parse({
            "subjects": [{"name": "Example", "aliases": [], "attributes": ["price"]}], "events": [],
        })
        self.assertFalse(issues)
        form = {"subject": "Example", "attribute": "price",
                "from": {"kind": "money", "value": 200, "currency": "EUR"},
                "to": {"kind": "money", "value": 350, "currency": "EUR"}}
        self.assertEqual(validate_claim_text("change", "Example's price went from €200 to €350.", form, lexicon), [])

    def test_quantity_unit_that_is_also_an_entity_name_is_not_masked(self):
        names = Names(ROOT / "data" / "lexicon.json")
        lexicon_raw = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8-sig"))
        lexicon, issues = Lexicon.parse(lexicon_raw)
        self.assertFalse(issues)
        form = {"subject": "Hooly Photos", "attribute": "photos_stored",
                "from": {"kind": "quantity", "value": 4200000000, "unit": "photo"},
                "to": {"kind": "quantity", "value": 4900000000, "unit": "photo"}}
        text = "Hooly Photos's photos stored went from 4,200,000,000 photos to 4,900,000,000 photos."
        self.assertEqual(textcheck.check_text("change", text, form, names), [])
        self.assertEqual(validate_claim_text("change", text, form, lexicon), [])

    def test_unverified_change_preserves_endpoint_ids_and_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lex_path = root / "lexicon.json"
            lex_path.write_text(json.dumps({
                "subjects": [{"name": "Example", "aliases": [], "attributes": ["price"]}], "events": []}),
                encoding="utf-8")
            source = root / "practice.csv"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
                writer.writeheader()
                for row_id, day, amount in (("r-from", "2026-01-01", 49), ("r-to", "2026-02-01", 59)):
                    writer.writerow({"id": row_id, "text": f"Example costs €{amount}.", "date": day,
                                    "label": "true", "form": json.dumps([{
                                        "subject": "Example", "attribute": "price",
                                        "value": {"kind": "money", "value": amount, "currency": "EUR"}}])})
            store = Store(source, lex_path, Params(change_rule="engine", relation_rule="engine"), reference_csv=source)
            changes = [c for c in gen_change(store) if c.form["from"]["value"] == 49]
            self.assertEqual(len(changes), 1)
            self.assertFalse(changes[0].verified)
            self.assertEqual(changes[0].engine["status"], "UNVERIFIED_CANDIDATE")
            proof = changes[0].evidence
            self.assertEqual(proof["evidence_ids"], ["r-from", "r-to"])
            self.assertEqual((proof["from_date"], proof["to_date"]), ("2026-01-01", "2026-02-01"))

    def test_relation_requires_co_temporal_verified_link_and_target_not_asof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lex_path = root / "lexicon.json"
            lex_path.write_text(json.dumps({"subjects": [
                {"name": "Acme", "aliases": [], "attributes": ["cto"]},
                {"name": "Bertram", "aliases": [], "attributes": ["joined"]}], "events": []}), encoding="utf-8")

            def make_store(target_day):
                source = root / f"practice-{target_day}.csv"
                with source.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
                    writer.writeheader()
                    writer.writerow({"id": "link", "text": "Acme named Bertram as CTO.", "date": "2025-01-01",
                                     "label": "true", "form": json.dumps([{
                                         "subject": "Acme", "attribute": "cto", "value": {"kind": "name", "value": "Bertram"}}])})
                    writer.writerow({"id": "target", "text": "Bertram joined on 1 January 2020.", "date": target_day,
                                     "label": "true", "form": json.dumps([{
                                         "subject": "Bertram", "attribute": "joined", "value": {"kind": "date", "value": "2020-01-01"}}])})
                return Store(source, lex_path, Params(change_rule="engine", relation_rule="engine"), reference_csv=source)

            co_temporal = make_store("2025-01-01")
            relation = next(c for c in gen_relation(co_temporal) if c.form and c.form["attribute"] == "joined")
            self.assertTrue(relation.verified)
            self.assertEqual(set(relation.evidence["evidence_ids"]), {"link", "target"})
            self.assertEqual(ClaimFactory._eligible(relation, co_temporal), (True, None))
            non_temporal = make_store("2025-01-02")
            unsupported = [c for c in gen_relation(non_temporal) if c.form and c.form["attribute"] == "joined"]
            self.assertTrue(unsupported)
            self.assertFalse(any(c.verified for c in unsupported))


if __name__ == "__main__":
    unittest.main()
