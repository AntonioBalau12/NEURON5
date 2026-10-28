"""Profile complete M2 inference on runtime-shaped input (synthetic scale is labeled)."""

from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

os.environ.update({"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"})
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from foundation import load_inputs
from runner import atomic_write_csv, predict_unlabeled


def expanded_rows(practice: list[dict[str, str]], target_rows: int) -> list[dict[str, str]]:
    if target_rows < len(practice):
        raise ValueError("target rows must be at least the practice row count")
    rows = [dict(row) for row in practice]
    extra = target_rows - len(rows)
    for i in range(extra):
        source = practice[i % len(practice)]
        rows.append({"id": f"bench-{i:06d}", "text": source["text"], "date": source["date"], "label": ""})
    return rows


class PeakRSS:
    def __init__(self) -> None:
        self.peak = self._read_peak()

    @staticmethod
    def _read_peak() -> int:
        if os.name == "nt":
            class Counters(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                            ("PrivateUsage", ctypes.c_size_t)]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_int
            process = kernel32.GetCurrentProcess()
            ok = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            return int(counters.PeakWorkingSetSize)
        status = Path("/proc/self/status")
        if status.is_file():
            for line in status.read_text().splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) * 1024
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys.platform == "darwin" else value * 1024)

    def __enter__(self):
        return self

    def __exit__(self, *_: Any) -> None:
        self.peak = self._read_peak()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    v2_default = ROOT / "ml/classical/results_m2_v2/model.joblib"
    v1_default = ROOT / "ml/classical/results_m2_v1/model.joblib"
    model_default = v2_default if v2_default.is_file() else v1_default

    parser.add_argument("--universe", type=Path, help="Use the actual runtime-shaped universe CSV")
    parser.add_argument("--rows", type=int, default=20_000, help="Synthetic row target when --universe is omitted")
    parser.add_argument("--model", type=Path, default=model_default)
    parser.add_argument("--practice", type=Path, default=ROOT / "data/practice.csv")
    parser.add_argument("--lexicon", type=Path, default=ROOT / "data/lexicon.json")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    started = time.perf_counter()
    report: dict[str, Any] = {"synthetic_scale": args.universe is None, "requested_rows": args.rows if args.universe is None else None,
                              "cpu_threads": 2, "offline_code_path": True}
    with PeakRSS() as rss:
        with tempfile.TemporaryDirectory() as temp:
            tempdir = Path(temp)
            if args.universe is None:
                with args.practice.open(encoding="utf-8-sig", newline="") as handle:
                    base = list(csv.DictReader(handle))
                generated = expanded_rows(base, args.rows)
                universe = tempdir / "universe.csv"
                with universe.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label"))
                    writer.writeheader()
                    writer.writerows({key: row.get(key, "") for key in writer.fieldnames} for row in generated)
            else:
                universe = args.universe

            t0 = time.perf_counter()
            data = load_inputs(universe, args.lexicon)
            report["input_load_seconds"] = time.perf_counter() - t0
            if data.issues or data.lexicon is None:
                raise ValueError("runtime input failed validation: " + "; ".join(data.issues[:20]))

            timing_breakdown: dict[str, float] = {}
            t1 = time.perf_counter()
            predictions = predict_unlabeled(data, str(args.model), str(args.practice), timing_breakdown=timing_breakdown)
            report["graph_index_features_prediction_seconds"] = time.perf_counter() - t1
            report.update(timing_breakdown)
            output_rows = []
            for row in data.rows:
                if row.label is None:
                    label, confidence = predictions.get(row.row_id, ("unsure", None))
                    output_rows.append({"id": row.row_id, "type": "", "text": "", "form": "", "label": label,
                                        "confidence": "" if confidence is None else confidence})
            output_path = tempdir / "output.csv"
            t2 = time.perf_counter()
            atomic_write_csv(output_path, output_rows)
            report["csv_output_seconds"] = time.perf_counter() - t2
            report["rows"] = len(data.rows)
            report["unlabeled_rows"] = len(output_rows)
            report["output_bytes"] = output_path.stat().st_size
            report["output_columns"] = list(output_rows[0]) if output_rows else []

    report["end_to_end_seconds"] = time.perf_counter() - started
    report["process_peak_rss_mib"] = round(rss.peak / 1024**2, 2)
    report["official_limits"] = {"cpu_cores": 2, "memory_mib": 6144, "deadline_seconds": 1800,
                                  "read_only_root": "not enforced outside Docker", "offline": "no network calls in this benchmark path"}
    payload = json.dumps(report, indent=2)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        if args.output_json.exists():
            raise FileExistsError(f"refusing to overwrite: {args.output_json}")
        args.output_json.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
