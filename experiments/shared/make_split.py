"""Coordinator-owned: build the fixed dev / held-out split. Deterministic, no randomness.

held-out  = sha1(row id) % 100 < 15   (about 15% of rows)
dev       = everything else

Outputs (relative to this directory):
  data/full_input.csv          id,text,date,label            ALL rows, NO form (runtime-shaped)
  data/dev_rows.csv            id,text,date,label,form       DEV rows only, with gold form
  data/split.json              dev ids, held-out ids (held-out ids only; no held-out text)
  _heldout/heldout_gold.csv    id,text,date,label,form       HELD-OUT gold. Only the evaluator reads it.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "data" / "practice.csv"


def is_heldout(row_id: str) -> bool:
    return int(hashlib.sha1(row_id.encode("utf-8")).hexdigest(), 16) % 100 < 15


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "_heldout").mkdir(exist_ok=True)

    def write(path: Path, fields: list[str], selected: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            for row in selected:
                writer.writerow({key: row[key] for key in fields})

    held = [r for r in rows if is_heldout(r["id"])]
    dev = [r for r in rows if not is_heldout(r["id"])]
    write(HERE / "data" / "full_input.csv", ["id", "text", "date", "label"], rows)
    write(HERE / "data" / "dev_rows.csv", ["id", "text", "date", "label", "form"], dev)
    write(HERE / "_heldout" / "heldout_gold.csv", ["id", "text", "date", "label", "form"], held)
    (HERE / "data" / "split.json").write_text(json.dumps({
        "rule": "sha1(id) % 100 < 15 is held-out",
        "total": len(rows), "dev": len(dev), "heldout": len(held),
        "heldout_ids": [r["id"] for r in held],
    }, indent=1), encoding="utf-8")
    print(f"total={len(rows)} dev={len(dev)} heldout={len(held)}")


if __name__ == "__main__":
    main()
