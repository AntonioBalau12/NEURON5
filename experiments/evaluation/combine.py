"""Combine the OpenIE and slot-filling fact files into `combined` fact files (several variants).

  py experiments/evaluation/combine.py                       # all variants, default input/output paths
  py experiments/evaluation/combine.py --variants union intersection
  py experiments/evaluation/combine.py --a path/openie.jsonl --b path/slot_filling.jsonl --out-dir some/dir

Inputs : A = experiments/openie/output/facts.jsonl, B = experiments/slot_filling/output/facts.jsonl
Outputs: <out-dir>/combined_<variant>_facts.jsonl  (+ .run_info.json), extraction_method = "combined"

Only MAPPED facts (parse_status != unmapped, subject+attribute+value set) are combined; unmapped records of the
inputs are dropped. Two facts are "the same" when (source_row_id, subject, attribute, value) have the same
identity under common.fact_key (units convert, names through the lexicon, op kept).

Variants (chosen before any real output existed; none is tuned on the evaluation set)
  union           every distinct fact of A and B. Same-fact pairs are merged (span = union of the two spans,
                  negated = A or B, temporal fields from the preferred side, confidence = max).
                  If the two sources give DIFFERENT values for the same (row, subject, attribute), all of those facts
                  are kept and flagged parse_status="ambiguous" with note "conflict". Maximises recall.
  union_resolved  like union, but a cross-source conflicted slot keeps ONE fact: (1) the fact both agree on,
                  else (2) the better parse_status (complete > partial > ambiguous), (3) higher extraction_confidence,
                  (4) slot_filling (B) over openie (A). Other facts of that slot are dropped. One value per slot.
  intersection    only facts extracted by both sources (same identity). High precision, recall limited by the weaker
                  source.

Confidence is an extractor-internal score, never evidence of truth. The combiner does not use labels, gold forms or
the evaluation set.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

VARIANTS = ("union", "union_resolved", "intersection")
STATUS_RANK = {"complete": 3, "partial": 2, "ambiguous": 1, "unmapped": 0}
SOURCES = ("openie", "slot_filling")      # index 0 = A, index 1 = B


def is_mapped(fact: dict[str, Any]) -> bool:
    return fact.get("parse_status") != "unmapped" and None not in (fact.get("subject"), fact.get("attribute"), fact.get("value"))


def fkey(fact: dict[str, Any]):
    return C.fact_key(fact["subject"], fact["attribute"], fact["value"])


def slot(fact: dict[str, Any]):
    return (fact["source_row_id"], C.canonical_subject(fact["subject"]), fact["attribute"])


def preference(item: dict[str, Any]) -> tuple:
    """Higher is better: agreement, parse status, confidence, source (slot_filling over openie)."""
    f = item["fact"]
    return (len(item["sources"]), STATUS_RANK.get(f["parse_status"], 0), float(f["extraction_confidence"]),
            1 if "slot_filling" in item["sources"] else 0)


def merge_items(a: dict[str, Any], b: dict[str, Any], text: str) -> dict[str, Any]:
    """Merge the same fact seen by both sources. `a` and `b` are items {fact, sources, notes}."""
    primary, secondary = (a, b) if preference(a) >= preference(b) else (b, a)
    p, s = dict(primary["fact"]), secondary["fact"]
    start, end = min(p["span_start"], s["span_start"]), max(p["span_end"], s["span_end"])
    p.update({"span_start": start, "span_end": end, "source_text_span": text[start:end]})
    p["negated"] = bool(p["negated"] or s["negated"])
    for name in ("fact_observation_date", "valid_from", "valid_to", "temporal_qualifier", "relation_surface", "object_surface",
                 "subject_surface"):
        if p.get(name) in (None, "") and s.get(name) not in (None, ""):
            p[name] = s[name]
    p["extraction_confidence"] = max(float(p["extraction_confidence"]), float(s["extraction_confidence"]))
    if STATUS_RANK.get(s["parse_status"], 0) > STATUS_RANK.get(p["parse_status"], 0):
        p["parse_status"] = s["parse_status"]
    notes = ["agree"]
    if a["fact"]["negated"] != b["fact"]["negated"]:
        notes.append("negation_disagreement(A=%s,B=%s)" % (a["fact"]["negated"], b["fact"]["negated"]))
    return {"fact": p, "sources": sorted(set(a["sources"]) | set(b["sources"])), "notes": notes}


def combine_row(row_id: str, text: str, a_facts: list[dict[str, Any]], b_facts: list[dict[str, Any]],
                variant: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Combine one row. Returns (items, stats)."""
    stats = defaultdict(int)
    by_key: dict[Any, dict[str, Any]] = {}
    for src, facts in ((SOURCES[0], a_facts), (SOURCES[1], b_facts)):
        for f in facts:
            item = {"fact": f, "sources": [src], "notes": [f"only_{src}"]}
            k = fkey(f)
            if k is None:
                continue
            if k in by_key:
                if src in by_key[k]["sources"]:       # duplicate inside one source: keep the first
                    stats["duplicates_inside_source"] += 1
                    continue
                by_key[k] = merge_items(by_key[k], item, text)
            else:
                by_key[k] = item
    items = list(by_key.values())
    agreed = [i for i in items if len(i["sources"]) == 2]
    stats["agree"] += len(agreed)
    stats["only_openie"] += sum(1 for i in items if i["sources"] == ["openie"])
    stats["only_slot_filling"] += sum(1 for i in items if i["sources"] == ["slot_filling"])

    slots: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for i in items:
        slots[slot(i["fact"])].append(i)
    conflicted = {s for s, group in slots.items()
                  if len({src for i in group for src in i["sources"]}) == 2
                  and not any(len(i["sources"]) == 2 for i in group)}
    # a slot is in conflict when both sources say something about it but they never state the same value
    stats["conflicted_slots"] += len(conflicted)

    if variant == "intersection":
        return agreed, dict(stats)
    out: list[dict[str, Any]] = []
    for s, group in slots.items():
        if s in conflicted:
            if variant == "union_resolved":
                best = max(group, key=preference)
                best["notes"] = best["notes"] + [f"conflict_resolved_over={len(group) - 1}_other"]
                out.append(best)
                stats["dropped_by_resolution"] += len(group) - 1
            else:
                for i in group:
                    i["notes"] = i["notes"] + ["conflict"]
                    i["fact"] = dict(i["fact"], parse_status="ambiguous")
                    out.append(i)
        else:
            out.extend(group)
    return out, dict(stats)


