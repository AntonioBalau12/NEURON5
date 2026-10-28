"""Build the stratified evaluation set and the annotation worksheet. Deterministic, no extractor output used.

  py experiments/evaluation/build_eval_set.py

Writes (all under experiments/evaluation/):
  eval_set/eval_rows.csv              id,text,date,label        runtime-shaped, NO form
  eval_set/selection_log.json         seed, rules, quotas, per-row strata, id-list hash
  eval_set/selection_provenance.json  written once: which extractor outputs existed at first selection
  worksheet/evaluator_reference.json  machine-readable form_gold / evaluator_suggested / temporal cues
  worksheet/annotation_worksheet.csv  human-fillable worksheet (+ .md readable copy)

Selection rule: per-row score = sha1(SEED|id). Strata are processed from the smallest pool to the largest;
for each stratum the lowest-score rows of its pool are added until the number of already selected rows
carrying that flag reaches the quota. Remaining slots are filled with the lowest-score unselected rows.
The held-out pool gets HELDOUT_TARGET rows, the dev pool (a "control": methods were tuned on it) DEV_TARGET.

Strata are identified from the text, the form size and the lexicon only (see FLAG_RULES in selection_log.json).
The evaluator reads held-out gold forms (experiments/shared/_heldout) here. Extractors must never do so.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

SEED = "neuron5-p3-evalset-v1"
HELDOUT_TARGET = 120
DEV_TARGET = 15

HELDOUT_QUOTAS = {
    "label_unsure": 7, "label_false": 25,
    "paraphrase": 18, "multi_fact": 30, "implicit_attribute": 15, "implicit_subject": 12,
    "negation": 15, "numeric_confusable": 20, "temporal": 20, "likely_incomplete_form": 20,
    "kind_date": 10, "kind_money": 10, "kind_quantity": 15, "kind_percent": 8,
    "kind_duration": 8, "kind_version": 7, "kind_name": 10, "kind_boolean": 10,
}

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
DATE_RE = re.compile(
    r"\b(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:" + MONTHS + r")\.?,?\s+\d{4}"
    r"|(?:" + MONTHS + r")\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|(?:" + MONTHS + r")\.?\s+\d{4}"
    r"|\d{4}-\d{2}(?:-\d{2})?)\b", re.I)
NUMBER_WORD_RE = re.compile(
    r"\b(?:two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|dozen)(?:-\w+)?\b", re.I)
DIGIT_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
TEMPORAL_RE = re.compile(
    r"\b(?:today|now|still|since|until|yet|already|currently|no longer|remains?|used to|previously|formerly|"
    r"this (?:month|week|year|summer|quarter|autumn)|last (?:quarter|year|month|week)|from (?:today|this|now)|as of|so far|"
    r"for the moment|again|starting|began|begins|planned|soon|next|every \d+|autumn|summer|spring|winter|"
    r"ships?|launch(?:es|ed)?|released?|opened|founded|announced|joined|started|came|took over|handed over)\b", re.I)
TEMPORAL_CUE_RE = re.compile(
    r"\b(?:today|now|still|since|until|yet|already|currently|no longer|remains?|used to|previously|formerly|"
    r"this (?:month|week|year|summer|quarter|autumn)|last (?:quarter|year|month|week)|from today|from this|as of|so far|"
    r"for the moment|again|starting|soon|ago)\b", re.I)

FLAG_RULES = {
    "label_true/false/unsure": "row label (given in the input)",
    "paraphrase": "some form fact (subject, attribute, canonical value) of the row also occurs in the form of at least one other row of the full dataset (dev or held-out) whose text differs: word-set Jaccard similarity of the two texts < 0.5, i.e. the same fact is worded differently elsewhere",
    "multi_fact": "form has >= 2 facts OR the text (after masking entities and dates) has >= 2 numeric tokens/number words",
    "implicit_attribute": "for at least one form fact, no 5-character stem of any attribute-name token (split on '_') occurs in the lower-cased text, e.g. 'started' for attribute 'joined'",
    "implicit_subject": "for at least one form fact the subject (canonical name or alias, found by the evaluator's own whole-word lexicon matcher) is not written in the text (context-dependent sentence)",
    "negation": "text matches the negation words of contracts/value-forms.md 'Yes or no' (not,no,never,none,nobody,nothing,neither,nor,without,cannot,n't) OR the form has a boolean false",
    "numeric_confusable": "a numeric form fact (quantity, money, percent, duration) shares subject+attribute with a different value of the same kind/unit in another row whose relative difference is <= 50%, OR the text contains >= 3 numeric tokens",
    "temporal": "text contains a month-name/ISO date, a 4-digit year 19xx/20xx, a temporal cue word (today, now, still, since, until, planned, ships, released, founded, ...) OR the form has a date-valued fact",
    "likely_incomplete_form": "(a) a lexicon entity is written in the text but is neither a form subject nor a form name value, OR (b) the text has more numeric tokens/number words/dates (after masking entity names, dates, quarter tags) than the form has numeric/date/version facts, OR (c) the text has >= 2 sentences/clauses joined by ';' or ' and ' while the form has a single fact",
    "kind_<kind>": "the form has at least one fact of that value kind (date, money, quantity, percent, duration, version, name, boolean)",
}


def load_pools() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    held = C.read_csv(C.HELDOUT_GOLD)
    dev = C.read_csv(C.DEV_ROWS)
    for r in held:
        r["split"] = "heldout"
    for r in dev:
        r["split"] = "dev"
    for r in held + dev:
        r["facts"] = json.loads(r["form"])
    return held, dev


def stems_of(attribute: str) -> list[str]:
    toks = [t for t in attribute.split("_") if len(t) >= 3 and t not in {"the", "per", "for", "and"}]
    return [t[:5].casefold() for t in toks]


def masked_text(text: str, mentions: list[tuple[int, int, str]]) -> str:
    out = text
    for a, b, _ in mentions:
        out = out[:a] + " " * (b - a) + out[b:]
    out = DATE_RE.sub(lambda m: " " * len(m.group()), out)
    out = re.sub(r"\bQ[1-4]\b|\bp\d{2}\b", " ", out)
    return out


def word_jaccard(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"\w+", a.casefold())), set(re.findall(r"\w+", b.casefold()))
    return len(wa & wb) / len(wa | wb) if wa | wb else 1.0


def compute_flags(row: dict[str, Any], index: dict[tuple, set[str]], by_slot: dict[tuple, list[tuple[str, dict]]],
                  texts: dict[str, str]) -> dict[str, bool]:
    text, facts = row["text"], row["facts"]
    lex_mentions = C.mention_spans(text)
    mentioned = {name for _, _, name in lex_mentions}
    masked = masked_text(text, lex_mentions)
    n_numbers = len(DIGIT_RE.findall(masked)) + len(NUMBER_WORD_RE.findall(masked))
    n_dates = len(DATE_RE.findall(text))
    form_numeric = [f for f in facts if f["value"]["kind"] in ("quantity", "money", "percent", "date", "duration", "version")]
    kinds = {f["value"]["kind"] for f in facts}
    subjects = {C.canonical_subject(f["subject"]) for f in facts}
    name_values = {C.canonical_subject(str(f["value"]["value"])) for f in facts if f["value"]["kind"] == "name"}
    low = text.casefold()

    flags: dict[str, bool] = {}
    flags["label_true"] = row["label"] == "true"
    flags["label_false"] = row["label"] == "false"
    flags["label_unsure"] = row["label"] == "unsure"

    keys = {C.fact_key(f["subject"], f["attribute"], f["value"]) for f in facts}
    flags["paraphrase"] = any(
        word_jaccard(text, texts[other]) < 0.5
        for k in keys if k for other in index.get(k, set()) - {row["id"]})
    flags["multi_fact"] = len(facts) >= 2 or (n_numbers + n_dates) >= 2
    flags["implicit_attribute"] = any(not any(s in low for s in stems_of(f["attribute"])) for f in facts)
    flags["implicit_subject"] = any(C.canonical_subject(f["subject"]) not in mentioned for f in facts)
    flags["negation"] = bool(C.NEGATION_RE.search(text)) or any(f["value"]["kind"] == "boolean" and f["value"]["value"] is False for f in facts)

    confusable = False
    for f in facts:
        v = f["value"]
        if v["kind"] not in ("quantity", "money", "percent", "duration"):
            continue
        slot = (C.canonical_subject(f["subject"]), f["attribute"])
        for other_id, other in by_slot.get(slot, []):
            if other_id == row["id"]:
                continue
            ov = other["value"]
            if ov["kind"] != v["kind"] or ov.get("unit") != v.get("unit") or ov.get("currency") != v.get("currency"):
                continue
            a, b = float(v["value"]), float(ov["value"])
            if a != b and abs(a - b) / max(abs(a), abs(b), 1e-9) <= 0.5:
                confusable = True
    flags["numeric_confusable"] = confusable or (n_numbers + n_dates) >= 3
    flags["temporal"] = bool(DATE_RE.search(text) or re.search(r"\b(?:19|20)\d{2}\b", text) or TEMPORAL_RE.search(text) or "date" in kinds)

    unused_entity = any(n not in subjects and n not in name_values for n in mentioned)
    fewer_facts = (n_numbers + n_dates) > len(form_numeric)
    multi_clause = len(facts) == 1 and bool(re.search(r";|\band\b", text)) and (n_numbers + n_dates) >= 2
    flags["likely_incomplete_form"] = unused_entity or fewer_facts or multi_clause
    for kind in C.VALUE_KINDS:
        flags[f"kind_{kind}"] = kind in kinds
    return flags


def score(row_id: str) -> int:
    return int(hashlib.sha1(f"{SEED}|{row_id}".encode("utf-8")).hexdigest(), 16)


def select(pool: list[dict[str, Any]], quotas: dict[str, int], target: int) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    order = sorted(quotas, key=lambda s: (sum(1 for r in pool if r["flags"][s]), s))
    for stratum in order:
        have = sum(1 for r in chosen.values() if r["flags"][stratum])
        candidates = sorted((r for r in pool if r["flags"][stratum] and r["id"] not in chosen), key=lambda r: score(r["id"]))
        for r in candidates:
            if have >= quotas[stratum]:
                break
            chosen[r["id"]] = r
            r.setdefault("picked_for", stratum)
            have += 1
    fill = sorted((r for r in pool if r["id"] not in chosen), key=lambda r: score(r["id"]))
    for r in fill:
        if len(chosen) >= target:
            break
        chosen[r["id"]] = r
        r["picked_for"] = "fill"
    return sorted(chosen.values(), key=lambda r: C.row_sort_key(r["id"]))


def main() -> None:
    held, dev = load_pools()
    index: dict[tuple, set[str]] = defaultdict(set)
    by_slot: dict[tuple, list[tuple[str, dict]]] = defaultdict(list)
    for r in held + dev:
        for f in r["facts"]:
            k = C.fact_key(f["subject"], f["attribute"], f["value"])
            if k:
                index[k].add(r["id"])
            by_slot[(C.canonical_subject(f["subject"]), f["attribute"])].append((r["id"], f))
    texts = {r["id"]: r["text"] for r in held + dev}
    for r in held + dev:
        r["flags"] = compute_flags(r, index, by_slot, texts)

    dev_quotas = {k: max(1, round(v * DEV_TARGET / HELDOUT_TARGET)) for k, v in HELDOUT_QUOTAS.items()}
    sel_held = select(held, HELDOUT_QUOTAS, HELDOUT_TARGET)
    sel_dev = select(dev, dev_quotas, DEV_TARGET)
    selected = sorted(sel_held + sel_dev, key=lambda r: C.row_sort_key(r["id"]))

    C.EVAL_DIR.mkdir(parents=True, exist_ok=True)
    C.write_csv(C.EVAL_ROWS, ["id", "text", "date", "label"], selected)

    pool_sizes = {s: sum(1 for r in held if r["flags"][s]) for s in HELDOUT_QUOTAS}
    achieved = {s: sum(1 for r in sel_held if r["flags"][s]) for s in HELDOUT_QUOTAS}
    achieved_dev = {s: sum(1 for r in sel_dev if r["flags"][s]) for s in HELDOUT_QUOTAS}
    log = {
        "seed": SEED,
        "selection_rule": __doc__.split("Selection rule:")[1].split("Strata are")[0].strip(),
        "heldout_target": HELDOUT_TARGET, "dev_target": DEV_TARGET,
        "n_selected": len(selected), "n_heldout": len(sel_held), "n_dev": len(sel_dev),
        "heldout_pool_size": len(held), "dev_pool_size": len(dev),
        "heldout_quotas": HELDOUT_QUOTAS, "dev_quotas": dev_quotas,
        "heldout_pool_stratum_sizes": pool_sizes,
        "heldout_selected_stratum_counts": achieved,
        "dev_selected_stratum_counts": achieved_dev,
        "label_counts_selected": dict(Counter(r["label"] for r in selected)),
        "flag_rules": FLAG_RULES,
        "regexes": {
            "negation": C.NEGATION_RE.pattern, "date": DATE_RE.pattern, "number_words": NUMBER_WORD_RE.pattern,
            "temporal": TEMPORAL_RE.pattern,
        },
        "integrity": [
            "chosen using only row text, label, given form (kinds, subjects, attributes, values) and the lexicon",
            "no extractor output (baseline, openie, slot_filling, claim_factory) was read for selection",
            "eval_rows.csv is runtime-shaped (id,text,date,label); gold forms live in worksheet/ and are evaluator-private",
        ],
        "id_list_sha1": hashlib.sha1("\n".join(r["id"] for r in selected).encode()).hexdigest(),
        "rows": [{"id": r["id"], "split": r["split"], "picked_for": r.get("picked_for"),
                  "strata": sorted(k for k, v in r["flags"].items() if v)} for r in selected],
    }
    C.SELECTION_LOG.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")

    prov = C.EVAL_DIR / "selection_provenance.json"
    if not prov.exists():
        import datetime
        prov.write_text(json.dumps({
            "written_once_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "id_list_sha1": log["id_list_sha1"],
            "extractor_outputs_existing_at_first_selection": {
                name: path.exists() for name, path in C.METHOD_FILES.items() if name != "baseline"
            },
            "baseline_output_existing_at_first_selection": C.METHOD_FILES["baseline"].exists(),
            "note": "recorded on the first run only; later runs do not overwrite this file",
        }, indent=1), encoding="utf-8")

    build_reference_and_worksheet(selected)
    print(f"selected {len(selected)} rows: {len(sel_held)} held-out + {len(sel_dev)} dev; id hash {log['id_list_sha1'][:12]}")
    print("held-out stratum counts (selected/pool):")
    for s in HELDOUT_QUOTAS:
        print(f"  {s:24s} {achieved[s]:3d}/{pool_sizes[s]:3d} (quota {HELDOUT_QUOTAS[s]})")


# ---------------------------------------------------------------- reference + worksheet

def load_suggestions() -> dict[str, Any]:
    if C.SUGGESTIONS_JSON.exists():
        return json.loads(C.SUGGESTIONS_JSON.read_text(encoding="utf-8"))
    return {"meta": {}, "rows": {}}


def build_reference_and_worksheet(selected: list[dict[str, Any]]) -> None:
    sugg = load_suggestions()
    sugg_rows = sugg.get("rows", {})
    reviewed = set(sugg.get("meta", {}).get("reviewed_row_ids", []))
    reference: dict[str, Any] = {"meta": {
        "form_gold": "facts of the given form; incomplete, NOT exhaustive ground truth",
        "evaluator_suggested": "form facts + additional facts suggested by evaluator_llm; UNVERIFIED",
        "suggestions_status": sugg.get("meta", {}).get("status", "no suggestions file"),
        "n_rows_with_evaluator_review": len(reviewed),
    }, "rows": {}}
    ws_rows: list[dict[str, Any]] = []
    md: list[str] = [
        "# Fact annotation worksheet (evaluation set)", "",
        "**How to read this.** `Form facts` come from the dataset `form` column and are *possibly incomplete*; they are NOT an exhaustive list of what the sentence states. "
        "`Suggested additional facts` were proposed by the evaluator (`suggested_by=evaluator_llm`, status `needs_human_verification`); they are NOT ground truth. "
        "Fill the human columns in `annotation_worksheet.csv` (format in `README.md`), then run `py experiments/evaluation/ingest_worksheet.py`.", "",
    ]
    for n, r in enumerate(selected, 1):
        rid, text = r["id"], r["text"]
        info = sugg_rows.get(rid, {})
        form_facts = []
        for i, f in enumerate(r["facts"], 1):
            form_facts.append({
                "fid": f"F{i}", "subject": C.canonical_subject(f["subject"]), "attribute": f["attribute"], "value": f["value"],
                "subject_written_in_text": C.subject_in_text(f["subject"], text),
            })
        extras = []
        for j, s in enumerate(info.get("suggested", []), 1):
            extras.append({"sid": f"S{j}", "subject": C.canonical_subject(s["subject"]), "attribute": s["attribute"], "value": s["value"],
                           "rationale": s.get("rationale", ""), "suggested_by": "evaluator_llm", "status": "needs_human_verification"})
        cues = info.get("temporal", {}).get("cues")
        if cues is None:
            cues = sorted({m.group().casefold() for m in TEMPORAL_CUE_RE.finditer(text)})
        obs = info.get("temporal", {}).get("observation_dates", [])
        flags = sorted(k for k, v in r["flags"].items() if v)
        reference["rows"][rid] = {
            "split": r["split"], "label": r["label"], "date": r["date"], "strata": flags,
            "form_gold": form_facts, "evaluator_suggested_extra": extras,
            "form_concerns": info.get("form_concerns", []),
            "temporal_cues": cues, "explicit_observation_dates": obs,
            "evaluator_reviewed": rid in reviewed,
        }

        def lines_form() -> str:
            return "\n".join(f"{x['fid']}: {C.fmt_fact(x['subject'], x['attribute'], x['value'])}" + ("" if x["subject_written_in_text"] else "   [subject not written in text]") for x in form_facts)

        def lines_extra() -> str:
            return "\n".join(f"{x['sid']}: {C.fmt_fact(x['subject'], x['attribute'], x['value'])}" for x in extras)

        ws_rows.append({
            "eval_idx": n, "id": rid, "split": r["split"], "date": r["date"], "label": r["label"],
            "strata": ";".join(flags), "text": text,
            "form_facts_FROM_FORM_POSSIBLY_INCOMPLETE": lines_form(),
            "form_facts_json": json.dumps([{k: x[k] for k in ("subject", "attribute", "value")} for x in form_facts], ensure_ascii=False),
            "suggested_additional_facts_UNVERIFIED": lines_extra(),
            "suggested_facts_json": json.dumps([{k: x[k] for k in ("subject", "attribute", "value")} for x in extras], ensure_ascii=False),
            "suggested_by": "evaluator_llm" if extras else "",
            "suggested_status": "needs_human_verification" if extras else "",
            "suggestion_rationale": "\n".join(f"{x['sid']}: {x['rationale']}" for x in extras),
            "form_concerns": " | ".join(info.get("form_concerns", [])),
            "evaluator_temporal_cues": ";".join(cues),
            "annotator": "", "reviewed": "",
            "form_fact_verdicts": "", "suggested_fact_verdicts": "",
            "human_complete_facts": "", "human_extra_facts": "", "human_notes": "",
        })
        md += [f"## {n}. `{rid}` ({r['split']}, label={r['label']}, date={r['date']})", "",
               f"> {text.replace(chr(10), ' / ')}", "",
               f"*Strata:* {', '.join(flags)}", "",
               "**Form facts (from form, possibly incomplete):**", ""]
        md += [f"- `{x['fid']}` {C.fmt_fact(x['subject'], x['attribute'], x['value'])}" + ("" if x["subject_written_in_text"] else " *(subject not written in the text)*") for x in form_facts] or ["- (none)"]
        md += ["", "**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**", ""]
        md += [f"- `{x['sid']}` {C.fmt_fact(x['subject'], x['attribute'], x['value'])}  \n  *why:* {x['rationale']}" for x in extras] or ["- (none suggested)"]
        if info.get("form_concerns"):
            md += ["", "**Concerns about the form:** " + " | ".join(info["form_concerns"])]
        md += ["", "**Human annotator:** complete atomic fact list: ______  verified: ______", "", "---", ""]

    C.WORKSHEET_DIR.mkdir(parents=True, exist_ok=True)
    (C.WORKSHEET_DIR / "evaluator_reference.json").write_text(json.dumps(reference, indent=1, ensure_ascii=False), encoding="utf-8")
    fields = list(ws_rows[0].keys())
    C.write_csv(C.WORKSHEET_DIR / "annotation_worksheet.csv", fields, ws_rows)
    (C.WORKSHEET_DIR / "annotation_worksheet.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()

