"""Unit checks: examples copied from contracts/value-forms.md (documentation examples, not dataset sentences)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from oie.values import ValueFinder, Val  # noqa: E402

KNOWN = {"language", "customer", "company", "user", "step", "engineer", "partner", "person", "outage", "test", "employee"}


def find_all(text: str) -> list[Val]:
    vf = ValueFinder(KNOWN)
    taken: list[tuple[int, int]] = []
    vf.dead_dates(text, taken)
    out = vf.dates(text, taken)
    out += vf.versions(text, taken, [])
    out += vf.money(text, taken)
    out += vf.percent(text, taken)
    out += vf.durations(text, taken)
    out += vf.quantities(text, taken)
    out += vf.versions(text, taken, [], late=True)
    return sorted(out, key=lambda v: v.start)


def vals(text: str) -> list[dict]:
    return [v.value for v in find_all(text) if v.readable]


CASES = [
    ("128 GB of storage", [{"kind": "quantity", "value": 128, "unit": "GB"}]),
    ("128GB", [{"kind": "quantity", "value": 128, "unit": "GB"}]),
    ("2 terabytes", [{"kind": "quantity", "value": 2, "unit": "TB"}]),
    ("a 5,000 mAh battery", [{"kind": "quantity", "value": 5000, "unit": "mAh"}]),
    ("weighs 1.2 kg", [{"kind": "quantity", "value": 1.2, "unit": "kg"}]),
    ('a 6.1" display', [{"kind": "quantity", "value": 6.1, "unit": "inch"}]),
    ("a 6.1-inch display", [{"kind": "quantity", "value": 6.1, "unit": "inch"}]),
    ("3.2 GHz", [{"kind": "quantity", "value": 3.2, "unit": "GHz"}]),
    ("a 65-watt charger", [{"kind": "quantity", "value": 65, "unit": "W"}]),
    ("speaks 40 languages", [{"kind": "quantity", "value": 40, "unit": "language"}]),
    ("speaks forty languages", [{"kind": "quantity", "value": 40, "unit": "language"}]),
    ("trusted by 10,000 companies", [{"kind": "quantity", "value": 10000, "unit": "company"}]),
    ("1,200 paying customers", [{"kind": "quantity", "value": 1200, "unit": "customer"}]),
    ("10,000 of our customers", [{"kind": "quantity", "value": 10000, "unit": "customer"}]),
    ("1.2 million users", [{"kind": "quantity", "value": 1200000, "unit": "user"}]),
    ("1M tests", [{"kind": "quantity", "value": 1000000, "unit": "test"}]),
    ("10k steps", [{"kind": "quantity", "value": 10000, "unit": "step"}]),
    ("twenty-four engineers", [{"kind": "quantity", "value": 24, "unit": "engineer"}]),
    ("a dozen partners", [{"kind": "quantity", "value": 12, "unit": "partner"}]),
    ("12 people", [{"kind": "quantity", "value": 12, "unit": "person"}]),
    ("zero outages", [{"kind": "quantity", "value": 0, "unit": "outage"}]),
    ("2,048 customers", [{"kind": "quantity", "value": 2048, "unit": "customer"}]),
    ("speaks 30 languages and never misses a beat", [{"kind": "quantity", "value": 30, "unit": "language"}]),
    ("€49 a month", [{"kind": "money", "value": 49, "currency": "EUR", "per": "month"}]),
    ("€49/mo", [{"kind": "money", "value": 49, "currency": "EUR", "per": "month"}]),
    ("49 euros per month", [{"kind": "money", "value": 49, "currency": "EUR", "per": "month"}]),
    ("EUR 49 monthly", [{"kind": "money", "value": 49, "currency": "EUR", "per": "month"}]),
    ("€49,99 a month", [{"kind": "money", "value": 49.99, "currency": "EUR", "per": "month"}]),
    ("€10 per user per month", [{"kind": "money", "value": 10, "currency": "EUR", "per": "month"}]),
    ("AI Pro from €39/month", [{"kind": "money", "value": 39, "currency": "EUR", "per": "month"}]),
    ("£9 a week", [{"kind": "money", "value": 9, "currency": "GBP", "per": "week"}]),
    ("€490 per annum", [{"kind": "money", "value": 490, "currency": "EUR", "per": "year"}]),
    ("$299.99", [{"kind": "money", "value": 299.99, "currency": "USD"}]),
    ("US$12", [{"kind": "money", "value": 12, "currency": "USD"}]),
    ("a €12M seed round", [{"kind": "money", "value": 12000000, "currency": "EUR"}]),
    ("€1.2bn", [{"kind": "money", "value": 1200000000, "currency": "EUR"}]),
    ("1,999 lei", [{"kind": "money", "value": 1999, "currency": "RON"}]),
    ("€49 a month or €490 a year", [{"kind": "money", "value": 49, "currency": "EUR", "per": "month"},
                                     {"kind": "money", "value": 490, "currency": "EUR", "per": "year"}]),
    ("99.99% uptime", [{"kind": "percent", "value": 99.99}]),
    ("99.9 % uptime", [{"kind": "percent", "value": 99.9}]),
    ("50 percent", [{"kind": "percent", "value": 50}]),
    ("50 per cent", [{"kind": "percent", "value": 50}]),
    ("fifty percent", [{"kind": "percent", "value": 50}]),
    ("99.999% uptime", [{"kind": "percent", "value": 99.999}]),
    ("2026-03-12", [{"kind": "date", "value": "2026-03-12"}]),
    ("2026-03", [{"kind": "date", "value": "2026-03"}]),
    ("12 March 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("12th March 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("the 12th of March 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("12March 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("March 12, 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("Mar 12th 2026", [{"kind": "date", "value": "2026-03-12"}]),
    ("since 1 Mar. 2026", [{"kind": "date", "value": "2026-03-01"}]),
    ("March 2026", [{"kind": "date", "value": "2026-03"}]),
    ("Sept 2026", [{"kind": "date", "value": "2026-09"}]),
    ("founded in 2025", [{"kind": "date", "value": "2025"}]),
    ("v2.3", [{"kind": "version", "value": "2.3"}]),
    ("version 2.3", [{"kind": "version", "value": "2.3"}]),
    ("ver. 2.3", [{"kind": "version", "value": "2.3"}]),
    ("v3", [{"kind": "version", "value": "3"}]),
    ("2.3.1", [{"kind": "version", "value": "2.3.1"}]),
    ("Hooly Gemini 2.2", [{"kind": "version", "value": "2.2"}]),
    ("battery lasts 14 days", [{"kind": "duration", "value": 14, "unit": "day"}]),
    ("a 14-day trial", [{"kind": "duration", "value": 14, "unit": "day"}]),
    ("14days", [{"kind": "duration", "value": 14, "unit": "day"}]),
    ("two weeks", [{"kind": "duration", "value": 2, "unit": "week"}]),
    ("a two-week trial", [{"kind": "duration", "value": 2, "unit": "week"}]),
    ("for a fortnight", [{"kind": "duration", "value": 2, "unit": "week"}]),
    ("24 hours", [{"kind": "duration", "value": 24, "unit": "h"}]),
    ("24h", [{"kind": "duration", "value": 24, "unit": "h"}]),
    ("30 min", [{"kind": "duration", "value": 30, "unit": "min"}]),
    ("p95 latency 1.8 s", [{"kind": "duration", "value": 1.8, "unit": "s"}]),
    ("500 ms", [{"kind": "duration", "value": 500, "unit": "ms"}]),
    ("12 months", [{"kind": "duration", "value": 12, "unit": "month"}]),
    ("for a week", [{"kind": "duration", "value": 1, "unit": "week"}]),
    # not read
    ("12/03/2026", []), ("12.03.2026", []), ("March 12", []), ("Q4 2026", []), ("1.000.000 users", []),
    ("1,5 GB", []), ("99,9% uptime", []), ("1.500 mAh", []), ("about 10,000 customers", []), ("~10 GB", []),
    ("40 languages or so", []), ("10–20 GB", []), ("10 GB to 20 GB", []), ("between 10 and 20 GB", []),
    ("1 or 2 days", []), ("10m users", [{"kind": "quantity", "value": 10, "unit": "m"}]), ("2026 customers", []), ("half an hour", []),
    ("1,000 requests a day", []), ("5 pounds", []), ("over 10,000 customers", []),
    ("10,000 of our happy loyal customers", []), ("Hooly Gemini 11", []), ("99.6% uptime", [{"kind": "percent", "value": 99.6}]),
]


def main() -> int:
    bad = 0
    for text, want in CASES:
        got = vals(text)
        if got != want:
            bad += 1
            print("FAIL", repr(text), "got", got, "want", want)
    print(f"{len(CASES) - bad}/{len(CASES)} pass")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

