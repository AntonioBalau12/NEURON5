"""Negative test of validate_claims.py: each deliberately BAD claim below must be reported with at least one problem.

  py experiments/claim_factory/selftest_validator.py
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

import validate_claims
from store import Params

M = lambda v, per="month": {"kind": "money", "value": v, "currency": "EUR", "per": per}
PRO = lambda text, v=59: ("fact", text, {"subject": "Hooly AI Pro", "attribute": "price", "value": M(v)})
BAD = [
    ("stale/old value", *PRO("Hooly AI Pro costs €49 per month.", 49)),
    ("duplicate of an input row text", *PRO("Hooly AI Pro costs €59 per month")),
    ("name-in-longer-name (Hooly vs Hooly AI Pro)", *PRO("Hooly costs €59 per month.")),
    ("approximation", *PRO("Hooly AI Pro costs about €59 per month.")),
    ("negation", *PRO("Hooly AI Pro does not cost €59 per month.")),
    ("second value of the same kind", *PRO("Hooly AI Pro costs €59 per month, up from €49 per month.")),
    ("date word", *PRO("In April, Hooly AI Pro cost €59 per month.")),
    ("value without period", *PRO("Hooly AI Pro costs €59.")),
    ("two sentences", *PRO("Hooly AI Pro is a plan. It costs €59 per month.")),
    ("unknown attribute", "fact", "Hooly AI Pro has 3 wheels.", {"subject": "Hooly AI Pro", "attribute": "wheels", "value": {"kind": "quantity", "value": 3, "unit": "wheel"}}),
    ("value with op", "fact", "Hooly AI Pro costs over €59 per month.", {"subject": "Hooly AI Pro", "attribute": "price", "value": {**M(59), "op": "gt"}}),
    ("compare states a value", "compare", "Hooly Workspace costs €100 more than Hooly AI Pro.",
     {"left": {"subject": "Hooly Workspace", "attribute": "price"}, "right": {"subject": "Hooly AI Pro", "attribute": "price"}, "op": "gt"}),
    ("compare wrong direction", "compare", "Hooly Workspace costs less than Hooly AI Pro.",
     {"left": {"subject": "Hooly Workspace", "attribute": "price"}, "right": {"subject": "Hooly AI Pro", "attribute": "price"}, "op": "lt"}),
    ("compare of a fact with itself", "compare", "Hooly AI Pro costs more than Hooly AI Pro.",
     {"left": {"subject": "Hooly AI Pro", "attribute": "price"}, "right": {"subject": "Hooly AI Pro", "attribute": "price"}, "op": "gt"}),
    ("change not verified by the engine", "change", "Hooly AI Pro's price went from €49 per month to €59 per month.",
     {"subject": "Hooly AI Pro", "attribute": "price", "from": M(49), "to": M(59)}),
    ("at_event, wrong event", "at_event", "Hooly AI Pro costs €59 per month at Hooly I/O 2026.",
     {"subject": "Hooly AI Pro", "attribute": "price", "event": "Hooly I/O 2026", "value": M(59)}),
    ("relation without relation words", "relation", "Bertram Gilfoil joined Hooly on 1 July 2026.",
     {"subject": "Hooly", "link": "cto", "target": "Bertram Gilfoil", "attribute": "joined", "value": {"kind": "date", "value": "2026-07-01"}}),
    ("relation with a date of its own", "relation", "The CTO of Hooly, who left on 3 May 2027, joined on 1 July 2026.",
     {"subject": "Hooly", "link": "cto", "target": "Bertram Gilfoil", "attribute": "joined", "value": {"kind": "date", "value": "2026-07-01"}}),
    ("compare date wrong direction (outage is after I/O)", "compare", "The May 2026 outage took place before Hooly I/O 2026.",
     {"left": {"subject": "The May 2026 outage", "attribute": "date"}, "right": {"subject": "Hooly I/O 2026", "attribute": "date"}, "op": "lt"}),
    ("fact: wrong day for an immutable launch date", "fact", "Hooly Sheets launched on 4 March 2026.",
     {"subject": "Hooly Sheets", "attribute": "launched", "value": {"kind": "date", "value": "2026-03-04"}}),
    ("boolean polarity", "fact", "Hooly is SOC 2 certified.", {"subject": "Hooly", "attribute": "soc2_certified", "value": {"kind": "boolean", "value": False}}),
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp()) / "bad.csv"
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["id", "type", "text", "form", "label", "confidence"])
        for i, (_, ctype, text, form) in enumerate(BAD):
            w.writerow([f"bad-{i}", ctype, text, json.dumps(form, ensure_ascii=False), "true", "0.9"])
    report = validate_claims.validate(tmp, Params(), None, None)
    flagged = {p["id"]: p["problems"] for p in report["problem_examples"]}
    # problem_examples is truncated at 25 -> recompute from layers when needed
    missed = [BAD[i][0] for i in range(len(BAD)) if f"bad-{i}" not in flagged]
    print(f"{len(BAD)} bad claims, flagged {len(BAD) - len(missed)}")
    for i, (name, *_rest) in enumerate(BAD):
        pr = flagged.get(f"bad-{i}", [])
        print(f"  {'OK ' if pr else 'MISSED'} {name}: {[x.split(':')[0] + ':' + x.split(':')[1][:40] for x in pr[:3]]}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
