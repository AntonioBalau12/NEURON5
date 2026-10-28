"""Compare BM25 graph-to-index construction across corpus sizes."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.graph import build_graph
from core.graph.models import EvidenceState
from core.retrieval.bm25 import BM25Index


def legacy_index(graph) -> BM25Index:
    """Pre-optimization reference: scan every graph fact for each document."""
    index = BM25Index(lexicon=graph.lexicon)
    for evidence in graph.evidence_by_id.values():
        records = [record for bucket in graph.facts_by_subject_attribute.values()
                   for record in bucket if record.source_row_id == evidence.source_row_id]
        if any(record.evidence_status == EvidenceState.VERIFIED_SUPPORT for record in records):
            status = EvidenceState.VERIFIED_SUPPORT
        elif any(record.evidence_status == EvidenceState.CONFLICTING for record in records):
            status = EvidenceState.CONFLICTING
        elif any(record.evidence_status == EvidenceState.VERIFIED_REFUTATION for record in records):
            status = EvidenceState.VERIFIED_REFUTATION
        else:
            status = EvidenceState.UNVERIFIED_CANDIDATE
        index.add_document(evidence_id=evidence.source_row_id, text=evidence.text,
                           source_date=evidence.observed_on, evidence_status=status,
                           entities=tuple(f.subject for f in evidence.facts),
                           attributes=tuple(f.attribute for f in evidence.facts), facts=evidence.facts,
                           provenance=evidence.provenance, raw_record=evidence)
    index.build()
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=(250, 500, 1000, 1897))
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    with (ROOT / "data/practice.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    lexicon = json.loads((ROOT / "data/lexicon.json").read_text(encoding="utf-8"))
    report: dict[str, Any] = {"corpus": "practice.csv prefixes; index construction timed separately from graph construction", "sizes": []}
    for size in args.sizes:
        subset = rows[:size]
        if len(subset) != size:
            raise ValueError(f"requested {size} rows; dataset has {len(rows)}")
        graph = build_graph(subset, lexicon)
        start = time.perf_counter(); legacy = legacy_index(graph); legacy_seconds = time.perf_counter() - start
        start = time.perf_counter(); optimized = BM25Index.from_graph(graph); optimized_seconds = time.perf_counter() - start
        comparisons = []
        for query in subset[:min(20, len(subset))]:
            old = legacy.search(query["text"], query.get("date"), top_k=10, exclude_evidence_ids=(query["id"],))
            new = optimized.search(query["text"], query.get("date"), top_k=10, exclude_evidence_ids=(query["id"],))
            equivalent = ([x.evidence_id for x in old] == [x.evidence_id for x in new]
                          and all(abs(a.bm25_score - b.bm25_score) < 1e-12 for a, b in zip(old, new)))
            comparisons.append(equivalent)
        report["sizes"].append({"documents": size, "fact_records": sum(map(len, graph.facts_by_subject_attribute.values())),
                                "legacy_seconds": legacy_seconds, "optimized_seconds": optimized_seconds,
                                "speedup": legacy_seconds / optimized_seconds if optimized_seconds else None,
                                "retrieval_equivalent_queries": sum(comparisons), "checked_queries": len(comparisons),
                                "equivalent": all(comparisons)})
    payload = json.dumps(report, indent=2)
    if args.output_json:
        if args.output_json.exists():
            raise FileExistsError(f"refusing to overwrite: {args.output_json}")
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
