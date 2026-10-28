"""Throughput / memory check on ~20,000 rows: full_input.csv replicated with fresh ids (input columns only).

Everything is written to output/_scale/ (deleted at the end) so the frozen output/facts.jsonl and the derived
output/facts_mapped.csv are never touched (extract_openie.py writes facts_mapped.csv next to its --out file).
Run: py experiments/openie/tools/scale_test.py [reps]   (default 11 reps x 1,897 rows = 20,867 rows)
"""
import csv
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
reps = int(sys.argv[1]) if len(sys.argv) > 1 else 11
src = ROOT / "experiments" / "shared" / "data" / "full_input.csv"
work = HERE / "output" / "_scale"
work.mkdir(parents=True, exist_ok=True)
tmp_in = work / "input.csv"
tmp_out = work / "facts.jsonl"
rows = list(csv.DictReader(src.open(encoding="utf-8-sig", newline="")))
n = 0
with tmp_in.open("w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["id", "text", "date", "label"])
    for rep in range(reps):
        for r in rows:
            w.writerow([f"{r['id']}-r{rep}", r["text"], r["date"], r["label"]])
            n += 1
print("rows written", n)
t0 = time.perf_counter()
res = subprocess.run([sys.executable, str(HERE / "extract_openie.py"), "--input", str(tmp_in), "--lexicon",
                      str(ROOT / "data" / "lexicon.json"), "--out", str(tmp_out)], capture_output=True, text=True)
wall = time.perf_counter() - t0
print(res.stdout.strip(), res.stderr.strip()[:500])
print(f"wall seconds incl. interpreter start and output writing: {wall:.1f}")
shutil.rmtree(work)
