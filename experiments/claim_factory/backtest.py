"""Backtest of the as-of (persistence) rule on the practice data.

For every (subject, attribute) and every date T on which a TRUE row states the fact, the rule is applied using only
observations dated strictly BEFORE T; its accepted value is compared with the value(s) the true rows state ON T.
This mirrors the real task (predict the value on a date from earlier evidence) and measures the error of the heuristic.

  py experiments/claim_factory/backtest.py [--out experiments/claim_factory/output/backtest.json]

Caveats: the truth on T is again a (true-labelled) row of the practice sample, so this is an agreement rate, not a proof.
Ages in the real run are 1-60 days for volatile keys (as-of 29 Oct vs last row <= 28 Oct).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from cf_common import LEXICON_JSON, PRACTICE_CSV  # noqa: F401
from observations import same_value
from store import Params, Store

VARIANTS = {
    "default(min1,block,age<=14d)": Params(),
    "strict(min2,block,age<=7d)": Params(min_support_rows=2, max_age_days=7),
    "age<=3d": Params(max_age_days=3),
    "age<=7d": Params(max_age_days=7),
    "age<=30d": Params(max_age_days=30),
    "age<=60d": Params(max_age_days=60),
    "age<=14d,min2": Params(min_support_rows=2),
    "age<=14d,no_block_on_false_candidates": Params(block_on_false_candidates=False),
    "no age limit (min1)": Params(max_age_days=10**6),
}


def run(store: Store, params: Params) -> dict:
    stats = Counter()
    by_age = defaultdict(lambda: Counter())
    misses = []
    for key in sorted(store.obs):
        sup = store.support(key)
        days = sorted({o.on for o in sup})
        for T in days[1:]:
            truth = [o for o in sup if o.on == T and o.clean]
            if not truth:
                continue
            # ignore days on which the true rows disagree with each other
            if any(not same_value(truth[0].value, o.value) for o in truth):
                stats["skipped_conflicting_truth_day"] += 1
                continue
            stats["targets"] += 1
            res = store.asof_at(key, T, params)
            if not res.accepted or res.value is None:
                stats["rule_abstains"] += 1
                continue
            stats["rule_accepts"] += 1
            age = res.age_days or 0
            bucket = "0-7d" if age <= 7 else "8-30d" if age <= 30 else "31-60d" if age <= 60 else "61-120d" if age <= 120 else ">120d"
            ok = same_value(res.value, truth[0].value)
            stats["agree" if ok else "contradicted"] += 1
            stats["immutable_event_date_" + ("agree" if ok else "contradicted") if res.immutable else "mutable_" + ("agree" if ok else "contradicted")] += 1
            by_age[bucket]["agree" if ok else "contradicted"] += 1
            if not ok and len(misses) < 12:
                misses.append({"key": list(key), "target_date": T.isoformat(), "rule_value": str(res.value.value), "truth_value": str(truth[0].value.value),
                               "last_obs": res.last.on.isoformat(), "age": age})
    acc = stats["rule_accepts"]
    return {"counts": dict(stats), "precision": round(stats["agree"] / acc, 4) if acc else None,
            "coverage_of_targets": round(acc / stats["targets"], 4) if stats["targets"] else None,
            "by_age": {k: dict(v) | {"precision": round(v["agree"] / (v["agree"] + v["contradicted"]), 4)} for k, v in sorted(by_age.items())},
            "examples_of_contradiction": misses}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    store = Store(PRACTICE_CSV, LEXICON_JSON)
    report = {name: run(store, p) for name, p in VARIANTS.items()}
    # how many keys / decisions are 'stable' (never changed) vs volatile, for context
    vol = sum(1 for k in store.obs if store.asof_fact(k).volatile)
    report["_context"] = {"keys_with_support": sum(1 for k in store.obs if store.support(k)), "volatile_keys": vol}
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    for name, r in report.items():
        if name.startswith("_"):
            continue
        print(f"{name:40s} targets={r['counts'].get('targets')} accepts={r['counts'].get('rule_accepts')} "
              f"precision={r['precision']} coverage={r['coverage_of_targets']}")
    print(json.dumps(report["no age limit (min1)"]["by_age"]))
    print(json.dumps(report["default(min1,block,age<=14d)"]["counts"]))
    print(json.dumps(report["_context"]))


if __name__ == "__main__":
    main()
