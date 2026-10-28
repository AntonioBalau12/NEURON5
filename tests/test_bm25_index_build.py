"""Focused regression tests for building BM25 indexes from graph evidence."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from core.graph import EvidenceState, build_graph
from core.retrieval import BM25Index


LEXICON = {
    "subjects": [{"name": "Alpha", "aliases": [], "attributes": ["customers"]}],
    "events": [],
}


def _legacy_status(graph, source_row_id):
    records = [
        record
        for bucket in graph.facts_by_subject_attribute.values()
        for record in bucket
        if record.source_row_id == source_row_id
    ]
    if any(record.evidence_status == EvidenceState.VERIFIED_SUPPORT for record in records):
        return EvidenceState.VERIFIED_SUPPORT
    if any(record.evidence_status == EvidenceState.CONFLICTING for record in records):
        return EvidenceState.CONFLICTING
    if any(record.evidence_status == EvidenceState.VERIFIED_REFUTATION for record in records):
        return EvidenceState.VERIFIED_REFUTATION
    return EvidenceState.UNVERIFIED_CANDIDATE


class BM25IndexBuildTests(unittest.TestCase):
    def test_from_graph_preserves_status_precedence_and_missing_record_fallback(self):
        graph = build_graph(
            [{
                "id": "template",
                "text": "Alpha has 40 customers.",
                "date": "2026-01-01",
                "label": "true",
                "form": json.dumps([{
                    "subject": "Alpha",
                    "attribute": "customers",
                    "value": {"kind": "quantity", "value": 40, "unit": "customer"},
                }]),
            }],
            LEXICON,
        )
        template_record = next(iter(next(iter(graph.facts_by_subject_attribute.values()))))
        template_evidence = graph.evidence_by_id.pop("template")
        status_cases = {
            "support": (
                EvidenceState.VERIFIED_REFUTATION,
                EvidenceState.CONFLICTING,
                EvidenceState.VERIFIED_SUPPORT,
            ),
            "conflict": (EvidenceState.VERIFIED_REFUTATION, EvidenceState.CONFLICTING),
            "refutation": (EvidenceState.VERIFIED_REFUTATION,),
            "unknown": (EvidenceState.UNKNOWN,),
        }
        for source_row_id, statuses in status_cases.items():
            graph.evidence_by_id[source_row_id] = replace(
                template_evidence, source_row_id=source_row_id, text=f"Evidence {source_row_id}"
            )
            graph.facts_by_subject_attribute[("synthetic", source_row_id)] = [
                replace(template_record, source_row_id=source_row_id, evidence_status=status)
                for status in statuses
            ]
        graph.evidence_by_id["no-record"] = replace(
            template_evidence, source_row_id="no-record", text="Evidence without graph facts"
        )

        index = BM25Index.from_graph(graph)

        for source_row_id in graph.evidence_by_id:
            self.assertEqual(
                index.documents[source_row_id].evidence_status,
                _legacy_status(graph, source_row_id),
            )
        self.assertEqual(index.documents["support"].evidence_status, EvidenceState.VERIFIED_SUPPORT)
        self.assertEqual(index.documents["conflict"].evidence_status, EvidenceState.CONFLICTING)
        self.assertEqual(index.documents["refutation"].evidence_status, EvidenceState.VERIFIED_REFUTATION)
        self.assertEqual(index.documents["unknown"].evidence_status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(index.documents["no-record"].evidence_status, EvidenceState.UNVERIFIED_CANDIDATE)
        self.assertEqual(index.documents["support"].raw_record, graph.evidence_by_id["support"])

    def test_optimized_builder_preserves_legacy_retrieval_ranking(self):
        rows = []
        for i, count in enumerate((40, 40, 55, 72)):
            rows.append({
                "id": f"p-{i}", "text": f"Alpha has {count} customers in region {i}.",
                "date": f"2026-01-0{i + 1}", "label": "true",
                "form": json.dumps([{"subject": "Alpha", "attribute": "customers",
                                     "value": {"kind": "quantity", "value": count, "unit": "customer"}}]),
            })
        graph = build_graph(rows, LEXICON)
        optimized = BM25Index.from_graph(graph)
        legacy = BM25Index(lexicon=graph.lexicon)
        for evidence in graph.evidence_by_id.values():
            legacy.add_document(
                evidence_id=evidence.source_row_id, text=evidence.text, source_date=evidence.observed_on,
                evidence_status=_legacy_status(graph, evidence.source_row_id),
                entities=tuple(f.subject for f in evidence.facts),
                attributes=tuple(f.attribute for f in evidence.facts), facts=evidence.facts,
                provenance=evidence.provenance, raw_record=evidence,
            )
        legacy.build()

        for query in ("Alpha has 40 customers", "Alpha had 55 customers", "region 3 customers"):
            old = legacy.search(query, top_k=4)
            new = optimized.search(query, top_k=4)
            self.assertEqual([item.evidence_id for item in new], [item.evidence_id for item in old])
            for left, right in zip(new, old):
                self.assertAlmostEqual(left.bm25_score, right.bm25_score, places=12)


if __name__ == "__main__":
    unittest.main()
