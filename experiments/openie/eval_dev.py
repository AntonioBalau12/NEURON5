"""DEV-only self-check of the OpenIE extractor against the dev gold forms.

This is my own observation on dev rows. It is NOT the independent evaluation and says nothing about held-out rows.

  py experiments/openie/eval_dev.py                 # frozen facts.jsonl on dev ids + 5-fold CV inside dev + extras sample
  py experiments/openie/eval_dev.py --cv 0          # frozen file only

Matching: subject (lexicon-resolved canonical name) + attribute (exact) + value equivalence using
foundation.compare_values(..., "eq") (units convert: GB/MB, kg/g, h/min, ...; money needs same currency+period; dates need
equal precision) and the lexicon for name values. Gold `op` (gt/lt/...) is ignored for the "op-free" match and counted
as a miss/incorrect in the "strict" match, because the extractor never emits an op.

Reads only experiments/shared/data/dev_rows.csv (dev gold), full_input.csv statistics, and output/facts.jsonl (read-only).
Writes only: output/eval_dev.txt, output/eval_dev.json, output/extras_review.csv, output/misses_dev.csv.
Manual labels for the extras sample live in data/extras_labels.json (written by hand after reading the sentences).
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.stdout.reconfigure(encoding="utf-8")

from foundation import Lexicon, TypedValue, compare_values  # noqa: E402  (read-only reuse)

DEV = ROOT / "experiments" / "shared" / "data" / "dev_rows.csv"
FULL = ROOT / "experiments" / "shared" / "data" / "full_input.csv"
LEXICON_PATH = ROOT / "data" / "lexicon.json"
FACTS = HERE / "output" / "facts.jsonl"
OUT = HERE / "output"
LABELS = HERE / "data" / "extras_labels.json"
MAPPED = {"complete", "partial", "ambiguous"}

LEX, _issues = Lexicon.parse(json.loads(LEXICON_PATH.read_text(encoding="utf-8")))
_LOG: list[str] = []


def say(s: str = "") -> None:
    print(s)
    _LOG.append(s)


# ----------------------------------------------------------------------------------------------- matching
def canon_subject(name: str) -> str:
    e = LEX.resolve(name)
    return e.name.casefold() if e else Lexicon.normalize_name(name)


def value_equiv(pred: dict, gold: dict) -> bool:
    g = {k: v for k, v in gold.items() if k != "op"}
    p = {k: v for k, v in pred.items() if k != "op"}
    if p.get("kind") != g.get("kind"):
        return False
    if p["kind"] == "name":
        return canon_subject(str(p["value"])) == canon_subject(str(g["value"]))
    lv, _ = TypedValue.parse(p)
    rv, _ = TypedValue.parse(g)
    if lv is None or rv is None:
        return False
    try:
        return compare_values(lv, rv, "eq") is True
    except (TypeError, ValueError):
        return False


def same_fact(p: dict, g: dict) -> bool:
    return (canon_subject(p["subject"]) == canon_subject(g["subject"]) and p["attribute"] == g["attribute"]
            and value_equiv(p["value"], g["value"]))


def mapped_preds(facts: list[dict], statuses: set[str]) -> list[dict]:
    return [f for f in facts if f["parse_status"] in statuses and f.get("subject") and f.get("attribute")
            and f.get("value") is not None]


def score(rows: list[dict], preds_by_row: dict[str, list[dict]], statuses: set[str], label: str, detail: bool = True) -> dict:
    gold_n = gold_hit = gold_hit_strict = 0
    pred_n = pred_tp = pred_tp_strict = 0
    gold_noop = 0
    per_gold = collections.defaultdict(lambda: [0, 0, 0])      # kind -> [gold, hit(op-free), hit(strict)]
    per_pred = collections.defaultdict(lambda: [0, 0, 0])      # kind -> [pred, tp(op-free), tp(strict)]
    extras: list[dict] = []
    misses: list[dict] = []
    cats = collections.Counter()
    bool_pol = collections.Counter()
    for r in rows:
        gold = json.loads(r["form"])
        preds = []
        for f in mapped_preds(preds_by_row.get(r["id"], []), statuses):
            if not any(same_fact(f, q) for q in preds):            # drop exact duplicates
                preds.append(f)
        g_hit = [False] * len(gold)
        g_hit_strict = [False] * len(gold)
        for f in preds:
            kd = f["value"]["kind"]
            per_pred[kd][0] += 1
            pn = pt = False
            for i, g in enumerate(gold):
                if same_fact(f, g):
                    pn = True
                    g_hit[i] = True
                    if "op" not in g["value"]:
                        pt = True
                        g_hit_strict[i] = True
            pred_n += 1
            if pn:
                pred_tp += 1
                per_pred[kd][1] += 1
            if pt:
                pred_tp_strict += 1
                per_pred[kd][2] += 1
            if not pn:
                same_sa = [g for g in gold if canon_subject(g["subject"]) == canon_subject(f["subject"]) and g["attribute"] == f["attribute"]]
                same_val = [g for g in gold if value_equiv(f["value"], g["value"])]
                if same_sa:
                    cat = "same subject+attribute as gold, different value"
                    if kd == "boolean":
                        bool_pol["wrong_polarity"] += 1
                elif same_val:
                    cat = "gold value found under another subject/attribute"
                else:
                    cat = "not in the form at all"
                cats[cat] += 1
                extras.append({"row": r, "fact": f, "category": cat})
            elif kd == "boolean":
                bool_pol["correct_polarity"] += 1
        for i, g in enumerate(gold):
            kd = g["value"]["kind"]
            per_gold[kd][0] += 1
            gold_n += 1
            if "op" not in g["value"]:
                gold_noop += 1
            if g_hit[i]:
                per_gold[kd][1] += 1
                gold_hit += 1
            if g_hit_strict[i]:
                per_gold[kd][2] += 1
                gold_hit_strict += 1
            if not g_hit[i]:
                misses.append({"row": r, "gold": g})
    res = {
        "label": label, "statuses": sorted(statuses), "gold": gold_n, "gold_without_op": gold_noop, "predicted": pred_n,
        "tp_op_free": pred_tp, "precision_op_free": pred_tp / max(pred_n, 1), "recall_op_free": gold_hit / gold_n,
        "tp_strict": pred_tp_strict, "precision_strict": pred_tp_strict / max(pred_n, 1),
        "recall_strict": gold_hit_strict / gold_n, "extras_beyond_form": pred_n - pred_tp, "extra_categories": dict(cats),
        "boolean_polarity": dict(bool_pol),
        "per_kind": {k: {"gold": g[0], "recalled": g[1], "recall": round(g[1] / max(g[0], 1), 3), "predicted": per_pred[k][0],
                         "tp": per_pred[k][1], "precision": round(per_pred[k][1] / max(per_pred[k][0], 1), 3),
                         "recalled_strict": g[2], "recall_strict": round(g[2] / max(g[0], 1), 3)}
                     for k, g in sorted(per_gold.items())},
    }
    if detail:
        say(f"[{label}] statuses={'+'.join(sorted(statuses))}")
        say(f"   gold={gold_n} (without op={gold_noop})  predicted={pred_n}  TP={pred_tp}  extras beyond the form={pred_n - pred_tp}")
        say(f"   op-free match : precision={res['precision_op_free']:.3f}  recall={res['recall_op_free']:.3f}")
        say(f"   strict (gold op counts): precision={res['precision_strict']:.3f}  recall={res['recall_strict']:.3f}")
        say(f"   extras by category: {dict(cats)}   boolean polarity: {dict(bool_pol)}")
        say("   kind       gold  recalled  recall | pred   TP  precision | strict-recall")
        for k, v in res["per_kind"].items():
            say(f"   {k:<9} {v['gold']:5d} {v['recalled']:8d}  {v['recall']:.3f}  | {v['predicted']:4d} {v['tp']:4d}  {v['precision']:.3f}     | {v['recall_strict']:.3f}")
    res["_extras"] = extras
    res["_misses"] = misses
    return res


# ----------------------------------------------------------------------------------------------- data
def load_csv(p: Path) -> list[dict]:
    with p.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def frozen_by_row() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    with FACTS.open(encoding="utf-8") as fh:
        for line in fh:
            f = json.loads(line)
            out[f["source_row_id"]].append(f)
    return out


def fold_of(rid: str, k: int) -> int:
    return int(hashlib.sha1(rid.encode()).hexdigest(), 16) % k


def cv_preds(dev: list[dict], k: int) -> dict[str, list[dict]]:
    from learn import train                                # tools/learn.py (dev-only training)
    from oie.pipeline import Extractor, Params
    out: dict[str, list[dict]] = {}
    for fold in range(k):
        tr = [r for r in dev if fold_of(r["id"], k) != fold]
        te = [r for r in dev if fold_of(r["id"], k) == fold]
        p = Params()
        ex = Extractor(LEXICON_PATH, train(tr, LEXICON_PATH, p), p)
        for r in te:
            out[r["id"]] = [{k2: v for k2, v in f.items() if k2 not in ("_key", "_val", "_drop")} for f in ex.extract(r)]
    return out


def sanity_reproduces_frozen(dev: list[dict], frozen: dict[str, list[dict]]) -> bool:
    """In-memory re-extraction of dev rows with the saved relation table equals the frozen file (nothing is written)."""
    from oie.model import Model
    from oie.pipeline import Extractor, Params
    ex = Extractor(LEXICON_PATH, Model.load(HERE / "data" / "relation_table.json"), Params())
    for r in dev:
        new = [{k: v for k, v in f.items() if k not in ("_key", "_val", "_drop")} for f in ex.extract(r)]
        if json.dumps(new, sort_keys=True) != json.dumps(frozen.get(r["id"], []), sort_keys=True):
            return False
    return True


# ----------------------------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cv", type=int, default=5)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--n-review", type=int, default=50)
    args = ap.parse_args()

    dev = load_csv(DEV)
    full = load_csv(FULL)
    dev_ids = {r["id"] for r in dev}
    frozen = frozen_by_row()
    sha = hashlib.sha1(FACTS.read_bytes()).hexdigest()
    say(f"facts.jsonl sha1={sha}")
    say(f"dev rows={len(dev)}  full_input rows={len(full)}  non-dev rows in full_input={len([r for r in full if r['id'] not in dev_ids])}")
    gold_ops = collections.Counter(g["value"].get("op", "(none)") for r in dev for g in json.loads(r["form"]))
    say(f"dev gold ops: {dict(gold_ops)}")
    say(f"re-extraction of dev rows in memory equals frozen facts: {sanity_reproduces_frozen(dev, frozen)}")
    say()
    results: dict[str, dict] = {}
    say("=== A. frozen facts.jsonl restricted to dev ids (table learned on ALL dev rows => resubstitution, optimistic)")
    for sts in ({"complete"}, MAPPED):
        results[f"frozen_{'+'.join(sorted(sts))}"] = score(dev, frozen, sts, "frozen/dev")
    if args.cv:
        say()
        say(f"=== B. {args.cv}-fold cross-validation inside dev (table learned on the other folds): honest estimate of generalisation")
        cvp = cv_preds(dev, args.cv)
        for sts in ({"complete"}, MAPPED):
            results[f"cv_{'+'.join(sorted(sts))}"] = score(dev, cvp, sts, f"cv{args.cv}")
    else:
        cvp = {}

    # status counts
    say()
    say("=== C. fact counts in the frozen file")
    st_all = collections.Counter(f["parse_status"] for fs in frozen.values() for f in fs)
    st_dev = collections.Counter(f["parse_status"] for rid, fs in frozen.items() if rid in dev_ids for f in fs)
    st_non = collections.Counter(f["parse_status"] for rid, fs in frozen.items() if rid not in dev_ids for f in fs)
    say(f"   all rows: {dict(st_all)} total={sum(st_all.values())}")
    say(f"   dev rows: {dict(st_dev)} total={sum(st_dev.values())}")
    say(f"   non-dev rows: {dict(st_non)} total={sum(st_non.values())}")
    amb = [f for fs in frozen.values() for f in fs if f["parse_status"] == "ambiguous"]
    say(f"   ambiguous facts that equal gold (dev only): "
        f"{sum(1 for f in amb if f['source_row_id'] in dev_ids and any(same_fact(f, g) for g in json.loads(next(r['form'] for r in dev if r['id'] == f['source_row_id']))))}"
        f" of {sum(1 for f in amb if f['source_row_id'] in dev_ids)}")
    # unmapped with typed value: which gold values were visible there (value found, subject not named)
    gold_by_row = {r["id"]: json.loads(r["form"]) for r in dev}
    unm = [f for rid, fs in frozen.items() if rid in dev_ids for f in fs if f["parse_status"] == "unmapped" and f["value"] is not None]
    seen = 0
    for f in unm:
        if any(value_equiv(f["value"], g["value"]) for g in gold_by_row[f["source_row_id"]]):
            seen += 1
    say(f"   dev unmapped facts carrying a typed value: {len(unm)}; of those, value equals some gold value of the row: {seen} "
        f"(value read correctly, but subject/attribute not mapped)")

    # temporal / negation / date handling on dev (frozen)
    say()
    say("=== D. negation / temporal / date handling, frozen facts on dev ids")
    dev_mapped = [f for rid in dev_ids for f in mapped_preds(frozen.get(rid, []), MAPPED)]
    bools = [f for f in dev_mapped if f["value"]["kind"] == "boolean"]
    neg_true = [f for f in bools if f["negated"]]
    say(f"   mapped boolean facts={len(bools)}; negated={len(neg_true)}; value false & negated: "
        f"{sum(1 for f in bools if f['value']['value'] is False and f['negated'])}; value true & negated: "
        f"{sum(1 for f in bools if f['value']['value'] is True and f['negated'])}")
    gold_bools = [(r['id'], g) for r in dev for g in json.loads(r['form']) if g['value']['kind'] == 'boolean']
    say(f"   dev gold boolean facts={len(gold_bools)} (false={sum(1 for _, g in gold_bools if g['value']['value'] is False)})")
    rows_by_id = {r["id"]: r for r in dev}
    dates = [f for f in dev_mapped if f["value"]["kind"] == "date"]
    say(f"   mapped date facts={len(dates)}; date value equals the row's page date: "
        f"{sum(1 for f in dates if f['value']['value'] == f['source_publication_date'])}; "
        f"of which match gold: {sum(1 for f in dates if f['value']['value'] == f['source_publication_date'] and any(same_fact(f, g) for g in gold_by_row[f['source_row_id']]))}")
    say(f"   facts with fact_observation_date set={sum(1 for f in dev_mapped if f['fact_observation_date'])}; "
        f"valid_from={sum(1 for f in dev_mapped if f['valid_from'])}; valid_to={sum(1 for f in dev_mapped if f['valid_to'])}; "
        f"any equal to page date={sum(1 for f in dev_mapped if f['source_publication_date'] in (f['fact_observation_date'], f['valid_from'], f['valid_to']))}")
    say(f"   facts with temporal_qualifier={sum(1 for f in dev_mapped if f['temporal_qualifier'])} of {len(dev_mapped)} mapped dev facts")
    say(f"   mapped dev facts whose value carries an op={sum(1 for f in dev_mapped if 'op' in f['value'])}")
    # gold facts with op: how many does the extractor collide with (emits the bare number)
    coll = 0
    for r in dev:
        for g in json.loads(r["form"]):
            if "op" in g["value"] and any(same_fact(f, g) for f in mapped_preds(frozen.get(r["id"], []), MAPPED)):
                coll += 1
    say(f"   gold facts with op={sum(gold_ops[k] for k in gold_ops if k != '(none)')}; frozen mapped facts equal to them ignoring op "
        f"(bare number emitted, op lost)={coll}")

    # ---------------- extras review sample
    pool: dict[tuple, dict] = {}
    for origin, src_res in (("frozen", results["frozen_ambiguous+complete+partial"]),) + \
            ((("cv", results["cv_ambiguous+complete+partial"]),) if args.cv else ()):
        for e in src_res["_extras"]:
            f = e["fact"]
            k = (f["source_row_id"], f["subject"], f["attribute"], json.dumps(f["value"], sort_keys=True))
            if k in pool:
                pool[k]["origin"] = "frozen+cv"
            else:
                pool[k] = {"key": k, "origin": origin, "row": e["row"], "fact": f, "category": e["category"]}
    keys = sorted(pool)
    rnd = random.Random(args.seed)
    sample = rnd.sample(keys, min(args.n_review, len(keys)))
    sample.sort()
    labels = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    say()
    say(f"=== E. extras review: pool={len(pool)} distinct extras (frozen-on-dev + CV), sampled {len(sample)} with seed {args.seed}; "
        f"labelled so far={sum(1 for k in sample if '|'.join(k) in labels)}")
    with (OUT / "extras_review.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "origin", "row_id", "parse_status", "subject", "attribute", "value", "auto_category",
                    "gold_form_of_row", "sentence", "span", "my_label", "my_reason"])
        for k in sample:
            e = pool[k]
            f = e["fact"]
            lab = labels.get("|".join(k), ["", ""])
            gold_short = "; ".join(f"{g['subject']}/{g['attribute']}={json.dumps(g['value'], ensure_ascii=False)}" for g in json.loads(e["row"]["form"]))
            w.writerow(["|".join(k), e["origin"], f["source_row_id"], f["parse_status"], f["subject"], f["attribute"],
                        json.dumps(f["value"], ensure_ascii=False), e["category"], gold_short, e["row"]["text"],
                        f["source_text_span"], lab[0], lab[1]])
    lab_count = collections.Counter(labels["|".join(k)][0] for k in sample if "|".join(k) in labels)
    say(f"   my labels on the sample: {dict(lab_count)}")

    # ---------------- misses (frozen, mapped statuses) with a diagnosis
    with (OUT / "misses_dev.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["row_id", "gold_subject", "gold_attribute", "gold_value", "diagnosis", "sentence"])
        diag = collections.Counter()
        for m in results["frozen_ambiguous+complete+partial"]["_misses"]:
            r, g = m["row"], m["gold"]
            fs = frozen.get(r["id"], [])
            if "op" in g["value"]:
                d = f"gold carries op={g['value']['op']}; extractor does not emit comparison/approximate values"
            elif any(f["parse_status"] == "unmapped" and f["value"] is not None and value_equiv(f["value"], g["value"]) for f in fs):
                d = "value found, left unmapped (subject not named or attribute context too weak)"
            elif g["value"]["kind"] == "boolean":
                d = "boolean not detected"
            elif any(f["parse_status"] in MAPPED and f.get("subject") and value_equiv(f["value"], g["value"]) for f in fs):
                d = "value found but mapped to another subject/attribute"
            else:
                d = "value not found by the value finder"
            diag[d.split(";")[0].split(" (")[0]] += 1
            w.writerow([r["id"], g["subject"], g["attribute"], json.dumps(g["value"], ensure_ascii=False), d, r["text"]])
    say()
    say(f"=== F. misses of the frozen file on dev (mapped statuses): {sum(diag.values())}")
    for d, n in diag.most_common():
        say(f"   {n:5d}  {d}")

    for r in results.values():
        r.pop("_extras", None)
        r.pop("_misses", None)
    results["sha1_facts_jsonl"] = sha
    results["extras_pool"] = len(pool)
    results["extras_sample"] = len(sample)
    results["extras_labels"] = dict(lab_count)
    (OUT / "eval_dev.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "eval_dev.txt").write_text("\n".join(_LOG) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
