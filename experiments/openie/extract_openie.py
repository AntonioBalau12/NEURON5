"""Offline OpenIE-style fact reconstruction for Hooly sentences (stdlib only, no network, no LLM).

  py experiments/openie/extract_openie.py --input experiments/shared/data/full_input.csv \
      --lexicon data/lexicon.json --out experiments/openie/output/facts.jsonl

Input columns used: id, text, date, label. Gold `form` columns, if present, are ignored.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from oie.model import Model  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402

PRIVATE = ("_key", "_val", "_drop")


def peak_rss_mb() -> float | None:
    """Peak working set of this process in MiB (Windows via ctypes, Linux via resource)."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            k32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
            if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                return None
            return pmc.PeakWorkingSetSize / 2**20
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return None


def clean(f: dict) -> dict:
    return {k: v for k, v in f.items() if k not in PRIVATE}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--lexicon", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--table", default=str(HERE / "data" / "relation_table.json"))
    args = ap.parse_args()

    t0 = time.perf_counter()
    model = Model.load(args.table)
    ex = Extractor(args.lexicon, model, Params())
    with open(args.input, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t1 = time.perf_counter()
    n = 0
    status: dict[str, int] = {}
    flat = []
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            for f in ex.extract(row):
                f = clean(f)
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
                n += 1
                status[f["parse_status"]] = status.get(f["parse_status"], 0) + 1
                flat.append(f)
    t2 = time.perf_counter()
    csv_path = out.with_name("facts_mapped.csv")
    cols = ["extraction_id", "source_row_id", "source_label", "parse_status", "subject", "attribute", "value_kind",
            "value", "negated", "relation_surface", "object_surface", "temporal_qualifier", "fact_observation_date",
            "valid_from", "valid_to", "extraction_confidence", "source_text_span", "notes"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in flat:
            if f["parse_status"] == "unmapped":
                continue
            w.writerow([f["extraction_id"], f["source_row_id"], f["source_label"], f["parse_status"], f["subject"],
                        f["attribute"], f["value"]["kind"], json.dumps(f["value"], ensure_ascii=False), f["negated"],
                        f["relation_surface"] or "", f["object_surface"] or "", f["temporal_qualifier"] or "",
                        f["fact_observation_date"] or "", f["valid_from"] or "", f["valid_to"] or "",
                        f["extraction_confidence"], f["source_text_span"], f["notes"]])
    rss = peak_rss_mb()
    print(json.dumps({"rows": len(rows), "facts": n, "by_parse_status": status,
                      "load_s": round(t1 - t0, 3), "extract_s": round(t2 - t1, 3),
                      "rows_per_s": round(len(rows) / max(t2 - t1, 1e-9), 1),
                      "peak_rss_mib": round(rss, 1) if rss else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