def to_record(item: dict[str, Any], row_id: str, variant: str, n: int) -> dict[str, Any]:
    f = dict(item["fact"])
    f["extraction_id"] = f"{row_id}#combined_{variant}#{n}"
    f["extraction_method"] = "combined"
    f["verification_status"] = "candidate"
    f["notes"] = ("variant=%s; sources=%s; %s; inputs: %s" % (variant, "+".join(item["sources"]), ",".join(item["notes"]),
                                                              (item["fact"].get("notes") or "")[:120])).strip()
    return f


def combine(a_all: list[dict[str, Any]], b_all: list[dict[str, Any]], rows: dict[str, dict[str, str]],
            variant: str) -> tuple[list[dict[str, Any]], dict[str, int]]:
    ga, gb = defaultdict(list), defaultdict(list)
    for f in a_all:
        if is_mapped(f):
            ga[f["source_row_id"]].append(f)
    for f in b_all:
        if is_mapped(f):
            gb[f["source_row_id"]].append(f)
    out: list[dict[str, Any]] = []
    total = defaultdict(int)
    for row_id in rows:
        if row_id not in ga and row_id not in gb:
            continue
        items, stats = combine_row(row_id, rows[row_id]["text"], ga.get(row_id, []), gb.get(row_id, []), variant)
        for k, v in stats.items():
            total[k] += v
        items.sort(key=lambda i: (i["fact"]["span_start"], i["fact"]["span_end"], i["fact"]["attribute"]))
        out.extend(to_record(i, row_id, variant, n) for n, i in enumerate(items))
    return out, dict(total)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default=str(C.METHOD_FILES["openie"]), help="OpenIE facts.jsonl")
    ap.add_argument("--b", default=str(C.METHOD_FILES["slot_filling"]), help="slot-filling facts.jsonl")
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    ap.add_argument("--out-dir", default=str(C.OUTPUT_DIR))
    ap.add_argument("--overwrite", action="store_true", help="replace existing combined_* files (they are derived data)")
    args = ap.parse_args()

    missing = [p for p in (args.a, args.b) if not Path(p).exists()]
    if missing:
        print("cannot combine, input facts file(s) missing:", *missing, sep="\n  ")
        return 2
    rows = C.fact_schema.load_input_rows()
    a_all, info_a = C.load_facts(args.a, rows)
    b_all, info_b = C.load_facts(args.b, rows)
    print(f"A (openie)       : {info_a['valid']} valid / {info_a['lines']} lines, {info_a['invalid']} invalid dropped")
    print(f"B (slot_filling) : {info_b['valid']} valid / {info_b['lines']} lines, {info_b['invalid']} invalid dropped")
    for variant in args.variants:
        out_path = Path(args.out_dir) / f"combined_{variant}_facts.jsonl"
        if out_path.exists() and not args.overwrite:
            print(f"{out_path} exists; pass --overwrite to regenerate it")
            continue
        facts, stats = combine(a_all, b_all, rows, variant)
        n = C.dump_jsonl(out_path, facts)
        report = C.fact_schema.validate_file(out_path, rows)
        info = {"variant": variant, "inputs": {"a": str(args.a), "b": str(args.b)}, "input_info": {"a": info_a, "b": info_b},
                "combined_facts": n, "schema_report": {k: v for k, v in report.items() if k != "examples"},
                "schema_examples": report["examples"][:5], "stats": stats}
        Path(str(out_path) + ".run_info.json").write_text(json.dumps(info, indent=1, default=str), encoding="utf-8")
        print(f"{variant:15s} -> {n} facts ({out_path.name}); invalid by schema: {report['invalid']}; stats {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
