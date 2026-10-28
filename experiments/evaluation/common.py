"""Shared helpers for the fact-reconstruction evaluation harness.

Everything here is evaluator-side. Extractors never import this module.

Value equivalence (documented, see README.md "Value equivalence"):
  * subject: resolved through data/lexicon.json (name or alias) to the canonical name.
  * value: foundation._canonical_value_key, i.e. physical units convert (1 GB == 1000 MB),
    durations in fixed units convert (14 days == 2 weeks), month/year convert among themselves
    only, names are compared through the lexicon (aliases collapse), money keeps currency and
    billing period, dates are compared as written (2026-03 != 2026-03-12), versions as written.
  * on top of that: op "eq" is treated as no op; counted-noun units are lower-cased and
    singularised (customers == customer).
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHARED = ROOT / "experiments" / "shared"
for _p in (ROOT, SHARED):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from foundation import Lexicon, _canonical_value_key, _quantity_unit  # noqa: E402
import fact_schema  # noqa: E402

LEXICON_PATH = ROOT / "data" / "lexicon.json"
FULL_INPUT = SHARED / "data" / "full_input.csv"
DEV_ROWS = SHARED / "data" / "dev_rows.csv"
SPLIT_JSON = SHARED / "data" / "split.json"
HELDOUT_GOLD = SHARED / "_heldout" / "heldout_gold.csv"   # evaluator only

EVAL_DIR = HERE / "eval_set"
EVAL_ROWS = EVAL_DIR / "eval_rows.csv"
SELECTION_LOG = EVAL_DIR / "selection_log.json"
WORKSHEET_DIR = HERE / "worksheet"
SUGGESTIONS_JSON = WORKSHEET_DIR / "evaluator_suggestions.json"
REVIEW_DIR = HERE / "review"
JUDGEMENTS_CSV = REVIEW_DIR / "evaluator_judgements.csv"
OUTPUT_DIR = HERE / "output"
RESULTS_DIR = HERE / "results"

METHOD_FILES = {
    "baseline": OUTPUT_DIR / "baseline_facts.jsonl",
    "openie": ROOT / "experiments" / "openie" / "output" / "facts.jsonl",
    "slot_filling": ROOT / "experiments" / "slot_filling" / "output" / "facts.jsonl",
}

VALUE_KINDS = ("date", "money", "quantity", "percent", "duration", "version", "name", "boolean")
NEGATION_RE = re.compile(r"(?:\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n[’']t\b)", re.I)

_lexicon: Lexicon | None = None


def lexicon() -> Lexicon:
    global _lexicon
    if _lexicon is None:
        _lexicon = fact_schema.load_lexicon(LEXICON_PATH)
    return _lexicon


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: str | Path, fields: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def sha1_file(path: str | Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()


def row_sort_key(row_id: str) -> tuple[str, int, str]:
    match = re.fullmatch(r"([A-Za-z_-]*?)-?(\d+)", row_id)
    if match:
        return (match.group(1), int(match.group(2)), row_id)
    return ("~", 0, row_id)


# --------------------------------------------------------------------------- values

_IRREGULAR = {"people": "person", "men": "man", "women": "woman", "children": "child", "indices": "index", "mice": "mouse"}


def singular(word: str) -> str:
    lower = word.casefold()
    if lower in _IRREGULAR:
        return _IRREGULAR[lower]
    if lower.endswith("ies") and len(lower) > 3:
        return lower[:-3] + "y"
    if lower.endswith("s") and not lower.endswith(("ss", "us", "is")):
        return lower[:-1]
    return lower


def canonical_subject(subject: str | None) -> str | None:
    if subject is None:
        return None
    entity = lexicon().resolve(subject)
    return entity.name if entity else subject.strip()


def value_key(value: Any) -> tuple[Any, ...] | None:
    """Canonical comparison key of a claimed value (None if the value is unusable)."""
    if not isinstance(value, Mapping):
        return None
    v = dict(value)
    op = v.pop("op", None)
    op = None if op in (None, "eq") else op
    kind = v.get("kind")
    if kind == "quantity" and isinstance(v.get("unit"), str) and _quantity_unit(v["unit"]) is None:
        v["unit"] = singular(v["unit"])
    if kind in ("quantity", "money", "percent", "duration") and isinstance(v.get("value"), (int, float)) \
            and not isinstance(v["value"], bool):
        number = float(v["value"])
        if not math.isfinite(number):
            return None
        v["value"] = round(number, 9)
    v["op"] = op
    try:
        key = _canonical_value_key(v, lexicon())
    except Exception:  # defensive: a malformed value must not crash a whole evaluation run
        key = None
    if key is None:
        key = ("raw", json.dumps(v, sort_keys=True, ensure_ascii=False))
    return key


def fact_key(subject: str | None, attribute: str | None, value: Any) -> tuple[Any, ...] | None:
    vkey = value_key(value)
    if subject is None or attribute is None or vkey is None:
        return None
    return (canonical_subject(subject), attribute, vkey)


def kind_of(value: Any) -> str | None:
    return value.get("kind") if isinstance(value, Mapping) else None


def _num(x: Any) -> str:
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return str(x)


_CUR_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
_OP_TEXT = {"gt": ">", "lt": "<", "ge": "≥", "le": "≤"}


def fmt_value(value: Mapping[str, Any] | None) -> str:
    """Compact human-readable form of a claimed value (used in worksheets and reports)."""
    if not isinstance(value, Mapping):
        return "∅"
    kind, v = value.get("kind"), value.get("value")
    op = _OP_TEXT.get(value.get("op") or "", "")
    if kind == "money":
        sym = _CUR_SYMBOL.get(value.get("currency"), value.get("currency", "") + " ")
        per = f"/{value['per']}" if value.get("per") else ""
        return f"{op}{sym}{_num(v)}{per}"
    if kind == "percent":
        return f"{op}{_num(v)}%"
    if kind == "version":
        return f"{op}v{v}"
    if kind in ("quantity", "duration"):
        return f"{op}{_num(v)} {value.get('unit')}"
    if kind == "boolean":
        return "true" if v else "false"
    if kind == "date":
        return f"{op}{v}"
    return f"{v}"


def fmt_fact(subject: str | None, attribute: str | None, value: Mapping[str, Any] | None) -> str:
    return f"{subject} | {attribute} | {fmt_value(value)}"


def parse_shorthand(text: str) -> dict[str, Any] | None:
    """Parse the readable forms produced by fmt_value back into a claimed-value object."""
    s = text.strip()
    ops = {v: k for k, v in _OP_TEXT.items()}
    op = None
    if s and s[0] in ops:
        op, s = ops[s[0]], s[1:].strip()

    def finish(obj: dict[str, Any]) -> dict[str, Any]:
        if op:
            obj["op"] = op
        return obj

    def number(raw: str) -> float | int:
        value = float(raw.replace(",", ""))
        return int(value) if value.is_integer() else value

    if s.casefold() in ("true", "false"):
        return {"kind": "boolean", "value": s.casefold() == "true"}
    m = re.fullmatch(r"([€$£])\s*([\d,]*\.?\d+)(?:/(day|week|month|year))?", s)
    if m:
        cur = {"€": "EUR", "$": "USD", "£": "GBP"}[m.group(1)]
        obj = {"kind": "money", "value": number(m.group(2)), "currency": cur}
        if m.group(3):
            obj["per"] = m.group(3)
        return finish(obj)
    m = re.fullmatch(r"([A-Z]{3})\s+([\d,]*\.?\d+)(?:/(day|week|month|year))?", s)
    if m:
        obj = {"kind": "money", "value": number(m.group(2)), "currency": m.group(1)}
        if m.group(3):
            obj["per"] = m.group(3)
        return finish(obj)
    m = re.fullmatch(r"([\d,]*\.?\d+)\s*%", s)
    if m:
        return finish({"kind": "percent", "value": number(m.group(1))})
    m = re.fullmatch(r"v(\d+(?:\.\d+){0,3})", s)
    if m:
        return finish({"kind": "version", "value": m.group(1)})
    if re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", s):
        return finish({"kind": "date", "value": s})
    m = re.fullmatch(r"([\d,]*\.?\d+)\s+([A-Za-z][A-Za-z0-9_]*)", s)
    if m:
        unit = m.group(2)
        unit = {"days": "day", "weeks": "week", "months": "month", "years": "year", "hours": "h", "hour": "h", "hr": "h",
                "minutes": "min", "minute": "min", "seconds": "s", "second": "s", "sec": "s"}.get(unit.casefold(), unit)
        kind = "duration" if unit in {"ms", "s", "min", "h", "day", "week", "month", "year"} else "quantity"
        return finish({"kind": kind, "value": number(m.group(1)), "unit": unit})
    if s:
        return {"kind": "name", "value": s}
    return None


# --------------------------------------------------------------------------- facts files

def load_facts(path: str | Path, rows: Mapping[str, Mapping[str, str]] | None = None,
               validate: bool = True) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read a facts JSONL. Returns (valid facts, info). Invalid facts are dropped and counted."""
    rows = rows if rows is not None else fact_schema.load_input_rows()
    lex = lexicon()
    facts: list[dict[str, Any]] = []
    info = {"path": str(path), "lines": 0, "invalid": 0, "invalid_examples": [], "unreadable_json": 0}
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            info["lines"] += 1
            try:
                fact = json.loads(line)
            except json.JSONDecodeError:
                info["unreadable_json"] += 1
                info["invalid"] += 1
                continue
            errs = fact_schema.validate_fact(fact, lex, rows) if validate else []
            if fact.get("extraction_id") in seen:
                errs = errs + ["duplicate extraction_id"]
            seen.add(fact.get("extraction_id"))
            if errs:
                info["invalid"] += 1
                if len(info["invalid_examples"]) < 10:
                    info["invalid_examples"].append(f"line {line_no}: {'; '.join(errs)[:300]}")
                continue
            facts.append(fact)
    info["valid"] = len(facts)
    return facts, info


