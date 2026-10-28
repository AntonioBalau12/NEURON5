"""DEV-only self check of the OpenIE extractor against the dev gold forms (my own observation, not the independent eval).

  py experiments/openie/tools/eval_dev.py                 # table learned on all dev rows (optimistic, resubstitution)
  py experiments/openie/tools/eval_dev.py --cv 5          # 5-fold CV inside dev: table learned on the other folds
  py experiments/openie/tools/eval_dev.py --dump extras.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.stdout.reconfigure(encoding="utf-8")

from learn import LEXICON, load_dev, train  # noqa: E402
from oie.model import Model  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402


def key(subject, attribute, value):
    v = {k: w for k, w in value.items() if k != "op"}
    return (subject, attribute, json.dumps(v, sort_keys=True))


def fold_of(rid: str, k: int) -> int:
    return int(hashlib.sha1(rid.encode()).hexdigest(), 16) % k


def run(rows, ex):
    preds = []
    for r in rows:
        for f in ex.extract(r):
            f["_row"] = r
            preds.append(f)
    return preds


def score(rows, preds, statuses, label):
    gold = collections.defaultdict(set)
    gold_op = set()
    kind_of = {}
    for r in rows:
        for x in json.loads(r["form"]):
            k = (r["id"],) + key(x["subject"], x["attribute"], x["value"])
            gold[r["id"]].add(k)
            kind_of[k] = x["value"]["kind"]
            if "op" in x["value"]:
                gold_op.add(k)
    pred_keys = {}
    for f in preds:
        if f["value"] is None or f["parse_status"] not in statuses or f["subject"] is None or f["attribute"] is None:
            continue
        k = (f["source_row_id"],) + key(f["subject"], f["attribute"], f["value"])
        pred_keys.setdefault(k, f)
    all_gold = set().union(*gold.values())
    tp = {k for k in pred_keys if k in all_gold}
    n_pred, n_gold = len(pred_keys), len(all_gold)
    gold_noop = all_gold - gold_op
    print(f"[{label}] statuses={sorted(statuses)} predicted={n_pred} gold={n_gold} (no-op gold={len(gold_noop)}) "
          f"TP={len(tp)} P={len(tp)/max(n_pred,1):.3f} R={len(tp)/n_gold:.3f} R_noop={len(tp & gold_noop)/len(gold_noop):.3f} "
          f"extras={n_pred-len(tp)}")
    if QUIET:
        return pred_keys, tp, all_gold
    per = collections.defaultdict(lambda: [0, 0, 0])
    for k in all_gold:
        per[kind_of[k]][1] += 1
        if k in tp:
            per[kind_of[k]][0] += 1
    for k, f in pred_keys.items():
        per[f["value"]["kind"]][2] += 1
    print("   kind        TP  gold  pred  P     R")
    for kd, (a, g, p) in sorted(per.items()):
        tpk = sum(1 for k in tp if json.loads(k[3])["kind"] == kd)
        print(f"   {kd:<9} {tpk:4d} {g:5d} {p:5d}  {tpk/max(p,1):.2f}  {tpk/max(g,1):.2f}")
    return pred_keys, tp, all_gold


QUIET = False


def main() -> None:
    global QUIET
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", type=int, default=0)
    ap.add_argument("--dump", default=None)
    ap.add_argument("--set", action="append", default=[], help="Params override, e.g. --set min_attr_score=1.5")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    QUIET = args.quiet
    rows = load_dev()
    params = Params()
    for kv in args.set:
        k, v = kv.split("=")
        cur = getattr(params, k)
        setattr(params, k, (v.lower() in ("1", "true", "yes")) if isinstance(cur, bool) else type(cur)(v))
    preds = []
    if args.cv:
        for k in range(args.cv):
            tr = [r for r in rows if fold_of(r["id"], args.cv) != k]
            te = [r for r in rows if fold_of(r["id"], args.cv) == k]
            ex = Extractor(LEXICON, train(tr, LEXICON, params), params)
            preds += run(te, ex)
        label = f"{args.cv}-fold CV"
    else:
        ex = Extractor(LEXICON, train(rows, LEXICON, params), params)
        preds = run(rows, ex)
        label = "resubstitution"
    pk, tp, gold = score(rows, preds, {"complete"}, label)
    pk, tp, gold = score(rows, preds, {"complete", "partial", "ambiguous"}, label)
    # OBSERVATION ONLY: facts whose subject is not named in the sentence, subject taken from the lexicon's unique
    # owner of the hinted attribute. This is NOT part of the output facts and breaks the "subject named" rule.
    hint_keys = {}
    for f in preds:
        if f["parse_status"] == "unmapped" and f["value"] is not None and "hint_attr=" in f["notes"]:
            parts = dict(p.split("=", 1) for p in f["notes"].split("; ") if "=" in p)
            owners = parts.get("hint_owners", "").split("|")
            if len(owners) == 1 and owners[0]:
                hint_keys[(f["source_row_id"],) + key(owners[0], parts["hint_attr"], f["value"])] = f
    all_gold = set().union(*[{(r["id"],) + key(x["subject"], x["attribute"], x["value"]) for x in json.loads(r["form"])} for r in rows])
    h_tp = {k for k in hint_keys if k in all_gold}
    print(f"[{label}] OBSERVATION: unique-owner subject inference for unnamed subjects: predicted={len(hint_keys)} TP={len(h_tp)} "
          f"P={len(h_tp)/max(len(hint_keys),1):.3f}; combined with complete: P={(len(tp)+len(h_tp))/max(len(pk)+len(hint_keys),1):.3f} "
          f"R={(len(tp)+len(h_tp))/len(all_gold):.3f}")
    if args.dump:
        extras = [dict(source_row_id=k[0], subject=k[1], attribute=k[2], value=json.loads(k[3]), status=f["parse_status"],
                       text=f["_row"]["text"], span=f["source_text_span"], notes=f["notes"]) for k, f in pk.items() if k not in tp]
        missed = [dict(source_row_id=k[0], subject=k[1], attribute=k[2], value=json.loads(k[3]),
                       text=next(r["text"] for r in rows if r["id"] == k[0])) for k in gold if k not in pk]
        Path(args.dump).write_text(json.dumps({"extras": extras, "missed": missed}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
