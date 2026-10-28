"""Learn the relation->attribute table from DEV rows only (experiments/shared/data/dev_rows.csv).

Usage: py experiments/openie/tools/learn.py [--out experiments/openie/data/relation_table.json]
The saved table is the only thing extraction reads; extraction never sees a gold form.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from oie.model import Model, value_sig  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402
from oie.values import UNIT_SYMBOLS, UNIT_WORDS  # noqa: E402

DEV = ROOT / "experiments" / "shared" / "data" / "dev_rows.csv"
LEXICON = ROOT / "data" / "lexicon.json"


def load_dev(path: Path = DEV) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def train(rows: list[dict], lexicon_path: Path = LEXICON, params: Params | None = None) -> Model:
    model = Model()
    physical = set(UNIT_SYMBOLS.values()) | set(UNIT_WORDS.values())
    for r in rows:
        for x in json.loads(r["form"]):
            v = x["value"]
            if v["kind"] == "quantity" and v["unit"] not in physical:
                model.units.add(v["unit"])
            elif v["kind"] == "name":
                model.names.add(v["value"])
    ex = Extractor(lexicon_path, model, params or Params())
    for r in rows:
        gold = json.loads(r["form"])
        sents = ex.analyse(r["text"])
        for g in gold:
            subj, attr, val = g["subject"], g["attribute"], g["value"]
            kind = val["kind"]
            best = None
            for s in sents:
                has_subj = any(m.entity == subj for m in s.mentions)
                if kind == "boolean":
                    if has_subj:
                        best = (s, None, 2)
                    elif best is None:
                        best = (s, None, 0)
                    continue
                pool = s.names if kind == "name" else s.vals
                for v in pool:
                    if v.kind != kind:
                        continue
                    if kind == "name":
                        if v.surface != val["value"]:
                            continue
                    else:
                        want = {k: w for k, w in val.items() if k != "op"}
                        if v.value != want:
                            continue
                    score = (2 if has_subj else 0) + (1 if v.readable else 0)
                    if best is None or score > best[2]:
                        best = (s, v, score)
            if best is None:
                continue
            s, v, _ = best
            if kind == "boolean":
                feats = ex.bool_feats(s)
                model.add(attr, kind, None, set(feats))
            else:
                allv = sorted(s.vals + s.names, key=lambda z: z.start)
                others = [o for o in allv if o is not v and not (o.kind == "name" and v.kind != "name")]
                feats = ex.features(s, v, others, ex.skip_spans(s))
                model.add(attr, kind, value_sig(kind, val), set(feats))
    model.finalize()
    return model


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "data" / "relation_table.json"))
    args = ap.parse_args()
    rows = load_dev()
    model = train(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    model.save(args.out)
    print(f"trained on {len(rows)} dev rows: {len(model.attr_n)} attributes, {sum(model.attr_n.values())} aligned gold facts, "
          f"{len(model.units)} counted-noun units, {len(model.names)} gazetteer names -> {args.out}")


if __name__ == "__main__":
    main()
