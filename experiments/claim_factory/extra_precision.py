"""Precision of reconstructed facts against the gold forms of the practice rows (evaluation only), by confidence threshold."""
import csv, json, sys
from collections import Counter, defaultdict
sys.path.insert(0, "experiments/claim_factory")
from cf_common import LEXICON_JSON, PRACTICE_CSV
import foundation
from foundation import TypedValue
from observations import same_value
data = foundation.load_inputs(PRACTICE_CSV, LEXICON_JSON); lex = data.lexicon
gold = defaultdict(list); labels = {}
for r in csv.DictReader(PRACTICE_CSV.open(encoding="utf-8-sig", newline="")):
    labels[r["id"]] = r["label"]
    for f in json.loads(r["form"] or "[]"):
        ref = lex.resolve(f["subject"]); tv, _ = TypedValue.parse(f["value"])
        gold[r["id"]].append((ref.name if ref else f["subject"], f["attribute"], tv))
full_ids = {r["id"] for r in csv.DictReader(open("experiments/shared/data/full_input.csv", encoding="utf-8-sig", newline=""))}
res = {}
for name, path in (("openie", "experiments/openie/output/facts.jsonl"), ("slot_filling", "experiments/slot_filling/output/facts.jsonl")):
    R = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    pr = [r for r in R if r["source_row_id"] in gold]
    out = {"facts": len(R), "facts_on_practice_rows": len(pr), "facts_on_non_practice_rows": len(R) - len(pr),
           "source_labels_on_non_practice_rows": dict(Counter(r["source_label"] for r in R if r["source_row_id"] not in gold))}
    for thr in (0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.9):
        sel = [r for r in pr if r["parse_status"] == "complete" and r["source_label"] == "true" and r["extraction_confidence"] >= thr and not r["negated"] and r["subject"] and r["value"]]
        ok = in_form = 0
        for r in sel:
            tv, _ = TypedValue.parse(r["value"])
            if tv is None: continue
            ref = lex.resolve(r["subject"]); s = ref.name if ref else r["subject"]
            hit = any(g[0] == s and g[1] == r["attribute"] and same_value(g[2], tv) for g in gold[r["source_row_id"]])
            ok += hit
        out[f"thr>={thr}"] = {"n": len(sel), "in_gold_form_of_same_row": ok, "precision": round(ok / len(sel), 4) if sel else None}
    res[name] = out
print(json.dumps(res, indent=1))
Path = __import__("pathlib").Path
Path("experiments/claim_factory/output/audit_run_main").joinpath("extra_fact_precision_vs_gold.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
