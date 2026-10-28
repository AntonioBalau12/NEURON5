"""Stratified sample of run_main for hand review (seeded)."""
import csv, json, random, sys
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
run = sys.argv[1]; typ = sys.argv[2]; n = int(sys.argv[3]); seed = int(sys.argv[4]) if len(sys.argv) > 4 else 7
prov = [json.loads(l) for l in open(f"experiments/claim_factory/output/{run}/provenance.jsonl", encoding="utf-8")]
print(Counter(p["type"] for p in prov))
sel = [p for p in prov if p["type"] == typ]
random.Random(seed).shuffle(sel)
for p in sel[:n]:
    print("="*100)
    print(p["claim_id"], "|", p["text"], "| rule:", p["rule"], "| flags:", p["flags"], "| engine:", p["engine"])
    print("FORM:", json.dumps(p["form"], ensure_ascii=False))
    ev = p["evidence"]
    def show(rows, tag):
        for r in rows or []:
            print(f"  {tag} {r['row_id']} {r['date']} [{r['label']}] {r['subject']}.{r['attribute']}={r['value']} :: {r['text'][:170]}")
    if typ == "fact":
        print("  age", ev.get("age_days"), "nrows", ev.get("n_support_rows"), "volatile", ev.get("volatile"), "immut", ev.get("immutable_event_date"))
        show(ev.get("support"), "S")
    elif typ == "compare":
        for s in ev["sides"]:
            show(s["support"], "S" + s["key"][0][:10])
    elif typ == "change":
        print("  from", ev["from_date"], "to", ev["to_date"], "flapping", ev["flapping"])
        show(ev["support"], "S")
    elif typ == "at_event":
        print("  event_date", ev["event_date"], "fact_rows", ev["fact_rows"])
        show(ev["event_date_rows"], "ED"); show(ev.get("fact_rows_detail"), "F")
    elif typ == "relation":
        show(ev["link_rows"], "L"); show(ev["target_rows"], "T")
