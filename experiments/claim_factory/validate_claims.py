"""Stand-alone validation of a claims table (official CSV shape) produced by generate_claims.py or anything else.

  py experiments/claim_factory/validate_claims.py --claims experiments/claim_factory/output/run_x/claims_valid.csv
         [--provenance .../provenance.jsonl] [--report out.json] [--change-rule engine|corroborated]
         [--relation-rule engine|stable] [--max-age-days 14] [--min-support-rows 1]

Four independent layers (none trusts the generator):
  1. foundation.validate_output (the repository's official validator) on the table;
  2. per claim: entry.schema.json, lexicon names/attributes, foundation.validate_claim_text AND textcheck.py (own re-implementation
     of the key rules: single sentence, whole-word subject with the Hooly / Hooly AI Pro pitfall, no negation, no second value of the
     same kind, no date/time word, value rendered exactly as value-forms.md reads it, yes/no attribute words, compare phrase order);
  3. novelty (text is not an input row text) and duplicates (id, text, semantic key);
  4. truth re-check from the evidence store (core.graph + the as-of rule), starting from the claim only.
Exit code 0 only when all four layers are clean.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cf_common import CONTRACT_DIR, LEXICON_JSON, PRACTICE_CSV, ROOT  # noqa: E402
import foundation  # noqa: E402
from foundation import SchemaValidator, TypedValue, _claim_semantic_key, _validate_form_names, compare_values, validate_claim_text  # noqa: E402
from core.graph import EvidenceState  # noqa: E402
import textcheck  # noqa: E402
from observations import same_value  # noqa: E402
from rules import _clean_rows, _event_date_state  # noqa: E402
from store import Params, Store, load_novelty_texts, norm_text  # noqa: E402

FULL_INPUT = ROOT / "experiments" / "shared" / "data" / "full_input.csv"


def reverify(store: Store, ctype: str, form: dict, p: Params) -> list[str]:
    """Return the reasons a claim is NOT supported by the evidence store (empty = supported)."""
    def tv(raw):
        v, err = TypedValue.parse(raw)
        return v if not err else None

    def key(subject, attr):
        e = store.lexicon.resolve(str(subject))
        return (e.name, attr) if e else (str(subject), attr)

    out: list[str] = []
    if ctype == "fact":
        k = key(form["subject"], form["attribute"])
        r = store.asof_fact(k)
        v = tv(form["value"])
        if not r.accepted or r.value is None:
            out += ["as_of_rule:" + x for x in r.reasons] or ["as_of_rule:rejected"]
        elif v is None or compare_values(r.value, v, "eq") is not True and not same_value(r.value, v):
            out.append("value_differs_from_latest_supported_value")
    elif ctype == "compare":
        sides = []
        for side in ("left", "right"):
            k = key(form[side]["subject"], form[side]["attribute"])
            r = store.asof_fact(k)
            if not r.accepted or r.value is None:
                out += [f"as_of_rule[{side}]:" + x for x in r.reasons] or [f"as_of_rule[{side}]:rejected"]
            sides.append(r.value)
        if not out and sides[0] is not None and sides[1] is not None and compare_values(sides[0], sides[1], form["op"]) is not True:
            out.append("comparison_not_established_by_values")
    elif ctype == "change":
        status, _ = store.engine_status("change", form)
        if status != EvidenceState.VERIFIED_SUPPORT.value:
            if p.change_rule != "corroborated":
                out.append("engine_change_candidate_only")
            else:
                k = key(form["subject"], form["attribute"])
                sup = store.support(k)
                fv, tvv = tv(form["from"]), tv(form["to"])
                pairs = store.temporal.get_temporal_changes(form["subject"], form["attribute"])
                if not any(compare_values(c.from_value, fv, "eq") is True and compare_values(c.to_value, tvv, "eq") is True for c in pairs):
                    out.append("not_a_temporal_index_change_pair")
                need = lambda v: 1 if (v.kind == "date" and isinstance(v.value, str) and len(v.value) == 10) else 2
                if fv is not None and len(_clean_rows(sup, fv)) < need(fv):
                    out.append("from_endpoint_uncorroborated")
                if tvv is not None and len(_clean_rows(sup, tvv)) < need(tvv):
                    out.append("to_endpoint_uncorroborated")
    elif ctype == "at_event":
        status, why = store.engine_status("at_event", form)
        if status != EvidenceState.VERIFIED_SUPPORT.value:
            out.append(f"engine_at_event:{status}")
        e = store.lexicon.resolve(form["event"])
        day, _, reasons = _event_date_state(store, e.name) if e else (None, [], ["unknown_event"])
        if day is None:
            out += ["event_date:" + x for x in reasons]
        else:
            k = key(form["subject"], form["attribute"])
            v = tv(form["value"])
            on_day = [o for o in store.support(k) if o.on.isoformat() == day and o.clean and v is not None and same_value(o.value, v)]
            if not on_day:
                out.append("no_clean_verified_observation_of_the_fact_on_the_event_day")
    elif ctype == "relation":
        status, why = store.engine_status("relation", form)
        if status != EvidenceState.VERIFIED_SUPPORT.value:
            if p.relation_rule != "stable":
                out.append("engine_relation:" + status)
            else:
                k = key(form["target"], form["attribute"])
                r = store.asof_fact(k)
                if not r.accepted:
                    out += ["target_fact:" + x for x in r.reasons]
    return out


def validate(claims_csv: Path, p: Params, provenance: Path | None, report_path: Path | None) -> dict:
    t0 = time.perf_counter()
    store = Store(PRACTICE_CSV, LEXICON_JSON, p)
    t_store = time.perf_counter() - t0
    data = foundation.load_inputs(PRACTICE_CSV, LEXICON_JSON)
    rows = list(csv.DictReader(claims_csv.open(encoding="utf-8-sig", newline="")))
    n = len(rows)
    t1 = time.perf_counter()
    official_n = foundation.validate_output(claims_csv, data, CONTRACT_DIR, expected_claims=n)
    official_1000 = foundation.validate_output(claims_csv, data, CONTRACT_DIR, expected_claims=1000)
    t_official = time.perf_counter() - t1

    entry_validator = SchemaValidator(CONTRACT_DIR / "entry.schema.json")
    novelty = load_novelty_texts([x for x in (PRACTICE_CSV, FULL_INPUT) if x.is_file()])
    seen_text: set[str] = set()
    seen_key: set = set()
    seen_id: set[str] = set()
    per_claim: list[dict] = []
    layer = Counter()
    by_type = Counter()
    t2 = time.perf_counter()
    for r in rows:
        probs: list[str] = []
        ctype = r["type"]
        by_type[ctype] += 1
        try:
            form = json.loads(r["form"])
        except json.JSONDecodeError:
            per_claim.append({"id": r["id"], "problems": ["form_not_json"]})
            layer["form_not_json"] += 1
            continue
        if r["id"] in seen_id:
            probs.append("duplicate_id")
        seen_id.add(r["id"])
        if (r.get("label") or "true").strip().lower() != "true":
            probs.append("label_not_true")
        conf = float(r["confidence"]) if r.get("confidence") else None
        entry = {"id": r["id"], "type": ctype, "text": r["text"], "form": form, "tag": "true", "confidence": conf if conf is not None else 0}
        probs += [f"schema:{e}" for e in entry_validator.validate(entry)]
        lex: list[str] = []
        _validate_form_names(ctype, form, store.lexicon, 0, lex)
        probs += [f"lexicon:{e}" for e in lex]
        table = "amount"
        if ctype == "compare":
            ks = [store.lexicon.resolve(form["left"]["subject"]), form["left"]["attribute"]]
            sv = store.support((ks[0].name, ks[1])) if ks[0] else []
            table = "date" if sv and sv[-1].value.kind == "date" else "amount"
        probs += [f"text_independent:{c}: {m}" for c, m in textcheck.check_text(ctype, r["text"], form, store.names, table)]
        probs += [f"text_foundation:{m}" for m in validate_claim_text(ctype, r["text"], form, store.lexicon)]
        nt = norm_text(r["text"])
        if nt in novelty:
            probs.append("novelty:text_equals_an_input_row")
        if nt in seen_text:
            probs.append("dedup:duplicate_text")
        seen_text.add(nt)
        k = _claim_semantic_key(ctype, form, store.lexicon)
        if k is not None and k in seen_key:
            probs.append("dedup:semantic_duplicate")
        if k is not None:
            seen_key.add(k)
        truth = reverify(store, ctype, form, p)
        probs += [f"evidence:{x}" for x in truth]
        for pr in probs:
            layer[pr.split(":")[0]] += 1
        per_claim.append({"id": r["id"], "type": ctype, "problems": probs})
    t_claims = time.perf_counter() - t2

    prov_report = None
    if provenance and provenance.is_file():
        practice = {x["id"]: x for x in csv.DictReader(PRACTICE_CSV.open(encoding="utf-8-sig", newline=""))}
        have = {}
        for line in provenance.open(encoding="utf-8"):
            d = json.loads(line)
            have[d["claim_id"]] = d
        missing = [r["id"] for r in rows if r["id"] not in have]
        bad_rows = 0
        no_support = 0
        for cid, d in have.items():
            ids = _row_ids(d["evidence"])
            if not ids:
                no_support += 1
            for rid in ids:
                if rid not in practice:
                    bad_rows += 1
        prov_report = {"claims_without_provenance": missing, "claims_with_no_supporting_row_id": no_support,
                       "provenance_row_ids_not_in_practice_csv": bad_rows}
    bad = [c for c in per_claim if c["problems"]]
    report = {
        "claims": n, "by_type": dict(by_type), "claims_with_any_problem": len(bad),
        "problem_layers": dict(layer),
        "official_validate_output_expected_n": {"expected_claims": n, "problems": official_n[:40], "n_problems": len(official_n)},
        "official_validate_output_expected_1000": {"n_problems": len(official_1000), "first": official_1000[:3]},
        "provenance": prov_report,
        "params": {"min_support_rows": p.min_support_rows, "max_age_days": p.max_age_days, "change_rule": p.change_rule,
                   "relation_rule": p.relation_rule, "block_on_false_candidates": p.block_on_false_candidates},
        "timing_s": {"store_build": round(t_store, 2), "official_validate_output": round(t_official, 2), "per_claim_layers": round(t_claims, 2),
                     "total": round(time.perf_counter() - t0, 2)},
        "problem_examples": bad[:25],
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _row_ids(ev) -> set[str]:
    ids: set[str] = set()
    if isinstance(ev, dict):
        for k, v in ev.items():
            if k == "row_id" and isinstance(v, str):
                ids.add(v)
            elif k in ("evidence_ids", "fact_rows") and isinstance(v, list):
                ids.update(x for x in v if isinstance(x, str))
            else:
                ids |= _row_ids(v)
    elif isinstance(ev, list):
        for x in ev:
            ids |= _row_ids(x)
    return ids


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claims", required=True)
    ap.add_argument("--provenance", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--change-rule", default="engine", choices=["engine", "corroborated"])
    ap.add_argument("--relation-rule", default="engine", choices=["engine", "stable"])
    ap.add_argument("--max-age-days", type=int, default=14)
    ap.add_argument("--min-support-rows", type=int, default=1)
    ap.add_argument("--no-block-on-false-candidates", action="store_true")
    ap.add_argument("--allow-unlisted-names", action="store_true")
    a = ap.parse_args(argv)
    p = Params(min_support_rows=a.min_support_rows, max_age_days=a.max_age_days, change_rule=a.change_rule, relation_rule=a.relation_rule,
               block_on_false_candidates=not a.no_block_on_false_candidates, allow_unlisted_names=a.allow_unlisted_names)
    rep = validate(Path(a.claims), p, Path(a.provenance) if a.provenance else None, Path(a.report) if a.report else None)
    print(json.dumps({k: rep[k] for k in ("claims", "by_type", "claims_with_any_problem", "problem_layers", "provenance", "timing_s")}, indent=2))
    print("official validate_output (expected_claims=n): problems =", rep["official_validate_output_expected_n"]["n_problems"],
          "| (expected_claims=1000): problems =", rep["official_validate_output_expected_1000"]["n_problems"])
    for ex in rep["problem_examples"][:10]:
        print("  PROBLEM", ex["id"], ex["problems"][:3])
    clean = rep["claims_with_any_problem"] == 0 and rep["official_validate_output_expected_n"]["n_problems"] == 0
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
