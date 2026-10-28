from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from foundation import load_inputs
from core.graph.semantic_extraction import grouped_train_validation_split
from candidate_factory import CandidateFactory, _overlapping_entities


class CandidateFactoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
        cls.split = grouped_train_validation_split(cls.data, seed="neuron5-p15-confirm-v2")
        cls.factory = CandidateFactory.fit(cls.data, cls.split.train_row_ids)

    def test_multiple_hypotheses_and_clause_local_multi_fact(self):
        row = self.data.rows[4]
        candidates, stats = self.factory.generate(row.row_id, row.text, config="R4")
        keys = {(c.fact.subject, c.fact.attribute, c.fact.value.kind, c.fact.value.value, c.fact.value.unit)
                for c in candidates}
        self.assertIn(("Hooly Cloud", "launched", "date", "2025-11", None), keys)
        self.assertIn(("Hooly Cloud", "regions", "quantity", 3, "region"), keys)
        self.assertGreaterEqual(len(candidates), 2)
        self.assertEqual(len({c.key() for c in candidates}), len(candidates))
        self.assertTrue(all(c.evidence_state == "UNVERIFIED_CANDIDATE" for c in candidates))
        self.assertEqual(stats["generated_before_caps"], len({c.key() for c in candidates}))

    def test_overlapping_entities_keep_alternatives(self):
        text = "Hooly AI Pro costs €59 per month."
        mentions = _overlapping_entities(text, self.data.lexicon)
        names = {entity.name for _a, _b, entity in mentions}
        self.assertIn("Hooly AI Pro", names)
        self.assertIn("Hooly", names)
        alias_owner = next(entity for entity in self.data.lexicon.entities if entity.aliases)
        alias = alias_owner.aliases[0]
        self.assertTrue(any(entity.name == alias_owner.name for _a, _b, entity in
                            _overlapping_entities(alias, self.data.lexicon)))

    def test_date_and_unit_precision_and_numeric_name_protection(self):
        row = self.data.rows[4]
        _candidates, stats = self.factory.generate(row.row_id, row.text, config="R1")
        values = [item["value"] for item in stats["value_candidates"]]
        self.assertIn({"kind": "date", "value": "2025-11"}, values)
        self.assertTrue(any(v.get("kind") == "quantity" and v.get("value") == 3 and v.get("unit") == "region" for v in values))
        numeric_entities = [e for e in self.data.lexicon.entities if re.search(r"\d", e.name)]
        if numeric_entities:
            name = numeric_entities[0].name
            mentions = _overlapping_entities(name, self.data.lexicon)
            self.assertTrue(any(e.name == name and a == 0 and b == len(name) for a, b, e in mentions))
            _candidates, numeric_stats = self.factory.generate("numeric-name", name, config="R4")
            self.assertFalse(any(v["value"].get("kind") == "date" and v["value"].get("value") == name[-4:]
                                 for v in numeric_stats["value_candidates"]))

    def test_values_use_contract_kinds_and_keep_explicit_operator(self):
        row = self.data.rows[6]
        candidates, stats = self.factory.generate(row.row_id, row.text, config="R4")
        allowed = {"quantity", "money", "percent", "date", "version", "duration", "name", "boolean"}
        self.assertTrue(all(c.fact.value.kind in allowed for c in candidates))
        values = [v["value"] for v in stats["value_candidates"]]
        self.assertTrue(any(v.get("kind") == "quantity" and v.get("value") == 100
                            and v.get("unit") == "customer" and v.get("op") == "gt" for v in values))

    def test_same_row_pronouns_create_bounded_ambiguous_subject_hypotheses(self):
        text = "Hooly Cloud says it covers 3 regions."
        candidates, stats = self.factory.generate("pronoun-row", text, config="R3")
        self.assertIn("Hooly Cloud", stats["subject_candidates"])
        self.assertTrue(any("same_row_pronoun_antecedent" in c.methods for c in candidates))
        self.assertTrue(all(c.evidence_state == "UNVERIFIED_CANDIDATE" for c in candidates))

    def test_bm25_is_deterministic_and_uses_training_rows_only(self):
        validation = self.split.validation_row_ids
        self.assertTrue(self.factory.training_ids.isdisjoint(validation))
        for index in self.factory.indexes.values():
            self.assertTrue(all(record["row_id"] in self.factory.training_ids for record in index.records))
            self.assertEqual(index.search("Hooly Cloud has 3 regions", 5),
                             index.search("Hooly Cloud has 3 regions", 5))

    def test_candidate_deduplication_and_hard_caps(self):
        limited = CandidateFactory.fit(self.data, self.split.train_row_ids, per_row_cap=1, global_cap=1)
        text = self.data.rows[4].text
        candidates, info = limited.generate("synthetic-1", text, config="R5")
        self.assertEqual(len(candidates), 1)
        self.assertTrue(info["per_row_truncated"])
        self.assertEqual(candidates[0].evidence_state, "UNVERIFIED_CANDIDATE")
        second, second_info = limited.generate("synthetic-2", text, config="R5")
        self.assertEqual(second, [])
        self.assertTrue(second_info["global_truncated"])

    def test_runtime_deadline_is_configurable_and_reported(self):
        limited = CandidateFactory.fit(self.data, self.split.train_row_ids,
                                       per_row_cap=20, global_cap=100, deadline_seconds=0)
        candidates, info = limited.generate("deadline-row", self.data.rows[4].text, config="R5")
        self.assertEqual(candidates, [])
        self.assertTrue(info["deadline_exceeded"])
        self.assertTrue(info["deadline_truncated"])


if __name__ == "__main__":
    unittest.main()
