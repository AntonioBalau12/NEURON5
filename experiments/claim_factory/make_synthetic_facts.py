"""Builds a SMALL SYNTHETIC reconstructed-fact file to exercise --extra-facts (gates + corroboration rules).

These facts are test fixtures, NOT extractor output: the spans are arbitrary exact substrings of real row texts and the values
are taken from the existing verified store.  Any claim produced from this file is a test artefact and must not be submitted.

  py experiments/claim_factory/make_synthetic_facts.py [--out experiments/claim_factory/synthetic/synthetic_facts.jsonl]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from cf_common import LEXICON_JSON, PRACTICE_CSV, ROOT
from store import Params, Store

FULL = ROOT / "experiments" / "shared" / "data" / "full_input.csv"


def base(rows, rid, subject, attr, value, method, conf=0.95, **kw):
    r = rows[rid]
    text = r["text"]
    span = kw.pop("span", text[: min(len(text), 25)])
    start = text.index(span)
    d = {"extraction_id": f"{rid}#{method}#{kw.pop('n', 0)}", "source_row_id": rid, "source_label": r["label"],
         "source_publication_date": r["date"], "subject": subject, "subject_surface": subject, "attribute": attr,
         "relation_surface": attr, "value": value, "object_surface": None, "negated": False, "source_text_span": span,
         "span_start": start, "span_end": start + len(span), "fact_observation_date": None, "valid_from": None, "valid_to": None,
         "temporal_qualifier": None, "extraction_method": method, "extraction_confidence": conf, "parse_status": "complete",
         "verification_status": "candidate", "notes": "SYNTHETIC TEST FIXTURE"}
    d.update(kw)
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "synthetic" / "synthetic_facts.jsonl"))
    out = Path(ap.parse_args().out)
    rows = {r["id"]: r for r in csv.DictReader(FULL.open(encoding="utf-8-sig", newline=""))}
    store = Store(PRACTICE_CSV, LEXICON_JSON, Params())
    latest_true = sorted((r for r in rows.values() if r["label"] == "true"), key=lambda r: (r["date"], r["id"]))[-1]
    false_row = next(r for r in rows.values() if r["label"] == "false")
    facts: list[dict] = []
    # (1) a fact already in the form of its own row, read by two methods -> row_form + two_methods
    facts += [base(rows, "p-775", "Hooly Workspace", "price", {"kind": "money", "value": 199, "currency": "EUR", "per": "month"}, m, 0.93, span="Hooly Workspace costs €199 per month")
              for m in ("openie", "slot_filling")]
    # (2) stale keys refreshed by a later TRUE row, read by two methods -> two_methods
    stale = []
    for key in sorted(store.obs):
        r = store.asof_fact(key)
        if r.value is not None and r.volatile is False and any("stale" in x for x in r.reasons) and not r.blockers and r.last.clean and r.value.kind in ("quantity", "percent", "money", "duration"):
            stale.append((key, r))
    for key, r in stale[:4]:
        v = {"kind": r.value.kind, "value": r.value.value}
        for k in ("unit", "currency", "per"):
            if getattr(r.value, k) is not None:
                v[k] = getattr(r.value, k)
        for i, m in enumerate(("openie", "slot_filling")):
            facts.append(base(rows, latest_true["id"], key[0], key[1], v, m, 0.9, n=len(facts)))
    # (3) one method only, no cross-row support -> refused by corroboration
    key, r = stale[4] if len(stale) > 4 else stale[0]
    facts.append(base(rows, latest_true["id"], key[0], key[1], {"kind": r.value.kind, "value": r.value.value, **({"unit": r.value.unit} if r.value.unit else {})}, "openie", 0.99, n=99))
    # (4) refused fixtures, each one gate
    ref = "p-775"
    v199 = {"kind": "money", "value": 199, "currency": "EUR", "per": "month"}
    facts.append(base(rows, ref, "Hooly Workspace", "price", v199, "openie", 0.5, n=101))                                  # G3 low confidence
    facts.append(base(rows, ref, "Hooly Workspace", "price", v199, "openie", 0.95, n=102, parse_status="partial"))          # G2
    facts.append(base(rows, ref, "Hooly Workspace", "copilot_included", {"kind": "boolean", "value": False}, "openie", 0.95, n=103))  # G4 polarity vs negated flag
    facts.append(base(rows, false_row["id"], "Hooly Workspace", "price", v199, "openie", 0.95, n=104))                     # G5 false row
    facts.append(base(rows, ref, "Hooly Workspace", "price", {**v199, "op": "gt"}, "openie", 0.95, n=105))                  # G6 op
    facts.append(base(rows, ref, "Hooly Workspace", "price", v199, "openie", 0.95, n=106, valid_to="2026-05-01"))           # G6 validity end
    facts.append(base(rows, ref, "Hooly Workspace", "price", v199, "openie", 0.95, n=107, temporal_qualifier="was"))        # G6 qualifier
    f = base(rows, ref, "Hooly Workspace", "price", v199, "openie", 0.95, n=108)
    f["span_start"] += 1                                                                                                    # G1 span not exact
    facts.append(f)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in facts), encoding="utf-8")
    print(f"wrote {len(facts)} synthetic facts to {out} (stale keys used: {[k for k, _ in stale[:5]]}, latest true row {latest_true['id']} {latest_true['date']})")


if __name__ == "__main__":
    main()
