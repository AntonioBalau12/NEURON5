"""Populate the Docker image's reference graph using packaged practice evidence."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.graph.reference import DEFAULT_SNAPSHOT, write_reference_snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args()
    counts = write_reference_snapshot(args.output, ROOT / "data/practice.csv", ROOT / "data/lexicon.json")
    print("Reference graph populated:", json.dumps(counts), "->", args.output)
