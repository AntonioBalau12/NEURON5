"""Coordinator-owned exchange format validator for reconstructed facts.

Usage:
  py experiments/shared/fact_schema.py FACTS.jsonl [--input experiments/shared/data/full_input.csv]

A fact file is JSONL, one reconstructed fact per line. See EXCHANGE_FORMAT.md.
Importable: validate_fact(), validate_file(), load_input_rows(), load_lexicon().
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from foundation import Lexicon, SchemaValidator, TypedValue  # noqa: E402  (read-only reuse)

REQUIRED = (
    "extraction_id", "source_row_id", "source_label", "source_publication_date",
    "subject", "subject_surface", "attribute", "relation_surface", "value", "object_surface",
    "negated", "source_text_span", "span_start", "span_end",
    "fact_observation_date", "valid_from", "valid_to", "temporal_qualifier",
    "extraction_method", "extraction_confidence", "parse_status", "verification_status", "notes",
)
METHODS = {"openie", "slot_filling", "deterministic_parser", "combined"}
PARSE_STATUS = {"complete", "partial", "ambiguous", "unmapped"}
LABELS = {"true", "false", "unsure", ""}

_validator: SchemaValidator | None = None


def value_validator() -> SchemaValidator:
    global _validator
    if _validator is None:
        _validator = SchemaValidator(ROOT / "contracts" / "claimed_value.schema.json")
    return _validator


def load_lexicon(path: str | Path = ROOT / "data" / "lexicon.json") -> Lexicon:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    lexicon, issues = Lexicon.parse(raw)
    if lexicon is None:
        raise ValueError("; ".join(issues))
    return lexicon


def load_input_rows(path: str | Path = HERE / "data" / "full_input.csv") -> dict[str, dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return {row["id"]: row for row in csv.DictReader(handle)}


def _iso_ok(raw: Any, allow_partial: bool = False) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, str):
        return False
    try:
        date.fromisoformat(raw)
        return True
    except ValueError:
        return False


def validate_fact(fact: dict[str, Any], lexicon: Lexicon, rows: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    missing = [key for key in REQUIRED if key not in fact]
    if missing:
        return [f"missing fields: {missing}"]
    extra = set(fact) - set(REQUIRED)
    if extra:
        errors.append(f"unknown fields: {sorted(extra)}")
    if fact["verification_status"] != "candidate":
        errors.append("verification_status must be 'candidate'; extractors never verify")
    if fact["extraction_method"] not in METHODS:
        errors.append(f"extraction_method not in {sorted(METHODS)}")
    if fact["parse_status"] not in PARSE_STATUS:
        errors.append(f"parse_status not in {sorted(PARSE_STATUS)}")
    conf = fact["extraction_confidence"]
    if not isinstance(conf, (int, float)) or isinstance(conf, bool) or not 0.0 <= conf <= 1.0:
        errors.append("extraction_confidence must be a number in [0, 1]")
    if not isinstance(fact["negated"], bool):
        errors.append("negated must be a boolean")
    for key in ("fact_observation_date", "valid_from", "valid_to"):
        if not _iso_ok(fact[key]):
            errors.append(f"{key} must be null or a full ISO date")

    row = rows.get(fact["source_row_id"])
    if row is None:
        return errors + [f"unknown source_row_id {fact['source_row_id']!r}"]
    if fact["source_label"] != row.get("label", ""):
        errors.append("source_label does not match the input row label")
    if fact["source_publication_date"] != row.get("date"):
        errors.append("source_publication_date must equal the input row date")

    text = row["text"]
    span = fact["source_text_span"]
    start, end = fact["span_start"], fact["span_end"]
    if not isinstance(span, str) or not span:
        errors.append("source_text_span must be a non-empty string")
    elif not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)
              and text[start:end] == span):
        errors.append("span_start/span_end must slice exactly source_text_span out of the row text")

    # Canonical (mapped) facts: subject, attribute and value must all be present and valid.
    mapped = fact["subject"] is not None and fact["attribute"] is not None and fact["value"] is not None
    if fact["parse_status"] == "unmapped" and mapped:
        errors.append("parse_status 'unmapped' but subject/attribute/value are all set")
    if fact["parse_status"] != "unmapped" and not mapped:
        errors.append("a canonical fact needs subject, attribute and value; use parse_status 'unmapped' otherwise")
    if fact["subject"] is not None:
        entity = lexicon.resolve(fact["subject"])
        if entity is None or entity.name != fact["subject"]:
            errors.append("subject must be a canonical lexicon entity name")
        elif fact["attribute"] is not None and fact["attribute"] not in entity.attributes:
            errors.append(f"attribute {fact['attribute']!r} is not an attribute of {entity.name!r}")
    if fact["value"] is not None:
        typed, err = TypedValue.parse(fact["value"])
        if err:
            errors.append(f"value: {err}")
        else:
            errors.extend(f"value schema: {x}" for x in value_validator().validate(fact["value"]))
    return errors


def validate_file(path: str | Path, rows: dict[str, dict[str, str]] | None = None,
                  lexicon: Lexicon | None = None, max_report: int = 20) -> dict[str, Any]:
    rows = rows or load_input_rows()
    lexicon = lexicon or load_lexicon()
    seen: set[str] = set()
    total = bad = 0
    samples: list[str] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            total += 1
            try:
                fact = json.loads(line)
            except json.JSONDecodeError as exc:
                errs = [f"invalid JSON: {exc}"]
            else:
                errs = validate_fact(fact, lexicon, rows)
                if fact.get("extraction_id") in seen:
                    errs.append("duplicate extraction_id")
                seen.add(fact.get("extraction_id"))
            if errs:
                bad += 1
                if len(samples) < max_report:
                    samples.append(f"line {line_no}: {'; '.join(errs)}")
    return {"facts": total, "invalid": bad, "valid": total - bad, "examples": samples}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("facts")
    parser.add_argument("--input", default=str(HERE / "data" / "full_input.csv"))
    args = parser.parse_args()
    report = validate_file(args.facts, load_input_rows(args.input))
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if report["invalid"] else 0)
