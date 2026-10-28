from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from foundation import load_inputs, TypedValue
from experiments.p17_recall.candidate_factory import CandidateFactory, ValueSpan
from experiments.p17_p2_integration.r6 import (build_evidence_retriever,
                                                deterministic_name_version_boolean_spans,
                                                evidence_guided_ranking,
                                                expand_candidates_with_evidence)


class P17P2IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")

    def test_p2_graph_contains_only_supplied_reference_rows(self):
        rows = [row for row in self.data.rows if row.row_id in {"A001", "A002", "A003"}]
        if not rows:
            rows = self.data.rows[:3]
        graph, _retriever = build_evidence_retriever(rows, self.data.lexicon)
        self.assertEqual(set(graph.evidence_by_id), {row.row_id for row in rows})

    def test_evidence_expansion_keeps_claim_text_value_and_unverified_state(self):
        train = [row for row in self.data.rows if row.label is not None][:1000]
        train_ids = {row.row_id for row in train}
        factory = CandidateFactory.fit(self.data, train_ids)
        found = None
        for row in train[:250]:
            base, _stats = factory.generate(row.row_id, row.text, config="R4", collect_only=True)
            for source in base:
                entity = self.data.lexicon.resolve(source.fact.subject)
                if entity is None or source.value_span is None:
                    continue
                alternatives = [name for name in entity.attributes
                                if factory.attribute_kinds.get(name) == source.fact.value.kind
                                and name != source.fact.attribute]
                if alternatives:
                    found = (row.text, base, entity, source, alternatives[0])
                    break
            if found:
                break
        self.assertIsNotNone(found)
        text, base, entity, source, attr = found
        kind = source.fact.value.kind
        hints = {(entity.name, kind): {attr: 1.0}}
        expanded = expand_candidates_with_evidence(base, factory, hints,
                                                   {f"{entity.name}\t{kind}\t{attr}": ["train-1"]})
        linked = [candidate for candidate in expanded if candidate.fact.attribute == attr
                  and candidate.fact.value.key() == source.fact.value.key()]
        self.assertTrue(linked)
        self.assertTrue(all(candidate.evidence_state == "UNVERIFIED_CANDIDATE" for candidate in linked))
        self.assertTrue(all("p2_evidence:train-1" in candidate.matched_example_ids for candidate in linked))
        self.assertTrue(all(candidate.value_span == source.value_span for candidate in linked))

    def test_value_span_hints_cannot_invent_a_value(self):
        factory = CandidateFactory.fit(self.data, {row.row_id for row in self.data.rows[:1000]})
        entity = self.data.lexicon.entities[0]
        text = f"{entity.name} released version 3.4"
        hint = ValueSpan(TypedValue("version", "9.9.9"), text.index("3.4"), text.index("3.4") + 3,
                         "version_relation_span")
        candidates, _ = factory.generate("query-y", text, config="R4", collect_only=True,
                                         value_span_hints=(hint,))
        self.assertFalse(any(candidate.fact.value.value == "9.9.9" for candidate in candidates))

    def test_name_version_boolean_extraction_is_span_grounded(self):
        kinds = {fact.attribute: fact.value.kind for row in self.data.rows for fact in row.facts}
        entity = self.data.lexicon.entities[0]
        text = f'{entity.name} version v2.4 supports "Quartz Relay".'
        spans = deterministic_name_version_boolean_spans(text, self.data.lexicon, kinds)
        for span in spans:
            self.assertEqual(text[span.start:span.end].casefold(), str(span.value.value).casefold())
        self.assertTrue(any(span.value.kind == "version" and span.value.value == "2.4" for span in spans))
        self.assertTrue(evidence_guided_ranking([]) == [])


if __name__ == "__main__":
    unittest.main()
