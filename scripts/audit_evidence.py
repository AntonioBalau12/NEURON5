"""Print a conservative evidence-feasibility report for the practice data."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from foundation import evidence_audit, load_inputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="data/practice.csv")
    parser.add_argument("--lexicon", default="data/lexicon.json")
    args = parser.parse_args()
    data = load_inputs(args.universe, args.lexicon)
    report = evidence_audit(data)
    report["input_issues"] = len(data.issues)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True))
    if data.issues:
        print("sample issues:", *data.issues[:20], sep="\n- ")
    return 0 if data.lexicon is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
