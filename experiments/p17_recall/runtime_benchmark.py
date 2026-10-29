"""Performance-only synthetic replay; reads no forms or labels in timed loops."""
from __future__ import annotations
import json, os, platform, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(OUT))

from foundation import load_inputs
from core.graph.semantic_extraction import grouped_train_validation_split
from candidate_factory import CandidateFactory
from benchmark_recall import _memory_mb, CONFIRM_SEED

N_ROWS = 20_000

def _limit_two_cpus():
    try:
        if hasattr(os, "sched_getaffinity"):
            available = sorted(os.sched_getaffinity(0))
            chosen = set(available[:2]); os.sched_setaffinity(0, chosen)
            return {"applied": True, "method": "sched_setaffinity", "cpu_ids": sorted(chosen)}
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            k = ctypes.WinDLL("kernel32", use_last_error=True)
            k.GetCurrentProcess.restype = wintypes.HANDLE
            process = k.GetCurrentProcess()
            k.GetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
            k.GetProcessAffinityMask.restype = wintypes.BOOL
            system_mask, process_mask = ctypes.c_size_t(), ctypes.c_size_t()
            if not k.GetProcessAffinityMask(process, ctypes.byref(process_mask), ctypes.byref(system_mask)):
                return {"applied": False, "reason": f"GetProcessAffinityMask failed ({ctypes.get_last_error()})"}
            available = [i for i in range(system_mask.value.bit_length()) if system_mask.value & (1 << i)]
            chosen = available[:2]
            mask = sum(1 << i for i in chosen)
            k.SetProcessAffinityMask.argtypes = [wintypes.HANDLE, ctypes.c_size_t]
            k.SetProcessAffinityMask.restype = wintypes.BOOL
            applied = bool(k.SetProcessAffinityMask(process, ctypes.c_size_t(mask)))
            return {"applied": applied, "method": "SetProcessAffinityMask", "cpu_ids": chosen,
                    "reason": None if applied else "SetProcessAffinityMask failed"}
    except Exception as exc:
        return {"applied": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {"applied": False, "reason": "platform affinity API unavailable"}

def main():
    affinity = _limit_two_cpus()
    data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
    split = grouped_train_validation_split(data, seed=CONFIRM_SEED)
    validation_texts = [row.text for row in data.rows if row.row_id in split.validation_row_ids]
    t0 = time.perf_counter()
    factory = CandidateFactory.fit(data, split.train_row_ids, per_row_cap=512, global_cap=1_000_000)
    fit_seconds = time.perf_counter() - t0
    # The timed input objects contain only synthetic IDs and text strings.
    synthetic = [(f"synthetic-{i:05d}", validation_texts[i % len(validation_texts)]) for i in range(N_ROWS)]
    query_samples = synthetic[:500]
    query_latency = {}
    for k in (1, 3, 5, 10, 20):
        start = time.perf_counter()
        n = 0
        for _rid, text in query_samples:
            factory.indexes["full_claim"].search(text, k); n += 1
        query_latency[str(k)] = {"queries": n, "mean_ms": (time.perf_counter()-start)*1000/n}
    configs = []
    baseline = factory.baseline()
    for config in ("R0", "R4", "R5"):
        factory.generated_total = factory.emitted_total = 0
        generated = emitted = skipped = truncated_rows = 0
        start = time.perf_counter(); cpu0 = time.process_time()
        for row_id, text in synthetic:
            if config == "R0":
                result = baseline.extract(text, row_id)
                count = len(result.facts)
                generated += count; emitted += count
            else:
                candidates, stats = factory.generate(row_id, text, config=config, k=5)
                if stats.get("generated_before_caps") is not None:
                    generated += stats["generated_before_caps"]
                emitted += len(candidates)
                skipped += int(stats.get("skipped_after_global_cap", False))
                truncated_rows += int(stats.get("per_row_truncated", False) or stats.get("global_truncated", False))
        elapsed = time.perf_counter() - start
        cpu = time.process_time() - cpu0
        rss, rss_method = _memory_mb()
        configs.append({"configuration": config, "rows": N_ROWS, "generated_candidates_before_caps": generated,
            "emitted_candidates": emitted, "rows_skipped_after_global_cap": skipped,
            "truncated_rows": truncated_rows, "per_row_cap": factory.per_row_cap,
            "global_cap": factory.global_cap, "wall_seconds": elapsed, "cpu_seconds": cpu,
            "rows_per_second": N_ROWS/elapsed if elapsed else 0,
            "projected_18k_seconds": 18_000*elapsed/N_ROWS,
            "peak_memory_mb": rss, "memory_measurement": rss_method})
    payload = {"purpose": "performance only; synthetic repeated practice-length claim text, no labels or forms in timed loops",
        "platform": platform.platform(), "synthetic_rows": N_ROWS, "source_text_count": len(validation_texts),
        "split_seed": CONFIRM_SEED, "training_row_count_for_semantic_indexes": len(split.train_row_ids),
        "semantic_index_fit_wall_seconds": fit_seconds, "two_cpu_affinity": affinity,
        "BM25_full_claim_query_latency": query_latency, "configurations": configs}
    (OUT / "runtime_benchmark.json").write_text(json.dumps(payload, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
