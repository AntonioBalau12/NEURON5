"""Checks the independent text checker against the worked examples of contracts/claim-forms.md.

Run:  py experiments/claim_factory/selftest_textcheck.py
Every 'yes' example must give no problem; every 'no' example must give at least one.  A few 'yes' examples are
rejected on purpose because this checker is stricter than the contract (it bans any second value, any alias of the
fact's other entities is only a soft flag, etc.); those are listed in STRICTER.
"""
from __future__ import annotations

import sys

from cf_common import LEXICON_JSON  # noqa: F401  (sys.path)
from textcheck import Names, check_text

N = Names(LEXICON_JSON)
M = lambda v, cur="EUR", per="month": {"kind": "money", "value": v, "currency": cur, "per": per}
PRICE59 = {"subject": "Hooly AI Pro", "attribute": "price", "value": M(59)}
SOC_NO = {"subject": "Hooly", "attribute": "soc2_certified", "value": {"kind": "boolean", "value": False}}
CMP = {"left": {"subject": "Hooly Workspace", "attribute": "price"}, "right": {"subject": "Hooly AI Pro", "attribute": "price"}, "op": "gt"}


def cmp(op):
    d = dict(CMP)
    d["op"] = op
    return d


DATECMP = lambda op: {"left": {"subject": "Hooly I/O 2026", "attribute": "date"}, "right": {"subject": "The May 2026 outage", "attribute": "date"}, "op": op}
CHANGE = {"subject": "Hooly AI Pro", "attribute": "price", "from": M(49), "to": M(59)}
EVENT = {"subject": "Hooly Gemini", "attribute": "languages", "event": "Hooly I/O 2026", "value": {"kind": "quantity", "value": 12, "unit": "language"}}
REL = {"subject": "Hooly", "link": "cto", "target": "Bertram Gilfoil", "attribute": "joined", "value": {"kind": "date", "value": "2026-07-01"}}

