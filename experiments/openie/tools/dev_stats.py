"""Dev-only quality statistics for REPORT.md: negation, numeric/date quality, temporal fields (my own observation).

  py experiments/openie/tools/dev_stats.py [--cv 5]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.stdout.reconfigure(encoding="utf-8")

from eval_dev import fold_of, key  # noqa: E402
from learn import LEXICON, load_dev, train  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--cv", type=int, default=0)
args = ap.parse_args()
rows = load_dev()
params = Params()
preds, vals_seen = [], []
if args.cv:
    for k in range(args.cv):
        tr = [r for r in rows if fold_of(r["id"], args.cv) != k]
        te = [r for r in rows if fold_of(r["id"], args.cv) == k]
        ex = Extractor(LEXICON, train(tr, LEXICON, params), params)
        for r in te:
            for f in ex.extract(r):
                f["_row"] = r
                preds.append(f)
            for s in ex.analyse(r["text"]):
                for v in s.vals:
                    vals_seen.append((r, v))
else:
    ex = Extractor(LEXICON, train(rows, LEXICON, params), params)
    for r in rows:
        for f in ex.extract(r):
            f["_row"] = r
            preds.append(f)
        for s in ex.analyse(r["text"]):
            for v in s.vals:
                vals_seen.append((r, v))

gold_by_row = {r["id"]: json.loads(r["form"]) for r in rows}
out: dict = {"mode": f"{args.cv}-fold CV" if args.cv else "resubstitution"}

# --- boolean polarity / negation
pol = collections.Counter()
neg_flag = collections.Counter()
for f in preds:
    if f["value"] is None or f["subject"] is None or f["attribute"] is None:
        continue
    g = [x for x in gold_by_row[f["source_row_id"]] if x["subject"] == f["subject"] and x["attribute"] == f["attribute"]]
    if f["value"]["kind"] == "boolean":
        if g and g[0]["value"]["kind"] == "boolean":
            pol["same_fact_in_gold"] += 1
            pol["polarity_correct" if g[0]["value"]["value"] == f["value"]["value"] else "polarity_wrong"] += 1
            neg_flag["bool_negated_flag_agrees_with_value"] += int(f["negated"] == (not f["value"]["value"]))
        else:
            pol["boolean_not_in_gold"] += 1
    elif f["negated"]:
        neg_flag["non_boolean_with_negation"] += 1
        neg_flag["  of which in gold (should be 0: referee reads nothing)"] += int(
            any(key(x["subject"], x["attribute"], x["value"]) == key(f["subject"], f["attribute"], f["value"]) for x in gold_by_row[f["source_row_id"]]))
out["boolean_polarity"] = dict(pol)
out["negation_flags"] = dict(neg_flag)
out["bool_value_false_but_negated_false"] = sum(1 for f in preds if f["value"] and f["value"].get("kind") == "boolean"
                                                and f["value"]["value"] is False and not f["negated"])

# --- unreadable values (approximation / range / comparison / ambiguous number)
unread = collections.Counter()
unread_in_gold_plain = collections.Counter()
for r, v in vals_seen:
    if v.readable:
        continue
    for fl in v.flags:
        unread[fl.split(":")[0]] += 1
    want = {k: w for k, w in v.value.items() if k != "op"}
    for x in gold_by_row[r["id"]]:
        gv = x["value"]
        if {k: w for k, w in gv.items() if k != "op"} == want:
            unread_in_gold_plain[("with op in gold" if "op" in gv else "plain in gold") + " | " + "/".join(f.split(":")[0] for f in v.flags)] += 1
out["unreadable_values_found"] = dict(unread)
out["unreadable_values_vs_gold"] = dict(unread_in_gold_plain)

# --- numeric exactness per kind, among predicted facts whose subject+attribute are in gold
num = collections.defaultdict(collections.Counter)
for f in preds:
    if f["value"] is None or f["parse_status"] != "complete" or f["value"]["kind"] in ("boolean", "name"):
        continue
    for x in gold_by_row[f["source_row_id"]]:
        if x["subject"] == f["subject"] and x["attribute"] == f["attribute"] and x["value"]["kind"] == f["value"]["kind"]:
            exact = {k: w for k, w in x["value"].items() if k != "op"} == f["value"]
            num[f["value"]["kind"]]["exact" if exact else "same S+A, different value"] += 1
            break
out["same_subject_attribute_value_exactness"] = {k: dict(v) for k, v in num.items()}

# --- temporal fields
t = collections.Counter()
for f in preds:
    if f["parse_status"] == "unmapped":
        continue
    t["facts"] += 1
    t["with_temporal_qualifier"] += int(bool(f["temporal_qualifier"]))
    t["with_fact_observation_date"] += int(bool(f["fact_observation_date"]))
    t["with_valid_from"] += int(bool(f["valid_from"]))
    t["with_valid_to"] += int(bool(f["valid_to"]))
    t["obs_date_equals_page_date"] += int(f["fact_observation_date"] == f["source_publication_date"] and bool(f["fact_observation_date"]))
    if f["value"]["kind"] == "date":
        t["date_facts"] += 1
        t["date_value_equals_page_date"] += int(f["value"]["value"] == f["source_publication_date"])
out["temporal"] = dict(t)
tq = collections.Counter()
for f in preds:
    if f["temporal_qualifier"] and f["parse_status"] != "unmapped":
        for w in f["temporal_qualifier"].split("; "):
            tq[w.lower()] += 1
out["temporal_qualifier_words"] = dict(tq.most_common(15))
st = collections.Counter(f["parse_status"] for f in preds)
out["parse_status_dev"] = dict(st)
print(json.dumps(out, indent=1, ensure_ascii=False))
