"""Performance-only synthetic benchmark for the selected graph extractor."""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.graph import build_graph_from_paths


def _rss_bytes() -> tuple[int, int]:
    if os.name == "nt":
        import ctypes

        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel.GetCurrentProcess()

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong),
                        ("peak", ctypes.c_size_t), ("working", ctypes.c_size_t),
                        ("qpp", ctypes.c_size_t), ("qp", ctypes.c_size_t),
                        ("qnpp", ctypes.c_size_t), ("qnp", ctypes.c_size_t),
                        ("page", ctypes.c_size_t), ("peak_page", ctypes.c_size_t)]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        api = ctypes.windll.psapi.GetProcessMemoryInfo
        api.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
        api.restype = ctypes.c_int
        if not api(process, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return counters.working, counters.peak
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    try:
        current = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        current = peak_bytes
    return current, peak_bytes


def _limit_cpu_cores(count: int = 2) -> str | None:
    try:
        if hasattr(os, "sched_getaffinity"):
            available = sorted(os.sched_getaffinity(0))
            selected = set(available[:count])
            os.sched_setaffinity(0, selected)
            return ",".join(map(str, sorted(selected)))
        if os.name == "nt":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            process = kernel.GetCurrentProcess()
            process_mask, system_mask = ctypes.c_size_t(), ctypes.c_size_t()
            get_mask = kernel.GetProcessAffinityMask
            get_mask.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
            if not get_mask(process, ctypes.byref(process_mask), ctypes.byref(system_mask)):
                return None
            selected = 0
            for bit in range(process_mask.value.bit_length()):
                if process_mask.value & (1 << bit):
                    selected |= 1 << bit
                    if selected.bit_count() >= count:
                        break
            set_mask = kernel.SetProcessAffinityMask
            set_mask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
            return hex(selected) if selected and set_mask(process, selected) else None
    except (AttributeError, OSError):
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20_000)
    parser.add_argument("--source", default=str(ROOT / "data" / "practice.csv"))
    args = parser.parse_args()
    if args.rows < 1:
        raise SystemExit("--rows must be positive")
    resolver_artifact = ROOT / "core" / "graph" / "attribute_resolver.json"
    artifact_bytes = resolver_artifact.stat().st_size if resolver_artifact.is_file() else 0
    cpu_mask = _limit_cpu_cores(2)
    source_path = Path(args.source)
    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    if not source_rows:
        raise SystemExit("synthetic workload source is empty")
    baseline_rss, baseline_peak = _rss_bytes()
    with tempfile.TemporaryDirectory(prefix="neuron5-semantic-bench-") as temp:
        universe = Path(temp) / "universe.csv"
        with universe.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "text", "date", "label"])
            writer.writeheader()
            for index in range(args.rows):
                row = source_rows[index % len(source_rows)]
                writer.writerow({"id": f"synthetic-{index:06d}", "text": row.get("text", ""),
                                 "date": row.get("date", ""), "label": ""})
        started_wall = time.perf_counter()
        started_cpu = time.process_time()
        graph = build_graph_from_paths(universe, ROOT / "data" / "lexicon.json",
                                       use_packaged_practice=False)
        wall = time.perf_counter() - started_wall
        cpu = time.process_time() - started_cpu
        current_rss, peak_rss = _rss_bytes()
        records = [record for values in graph.facts_by_subject_attribute.values() for record in values]
    print(json.dumps({
        "workload": "synthetic performance-only rows repeated from practice claim text; no forms or labels",
        "rows": args.rows,
        "facts_extracted": len(records),
        "all_records_unverified": all(record.evidence_status.value == "UNVERIFIED_CANDIDATE" for record in records),
        "extractor": (
            "selected money-only hybrid (expanded deterministic + TF-IDF resolver)"
            if artifact_bytes else "expanded deterministic fallback"
        ),
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "cpu_cores_equivalent": cpu / wall if wall else 0,
        "cpu_affinity": cpu_mask,
        "rows_per_second": args.rows / wall if wall else 0,
        "baseline_rss_mib": baseline_rss / (1024 * 1024),
        "peak_rss_mib": peak_rss / (1024 * 1024),
        "incremental_peak_rss_mib": max(0, peak_rss - baseline_peak) / (1024 * 1024),
        "model_artifact_bytes": artifact_bytes,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
