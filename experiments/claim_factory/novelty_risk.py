"""Novelty risk: how close are generated claim texts to the practice rows' texts?

The contract refuses a claim whose text IS a row of the input; the real input holds ~18,000 further rows that are not available
here.  This measures the closeness to the 1,897 known rows (word-set Jaccard) as a proxy for the chance of an accidental
exact collision with an unseen row (those rows come from the same generator as the practice rows).

  py experiments/claim_factory/novelty_risk.py --claims <claims_valid.csv> [--out report.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

from cf_common import PRACTICE_CSV


def toks(t: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9€%$.]+", t.casefold()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--claims", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rows = [(r["id"], r["text"], toks(r["text"])) for r in csv.DictReader(PRACTICE_CSV.open(encoding="utf-8-sig", newline=""))]
    claims = list(csv.DictReader(Path(a.claims).open(encoding="utf-8-sig", newline="")))
    buckets = {"==1.0": 0, "0.8-0.99": 0, "0.6-0.79": 0, "<0.6": 0}
    near = []
    for c in claims:
        tc = toks(c["text"])
        best = max(((len(tc & t) / len(tc | t) if tc | t else 0.0), rid, txt) for rid, txt, t in rows)
        s = best[0]
        key = "==1.0" if s >= 1.0 else "0.8-0.99" if s >= 0.8 else "0.6-0.79" if s >= 0.6 else "<0.6"
        buckets[key] += 1
        if s >= 0.8:
            near.append({"claim": c["text"], "closest_row": best[1], "row_text": best[2], "jaccard": round(s, 3)})
    rep = {"claims": len(claims), "max_jaccard_to_a_practice_row": buckets, "near_examples": near[:15]}
    print(json.dumps({k: rep[k] for k in ("claims", "max_jaccard_to_a_practice_row")}, indent=2))
    for n in near[:8]:
        print("  ", n["jaccard"], "|", n["claim"], "||", n["row_text"])
    if a.out:
        Path(a.out).write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
