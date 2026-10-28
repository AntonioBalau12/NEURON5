"""How the number of valid claims moves with each rule (measured, no run folders written).

  py experiments/claim_factory/sensitivity.py [--out experiments/claim_factory/output/sensitivity.json]

Every row is a full pipeline run (graph -> candidates -> contract checks -> novelty/dedup).  The rows that relax a rule are
UPPER BOUNDS for what the data could yield under a weaker assumption; only the first row is the conservative default.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from cf_common import CLAIM_TYPES, LEXICON_JSON, PRACTICE_CSV, ROOT
from contract import ContractChecker
from rules import gen_at_event, gen_change, gen_compare, gen_fact, gen_relation
from store import Params, Store, load_novelty_texts

FULL_INPUT = ROOT / "experiments" / "shared" / "data" / "full_input.csv"
GRID = [
    ("DEFAULT strict: age<=14d, min1 row, block on false rows, engine change/relation", Params()),
    ("high-precision: age<=7d, min2 rows", Params(max_age_days=7, min_support_rows=2)),
    ("age<=3d", Params(max_age_days=3)),
    ("age<=30d (precision ~0.91 in backtest)", Params(max_age_days=30)),
    ("age<=60d (precision ~0.88)", Params(max_age_days=60)),
    ("no age limit (precision ~0.78, NOT recommended)", Params(max_age_days=10**6)),
    ("do not block on false/unsure-row candidates", Params(block_on_false_candidates=False)),
    ("change_rule=corroborated (not engine-verified)", Params(change_rule="corroborated")),
    ("relation_rule=stable (not engine-verified)", Params(relation_rule="stable")),
    ("RELAXED: corroborated changes + stable relations", Params(change_rule="corroborated", relation_rule="stable")),
    ("RELAXED + age<=30d", Params(change_rule="corroborated", relation_rule="stable", max_age_days=30)),
    ("compare_scope=same_kind (adds cross-attribute pairs; combinatorial)", Params(compare_scope="same_kind")),
    ("RELAXED + compare_scope=same_kind", Params(change_rule="corroborated", relation_rule="stable", compare_scope="same_kind")),
    ("allow name values that are not lexicon entities (UNVERIFIED referee behaviour)", Params(allow_unlisted_names=True)),
    ("RELAXED + unlisted names + age<=30d (loosest)", Params(change_rule="corroborated", relation_rule="stable", max_age_days=30, allow_unlisted_names=True)),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    novelty = load_novelty_texts([p for p in (PRACTICE_CSV, FULL_INPUT) if p.is_file()])
    results = []
    for name, params in GRID:
        t = time.perf_counter()
        store = Store(PRACTICE_CSV, LEXICON_JSON, params)
        cands = []
        for fn in (gen_fact, gen_compare, gen_change, gen_at_event, gen_relation):
            cands += fn(store)
        chk = ContractChecker(store, novelty)
        for c in cands:
            chk.check(c)
        acc = Counter(c.type for c in cands if c.status == "accepted")
        ver = Counter(c.type for c in cands if c.verified)
        results.append({"variant": name, "valid_claims": sum(acc.values()), "by_type": {k: acc.get(k, 0) for k in CLAIM_TYPES},
                        "verified_by_evidence_rules": {k: ver.get(k, 0) for k in CLAIM_TYPES}, "seconds": round(time.perf_counter() - t, 1)})
        print(f"{sum(acc.values()):5d}  {dict(acc)}  | {name}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
