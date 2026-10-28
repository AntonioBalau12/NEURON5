"""Checks the value parsers (values.py) against the examples of contracts/value-forms.md.

  py experiments/slot_filling/test_value_forms.py

READ cases: some mention of the text must read exactly as listed (value, unit, op). NOT_READ cases: no mention of the
text may be emittable (not approximate / range end / negated) with the listed value. The cases are typed in from the
tables of the contract by the author of this module, they are not read from the contract file.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from values import find_value_mentions  # noqa: E402

Q = lambda v, u, **k: {"kind": "quantity", "value": v, "unit": u, **k}
M = lambda v, c, per=None, **k: {"kind": "money", "value": v, "currency": c, **({"per": per} if per else {}), **k}
P = lambda v, **k: {"kind": "percent", "value": v, **k}
D = lambda v, **k: {"kind": "date", "value": v, **k}
V = lambda v: {"kind": "version", "value": v}
U = lambda v, u, **k: {"kind": "duration", "value": v, "unit": u, **k}

READ = [
    ("128 GB of storage", Q(128, "GB")), ("128GB", Q(128, "GB")), ("2 terabytes", Q(2, "TB")),
    ("a 5,000 mAh battery", Q(5000, "mAh")), ("weighs 1.2 kg", Q(1.2, "kg")), ('a 6.1" display', Q(6.1, "in")),
    ("a 6.1-inch display", Q(6.1, "in")), ("3.2 GHz", Q(3.2, "GHz")), ("a 65-watt charger", Q(65, "W")),
    ("water resistant to 100 m", Q(100, "m")),
    ("speaks 40 languages", Q(40, "language")), ("speaks forty languages", Q(40, "language")),
    ("trusted by 10,000 companies", Q(10000, "company")), ("1,200 paying customers", Q(1200, "customer")),
    ("10,000 of our customers", Q(10000, "customer")), ("1.2 million users", Q(1200000, "user")),
    ("1M tests", Q(1000000, "test")), ("10k steps", Q(10000, "step")), ("twenty-four engineers", Q(24, "engineer")),
    ("a dozen partners", Q(12, "partner")), ("12 people", Q(12, "person")), ("zero outages", Q(0, "outage")),
    ("2,048 customers", Q(2048, "customer")), ("speaks 30 languages and never misses a beat", Q(30, "language")),
    ("€49 a month", M(49, "EUR", "month")), ("€49/mo", M(49, "EUR", "month")), ("49 euros per month", M(49, "EUR", "month")),
    ("EUR 49 monthly", M(49, "EUR", "month")), ("€49,99 a month", M(49.99, "EUR", "month")),
    ("€10 per user per month", M(10, "EUR", "month")), ("AI Pro from €39/month", M(39, "EUR", "month")),
    ("£9 a week", M(9, "GBP", "week")), ("€490 per annum", M(490, "EUR", "year")), ("$299.99", M(299.99, "USD")),
    ("US$12", M(12, "USD")), ("a €12M seed round", M(12000000, "EUR")), ("€1.2bn", M(1200000000, "EUR")),
    ("1,999 lei", M(1999, "RON")), ("€49 a month or €490 a year", M(490, "EUR", "year")),
    ("99.99% uptime", P(99.99)), ("99.9 % uptime", P(99.9)), ("50 percent", P(50)), ("50 per cent", P(50)),
    ("fifty percent", P(50)), ("99.999% uptime", P(99.999)),
    ("2026-03-12", D("2026-03-12")), ("2026-03", D("2026-03")), ("12 March 2026", D("2026-03-12")),
    ("12th March 2026", D("2026-03-12")), ("the 12th of March 2026", D("2026-03-12")), ("12March 2026", D("2026-03-12")),
    ("March 12, 2026", D("2026-03-12")), ("Mar 12th 2026", D("2026-03-12")), ("since 1 Mar. 2026", D("2026-03-01")),
    ("March 2026", D("2026-03")), ("Sept 2026", D("2026-09")), ("founded in 2025", D("2025")),
    ("v2.3", V("2.3")), ("version 2.3", V("2.3")), ("ver. 2.3", V("2.3")), ("v3", V("3")), ("2.3.1", V("2.3.1")),
    ("Hooly Gemini 2.2", V("2.2")),
    ("battery lasts 14 days", U(14, "day")), ("a 14-day trial", U(14, "day")), ("14days", U(14, "day")),
    ("two weeks", U(2, "week")), ("a two-week trial", U(2, "week")), ("for a fortnight", U(2, "week")),
    ("24 hours", U(24, "h")), ("24h", U(24, "h")), ("30 min", U(30, "min")), ("p95 latency 1.8 s", U(1.8, "s")),
    ("500 ms", U(500, "ms")), ("12 months", U(12, "month")), ("for a week", U(1, "week")),
    ("over 10,000 customers", Q(10000, "customer", op="gt")), ("10,000+ customers", Q(10000, "customer", op="ge")),
    ("at least 12 languages", Q(12, "language", op="ge")), ("40 languages or more", Q(40, "language", op="ge")),
    ("uploads up to 25 MB", Q(25, "MB", op="le")), ("no more than 2 GB", Q(2, "GB", op="le")),
    ("2 GB or less", Q(2, "GB", op="le")), ("fewer than 50 employees", Q(50, "employee", op="lt")),
    ("under $300", M(300, "USD", op="lt")), ("over 99% accuracy", P(99, op="gt")),
    ("answers in under a second", U(1, "s", op="lt")), ("within an hour", U(1, "h", op="le")),
    ("before March 2026", D("2026-03", op="lt")), ("after 2025", D("2025", op="gt")), ("by 1 May 2026", D("2026-05-01", op="le")),
]

NOT_READ = [
    ("12/03/2026", D("2026-03-12")), ("12.03.2026", D("2026-03-12")), ("March 12", D("2026-03-12")),
    ("Q4 2026", D("2026")), ("12 March 2026", D("2026-03")), ("1.000.000 users", Q(1000000, "user")),
    ("1,5 GB", Q(1.5, "GB")), ("1,5 GB", Q(5, "GB")), ("99,9% uptime", P(9)), ("1.500 mAh", Q(1500, "mAh")),
    ("99.6% uptime", P(6)), ("we do not offer 99.9% uptime", P(99.9)), ("no 14-day trial", U(14, "day")),
    ("about 10,000 customers", Q(10000, "customer")), ("~10 GB", Q(10, "GB")), ("40 languages or so", Q(40, "language")),
    ("10–20 GB", Q(20, "GB")), ("10 GB to 20 GB", Q(10, "GB")), ("between 10 and 20 GB", Q(20, "GB")),
    ("1 or 2 days", U(2, "day")), ("10m users", Q(10000000, "user")), ("2026 customers", Q(2026, "customer")),
    ("half an hour", U(30, "min")), ("1,000 requests a day", U(1, "day")), ("€49 a month", M(49, "EUR")),
    ("5 pounds", M(5, "GBP")), ("Hooly Gemini 11", V("11")), ("v2.3", V("2.3.0")), ("30 days", U(1, "month")),
    ("over 10,000 customers", Q(10000, "customer")),
    ("10,000 of our happy loyal customers", Q(10000, "customer")),
    ("roughly 5 TB", Q(5, "TB")), ("around 99%", P(99)), ("circa 2 weeks", U(2, "week")), ("approximately €20", M(20, "EUR")),
    ("€49–€59", M(59, "EUR")), ("not founded in 2025", D("2025")), ("nearly 3 million users", Q(3000000, "user")),
]


def _norm(rd):
    """'inch' and 'in' are one unit (foundation converts both); the dataset forms write 'inch'."""
    return {**rd, "unit": "in"} if rd.get("unit") == "inch" else rd


def readable(text, want):
    base = {k: v for k, v in want.items() if k != "op"}
    for m in find_value_mentions(text, [], set()):
        if not m.surface_ok:
            continue
        for rd in m.readings:
            if _norm(rd) == base and (m.op or None) == want.get("op"):
                return True
    return False


def main():
    fails = []
    for text, want in READ:
        if not readable(text, want):
            fails.append(("READ", text, want))
    for text, nope in NOT_READ:
        if readable(text, nope):
            fails.append(("NOT_READ", text, nope))
    print(f"read cases {len(READ)}, not-read cases {len(NOT_READ)}, failures {len(fails)}")
    for f in fails:
        print("  ", f)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
