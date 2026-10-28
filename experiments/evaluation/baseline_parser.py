"""Leak-free wrapper of the existing deterministic parser core/graph/parsing.py TextFactParser.

  py experiments/evaluation/baseline_parser.py [--input FULL_INPUT.csv] [--out output/baseline_facts.jsonl]

Why a wrapper: core/graph/builder.py (and diagnostics.py) derive the parser's `attribute_kinds`
(attribute -> value kind hint) and `known_units` (counted nouns/units) from the GOLD forms of every
row. For held-out rows that leaks gold information into the baseline. This wrapper builds both
ONLY from the DEV split rows (experiments/shared/data/dev_rows.csv), which every method may use for
tuning. Held-out gold (experiments/shared/_heldout) is never opened.

Input is runtime-shaped: only id,text,date,label are read from the input CSV (any `form` column is ignored).
Output: the common fact format (experiments/shared/EXCHANGE_FORMAT.md), extraction_method=deterministic_parser.
Rows with no extracted fact produce no record; `<out>.run_info.json` lists them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
from foundation import SchemaValidator, TypedValue, parse_evidence_form  # noqa: E402
from core.graph.parsing import (TextFactParser, _attribute_mentions, _entity_mentions,  # noqa: E402
                                _value_spans)

METHOD = "deterministic_parser"


def dev_priors(dev_csv: Path = C.DEV_ROWS) -> tuple[dict[str, str], set[str], int]:
    """attribute_kinds and known_units from DEV rows only (mirrors builder.py but without held-out rows)."""
    split = json.loads(C.SPLIT_JSON.read_text(encoding="utf-8"))
    heldout_ids = set(split["heldout_ids"])
    validator = SchemaValidator(C.ROOT / "contracts" / "claimed_value.schema.json")
    kinds: dict[str, str] = {}
    units: set[str] = set()
    n = 0
    lex = C.lexicon()
    for row in C.read_csv(dev_csv):
        if row["id"] in heldout_ids:
            raise RuntimeError(f"held-out row {row['id']} found in dev file: refusing to use it")
        facts, _ = parse_evidence_form(row["form"], validator)
        n += 1
        for fact in facts:
            entity = lex.resolve(fact.subject)
            if entity is None or fact.attribute not in entity.attributes:
                continue
            kinds.setdefault(fact.attribute, fact.value.kind)
            if fact.value.kind in {"quantity", "duration"} and fact.value.unit:
                units.add(fact.value.unit)
    return kinds, units, n


def value_to_dict(value: TypedValue) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": value.kind, "value": value.value}
    for key in ("unit", "currency", "per", "op"):
        item = getattr(value, key)
        if item is not None:
            out[key] = item
    return out


def _find_support(text: str, mentions, spans, fact, lexicon) -> tuple[int, int, str | None, str | None]:
    """Locate (span_start, span_end, relation_surface, object_surface) for a parser fact."""
    entity_spans = [(a, b) for a, b, e in mentions
                    if e.name == fact.subject and text[a:b] == (fact.subject_spelling or text[a:b])]
    entity_spans = entity_spans or [(a, b) for a, b, e in mentions if e.name == fact.subject]
    if not entity_spans:
        return 0, len(text), None, None
    ea, eb = entity_spans[0]
    entity = lexicon.resolve(fact.subject)
    attr_cands = [(a, b) for a, b, name, _ in _attribute_mentions(text, entity) if name == fact.attribute] if entity else []
    value_cands = [(s.start, s.end) for s in spans if s.value.key() == fact.value.key()
                   and not (s.value.kind == "name" and (s.start, s.end) in entity_spans)]
    obj = None
    rel = None
    lo, hi = ea, eb
    if value_cands:
        va, vb = min(value_cands, key=lambda s: max(0, s[0] - eb, ea - s[1]))
        lo, hi = min(lo, va), max(hi, vb)
        obj = text[va:vb]
    if attr_cands:
        aa, ab = min(attr_cands, key=lambda s: max(0, s[0] - eb, ea - s[1]))
        lo, hi = min(lo, aa), max(hi, ab)
        rel = text[aa:ab]
    if obj is None and fact.value.kind != "boolean":
        return lo, hi, rel, None
    if hi - lo < 1:
        return 0, len(text), rel, obj
    return lo, hi, rel, obj


def extract_rows(rows: list[dict[str, str]], parser: TextFactParser) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lex = C.lexicon()
    all_rows = {r["id"]: r for r in rows}
    facts_out: list[dict[str, Any]] = []
    no_fact_rows: list[str] = []
    downgraded = 0
    for row in rows:
        text = row["text"]
        result = parser.parse(text)
        if not result.facts:
            no_fact_rows.append(row["id"])
            continue
        mentions = _entity_mentions(text, lex)
        spans = _value_spans(text, mentions, parser.known_units)
        for i, fact in enumerate(result.facts):
            start, end, rel, obj = _find_support(text, mentions, spans, fact, lex)
            span = text[start:end]
            value = value_to_dict(fact.value)
            if fact.value.kind == "boolean":
                negated = fact.value.value is False
            else:
                pos = text.find(obj, start) if obj else -1
                negated = bool(C.NEGATION_RE.search(text[start:pos])) if pos > start else False
            record = {
                "extraction_id": f"{row['id']}#{METHOD}#{i}",
                "source_row_id": row["id"], "source_label": row.get("label", ""),
                "source_publication_date": row["date"],
                "subject": fact.subject, "subject_surface": fact.subject_spelling,
                "attribute": fact.attribute, "relation_surface": rel,
                "value": value, "object_surface": obj,
                "negated": bool(negated),
                "source_text_span": span, "span_start": start, "span_end": end,
                "fact_observation_date": None, "valid_from": None, "valid_to": None,
                "temporal_qualifier": None,
                "extraction_method": METHOD, "extraction_confidence": float(result.confidence),
                "parse_status": "partial", "verification_status": "candidate",
                "notes": "TextFactParser; attribute matched by attribute-name cue; no temporal handling",
            }
            errors = _validate(record, all_rows)
            if errors:
                downgraded += 1
                record.update({"value": None, "parse_status": "unmapped",
                               "notes": "downgraded: invalid canonical fact: " + "; ".join(errors)[:200]})
            facts_out.append(record)
    info = {"rows": len(rows), "rows_without_facts": len(no_fact_rows), "facts": len(facts_out),
            "downgraded_to_unmapped": downgraded, "rows_without_facts_ids_sample": no_fact_rows[:20]}
    return facts_out, info


def _validate(record: dict[str, Any], rows: dict[str, dict[str, str]]) -> list[str]:
    import fact_schema
    return fact_schema.validate_fact(record, C.lexicon(), rows)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(C.FULL_INPUT))
    ap.add_argument("--out", default=str(C.METHOD_FILES["baseline"]))
    args = ap.parse_args()
    t0 = time.perf_counter()
    kinds, units, n_dev = dev_priors()
    parser = TextFactParser(C.lexicon(), kinds, units)
    rows = [{k: r.get(k, "") for k in ("id", "text", "date", "label")} for r in C.read_csv(args.input)]
    facts, info = extract_rows(rows, parser)
    n = C.dump_jsonl(args.out, facts)
    info.update({
        "method": METHOD, "input": str(args.input), "output": str(args.out),
        "attribute_kinds_from": f"dev_rows.csv ({n_dev} rows)", "n_attribute_kinds": len(kinds), "n_known_units": len(units),
        "leakage_note": "attribute_kinds and known_units come from DEV rows only, not from held-out gold forms",
        "seconds": round(time.perf_counter() - t0, 3),
    })
    Path(str(args.out) + ".run_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
