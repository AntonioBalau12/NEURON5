"""DEV-only self check: 5-fold cross-validation over experiments/shared/data/dev_rows.csv (gold forms used for scoring only).

  py experiments/slot_filling/eval_dev.py [--tune]

Each fold fits the cue profile / gazetteer / logistic weights on the other four folds and extracts the held-out rows.
Numbers here are the author's own measurements on dev; the in-sample row is optimistic by construction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract_slots import extract_row  # noqa: E402
from linking import Lexicon  # noqa: E402
from model import fit, load, load_dev  # noqa: E402

LOW_THR = {"default": 0.05}


def fold_of(rid, k=5):
    return int(hashlib.md5(rid.encode()).hexdigest(), 16) % k


def passes(f, thr):
    from pipeline import UNKNOWN_NAME_EXTRA
    kind = f["value"]["kind"]
    t = thr.get(kind, thr.get("default", 0.0))
    if kind == "name" and "name_src=unknown" in f["notes"]:
        t += UNKNOWN_NAME_EXTRA
    return f["extraction_confidence"] >= t


def fkey(subject, attribute, value):
    return (subject, attribute, json.dumps(value, sort_keys=True))


def cv_facts(rows, lex, k=5, epochs=120):
    out = {}
    for f in range(k):
        train = [r for r in rows if fold_of(r["id"], k) != f]
        test = [r for r in rows if fold_of(r["id"], k) == f]
        m = fit(train, lex, epochs=epochs)
        for r in test:
            out[r["id"]] = extract_row(r, m, lex, LOW_THR)
        print(f"fold {f}: train {len(train)} test {len(test)}", file=sys.stderr)
    return out


def score(rows, facts_by_row, thr=None, kinds=None):
    """Exact-match precision/recall against the dev gold forms."""
    thr = thr or {}
    tp = fp = fn = 0
    per_attr = defaultdict(lambda: Counter())
    per_kind = defaultdict(lambda: Counter())
    extras, matched = [], []
    for r in rows:
        gold = {fkey(g["subject"], g["attribute"], g["value"]): g for g in r["gold"]}
        pred = {}
        for f in facts_by_row.get(r["id"], []):
            if not passes(f, thr):
                continue
            pred[fkey(f["subject"], f["attribute"], f["value"])] = f
        for g in gold.values():
            per_attr[g["attribute"]]["gold"] += 1
            per_kind[g["value"]["kind"]]["gold"] += 1
        for key, f in pred.items():
            kind = f["value"]["kind"]
            per_attr[f["attribute"]]["pred"] += 1
            per_kind[kind]["pred"] += 1
            if key in gold:
                tp += 1
                per_attr[f["attribute"]]["tp"] += 1
                per_kind[kind]["tp"] += 1
                matched.append((r["id"], f))
            else:
                fp += 1
                extras.append((r["id"], f))
        fn += len([k_ for k_ in gold if k_ not in pred])
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec}, per_attr, per_kind, extras, matched


def tune(rows, facts_by_row):
    """Per-kind confidence threshold: smallest value whose cumulative CV precision on that kind is >= target, by sweep."""
    best = {}
    for kind in ("quantity", "money", "percent", "duration", "date", "version", "name", "boolean"):
        pts = []
        for t in [x / 100 for x in range(10, 95, 5)]:
            thr = {"default": 2.0, kind: t}
            s, _, pk, _, _ = score(rows, facts_by_row, thr)
            c = pk[kind]
            if c["pred"]:
                pts.append((t, c["tp"] / c["pred"], c["tp"], c["pred"]))
        best[kind] = pts
    return best


if __name__ == "__main__" and "--report" not in sys.argv:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    ap.add_argument("--save", default=str(HERE / "output" / "cv_facts.json"))
    args = ap.parse_args()
    lex = Lexicon(HERE.parents[1] / "data" / "lexicon.json")
    rows = load_dev()
    cv = cv_facts(rows, lex)
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(cv), encoding="utf-8")
    for t in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8):
        s, *_ = score(rows, cv, {"default": t})
        print(f"thr {t}: tp {s['tp']} fp {s['fp']} fn {s['fn']} P {s['precision']:.3f} R {s['recall']:.3f}")
    if args.tune:
        for k, pts in tune(rows, cv).items():
            print(k, [(t, round(p, 2), tp, n) for t, p, tp, n in pts])


# ----------------------------------------------------------------------------------------
# reports (run: py experiments/slot_filling/eval_dev.py --report)
# ----------------------------------------------------------------------------------------
def thresholds():
    return json.loads((HERE / "model" / "thresholds.json").read_text(encoding="utf-8"))


def accepted(cv, thr):
    out = {}
    for rid, fs in cv.items():
        out[rid] = [f for f in fs if passes(f, thr)]
    return out


def make_reports(rows, lex, cv):
    import csv
    from engine import entity_mentions
    thr = thresholds()
    acc = accepted(cv, thr)
    outdir = HERE / "output"
    s, per_attr, per_kind, extras, matched = score(rows, cv, thr)
    # reachability: gold facts whose subject is named in the sentence
    reach = Counter()
    reach_kind = Counter()
    for r in rows:
        names = {e.canon for e in entity_mentions(lex, r["text"])}
        for g in r["gold"]:
            if g["subject"] in names:
                reach[g["attribute"]] += 1
                reach_kind[g["value"]["kind"]] += 1
    # annotate and save CV facts (extras get a rule name in notes)
    gold_keys = {r["id"]: {fkey(g["subject"], g["attribute"], g["value"]) for g in r["gold"]} for r in rows}
    with (outdir / "dev_cv_facts_annotated.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            for f in acc.get(r["id"], []):
                f = dict(f)
                tag = "dev_gold=in_form" if fkey(f["subject"], f["attribute"], f["value"]) in gold_keys[r["id"]] \
                    else "dev_gold=missing_from_form; rule=extra_beyond_form"
                f["notes"] = f["notes"] + "; " + tag
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    # attribute coverage (all lexicon attributes)
    attrs = sorted({a for s_ in lex.subjects.values() for a in s_.attributes})
    all_pred_attr = Counter()
    for fs in acc.values():
        for f in fs:
            all_pred_attr[f["attribute"]] += 1
    with (outdir / "attribute_coverage.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["attribute", "subjects", "dev_gold", "gold_subject_in_sentence", "recovered_cv", "predicted_cv",
                    "precision_cv", "extras_beyond_form", "kinds_in_gold", "status"])
        none_extracted, no_gold = [], []
        for a in attrs:
            c = per_attr.get(a, Counter())
            gold_n, tp, pred = c["gold"], c["tp"], c["pred"]
            kinds = Counter()
            for r in rows:
                for g in r["gold"]:
                    if g["attribute"] == a:
                        kinds[g["value"]["kind"]] += 1
            status = "ok"
            if gold_n == 0:
                status = "no_dev_gold"
                no_gold.append(a)
            elif tp == 0:
                status = "no_correct_extraction"
                none_extracted.append(a)
            w.writerow([a, "|".join(lex.attr_subjects.get(a, [])), gold_n, reach[a], tp, pred,
                        f"{tp / pred:.3f}" if pred else "", pred - tp, json.dumps(dict(kinds)), status])
    # per-kind table
    with (outdir / "kind_table.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["value_kind", "dev_gold", "gold_subject_in_sentence", "predicted_cv", "correct_cv", "precision_cv",
                    "recall_cv", "recall_of_reachable_cv", "threshold"])
        for k in ("quantity", "money", "percent", "duration", "date", "version", "name", "boolean"):
            c = per_kind[k]
            w.writerow([k, c["gold"], reach_kind[k], c["pred"], c["tp"], f"{c['tp'] / c['pred']:.3f}" if c["pred"] else "",
                        f"{c['tp'] / c['gold']:.3f}" if c["gold"] else "",
                        f"{c['tp'] / reach_kind[k]:.3f}" if reach_kind[k] else "", thr.get(k, thr["default"])])
    # extras sample for manual review (deterministic, stratified by kind)
    import random
    random.seed(20260112)
    by_kind = defaultdict(list)
    for rid, f in extras:
        by_kind[f["value"]["kind"]].append((rid, f))
    sample = []
    for k, items in sorted(by_kind.items()):
        items.sort(key=lambda x: x[0])
        sample += random.sample(items, min(len(items), 8 if k != "quantity" else 10))
    texts = {r["id"]: r for r in rows}
    with (outdir / "extras_sample.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for rid, f in sample:
            fh.write(json.dumps({"row": rid, "text": texts[rid]["text"], "label": texts[rid]["label"],
                                 "gold_form": texts[rid]["gold"], "pred": {k: f[k] for k in (
                                     "subject", "attribute", "value", "extraction_confidence", "parse_status", "source_text_span",
                                     "notes")}}, ensure_ascii=False) + "\n")
    with (outdir / "dev_extras_all.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for rid, f in extras:
            fh.write(json.dumps({"row": rid, "text": texts[rid]["text"], "pred": {k: f[k] for k in (
                "subject", "attribute", "value", "extraction_confidence", "parse_status", "notes")}}, ensure_ascii=False) + "\n")
    summary = {"cv_tuned_thresholds": s, "total_gold": sum(len(r["gold"]) for r in rows),
               "gold_subject_in_sentence": sum(reach.values()), "extras_beyond_form": len(extras),
               "attributes_total": len(attrs), "attributes_no_dev_gold": no_gold,
               "attributes_with_gold_but_no_correct_extraction": len(none_extracted),
               "per_kind": {k: dict(v) for k, v in per_kind.items()}}
    # per parse_status precision
    st = defaultdict(Counter)
    gk = gold_keys
    for rid, fs in acc.items():
        for f in fs:
            st[f["parse_status"]]["n"] += 1
            st[f["parse_status"]]["tp"] += fkey(f["subject"], f["attribute"], f["value"]) in gk[rid]
    summary["per_parse_status"] = {k: dict(v) for k, v in st.items()}
    (outdir / "dev_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return summary


def insample(rows, lex):
    """Optimistic: model fitted on all dev, extracted on the same rows."""
    m = load(HERE / "model")
    thr = thresholds()
    facts = {r["id"]: extract_row(r, m, lex, thr) for r in rows}
    s, *_ = score(rows, facts, {"default": 0.0})
    return s


if __name__ == "__main__" and "--report" in sys.argv:
    lex = Lexicon(HERE.parents[1] / "data" / "lexicon.json")
    rows = load_dev()
    cvp = HERE / "output" / "cv_facts.json"
    cv = json.loads(cvp.read_text(encoding="utf-8"))
    make_reports(rows, lex, cv)
    print("in-sample (optimistic):", insample(rows, lex))
