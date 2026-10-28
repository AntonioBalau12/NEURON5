"""Joins output/extras_review_input.jsonl with the manual verdicts below -> output/extras_review.csv.

Verdicts are the author's own reading of each sentence (not an independent evaluation). Order = line order of the input file
(selfcheck_dev.py: all 46 out-of-fold extras + wrong-value predictions; fixed-seed sample size 60 exceeds the population,
so the whole population was reviewed).
"""
import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "output"
C, I, U = "correct", "incorrect", "uncertain"
V = {
    0: (C, "'joined Hooly as CTO': cto = Bertram Gilfoil is stated"),
    1: (C, "AI answers are said to exist in Hooly Search"),
    2: (C, "380 employees stated; the form attached it to the Q4 results entity, text says Hooly"),
    3: (C, "'Hooly Android 16.1' is a version of Hooly Android"),
    4: (C, "'Hooly Android 17.0' is a version of Hooly Android"),
    5: (C, "'Hooly raises ... Series A' supports raised_series_a"),
    6: (C, "'who chairs the Hooly Board' = chair is Peter Gregori (inverse of the form's chairs)"),
    7: (C, "'560 customers on paid plans' = paying_customers"),
    8: (I, "forward guidance for next quarter's revenue, not annual recurring revenue"),
    9: (C, "'Nelson Bighettie leads Hooly Jules'"),
    10: (C, "'raised ... in its Series A' supports raised_series_a"),
    11: (I, "customers belong to Hooly Workspace Enterprise, not Hooly (wrong subject; parse_status was ambiguous)"),
    12: (I, "200,000 tokens per chat is a context size; 'chat' read as the counted unit"),
    13: (I, "'can reach 250 seats' is a maximum, not included seats"),
    14: (I, "'ceiling of 100 seats' is a maximum, not included seats"),
    15: (I, "2025-01-14 is the founding date, nothing about a SOC 2 audit"),
    16: (I, "128,000 tokens is the session/context size, not output length"),
    17: (I, "verb 'covers' read as a counted noun 'cover' (value 1)"),
    18: (I, "up to EUR 200 is trade-in credit, not the device price"),
    19: (I, "Dublin is listed with Frankfurt; 'primary' is not stated"),
    20: (U, "Frankfurt is listed first among two regions; 'primary' is not stated"),
    21: (C, "'Richard Hendrix as the CTO'"),
    22: (I, "'admits 250 seats' is a maximum, not included seats"),
    23: (I, "'in a month' read as a one-month trial"),
    24: (C, "'On 24 March 2026 ... we launched Hooly Gemini 2.0'"),
    25: (I, "EUR 15 is the price of each further seat, not the plan price"),
    26: (I, "'two people' counted as the extra seat price"),
    27: (U, "memory saver is named only as a condition ('when memory saver is active')"),
    28: (I, "'next two years' read as a value of raised_series_b; the sentence negates the Series B"),
    29: (I, "85 speakers is not customers in the EU"),
    30: (I, "'5 regions in service': 'service' read as the counted noun"),
    31: (I, "Gavin Bellson founded Hooly; Lisbon is the headquarters"),
    32: (C, "'Android 17.0' is a version of Hooly Android (alias)"),
    33: (I, "retention period, nothing about encryption"),
    34: (I, "EUR 15 is the price of each further seat, not the plan price"),
    35: (U, "'shipped on' a release date: a launch of the product is not stated"),
    36: (C, "'Hooly Chrome 69.0 brings an AI sidebar'"),
    37: (I, "Frankfurt is the city, not the host"),
    38: (U, "'hosted at Rheinhalle' could be read as host/venue; the host organisation is not given"),
    39: (C, "'Hooly Android 16.1' is a version of Hooly Android"),
    40: (U, "a trade-in credit implies a trade-in programme but does not state it"),
    41: (I, "the 2 independent members belong to the Board; Peter Gregori is only the speaker label"),
    42: (I, "'It runs an audit committee': the speaker does not chair it"),
    43: (I, "'engineering' is not in the sentence; roles are not typed"),
    44: (I, "Hoovar is the speaker label; 34 employees belong to the Berlin office"),
    45: (I, "Hoovar is the speaker label; the 30 desks belong to the Berlin office"),
}

rows = [json.loads(l) for l in (OUT / "extras_review_input.jsonl").open(encoding="utf-8")]
assert len(rows) == len(V), (len(rows), len(V))
with (OUT / "extras_review.csv").open("w", encoding="utf-8", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["n", "row_id", "category", "text", "pred_subject", "pred_attribute", "pred_value", "confidence",
                "parse_status", "verdict", "reason"])
    for i, d in enumerate(rows):
        p = d["pred"]
        v, why = V[i]
        w.writerow([i, d["row"], d["category"], d["text"], p["subject"], p["attribute"], json.dumps(p["value"]),
                    p["extraction_confidence"], p["parse_status"], v, why])
from collections import Counter
print(Counter(v for v, _ in V.values()))
