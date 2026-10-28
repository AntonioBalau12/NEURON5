"""Offline schema-guided slot filling: Hooly sentence text -> canonical (subject, attribute, typed value) candidates.

  py experiments/slot_filling/extract_slots.py --input experiments/shared/data/full_input.csv \
      --lexicon data/lexicon.json --out experiments/slot_filling/output/facts.jsonl

Input per row: id, text, date (label is only copied through as source_label). The gold ``form`` is never read.
Everything is a ``candidate``; nothing is verified.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from engine import analyse_row  # noqa: E402
from linking import Lexicon  # noqa: E402
from model import Model, gaz_for, load  # noqa: E402
from pipeline import cue_words, generate, run_selection, score_groups, span_for, temporal_for  # noqa: E402
from values import CLAUSE_END, NEGATION_WORDS, COMPARISON_NEG, clause_bounds  # noqa: E402

DEFAULT_THR = {"default": 0.5}
T_COMPLETE = 0.6
SUPPRESS_COUNTERS: dict = {}


def clause_negated(text: str, pos: int) -> bool:
    a, b = clause_bounds(text, pos)
    return bool(NEGATION_WORDS.search(COMPARISON_NEG.sub(" ", text[a:b])))


def extract_row(row: dict, model: Model, lex: Lexicon, thr: dict, counters=None):
    text = row["text"]
    infos = analyse_row(text, lex, gaz_for(model.gaz), model.units)
    cands = generate(text, infos, lex, model.profile)
    score_groups(cands, model.lr)
    chosen = run_selection(cands, thr)
    chosen.sort(key=lambda c: (c.vm.start, -c.p))
    if counters is not None:
        for si in infos:
            for vm in si.vms:
                if vm.suppressed:
                    counters[vm.suppressed] = counters.get(vm.suppressed, 0) + 1
    date_vms = [vm for si in infos for vm in si.vms if vm.kind == "date"]
    # a date that only serves as 'as of / until / since' validity for another fact in its sentence is not a value
    nondate_sent = {(c.si.start) for c in chosen if c.vm.kind != "date"}
    facts, seen = [], {}
    for c in chosen:
        before = text[max(c.si.start, c.vm.start - 10):c.vm.start]
        if c.vm.kind == "date" and c.si.start in nondate_sent and re.search(r"\b(?:as of|until|till|through|since|from)\s*$", before, re.I):
            continue
        key = (c.ent.canon, c.attr, json.dumps(c.value, sort_keys=True))
        if key in seen and seen[key] >= c.p:
            continue
        seen[key] = c.p
        a, b = span_for(c, text)
        q, obs, vf, vt, tnotes = temporal_for(c, text, date_vms)
        neg = c.negated if c.vm.kind == "boolean" else clause_negated(text, c.vm.start)
        notes = [f"rule=slot_profile/{c.vm.kind}", f"vm_rule={c.vm.rule}"]
        if c.vm.kind == "name":
            notes.append(f"name_src={c.vm.name_src}")
        if c.vm.op:
            notes.append(f"op={c.vm.op} from comparison words in text")
        if len(c.vm.readings) > 1:
            notes.append("counted_noun_readings=" + "|".join(r.get("unit", "") for r in c.vm.readings))
        if any(p >= c.vm.clause[0] and p < c.vm.start for si in infos for p in si.pronoun_pos) and not (
                c.vm.clause[0] <= c.ent.start and c.ent.end <= c.vm.clause[1]):
            notes.append("pronoun_same_sentence")
        if neg and c.vm.kind != "boolean":
            notes.append("negation_in_clause_after_value")
        notes += tnotes
        notes.append(f"p={c.p:.3f}")
        notes.append("subject_alias" if c.ent.surface.lower() != c.ent.canon.lower() else "subject_canonical")
        status = "complete"
        if c.runner:
            status = "ambiguous"
            notes.append("runner_up=%s/%s" % c.runner)
        elif c.p < T_COMPLETE or c.features.get("cold") or (c.vm.kind == "name" and c.vm.name_src == "unknown") \
                or (c.vm.kind == "quantity" and c.features.get("sub_p", 1) < 0.2 and not c.features.get("unit_in_name")):
            status = "partial"
        if "pronoun_same_sentence" in notes and status == "complete":
            status = "ambiguous" if len({e.canon for e in c.si.ents}) > 1 else "complete"
        facts.append({
            "extraction_id": f"{row['id']}#slot#{len(facts)}",
            "source_row_id": row["id"],
            "source_label": row.get("label", ""),
            "source_publication_date": row.get("date", ""),
            "subject": c.ent.canon,
            "subject_surface": text[c.ent.start:c.ent.end],
            "attribute": c.attr,
            "relation_surface": cue_words(c, model.profile, text),
            "value": c.value,
            "object_surface": text[c.vm.start:c.end] if c.vm.kind != "boolean" else text[c.vm.clause[0]:c.vm.clause[1]].strip(),
            "negated": bool(neg),
            "source_text_span": text[a:b],
            "span_start": a,
            "span_end": b,
            "fact_observation_date": obs,
            "valid_from": vf,
            "valid_to": vt,
            "temporal_qualifier": q,
            "extraction_method": "slot_filling",
            "extraction_confidence": round(min(c.p, 0.99), 3),
            "parse_status": status,
            "verification_status": "candidate",
            "notes": "; ".join(notes),
        })
    return facts


def load_thresholds(model_dir: Path):
    p = model_dir / "thresholds.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return dict(DEFAULT_THR)


def read_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def mapped_csv(facts, path):
    cols = ["extraction_id", "source_row_id", "source_label", "subject", "attribute", "value_kind", "value", "unit_or_currency",
            "per", "op", "negated", "confidence", "parse_status", "temporal_qualifier", "fact_observation_date",
            "valid_from", "valid_to", "source_publication_date", "span_start", "span_end", "source_text_span", "notes"]
    with Path(path).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for f in facts:
            v = f["value"]
            w.writerow([f["extraction_id"], f["source_row_id"], f["source_label"], f["subject"], f["attribute"], v["kind"],
                        v["value"], v.get("unit") or v.get("currency") or "", v.get("per", ""), v.get("op", ""),
                        f["negated"], f["extraction_confidence"], f["parse_status"], f["temporal_qualifier"] or "",
                        f["fact_observation_date"] or "", f["valid_from"] or "", f["valid_to"] or "",
                        f["source_publication_date"], f["span_start"], f["span_end"], f["source_text_span"], f["notes"]])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--lexicon", default=str(HERE.parents[1] / "data" / "lexicon.json"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=str(HERE / "model"))
    ap.add_argument("--min-confidence", type=float, default=None, help="override every threshold")
    ap.add_argument("--csv", default=None, help="mapped CSV path (default: facts_mapped.csv beside --out)")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    lex = Lexicon(args.lexicon)
    model = load(Path(args.model))
    thr = load_thresholds(Path(args.model))
    if args.min_confidence is not None:
        thr = {k: args.min_confidence for k in thr}
    rows = read_rows(args.input)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    counters: dict = {}
    n = 0
    all_facts = []
    t1 = time.perf_counter()
    with out.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            for f in extract_row(row, model, lex, thr, counters):
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
                all_facts.append(f)
                n += 1
    t2 = time.perf_counter()
    mapped_csv(all_facts, Path(args.csv) if args.csv else out.with_name("facts_mapped.csv"))
    print(json.dumps({"rows": len(rows), "facts": n, "load_s": round(t1 - t0, 2), "extract_s": round(t2 - t1, 2),
                      "rows_per_s": round(len(rows) / max(t2 - t1, 1e-9), 1), "suppressed_mentions": counters}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
