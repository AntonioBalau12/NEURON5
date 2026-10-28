"""DEV-only self check of the slot-filling output, scored with foundation.compare_values equivalence.

  py experiments/slot_filling/selfcheck_dev.py

Reads only: experiments/shared/data/dev_rows.csv (gold forms, scoring only), output/cv_facts.json (out-of-fold facts made by
eval_dev.py), output/facts.jsonl (FROZEN, read only), model/thresholds.json, data/lexicon.json.
Writes: output/selfcheck_dev.json, kind_table.csv, attribute_coverage.csv, attribute_coverage_summary.md,
        extras_review_input.jsonl, failure_candidates.jsonl.
Never writes output/facts.jsonl and never runs the extractor.

Match rule: same subject (case-folded), same attribute, same value kind and either identical value objects or
foundation.compare_values(g, p, "eq") is True. A value carrying `op` matches only an identical object (compare_values returns
None for ops).
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import foundation  # noqa: E402  (read only)
from eval_dev import accepted, thresholds  # noqa: E402
from linking import Lexicon  # noqa: E402
from model import load_dev  # noqa: E402

OUT = HERE / "output"
KINDS = ("quantity", "money", "percent", "duration", "date", "version", "name", "boolean")


def tv(v):
    t, err = foundation.TypedValue.parse(v)
    return t


def same_value(g, p):
    if g == p:
        return True
    if g.get("kind") != p.get("kind"):
        return False
    a, b = tv(g), tv(p)
    if a is None or b is None:
        return False
    return foundation.compare_values(a, b, "eq") is True


def match_row(gold, preds):
    """-> (matched pred idx set, recovered gold idx set, wrong_value pred idx set, extra pred idx set)."""
    mp, rg, wv, ex = set(), set(), set(), set()
    for i, p in enumerate(preds):
        hit = False
        slot = False
        for j, g in enumerate(gold):
            if g["subject"].casefold() == p["subject"].casefold() and g["attribute"] == p["attribute"]:
                slot = True
                if same_value(g["value"], p["value"]):
                    hit = True
                    rg.add(j)
        if hit:
            mp.add(i)
        elif slot:
            wv.add(i)
        else:
            ex.add(i)
    return mp, rg, wv, ex


def dedupe(facts):
    seen, out = set(), []
    for f in facts:
        k = (f["subject"].casefold(), f["attribute"], json.dumps(f["value"], sort_keys=True))
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


def evaluate(rows, facts_by_row, lex):
    per_kind = defaultdict(Counter)
    per_attr = defaultdict(Counter)
    status = defaultdict(Counter)
    extras, wrongs, misses = [], [], []
    tot = Counter()
    for r in rows:
        gold = r["gold"]
        preds = dedupe(facts_by_row.get(r["id"], []))
        mp, rg, wv, ex = match_row(gold, preds)
        names = {m[2] for m in lex.mentions(r["text"])}
        for j, g in enumerate(gold):
            k, a = g["value"]["kind"], g["attribute"]
            per_kind[k]["gold"] += 1
            per_attr[a]["gold"] += 1
            if g["subject"] in names:
                per_kind[k]["gold_named"] += 1
                per_attr[a]["gold_named"] += 1
            if j in rg:
                per_kind[k]["recovered"] += 1
                per_attr[a]["recovered"] += 1
            else:
                misses.append((r, g))
        for i, p in enumerate(preds):
            k, a = p["value"]["kind"], p["attribute"]
            per_kind[k]["pred"] += 1
            per_attr[a]["pred"] += 1
            status[p["parse_status"]]["n"] += 1
            if i in mp:
                per_kind[k]["tp"] += 1
                per_attr[a]["tp"] += 1
                status[p["parse_status"]]["tp"] += 1
            elif i in wv:
                per_kind[k]["wrong_value"] += 1
                per_attr[a]["wrong_value"] += 1
                wrongs.append((r, p))
            else:
                per_kind[k]["extra"] += 1
                per_attr[a]["extra"] += 1
                extras.append((r, p))
        tot["gold"] += len(gold)
        tot["recovered"] += len(rg)
        tot["pred"] += len(preds)
        tot["tp"] += len(mp)
        tot["wrong_value"] += len(wv)
        tot["extra"] += len(ex)
    tot["precision"] = tot["tp"] / tot["pred"] if tot["pred"] else 0.0
    tot["recall"] = tot["recovered"] / tot["gold"] if tot["gold"] else 0.0
    return dict(tot), per_kind, per_attr, status, extras, wrongs, misses


def pct(a, b):
    return round(a / b, 3) if b else ""


def main():
    lex = Lexicon(ROOT / "data" / "lexicon.json")
    rows = load_dev()
    ids = {r["id"] for r in rows}
    thr = thresholds()
    cv = json.loads((OUT / "cv_facts.json").read_text(encoding="utf-8"))
    cv_acc = accepted(cv, thr)
    frozen_all = defaultdict(list)
    with (OUT / "facts.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            f = json.loads(line)
            frozen_all[f["source_row_id"]].append(f)
    frozen_dev = {rid: fs for rid, fs in frozen_all.items() if rid in ids}

    res = {}
    store = {}
    for name, fb in (("cv_out_of_fold", cv_acc), ("frozen_in_sample", frozen_dev)):
        tot, pk, pa, st, ex, wr, ms = evaluate(rows, fb, lex)
        store[name] = (tot, pk, pa, st, ex, wr, ms)
        res[name] = {"total": tot,
                     "per_kind": {k: {**dict(pk[k]), "precision": pct(pk[k]["tp"], pk[k]["pred"]),
                                      "recall": pct(pk[k]["recovered"], pk[k]["gold"])} for k in KINDS},
                     "parse_status_precision": {k: {**dict(v), "precision": pct(v["tp"], v["n"])} for k, v in st.items()}}

    # reference: frozen output over ALL rows
    allf = [f for fs in frozen_all.values() for f in fs]
    res["frozen_all_rows"] = {
        "rows_in_input": sum(1 for _ in csv.DictReader((ROOT / "experiments/shared/data/full_input.csv").open(encoding="utf-8-sig"))),
        "rows_with_fact": len(frozen_all), "facts": len(allf), "dev_rows_with_fact": len(frozen_dev),
        "by_kind": dict(Counter(f["value"]["kind"] for f in allf)),
        "parse_status": dict(Counter(f["parse_status"] for f in allf)),
        "negated_true": sum(1 for f in allf if f["negated"]),
        "with_op": sum(1 for f in allf if f["value"].get("op")),
        "temporal_qualifier": sum(1 for f in allf if f["temporal_qualifier"]),
        "fact_observation_date": sum(1 for f in allf if f["fact_observation_date"]),
        "valid_from": sum(1 for f in allf if f["valid_from"]),
        "valid_to": sum(1 for f in allf if f["valid_to"]),
        "unique_attributes": len({(f["attribute"]) for f in allf}),
        "confidence_mean": round(sum(f["extraction_confidence"] for f in allf) / len(allf), 3),
    }
    (OUT / "selfcheck_dev.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    # ---- kind table
    with (OUT / "kind_table.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["setting", "value_kind", "dev_gold", "gold_subject_named_in_text", "predicted", "correct", "wrong_value",
                    "extra_beyond_form", "precision", "recall", "recall_of_named"])
        for name in ("cv_out_of_fold", "frozen_in_sample"):
            pk = store[name][1]
            for k in KINDS:
                c = pk[k]
                w.writerow([name, k, c["gold"], c["gold_named"], c["pred"], c["tp"], c["wrong_value"], c["extra"],
                            pct(c["tp"], c["pred"]), pct(c["recovered"], c["gold"]), pct(c["recovered"], c["gold_named"])])

    # ---- attribute coverage
    attrs = sorted(lex.attr_subjects)
    pa_cv, pa_fz = store["cv_out_of_fold"][2], store["frozen_in_sample"][2]
    kinds_gold = defaultdict(Counter)
    for r in rows:
        for g in r["gold"]:
            kinds_gold[g["attribute"]][g["value"]["kind"]] += 1
    frozen_attr_all = Counter(f["attribute"] for f in allf)
    rows_out = []
    for a in attrs:
        c, z = pa_cv[a], pa_fz[a]
        if c["gold"] == 0:
            st_ = "no_dev_gold"
        elif c["pred"] == 0:
            st_ = "zero_extraction_cv"
        elif c["tp"] == 0:
            st_ = "extracted_but_none_correct_cv"
        else:
            st_ = "ok"
        rows_out.append([a, "|".join(lex.attr_subjects[a]), json.dumps(dict(kinds_gold[a])), c["gold"], c["gold_named"],
                         c["pred"], c["recovered"], pct(c["tp"], c["pred"]), c["wrong_value"], c["extra"],
                         z["pred"], z["recovered"], pct(z["tp"], z["pred"]), frozen_attr_all[a], st_])
    with (OUT / "attribute_coverage.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["attribute", "subjects", "kinds_in_dev_gold", "dev_gold", "dev_gold_subject_named_in_text",
                    "cv_predicted", "cv_recovered", "cv_precision", "cv_wrong_value", "cv_extra_beyond_form",
                    "frozen_dev_predicted", "frozen_dev_recovered", "frozen_dev_precision", "frozen_all_rows_predicted",
                    "status"])
        w.writerows(rows_out)
    stc = Counter(r[-1] for r in rows_out)
    zero_cv = [r[0] for r in rows_out if r[-1] == "zero_extraction_cv"]
    zero_fz_all = [r[0] for r in rows_out if r[13] == 0]
    nogold = [r[0] for r in rows_out if r[-1] == "no_dev_gold"]
    bad = [r for r in rows_out if r[-1] == "extracted_but_none_correct_cv"]
    # recall on attributes with gold
    with_gold = [r for r in rows_out if r[3] > 0]
    buckets = Counter()
    for r in with_gold:
        rec = r[6] / r[3]
        buckets["recall=0" if r[6] == 0 else "0<recall<0.5" if rec < 0.5 else "0.5<=recall<0.9" if rec < 0.9 else "recall>=0.9"] += 1
    lines = ["# Attribute coverage summary (dev only; CV = out-of-fold)", "",
             f"Lexicon attributes: {len(attrs)}. Detail: `attribute_coverage.csv`.", "",
             "| status | attributes |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(stc.items())]
    lines += ["", f"Attributes with dev gold: {len(with_gold)}. Recall buckets (CV): " +
              ", ".join(f"{k}: {v}" for k, v in sorted(buckets.items())), "",
              f"No dev gold ({len(nogold)}): {', '.join(nogold)}", "",
              f"Dev gold but zero extraction in CV ({len(zero_cv)}): {', '.join(zero_cv)}", "",
              f"Extracted but none correct in CV ({len(bad)}): {', '.join(r[0] for r in bad)}", "",
              f"Attributes with zero facts in the frozen output over all input rows: {len(zero_fz_all)}", "",
              "## Per value kind (CV, out-of-fold)", "",
              "| kind | dev gold | named in text | predicted | correct | wrong value | extra | precision | recall |",
              "|---|---|---|---|---|---|---|---|---|"]
    for k in KINDS:
        c = store["cv_out_of_fold"][1][k]
        lines.append(f"| {k} | {c['gold']} | {c['gold_named']} | {c['pred']} | {c['tp']} | {c['wrong_value']} | {c['extra']} | "
                     f"{pct(c['tp'], c['pred'])} | {pct(c['recovered'], c['gold'])} |")
    lines += ["", "## Per value kind (frozen output on dev rows, IN-SAMPLE: optimistic)", "",
              "| kind | dev gold | predicted | correct | wrong value | extra | precision | recall |", "|---|---|---|---|---|---|---|---|"]
    for k in KINDS:
        c = store["frozen_in_sample"][1][k]
        lines.append(f"| {k} | {c['gold']} | {c['pred']} | {c['tp']} | {c['wrong_value']} | {c['extra']} | "
                     f"{pct(c['tp'], c['pred'])} | {pct(c['recovered'], c['gold'])} |")
    (OUT / "attribute_coverage_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---- extras for manual review (CV extras beyond form + wrong values), fixed seed
    _, _, _, _, ex, wr, ms = store["cv_out_of_fold"]
    pool = [(r, p, "extra_beyond_form") for r, p in ex] + [(r, p, "wrong_value_for_form_slot") for r, p in wr]
    pool.sort(key=lambda t: (t[0]["id"], t[1]["attribute"], json.dumps(t[1]["value"], sort_keys=True)))
    rnd = random.Random(20261029)
    sample = rnd.sample(pool, min(len(pool), 60))
    sample.sort(key=lambda t: t[0]["id"])
    with (OUT / "extras_review_input.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r, p, cat in sample:
            fh.write(json.dumps({"row": r["id"], "category": cat, "text": r["text"],
                                 "gold_form": [{k: g[k] for k in ("subject", "attribute", "value")} for g in r["gold"]],
                                 "pred": {k: p[k] for k in ("subject", "attribute", "value", "extraction_confidence",
                                                            "parse_status", "source_text_span", "negated")}},
                                ensure_ascii=False) + "\n")
    # ---- misses for failure analysis (CV), deterministic sample
    rnd = random.Random(20261030)
    ms_s = sorted(ms, key=lambda t: (t[0]["id"], t[1]["attribute"]))
    ms_s = rnd.sample(ms_s, min(250, len(ms_s)))
    with (OUT / "failure_candidates.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r, p in sorted(wr, key=lambda t: t[0]["id"]):
            fh.write(json.dumps({"type": "wrong_value", "row": r["id"], "text": r["text"],
                                 "gold": [g for g in r["gold"] if g["attribute"] == p["attribute"]],
                                 "pred": {k: p[k] for k in ("subject", "attribute", "value", "extraction_confidence")}},
                                ensure_ascii=False) + "\n")
        for r, g in sorted(ms_s, key=lambda t: t[0]["id"]):
            got = [{k: p[k] for k in ("subject", "attribute", "value")} for p in cv_acc.get(r["id"], [])]
            fh.write(json.dumps({"type": "missed_gold", "row": r["id"], "text": r["text"], "gold": g, "preds_in_row": got},
                                ensure_ascii=False) + "\n")
    print(json.dumps({k: res[k]["total"] for k in ("cv_out_of_fold", "frozen_in_sample")}, indent=1))
    print(json.dumps(res["frozen_all_rows"], indent=1))
    print("pool size", len(pool), "extras", len(ex), "wrong_value", len(wr))


if __name__ == "__main__":
    main()