CASES = [  # (type, text, form, table, expected_yes)
    ("fact", "Hooly AI Pro costs €59 per month.", PRICE59, "amount", True),
    ("fact", "At €59 per month, Hooly AI Pro is our best seller.", PRICE59, "amount", True),
    ("fact", "Hooly AI Pro costs over €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly AI Pro costs about €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly AI Pro costs €59.", PRICE59, "amount", False),
    ("fact", "It costs €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly costs €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly AI Pro costs €59 per month, and never more.", PRICE59, "amount", False),
    ("fact", "Hooly AI Pro costs €59 per month, up from €49 per month.", PRICE59, "amount", False),
    ("fact", "In March 2026, Hooly AI Pro cost €59 per month.", PRICE59, "amount", False),
    ("fact", "In April, Hooly AI Pro cost €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly AI Pro used to cost €59 per month.", PRICE59, "amount", False),
    ("fact", "Hooly is not SOC 2 certified.", SOC_NO, "amount", True),
    ("fact", "Hooly has never been SOC2-certified.", SOC_NO, "amount", True),
    ("fact", "Hooly is fully SOC 2 certified.", SOC_NO, "amount", False),
    ("fact", "Hooly has never passed a SOC 2 audit.", SOC_NO, "amount", False),
    ("fact", "Hooly is not profitable.", SOC_NO, "amount", False),
    ("compare", "Hooly Workspace costs more than Hooly AI Pro.", cmp("gt"), "amount", True),
    ("compare", "Hooly Workspace is more expensive than Hooly AI Pro.", cmp("gt"), "amount", True),
    ("compare", "The Workspace plan costs a higher monthly price than Hooly AI Pro.", cmp("gt"), "amount", True),
    ("compare", "Hooly Workspace costs the same as Hooly AI Pro.", cmp("eq"), "amount", True),
    ("compare", "Hooly Workspace costs as much as Hooly AI Pro.", cmp("eq"), "amount", True),
    ("compare", "Hooly Workspace costs more than Hooly AI Pro.", cmp("lt"), "amount", False),
    ("compare", "Hooly AI Pro costs less than Hooly Workspace.", cmp("lt"), "amount", False),
    ("compare", "Hooly Workspace costs more than its rivals.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace outprices Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace does not cost more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace costs more than Hooly AI Pro, and less than Hooly AI Free.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace costs more than Hooly.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace comes after Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace costs more per month than Hooly AI Pro.", cmp("gt"), "amount", True),
    ("compare", "Hooly Workspace costs €100 more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace costs 100 more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace costs a hundred more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "In June 2026, Hooly Workspace cost more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "In June, Hooly Workspace cost more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace used to cost more than Hooly AI Pro.", cmp("gt"), "amount", False),
    ("compare", "Hooly Workspace cost more than Hooly AI Pro before the outage.", cmp("gt"), "amount", False),
    ("compare", "Hooly I/O 2026 took place before the May 2026 outage.", DATECMP("lt"), "date", True),
    ("compare", "Hooly I/O 2026 came earlier than the outage.", DATECMP("lt"), "date", True),
    ("compare", "Hooly I/O took place on the same day as the outage.", DATECMP("eq"), "date", True),
    ("compare", "Hooly I/O 2026 was more than the May 2026 outage.", DATECMP("gt"), "date", False),
    ("compare", "Hooly I/O 2026 took place two weeks before the May 2026 outage.", DATECMP("lt"), "date", False),
    ("compare", "Hooly I/O 2026 took place before the outage, in March 2026.", DATECMP("lt"), "date", False),
    ("change", "Hooly AI Pro went from €49 per month to €59 per month.", CHANGE, "amount", True),
    ("change", "The price of Hooly AI Pro rose from €49 per month to €59 per month in April.", CHANGE, "amount", True),
    ("change", "Hooly AI Pro went from €49 to €59 per month.", CHANGE, "amount", False),
    ("change", "Hooly AI Pro cost €49 per month and now costs €59 per month.", CHANGE, "amount", False),
    ("change", "Hooly AI Pro never went from €49 per month to €59 per month.", CHANGE, "amount", False),
    ("change", "Hooly AI Pro went from €59 per month to €49 per month.", CHANGE, "amount", False),
    ("at_event", "Hooly Gemini spoke 12 languages at Hooly I/O 2026.", EVENT, "amount", True),
    ("at_event", "Hooly Gemini supported 12 languages on the day of Hooly I/O 2026.", EVENT, "amount", True),
    ("at_event", "Hooly Gemini spoke 12 languages at the time of Hooly I/O 2026.", EVENT, "amount", True),
    ("at_event", "Hooly Gemini spoke 12 languages before Hooly I/O 2026.", EVENT, "amount", False),
    ("at_event", "Hooly Gemini spoke 12 languages in March.", EVENT, "amount", False),
    ("at_event", "At Hooly I/O 2026, Hooly spoke 12 languages.", EVENT, "amount", False),
    ("at_event", "Hooly Gemini spoke 12 languages at Hooly I/O 2026, up from 6 languages.", EVENT, "amount", False),
    ("at_event", "In March 2026, at Hooly I/O 2026, Hooly Gemini spoke 12 languages.", EVENT, "amount", False),
    ("relation", "The CTO of Hooly joined on 1 July 2026.", REL, "amount", True),
    ("relation", "Hooly's CTO started on 2026-07-01.", REL, "amount", True),
    ("relation", "Hooly's chief technology officer joined on 1 July 2026.", REL, "amount", False),
    ("relation", "Bertram Gilfoil joined Hooly on 1 July 2026.", REL, "amount", False),
    ("relation", "The CTO joined on 1 July 2026.", REL, "amount", False),
    ("relation", "The CTO of Hooly, who left on 3 May 2027, joined on 1 July 2026.", REL, "amount", False),
    ("relation", "The CTO of Hooly joined on 1 July 2026, after Richard Hendrix.", REL, "amount", False),
]
# 'yes' per the contract, deliberately not produced by this generator -> may be refused by the stricter checker
STRICTER = {"Hooly has never been SOC2-certified.", "The Workspace plan costs a higher monthly price than Hooly AI Pro.",
            "Hooly Workspace is more expensive than Hooly AI Pro.", "At €59 per month, Hooly AI Pro is our best seller.",
            "The price of Hooly AI Pro rose from €49 per month to €59 per month in April.",
            "Hooly's CTO started on 2026-07-01."}


def main() -> int:
    bad = 0
    for ctype, text, form, table, yes in CASES:
        probs = check_text(ctype, text, form, N, compare_table=table)
        ok = (not probs) if yes else bool(probs)
        if not ok and not (yes and text in STRICTER):
            bad += 1
            print("MISMATCH", ctype, "expected", "yes" if yes else "no", "|", text, "|", probs)
        elif not ok:
            print("stricter-by-design:", text, [p[0] for p in probs])
    print(f"{len(CASES)} contract examples, {bad} unexpected mismatches")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
