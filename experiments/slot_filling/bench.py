"""Indicative speed / memory benchmark. Runs extract_slots.py as a child process pinned to 2 logical CPUs (Windows affinity mask),
writes ONLY under output/_bench/ (never output/facts.jsonl), and reads the child's peak working set.

  py experiments/slot_filling/bench.py [--rows 20000]
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.wintypes as wt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BENCH = HERE / "output" / "_bench"


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def run(inp: Path, out: Path, cpus=(0, 1)):
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wt.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    cmd = [sys.executable, str(HERE / "extract_slots.py"), "--input", str(inp), "--lexicon", str(ROOT / "data" / "lexicon.json"),
           "--out", str(out), "--csv", str(out.with_suffix(".csv"))]
    env = {**__import__("os").environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "2",
           "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"}
    t0 = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    h = k32.OpenProcess(0x0400 | 0x0010 | 0x0200, False, p.pid)  # QUERY_INFORMATION | VM_READ | SET_INFORMATION
    mask = sum(1 << c for c in cpus)
    k32.SetProcessAffinityMask(h, ctypes.c_size_t(mask))
    out_s, _ = p.communicate()
    wall = time.perf_counter() - t0
    pmc = PMC()
    pmc.cb = ctypes.sizeof(pmc)
    psapi.GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb)
    stats = json.loads(out_s.strip().splitlines()[-1])
    stats.update({"wall_s": round(wall, 2), "peak_rss_mb": round(pmc.PeakWorkingSetSize / 2**20, 1),
                  "peak_pagefile_mb": round(pmc.PeakPagefileUsage / 2**20, 1), "affinity_cpus": list(cpus), "returncode": p.returncode})
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=20000)
    a = ap.parse_args()
    BENCH.mkdir(parents=True, exist_ok=True)
    src = ROOT / "experiments" / "shared" / "data" / "full_input.csv"
    with src.open(encoding="utf-8-sig", newline="") as fh:
        base = list(csv.DictReader(fh))
    big = BENCH / f"input_{a.rows}.csv"
    with big.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "text", "date", "label"])
        w.writeheader()
        for i in range(a.rows):
            r = base[i % len(base)]
            w.writerow({"id": f"{r['id']}~{i // len(base)}", "text": r["text"], "date": r["date"], "label": r["label"]})
    res = {"full_input_current_code": run(src, BENCH / "facts_current_code.jsonl"),
           f"replicated_{a.rows}": run(big, BENCH / f"facts_{a.rows}.jsonl")}
    (BENCH / "bench.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
