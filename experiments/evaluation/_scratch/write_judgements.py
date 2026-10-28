"""One-off: record evaluator_llm judgements of the 8 baseline facts beyond the form (read against the sentence)."""
import json
import sys

sys.path.insert(0, "experiments/evaluation")
import common as C  # noqa: E402

notes = {
    ("p-1209", "personalised_ads_by_default"): "incorrect: the sentence negates it (does not personalise); the parser missed the negation",
    ("p-1222", "offline_languages"): "incorrect: 117 is languages_supported; the offline languages are 20",
    ("p-1707", "free_storage"): "incorrect: no storage amount in the sentence; the unit 'and' is garbage",
    ("p-1716", "maximum_seats"): "incorrect: the sentence says included seats, not a maximum",
    ("p-1716", "minimum_seats"): "incorrect: the sentence says included seats, not a minimum",
    ("p-1834", "included_seats"): "incorrect for Hooly AI Pro: the 10 seats belong to Hooly Workspace, AI Pro has 1 seat",
    ("p-1834", "maximum_seats"): "incorrect: the sentence says included seats, not a maximum",
    ("p-1834", "minimum_seats"): "incorrect: the sentence says included seats, not a minimum",
}
facts = {}
for line in open("experiments/evaluation/output/baseline_facts.jsonl", encoding="utf-8"):
    f = json.loads(line)
    facts[f["extraction_id"]] = f
cand = C.read_csv("experiments/evaluation/_scratch/try1/per_method/baseline/unverified_candidates_beyond_form.csv")
out = []
for c in cand:
    f = facts[c["extraction_id"]]
    out.append({"source_row_id": c["row"], "subject": f["subject"], "attribute": f["attribute"],
                "value": json.dumps(f["value"], ensure_ascii=False), "verdict": "incorrect",
                "reviewer": "evaluator_llm", "note": notes[(c["row"], f["attribute"])]})
C.write_csv(C.JUDGEMENTS_CSV, ["source_row_id", "subject", "attribute", "value", "verdict", "reviewer", "note"], out)
print(len(out), "judgements written to", C.JUDGEMENTS_CSV)
