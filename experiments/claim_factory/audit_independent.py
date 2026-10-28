"""Independent re-derivation of a run's claims straight from data/practice.csv forms (does NOT use core.graph or store.py).

For every claim of <run>/claims_valid.csv it re-checks, from the raw forms of ALL labelled rows:
  fact      last TRUE observation of (subject, attribute) has the claim's value; no later/same-day false/unsure/conflicting row
            states a different value; age to 2026-10-29
  compare   same for both sides, plus the ordering of the two values
  at_event  event has one day-precision date among true rows and no non-true row states another day; the fact is stated with the
            claim's value on that day by a true row and no true row states another value of it that day
  relation  a true row names the target as the link's value; a true row states the target fact with the value on a day within
            [first, last] day the link names the target (or the stated range of link rows)
  change    (only for relaxed runs) the from/to endpoints are each stated by >=1 true row, the from-value row dated before the to-value row,
            and nothing later contradicts the to-value
Output: output/audit_<run>/audit_independent.json  (per-claim verdicts + summary).  Usage:  py experiments/claim_factory/audit_independent.py run_main
This is a self-consistency audit against the same data; it cannot see facts outside the practice sample.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cf_common import LEXICON_JSON, PRACTICE_CSV  # noqa: E402
import foundation  # noqa: E402
from foundation import TypedValue  # noqa: E402
from observations import same_value  # noqa: E402

AS_OF = date(2026, 10, 29)


def main(run: str) -> int:
    out_dir = HERE / "output" / run
    AUDIT_DIR = HERE / "output" / f"audit_{run}"
    AUDIT_DIR.mkdir(exist_ok=True)
    data = foundation.load_inputs(PRACTICE_CSV, LEXICON_JSON)
    lex = data.lexicon
    obs: dict[tuple[str, str], list[tuple[date, str, str, TypedValue]]] = defaultdict(list)
    with PRACTICE_CSV.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r["form"]:
                continue
            d = date.fromisoformat(r["date"])
            for f in json.loads(r["form"]):
                ref = lex.resolve(f["subject"])
                subj = ref.name if ref else f["subject"]
                tv, _ = TypedValue.parse(f["value"])
                if tv is None:
                    continue
                obs[(subj, f["attribute"])].append((d, r["id"], r["label"], tv))
    for lst in obs.values():
        lst.sort(key=lambda x: (x[0], x[1]))

    def asof(key):
        lst = obs.get(key, [])
        tr = [o for o in lst if o[2] == "true"]
        if not tr:
            return {"ok": False, "why": "no_true_observation"}
        last = tr[-1]
        run = []
        for o in reversed(tr):
            if same_value(o[3], last[3]):
                run.append(o)
            else:
                break
        fine = max((o[3] for o in run), key=lambda x: len(str(x.value)) if x.kind == "date" else 0)
        last = (last[0], last[1], last[2], fine)
        later_diff = [o for o in lst if o[0] >= last[0] and o[2] != "true" and not same_value(o[3], last[3])]
        same_day_true_diff = [o for o in tr if o[0] == last[0] and not same_value(o[3], last[3])]
        return {"ok": not later_diff and not same_day_true_diff, "value": last[3], "last_date": last[0], "age": (AS_OF - last[0]).days,
                "later_nontrue_diff": [(o[1], o[2], str(o[3].value)) for o in later_diff][:3],
                "same_day_true_diff": [(o[1], str(o[3].value)) for o in same_day_true_diff][:3],
                "n_true": len(tr), "distinct_true": len({(o[3].kind, str(o[3].value)) for o in tr})}

    verdicts = []
    with (out_dir / "claims_valid.csv").open(encoding="utf-8", newline="") as fh:
        claims = list(csv.DictReader(fh))
    for c in claims:
        form = json.loads(c["form"])
        t = c["type"]
        v = {"claim_id": c["id"], "type": t, "text": c["text"], "verdict": "pass", "notes": []}
        if t == "fact":
            ref = lex.resolve(form["subject"]); key = (ref.name if ref else form["subject"], form["attribute"])
            tv, _ = TypedValue.parse(form["value"])
            a = asof(key)
            if not a["ok"] and "value" not in a:
                v["verdict"] = "fail"; v["notes"].append(a["why"])
            else:
                if not same_value(a["value"], tv):
                    v["verdict"] = "fail"; v["notes"].append(f"last true value {a['value'].value} != claim")
                if a["later_nontrue_diff"] or a["same_day_true_diff"]:
                    v["verdict"] = "fail"; v["notes"].append(f"later contradiction {a['later_nontrue_diff'] or a['same_day_true_diff']}")
                v["age"] = a["age"]; v["volatile"] = a["distinct_true"] > 1; v["n_true"] = a["n_true"]
        elif t == "compare":
            sides = []
            for s in ("left", "right"):
                ref = lex.resolve(form[s]["subject"]); key = (ref.name if ref else form[s]["subject"], form[s]["attribute"])
                a = asof(key); sides.append(a)
                if "value" not in a or not a["ok"]:
                    v["verdict"] = "fail"; v["notes"].append(f"{s}: not stably derivable ({a.get('later_nontrue_diff') or a.get('same_day_true_diff') or a.get('why')})")
            if v["verdict"] == "pass":
                l, r = sides[0]["value"], sides[1]["value"]
                res = foundation.compare_values(l, r, form["op"])
                if res is not True:
                    v["verdict"] = "fail"; v["notes"].append(f"op {form['op']} does not hold: {l.value} vs {r.value}")
                v["ages"] = [sides[0]["age"], sides[1]["age"]]
                v["volatile"] = [sides[0]["distinct_true"] > 1, sides[1]["distinct_true"] > 1]
                v["kind"] = l.kind
        elif t == "at_event":
            ref = lex.resolve(form["event"]); ev = ref.name if ref else form["event"]
            days = {str(o[3].value) for o in obs.get((ev, "date"), []) if o[2] == "true" and len(str(o[3].value)) == 10}
            nontrue_days = {str(o[3].value) for o in obs.get((ev, "date"), []) if o[2] != "true" and len(str(o[3].value)) == 10}
            if not days:
                v["verdict"] = "fail"; v["notes"].append("event has no day-precision date among true rows")
            else:
                evl = [o for o in obs.get((ev, "date"), []) if o[2] == "true" and len(str(o[3].value)) == 10]
                day = str(evl[-1][3].value)
                if len(days) > 1:
                    v["verdict"] = "rescheduled_event"; v["notes"].append(f"true rows state several event days {sorted(days)}; latest {day} used")
                days = {day}
                if nontrue_days - days:
                    v["verdict"] = "uncertain" if v["verdict"] == "pass" else v["verdict"]; v["notes"].append(f"non-true rows state other event days {sorted(nontrue_days - days)}")
                ref = lex.resolve(form["subject"]); key = (ref.name if ref else form["subject"], form["attribute"])
                tv, _ = TypedValue.parse(form["value"])
                that = [o for o in obs.get(key, []) if str(o[0]) == day]
                good = [o for o in that if o[2] == "true" and same_value(o[3], tv)]
                bad = [o for o in that if not same_value(o[3], tv)]
                if not good:
                    v["verdict"] = "fail"; v["notes"].append("no true row states the fact on the event day")
                if bad:
                    v["verdict"] = "fail" if any(o[2] == "true" for o in bad) else ("uncertain" if v["verdict"] == "pass" else v["verdict"])
                    v["notes"].append(f"differing observation on the day: {[(o[1], o[2], str(o[3].value)) for o in bad][:3]}")
        elif t == "relation":
            ref = lex.resolve(form["subject"]); lk = (ref.name if ref else form["subject"], form["link"])
            tref = lex.resolve(form["target"]); tgt = tref.name if tref else form["target"]
            link_days = [o[0] for o in obs.get(lk, []) if o[2] == "true" and (lex.resolve(str(o[3].value)) or type("x", (), {"name": str(o[3].value)})).name == tgt]
            tv, _ = TypedValue.parse(form["value"])
            tf = [o for o in obs.get((tgt, form["attribute"]), []) if o[2] == "true" and same_value(o[3], tv)]
            if not link_days:
                v["verdict"] = "fail"; v["notes"].append("no true row names the target as the link")
            elif not tf:
                v["verdict"] = "fail"; v["notes"].append("no true row states the target fact")
            else:
                lo, hi = min(link_days), max(link_days)
                inside = [o for o in tf if lo <= o[0] <= hi]
                if not inside:
                    # the target fact may be stated about a time within the link period although the row is dated outside the link rows
                    v["verdict"] = "uncertain"; v["notes"].append(f"target fact rows {[str(o[0]) for o in tf][:3]} outside link rows [{lo}, {hi}]")
                other = {str(lex.resolve(str(o[3].value)).name) for o in obs.get(lk, []) if lex.resolve(str(o[3].value))} - {tgt}
                if other:
                    v["notes"].append(f"link also names {sorted(other)} at other dates")
        elif t == "change":
            ref = lex.resolve(form["subject"]); key = (ref.name if ref else form["subject"], form["attribute"])
            fv, _ = TypedValue.parse(form["from"]); tv, _ = TypedValue.parse(form["to"])
            tr = [o for o in obs.get(key, []) if o[2] == "true"]
            fr = [o for o in tr if same_value(o[3], fv)]; to = [o for o in tr if same_value(o[3], tv)]
            if not fr or not to:
                v["verdict"] = "fail"; v["notes"].append("an endpoint is not stated by any true row")
            else:
                if not (min(o[0] for o in fr) < max(o[0] for o in to)):
                    v["verdict"] = "fail"; v["notes"].append("from-value not observed before to-value")
                seq = []
                for o in tr:
                    if not seq or not same_value(o[3], seq[-1]):
                        seq.append(o[3])
                if len(seq) > 2 and any(same_value(seq[i], seq[j]) for i in range(len(seq)) for j in range(i + 2, len(seq))):
                    v["verdict"] = "uncertain" if v["verdict"] == "pass" else v["verdict"]; v["notes"].append("value sequence flaps")
                v["from_rows"] = len(fr); v["to_rows"] = len(to)
                later = [o for o in obs.get(key, []) if o[0] >= max(o[0] for o in to) and not same_value(o[3], tv)]
                if later:
                    v["verdict"] = "uncertain" if v["verdict"] == "pass" else v["verdict"]; v["notes"].append(f"later differing observation {[(o[1], o[2]) for o in later][:3]}")
        verdicts.append(v)

    summ: dict[str, Counter] = defaultdict(Counter)
    for v in verdicts:
        summ[v["type"]][v["verdict"]] += 1
    extra = {}
    facts = [v for v in verdicts if v["type"] == "fact"]
    if facts:
        extra["fact_age_days_hist"] = dict(sorted(Counter(("0-3" if v["age"] <= 3 else "4-7" if v["age"] <= 7 else "8-14" if v["age"] <= 14 else ">14(immutable dates)") for v in facts if "age" in v).items()))
        extra["fact_volatile_true_values"] = sum(1 for v in facts if v.get("volatile"))
        extra["fact_single_true_row"] = sum(1 for v in facts if v.get("n_true") == 1)
    (AUDIT_DIR / "audit_independent.json").write_text(json.dumps({"summary": {k: dict(c) for k, c in summ.items()}, "extra": extra, "verdicts": verdicts},
                                                               indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: dict(c) for k, c in summ.items()}, indent=1), json.dumps(extra))
    for v in verdicts:
        if v["verdict"] != "pass":
            print(v["verdict"], v["claim_id"], v["text"], v["notes"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))