def dump_jsonl(path: str | Path, facts: Iterable[Mapping[str, Any]]) -> int:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with Path(path).open("w", encoding="utf-8", newline="\n") as out:
        for fact in facts:
            out.write(json.dumps(fact, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


# --------------------------------------------------------------------------- text helpers

def mention_spans(text: str) -> list[tuple[int, int, str]]:
    """Evaluator-side lexicon mention finder (greedy longest-first, case-insensitive, whole word).

    Independent of the TextFactParser. Used only to build strata and to flag form facts whose
    subject is not written in the text."""
    spellings: list[tuple[str, str]] = []
    for entity in lexicon().entities:
        for name in (entity.name, *entity.aliases):
            spellings.append((name, entity.name))
    spellings.sort(key=lambda x: len(x[0]), reverse=True)
    masked = text
    found: list[tuple[int, int, str]] = []
    for spelling, canonical in spellings:
        words = [w for w in re.split(r"[\s-]+", spelling.strip()) if w]
        pattern = r"(?<![\w])" + r"[\s-]*".join(re.escape(w) for w in words) + r"(?![\w])"
        for match in re.finditer(pattern, masked, re.I):
            found.append((match.start(), match.end(), canonical))
            masked = masked[:match.start()] + " " * (match.end() - match.start()) + masked[match.end():]
    return sorted(found)


def subject_in_text(subject: str, text: str) -> bool:
    canon = canonical_subject(subject)
    return any(name == canon for _, _, name in mention_spans(text))
