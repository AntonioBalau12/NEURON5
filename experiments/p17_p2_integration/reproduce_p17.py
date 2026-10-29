"""Re-run the published P1.7 ablations into this integration experiment folder."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "p17_recall"))

import benchmark_recall

benchmark_recall.OUT = Path(__file__).resolve().parent / "p17_reproduction"
benchmark_recall.OUT.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    benchmark_recall.main()
