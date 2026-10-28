"""Measure CPU seconds, wall seconds and peak RAM of each extraction method.

  py experiments/evaluation/measure_resources.py --methods baseline openie slot_filling combined --out experiments/evaluation/results/resources_<name>.json

Every method runs as its OWN subprocess, one after another (never in parallel), with 2 threads:
OMP_NUM_THREADS, MKL_NUM_THREADS, OPENBLAS_NUM_THREADS, NUMEXPR_NUM_THREADS, VECLIB_MAXIMUM_THREADS = 2.
Libraries that ignore these variables are not constrained; check cpu_seconds / wall_seconds (> 2 means the cap leaked).
Add --affinity to also pin the process tree to two logical CPUs (Windows).

Commands come from resource_commands.json (this folder) or `--cmd name="command with {python} {input} {out}"`.
  {python}  this interpreter (sys.executable)      {input}  experiments/shared/data/full_input.csv
  {out}     <out stem>_runs/<method>/facts.jsonl   the run writes here, never over a method's official output
  {outdir}  <out stem>_runs/<method>
A method with no command configured, or whose command cannot start, is reported as not measured.
`combined` is measured as the combine.py step alone on top of the existing openie/slot_filling outputs;
the JSON adds `combined_pipeline_total` = openie + slot_filling + combine when all three were measured.

How it is measured (Windows, psutil not required)
  * the subprocess is put into a Job Object; the job's accounting gives user+kernel CPU time of the whole process
    tree, including children that already exited;
  * peak RAM: every 20 ms the working sets of all processes in the job are read; `peak_working_set_mb` is the larger of
    (a) the biggest sum of working sets seen at one instant and (b) the biggest per-process OS-reported peak working set.
    Exact for a single process; a sampled lower bound for a process tree;
  * wall seconds: perf_counter around start..exit, so it includes interpreter start-up and imports.
On other systems the fallback is resource.getrusage(RUSAGE_CHILDREN) (CPU, peak RSS).
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

COMMANDS_JSON = C.HERE / "resource_commands.json"
THREAD_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")

# --------------------------------------------------------------------------- Windows probes

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    SIZE_T = ctypes.c_size_t

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", SIZE_T),
                    ("WorkingSetSize", SIZE_T), ("QuotaPeakPagedPoolUsage", SIZE_T), ("QuotaPagedPoolUsage", SIZE_T),
                    ("QuotaPeakNonPagedPoolUsage", SIZE_T), ("QuotaNonPagedPoolUsage", SIZE_T),
                    ("PagefileUsage", SIZE_T), ("PeakPagefileUsage", SIZE_T)]

    class _JOB_ACCT(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                    ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    class _PIDLIST(ctypes.Structure):
        _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD), ("NumberOfProcessIdsInList", wintypes.DWORD),
                    ("ProcessIdList", ctypes.c_size_t * 256)]

    _k32.CreateJobObjectW.restype = wintypes.HANDLE
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]

    def _mem(handle) -> tuple[int, int] | None:
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        if _psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return int(pmc.WorkingSetSize), int(pmc.PeakWorkingSetSize)
        return None

    def _job_pids(job) -> list[int]:
        info = _PIDLIST()
        if _k32.QueryInformationJobObject(job, 3, ctypes.byref(info), ctypes.sizeof(info), None):
            return [int(info.ProcessIdList[i]) for i in range(info.NumberOfProcessIdsInList)]
        return []

    def _job_cpu_seconds(job) -> float | None:
        acct = _JOB_ACCT()
        if _k32.QueryInformationJobObject(job, 1, ctypes.byref(acct), ctypes.sizeof(acct), None):
            return (acct.TotalUserTime + acct.TotalKernelTime) / 1e7
        return None

    def run_measured(cmd: list[str], env: dict[str, str], cwd: Path, log_path: Path, affinity: bool) -> dict[str, Any]:
        job = _k32.CreateJobObjectW(None, None)
        log = log_path.open("wb")
        t0 = time.perf_counter()
        proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        assigned = bool(_k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))))
        if affinity:
            _k32.SetProcessAffinityMask(wintypes.HANDLE(int(proc._handle)), ctypes.c_size_t(0b11))
        peak_sum = 0
        peak_single = 0
        opened: dict[int, Any] = {}
        main_pid = proc.pid
        try:
            while proc.poll() is None:
                total = 0
                pids = _job_pids(job) if assigned else [main_pid]
                for pid in pids:
                    if pid not in opened:
                        opened[pid] = _k32.OpenProcess(0x0410, False, pid) or _k32.OpenProcess(0x1000, False, pid)
                    if opened[pid]:
                        m = _mem(opened[pid])
                        if m:
                            total += m[0]
                            peak_single = max(peak_single, m[1])
                peak_sum = max(peak_sum, total)
                time.sleep(0.02)
            wall = time.perf_counter() - t0
            # processes are gone, but the handles stay valid: read the final per-process peaks and the job CPU
            for handle in list(opened.values()):
                if handle:
                    m = _mem(handle)
                    if m:
                        peak_single = max(peak_single, m[1])
            main_m = _mem(wintypes.HANDLE(int(proc._handle)))
            if main_m:
                peak_single = max(peak_single, main_m[1])
            cpu = _job_cpu_seconds(job) if assigned else None
            if cpu is None:
                ft = [ctypes.c_uint64() for _ in range(4)]
                if _k32.GetProcessTimes(wintypes.HANDLE(int(proc._handle)), *[ctypes.byref(x) for x in ft]):
                    cpu = (ft[2].value + ft[3].value) / 1e7
        finally:
            for handle in opened.values():
                if handle:
                    _k32.CloseHandle(handle)
            _k32.CloseHandle(job)
            log.close()
        return {"returncode": proc.returncode, "wall_seconds": wall, "cpu_seconds": cpu,
                "peak_sampled_sum_bytes": peak_sum, "peak_single_process_bytes": peak_single, "job_object": assigned,
                "processes_seen": len(opened)}
else:
    def run_measured(cmd: list[str], env: dict[str, str], cwd: Path, log_path: Path, affinity: bool) -> dict[str, Any]:
        import resource
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        t0 = time.perf_counter()
        with log_path.open("wb") as log:
            proc = subprocess.run(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
        wall = time.perf_counter() - t0
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        scale = 1 if sys.platform == "darwin" else 1024
        peak = after.ru_maxrss * scale
        return {"returncode": proc.returncode, "wall_seconds": wall,
                "cpu_seconds": (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime),
                "peak_sampled_sum_bytes": peak, "peak_single_process_bytes": peak, "job_object": False, "processes_seen": 1}


# --------------------------------------------------------------------------- driver

def load_commands(overrides: list[str]) -> dict[str, list[str] | None]:
    commands: dict[str, list[str] | None] = {}
    if COMMANDS_JSON.exists():
        raw = json.loads(COMMANDS_JSON.read_text(encoding="utf-8"))
        commands.update({k: v for k, v in raw.items() if not k.startswith("_")})
    for item in overrides:
        name, _, command = item.partition("=")
        commands[name.strip()] = shlex.split(command, posix=False)
    return commands


def expand(cmd: list[str], mapping: dict[str, str]) -> list[str]:
    out = []
    for part in cmd:
        for key, value in mapping.items():
            part = part.replace("{" + key + "}", value)
        out.append(part.strip('"') if len(part) > 1 and part[0] == part[-1] == '"' else part)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--methods", nargs="+", default=["baseline", "openie", "slot_filling", "combined"])
    ap.add_argument("--out", required=True, help="resources JSON to create (must not exist)")
    ap.add_argument("--cmd", action="append", default=[], help='name="command"; overrides resource_commands.json')
    ap.add_argument("--repeats", type=int, default=1, help="runs per method; the median is reported")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--affinity", action="store_true", help="also pin to two logical CPUs (Windows)")
    ap.add_argument("--input", default=str(C.FULL_INPUT))
    args = ap.parse_args()

    out_json = Path(args.out)
    if out_json.exists():
        print(f"ERROR: {out_json} exists; results are never overwritten")
        return 2
    runs_dir = out_json.with_name(out_json.stem + "_runs")
    commands = load_commands(args.cmd)
    env = dict(os.environ)
    for var in THREAD_VARS:
        env[var] = str(args.threads)
    env.update({"PYTHONUTF8": "1", "TOKENIZERS_PARALLELISM": "false"})

    n_rows = len(C.read_csv(args.input))
    results: dict[str, Any] = {}
    for method in args.methods:
        cmd = commands.get(method)
        if not cmd:
            results[method] = {"measured": False, "reason": "no command configured (resource_commands.json or --cmd)"}
            print(f"{method}: not measured (no command configured)")
            continue
        mdir = runs_dir / method
        mdir.mkdir(parents=True, exist_ok=True)
        mapping = {"python": sys.executable, "input": str(args.input), "out": str(mdir / "facts.jsonl"), "outdir": str(mdir)}
        full = expand(cmd, mapping)
        runs = []
        for i in range(args.repeats):
            if (mdir / "facts.jsonl").exists():
                (mdir / "facts.jsonl").unlink()
            try:
                r = run_measured(full, env, C.ROOT, mdir / f"run{i}.log", args.affinity)
            except OSError as exc:
                r = {"returncode": None, "error": str(exc)}
            r["peak_working_set_mb"] = round(max(r.get("peak_sampled_sum_bytes", 0), r.get("peak_single_process_bytes", 0)) / 2**20, 1)
            if (mdir / "facts.jsonl").exists():
                with (mdir / "facts.jsonl").open(encoding="utf-8") as fh:
                    r["facts_written"] = sum(1 for line in fh if line.strip())
            runs.append(r)
            print(f"{method} run {i}: exit {r['returncode']} cpu {r.get('cpu_seconds')} s wall {r.get('wall_seconds')} s peak {r['peak_working_set_mb']} MB")
        ok = [r for r in runs if r.get("returncode") == 0]
        summary: dict[str, Any] = {"measured": bool(ok), "command": full, "runs": runs, "rows_processed": n_rows}
        if ok:
            summary.update({
                "returncode": 0,
                "cpu_seconds": round(statistics.median(r["cpu_seconds"] for r in ok if r.get("cpu_seconds") is not None), 2) if any(r.get("cpu_seconds") is not None for r in ok) else None,
                "wall_seconds": round(statistics.median(r["wall_seconds"] for r in ok), 2),
                "peak_working_set_mb": round(statistics.median(r["peak_working_set_mb"] for r in ok), 1),
                "cpu_per_wall": round(statistics.median(r["cpu_seconds"] / r["wall_seconds"] for r in ok if r.get("cpu_seconds") is not None), 2)
                if any(r.get("cpu_seconds") is not None for r in ok) else None,
                "cpu_seconds_per_1000_rows": round(1000 * statistics.median(r["cpu_seconds"] for r in ok if r.get("cpu_seconds") is not None) / n_rows, 2)
                if any(r.get("cpu_seconds") is not None for r in ok) else None,
            })
        else:
            summary["returncode"] = runs[-1].get("returncode") if runs else None
            summary["reason"] = f"command failed; see {mdir}"
        results[method] = summary

    parts = [results.get(m) for m in ("openie", "slot_filling", "combined")]
    if all(p and p.get("measured") for p in parts):
        results["combined_pipeline_total"] = {
            "measured": True, "note": "openie + slot_filling + combine step (sequential, so wall adds up)",
            "cpu_seconds": round(sum(p["cpu_seconds"] for p in parts), 2), "wall_seconds": round(sum(p["wall_seconds"] for p in parts), 2),
            "peak_working_set_mb": max(p["peak_working_set_mb"] for p in parts)}
    payload = {
        "machine": {"platform": platform.platform(), "processor": platform.processor(), "cpu_count": os.cpu_count(), "python": platform.python_version()},
        "threads": args.threads, "affinity_pinned": args.affinity, "thread_env": {v: env[v] for v in THREAD_VARS},
        "method_of_measurement": __doc__.split("How it is measured")[1].strip(),
        "sequential": True, "repeats": args.repeats, "input": str(args.input), "rows": n_rows,
        "methods": results,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print("written", out_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
