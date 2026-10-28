"""Benchmark the temporal graph on practice rows shaped like runtime input."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from foundation import load_inputs
from core.graph import EvidenceResolver, TemporalIndex, build_graph_from_paths
from core.graph.diagnostics import practice_extraction_metrics

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default=str(ROOT / "data" / "practice.csv"))
    parser.add_argument("--lexicon", default=str(ROOT / "data" / "lexicon.json"))
    parser.add_argument("--reference", default=str(ROOT / "data" / "practice.csv"))
    parser.add_argument("--query-iterations", type=int, default=1000)
    args = parser.parse_args()
    reference_data = load_inputs(args.reference, args.lexicon)
    if reference_data.lexicon is None:
        raise SystemExit("reference inputs are invalid: " + "; ".join(reference_data.issues))
    with tempfile.TemporaryDirectory(prefix="neuron5-runtime-shape-") as temp_dir:
        runtime_csv = Path(temp_dir) / "universe.csv"
        with open(args.universe, "r", encoding="utf-8-sig", newline="") as source:
            rows = csv.DictReader(source)
            with runtime_csv.open("w", encoding="utf-8", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=["id", "text", "date", "label"])
                writer.writeheader()
                for row in rows:
                    writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
        tracemalloc.start()
        start = time.perf_counter()
        graph = build_graph_from_paths(runtime_csv, args.lexicon, args.reference)
        build_seconds = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        resolver = EvidenceResolver(graph)
        temporal = TemporalIndex(graph)
        facts = [record for records in graph.facts_by_subject_attribute.values() for record in records]
        query_targets = facts[:min(100, len(facts))]
        durations: list[float] = []
        for i in range(max(0, args.query_iterations)):
            record = query_targets[i % len(query_targets)] if query_targets else None
            if record is None:
                break
            started = time.perf_counter()
            resolver.query(record.fact, record.observed_on)
            temporal.get_fact_history(record.fact.subject, record.fact.attribute)
            durations.append(time.perf_counter() - started)
        report = {
            "input_rows": len(graph.evidence_by_id),
            "entities": len(graph.entities),
            "fact_records": len(facts),
            "verified_support_records": sum(r.evidence_status.value == "VERIFIED_SUPPORT" for r in facts),
            "unverified_candidates": sum(r.evidence_status.value == "UNVERIFIED_CANDIDATE" for r in facts),
            "conflicting_records": sum(r.evidence_status.value == "CONFLICTING" for r in facts),
            "build_seconds": build_seconds,
            "tracemalloc_peak_bytes": peak_bytes,
            "indexed_queries": len(durations),
            "query_mean_ms": statistics.mean(durations) * 1000 if durations else 0,
            "query_p95_ms": sorted(durations)[int((len(durations) - 1) * 0.95)] * 1000 if durations else 0,
            "practice_extraction": practice_extraction_metrics(reference_data),
            "evidence_issues": len(graph.issues),
            "note": "Practice evidence is benchmark input, not independent factual evidence for unlabeled claims.",
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
