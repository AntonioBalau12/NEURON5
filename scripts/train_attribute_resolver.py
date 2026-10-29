"""Train and package the selected dependency-free money attribute resolver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from foundation import load_inputs
from core.graph import AttributeResolver, grouped_train_validation_split


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--practice", default=str(ROOT / "data" / "practice.csv"))
    parser.add_argument("--lexicon", default=str(ROOT / "data" / "lexicon.json"))
    parser.add_argument("--output", default=str(ROOT / "core" / "graph" / "attribute_resolver.json"))
    args = parser.parse_args()
    data = load_inputs(args.practice, args.lexicon)
    if data.lexicon is None:
        raise SystemExit("invalid training inputs: " + "; ".join(data.issues))
    split = grouped_train_validation_split(data, seed="neuron5-p15-confirm-v2")
    resolver = AttributeResolver().fit(data, split.train_row_ids)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    resolver.save(output)
    print(json.dumps({
        "artifact": str(output),
        "bytes": output.stat().st_size,
        "train_rows": len(split.train_row_ids),
        "excluded_validation_rows": len(split.validation_row_ids),
        "groups": split.group_count,
        "validation_groups": split.validation_groups,
        "semantic_training_examples": resolver.training_examples,
        "truth_labels_used": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
