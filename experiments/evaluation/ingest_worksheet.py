"""Recompute the metrics from a human-verified worksheet.

  py experiments/evaluation/ingest_worksheet.py --worksheet experiments/evaluation/worksheet/annotation_worksheet_filled.csv \
        --methods baseline openie slot_filling combined --out experiments/evaluation/results/<run>_human

The worksheet is a copy of worksheet/annotation_worksheet.csv with the human columns filled. Only rows with
`reviewed` = yes (y/true/1) are used. For such a row the HUMAN GOLD is built like this:

  1. human_complete_facts non-empty  -> it IS the gold of the row (replaces everything else). The word NONE means
     "the sentence states no usable fact".
  2. otherwise: the form facts, minus those marked wrong in form_fact_verdicts
                + the evaluator suggestions marked ok in suggested_fact_verdicts
                + human_extra_facts.
     Form facts not mentioned in form_fact_verdicts are KEPT. Suggestions not mentioned are DROPPED.

Cell formats (separators: new line or ';')
  form_fact_verdicts       F1=ok; F2=wrong        (ok|correct|keep|yes   vs   wrong|reject|unsupported|no|remove)
  suggested_fact_verdicts  S1=ok; S2=reject
  human_extra_facts / human_complete_facts
                           subject | attribute | value        one fact per line or per ';'
                           value shorthand as in the worksheet: 3200 seat, €59/month, 99.9%, v2.3, 2026-03-12, true,
                           >40000 user, 128 GB, 14 days, Frankfurt (name).   A JSON list of
                           {"subject":..,"attribute":..,"value":{..claimed value..}} is accepted too.
Subjects/attributes are checked against data/lexicon.json; a wrong one stops the run and is listed (use --lenient to
skip those facts instead).

Metrics: against the human gold of the reviewed rows (treated as COMPLETE, so precision is a real precision for those
rows), next to the same rows scored against form and suggested. Also written: human_review_stats.json (how many form facts
were rejected, how many suggestions accepted, how many extras added).
Results folders are never overwritten.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import metrics as M  # noqa: E402
import reporting as E  # noqa: E402  (not named evaluate: the repository root has its own evaluate.py)

OK = {"ok", "correct", "keep", "yes", "y", "true", "1"}
BAD = {"wrong", "reject", "rejected", "unsupported", "no", "n", "remove", "false", "0", "incorrect"}
YES = {"yes", "y", "true", "1"}


def split_cells(cell: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;\n]+", cell or "") if p.strip()]


def parse_verdicts(cell: str, prefix: str, errors: list[str], where: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for token in split_cells(cell):
        m = re.fullmatch(rf"({prefix}\d+)\s*[=:]\s*(\w+)", token, re.I)
        if not m or m.group(2).casefold() not in OK | BAD:
            errors.append(f"{where}: cannot read verdict {token!r}")
            continue
        out[m.group(1).upper()] = m.group(2).casefold() in OK
    return out


def parse_facts(cell: str, errors: list[str], where: str) -> list[tuple[str, str, dict[str, Any]]]:
    cell = (cell or "").strip()
    if not cell:
        return []
    if cell.upper() == "NONE":
        return []
    items: list[tuple[str, str, dict[str, Any]]] = []
    lex = C.lexicon()
    if cell.startswith("["):
        try:
            raw = [(d["subject"], d["attribute"], d["value"]) for d in json.loads(cell)]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            errors.append(f"{where}: bad JSON fact list ({exc})")
            return []
    else:
        raw = []
        for token in split_cells(cell):
            parts = [p.strip() for p in token.split("|")]
            if len(parts) != 3:
                errors.append(f"{where}: expected 'subject | attribute | value', got {token!r}")
                continue
            value = C.parse_shorthand(parts[2])
            if value is None:
                errors.append(f"{where}: cannot read value {parts[2]!r}")
                continue
            raw.append((parts[0], parts[1], value))
    for subject, attribute, value in raw:
        entity = lex.resolve(subject)
        if entity is None or attribute not in entity.attributes:
            errors.append(f"{where}: {subject!r} / {attribute!r} is not a lexicon entity / attribute of it")
            continue
        issues = C.fact_schema.value_validator().validate(value)
        if issues:
            errors.append(f"{where}: value {value} is not a valid claimed value: {issues[:1]}")
            continue
        items.append((entity.name, attribute, value))
    return items


def build_human_rows(ws: list[dict[str, str]], gold_rows: dict[str, M.RowGold], lenient: bool) -> tuple[list[M.RowGold], dict[str, Any], list[str]]:
    errors: list[str] = []
    stats = {"reviewed_rows": 0, "rows_with_complete_list": 0, "form_facts_kept": 0, "form_facts_rejected": 0,
             "suggestions_accepted": 0, "suggestions_rejected": 0, "suggestions_unmarked_dropped": 0, "human_extra_facts": 0,
             "annotators": sorted({(r.get("annotator") or "").strip() for r in ws if (r.get("reviewed") or "").strip().casefold() in YES} - {""})}
    out: list[M.RowGold] = []
    for r in ws:
        if (r.get("reviewed") or "").strip().casefold() not in YES:
            continue
        rid = r["id"]
        if rid not in gold_rows:
            errors.append(f"{rid}: not an evaluation row")
            continue
        row = gold_rows[rid]
        mentioned = {name for _, _, name in C.mention_spans(row.text)}
        before = len(errors)
        form_v = parse_verdicts(r.get("form_fact_verdicts", ""), "F", errors, rid)
        sugg_v = parse_verdicts(r.get("suggested_fact_verdicts", ""), "S", errors, rid)
        complete = parse_facts(r.get("human_complete_facts", ""), errors, f"{rid} human_complete_facts")
        extras = parse_facts(r.get("human_extra_facts", ""), errors, f"{rid} human_extra_facts")
        if len(errors) > before and not lenient:
            continue
        stats["reviewed_rows"] += 1
        if (r.get("human_complete_facts") or "").strip():
            stats["rows_with_complete_list"] += 1
            facts = complete
        else:
            facts = []
            for g in row.sets["form"]:
                if form_v.get(g.fid.upper(), True):
                    facts.append((g.subject, g.attribute, g.value))
                    stats["form_facts_kept"] += 1
                else:
                    stats["form_facts_rejected"] += 1
            for g in row.sets["extra"]:
                verdict = sugg_v.get(g.fid.upper())
                if verdict:
                    facts.append((g.subject, g.attribute, g.value))
                    stats["suggestions_accepted"] += 1
                elif verdict is False:
                    stats["suggestions_rejected"] += 1
                else:
                    stats["suggestions_unmarked_dropped"] += 1
            facts += extras
            stats["human_extra_facts"] += len(extras)
        human = M.dedupe(g for g in (M.make_gfact(s, a, v, mentioned, "human") for s, a, v in facts) if g)
        new = M.RowGold(row.id, row.text, row.date, row.label, row.split, row.strata, row.cues, dict(row.sets))
        new.sets["human"] = human
        out.append(new)
    return out, stats, errors


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--worksheet", required=True)
    ap.add_argument("--methods", nargs="+", default=["baseline", "openie", "slot_filling", "combined"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=E.DEFAULT_SEED)
    ap.add_argument("--judgements", default=str(C.JUDGEMENTS_CSV))
    ap.add_argument("--resources", default=None)
    ap.add_argument("--lenient", action="store_true", help="skip rows/facts with format errors instead of stopping")
    args = ap.parse_args()

    out_dir = Path(args.out)
    if out_dir.exists():
        print(f"ERROR: {out_dir} exists; results are never overwritten")
        return 2
    reference = json.loads((C.WORKSHEET_DIR / "evaluator_reference.json").read_text(encoding="utf-8"))
    gold = {r.id: r for r in M.load_gold(reference, C.read_csv(C.EVAL_ROWS))}
    ws = C.read_csv(args.worksheet)
    rows, stats, errors = build_human_rows(ws, gold, args.lenient)
    for e in errors:
        print("FORMAT PROBLEM:", e)
    if errors and not args.lenient:
        print(f"{len(errors)} problem(s); fix the worksheet or pass --lenient")
        return 4
    if not rows:
        print("no row with reviewed = yes in the worksheet; nothing to recompute")
        return 3
    methods, skipped = E.resolve_methods(args.methods)
    for s in skipped:
        print("SKIPPED", s)
    if not methods:
        return 3
    resources = json.loads(Path(args.resources).read_text(encoding="utf-8")) if args.resources else None
    payload = E.run(methods, out_dir, rows, ["form", "suggested", "human"], "human", M.load_judgements(args.judgements), args.bootstrap,
                    args.seed, f"Human-verified evaluation {out_dir.name} ({len(rows)} reviewed rows)",
                    extra_config={"worksheet": str(args.worksheet), "worksheet_sha1": C.sha1_file(args.worksheet), "human_review": stats,
                                  "format_problems_skipped": errors},
                    resources=resources, skipped=skipped)
    (out_dir / "human_review_stats.json").write_text(json.dumps({"stats": stats, "problems": errors}, indent=1), encoding="utf-8")
    print(json.dumps(stats, indent=1))
    for n, r in payload["methods"].items():
        o = r["overall"]
        print(f"{n:24s} P_human {E.fmt_pct(o['precision_human'])}  R_human {E.fmt_pct(o['recall_human'])}  F1_human {E.fmt_pct(o['f1_human'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
