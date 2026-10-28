"""Pure metric code for the fact-reconstruction evaluation (no file output, importable by tests).

Terminology
  gold sets (per row)   form       facts of the dataset `form`; incomplete, NOT exhaustive
                        extra      additional facts suggested by the evaluator (unverified)
                        suggested  form + extra
                        human      (optional) human-verified complete list from the worksheet
  predicted fact        a record of a facts.jsonl (EXCHANGE_FORMAT.md). "Mapped" = parse_status != unmapped and
                        subject, attribute and value all set. Only mapped facts enter precision/recall.
  identity of a fact    common.fact_key(subject, attribute, value): subject through the lexicon, value through
                        foundation._canonical_value_key (units convert, names via lexicon) + op. Duplicates of the
                        same key inside one row count once.

Every metric is a ratio of sums of per-row integer counters. That makes the cluster bootstrap over rows trivial:
resample rows with replacement, add up the counters, recompute the ratio.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

import common as C

KINDS = C.VALUE_KINDS


# --------------------------------------------------------------------------- data classes

@dataclass
class GFact:
    subject: str
    attribute: str
    value: dict[str, Any]
    key: tuple
    kind: str
    explicit: bool          # subject is written in the sentence (lexicon name or alias)
    negated: bool           # expected `negated` flag: boolean false in the gold value
    origin: str = "form"
    fid: str = ""


@dataclass
class RowGold:
    id: str
    text: str
    date: str
    label: str
    split: str
    strata: frozenset
    cues: tuple
    sets: dict[str, list[GFact]] = field(default_factory=dict)   # form, extra, suggested, human (optional)


@dataclass
class Pred:
    raw: dict[str, Any]
    row: str
    subject: str | None
    attribute: str | None
    value: dict[str, Any] | None
    mapped: bool
    key: tuple | None
    kind: str | None
    negated: bool


def make_gfact(subject: str, attribute: str, value: Mapping[str, Any], mentioned: set[str],
               origin: str, fid: str = "") -> GFact | None:
    key = C.fact_key(subject, attribute, value)
    if key is None:
        return None
    subj = C.canonical_subject(subject)
    kind = value.get("kind")
    return GFact(subj, attribute, dict(value), key, kind, subj in mentioned,
                 kind == "boolean" and value.get("value") is False, origin, fid)


def dedupe(facts: Iterable[GFact]) -> list[GFact]:
    seen: set[tuple] = set()
    out = []
    for f in facts:
        if f.key not in seen:
            seen.add(f.key)
            out.append(f)
    return out


def load_gold(reference: Mapping[str, Any], eval_rows: Sequence[Mapping[str, str]]) -> list[RowGold]:
    out: list[RowGold] = []
    for row in eval_rows:
        ref = reference["rows"][row["id"]]
        text = row["text"]
        mentioned = {name for _, _, name in C.mention_spans(text)}
        form = dedupe(g for g in (make_gfact(f["subject"], f["attribute"], f["value"], mentioned, "form", f.get("fid", ""))
                                  for f in ref["form_gold"]) if g)
        extra = dedupe(g for g in (make_gfact(f["subject"], f["attribute"], f["value"], mentioned, "suggested", f.get("sid", ""))
                                   for f in ref.get("evaluator_suggested_extra", [])) if g)
        form_keys = {g.key for g in form}
        extra = [g for g in extra if g.key not in form_keys]
        rg = RowGold(row["id"], text, row["date"], row.get("label", ""), ref.get("split", ""),
                     frozenset(ref.get("strata", [])), tuple(c.casefold() for c in ref.get("temporal_cues", [])))
        rg.sets = {"form": form, "extra": extra, "suggested": form + extra}
        out.append(rg)
    return out


def to_pred(fact: Mapping[str, Any]) -> Pred:
    subject, attribute, value = fact.get("subject"), fact.get("attribute"), fact.get("value")
    mapped = fact.get("parse_status") != "unmapped" and None not in (subject, attribute, value)
    key = C.fact_key(subject, attribute, value) if mapped else None
    if mapped and key is None:
        mapped = False
    return Pred(dict(fact), fact["source_row_id"], C.canonical_subject(subject), attribute, value if isinstance(value, dict) else None,
                mapped, key, C.kind_of(value), bool(fact.get("negated")))


def group_preds(facts: Iterable[Mapping[str, Any]], row_ids: Iterable[str]) -> dict[str, list[Pred]]:
    ids = set(row_ids)
    out: dict[str, list[Pred]] = {i: [] for i in ids}
    for f in facts:
        if f.get("source_row_id") in ids:
            out[f["source_row_id"]].append(to_pred(f))
    return out


# --------------------------------------------------------------------------- dates in text (temporal checks)

_MONTH_NAMES = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
                "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
                "oct": 10, "nov": 11, "dec": 12}
_MON = "|".join(sorted(_MONTH_NAMES, key=len, reverse=True))
_DATE_PATTERNS = [
    ("iso_day", re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")),
    ("dmy", re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(" + _MON + r")\.?,?\s+(\d{4})\b", re.I)),
    ("mdy", re.compile(r"\b(" + _MON + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.I)),
    ("iso_month", re.compile(r"\b(\d{4})-(\d{2})\b")),
    ("my", re.compile(r"\b(" + _MON + r")\.?\s+(\d{4})\b", re.I)),
    ("year", re.compile(r"\b((?:19|20)\d{2})\b")),
]


def text_dates(text: str) -> set[str]:
    """ISO dates (YYYY-MM-DD, YYYY-MM or YYYY) explicitly written in the text. Most specific pattern wins per span."""
    out: set[str] = set()
    masked = text
    for name, pattern in _DATE_PATTERNS:
        for m in list(pattern.finditer(masked)):
            g = m.groups()
            try:
                if name == "iso_day":
                    iso = f"{g[0]}-{g[1]}-{g[2]}"
                elif name == "dmy":
                    iso = f"{g[2]}-{_MONTH_NAMES[g[1].casefold()]:02d}-{int(g[0]):02d}"
                elif name == "mdy":
                    iso = f"{g[2]}-{_MONTH_NAMES[g[0].casefold()]:02d}-{int(g[1]):02d}"
                elif name == "iso_month":
                    iso = f"{g[0]}-{g[1]}"
                elif name == "my":
                    iso = f"{g[1]}-{_MONTH_NAMES[g[0].casefold()]:02d}"
                else:
                    iso = g[0]
            except (KeyError, ValueError):
                continue
            out.add(iso)
            masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    return out


def date_supported(iso: str, dates: set[str]) -> bool:
    """A full ISO date is supported by an identical written day, or by a written month it falls in."""
    return iso in dates or any(len(d) == 7 and iso.startswith(d) for d in dates)


def cue_hit(qualifier: str | None, cues: Sequence[str]) -> bool:
    if not qualifier or not qualifier.strip():
        return False
    q = qualifier.casefold().strip()
    return any(c in q or q in c for c in cues)


# --------------------------------------------------------------------------- judgements

def load_judgements(path) -> dict[tuple[str, tuple], dict[str, str]]:
    """review/evaluator_judgements.csv -> {(row_id, fact_key): {verdict, note, reviewer}}.

    Columns: source_row_id, subject, attribute, value (JSON object or shorthand like '€59/month'),
             verdict (correct | incorrect | unclear), reviewer, note."""
    import json
    from pathlib import Path
    out: dict[tuple[str, tuple], dict[str, str]] = {}
    if not path or not Path(path).exists():
        return out
    for r in C.read_csv(path):
        raw = (r.get("value") or "").strip()
        value = json.loads(raw) if raw.startswith("{") else C.parse_shorthand(raw)
        key = C.fact_key(r.get("subject"), r.get("attribute"), value)
        verdict = (r.get("verdict") or "").strip().casefold()
        if key is None or verdict not in {"correct", "incorrect", "unclear"}:
            continue
        out[(r["source_row_id"], key)] = {"verdict": verdict, "note": r.get("note", ""), "reviewer": r.get("reviewer", "")}
    return out


# --------------------------------------------------------------------------- per-row counters

def _has_negation_trap(row: RowGold, gold: Sequence[GFact]) -> bool:
    return bool(C.NEGATION_RE.search(row.text)) or any(g.negated for g in gold)


def row_counts(row: RowGold, preds: Sequence[Pred], primary: str = "form",
               judgements: Mapping[tuple[str, tuple], Mapping[str, str]] | None = None
               ) -> tuple[Counter, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Counters of one row. Also returns (candidate_rows, miss_rows, temporal_cases) detail records for CSV export."""
    judgements = judgements or {}
    c: Counter = Counter()
    mapped: dict[tuple, Pred] = {}
    for p in preds:
        if p.mapped:
            if p.key in mapped:
                c["n_dup"] += 1
            else:
                mapped[p.key] = p
        else:
            c["n_unmapped"] += 1
    c["n_facts_raw"] = len(preds)
    c["n_pred"] = len(mapped)
    c["row_with_pred"] = 1 if mapped else 0

    for name, golds in row.sets.items():
        if name == "extra":
            continue
        gkeys = {g.key for g in golds}
        c[f"n_gold_{name}"] = len(gkeys)
        c[f"tp_{name}"] = len(gkeys & mapped.keys())

    form = row.sets["form"]
    form_keys = {g.key for g in form}
    extra_keys = {g.key for g in row.sets["extra"]}
    form_slots = {(g.subject, g.attribute) for g in form}

    # ---- candidates beyond the form
    candidates: list[dict[str, Any]] = []
    for key, p in mapped.items():
        if key in form_keys:
            continue
        in_sugg = key in extra_keys
        slot = (p.subject, p.attribute)
        conflict = slot in form_slots and not in_sugg
        verdict = (judgements.get((row.id, key)) or {}).get("verdict")
        c["x_total"] += 1
        c["x_matches_suggestion" if in_sugg else "x_not_in_suggestions"] += 1
        if verdict:
            c["x_reviewed"] += 1
            c[f"x_judged_{verdict}"] += 1
        elif not in_sugg:
            c["x_not_in_suggestions_unreviewed"] += 1
        if conflict and verdict != "correct":
            c["x_conflicts_with_form_slot"] += 1
        if verdict == "incorrect" or (conflict and verdict != "correct"):
            c["x_incorrect_known"] += 1
        candidates.append({"row": row.id, "extraction_id": p.raw.get("extraction_id"), "subject": p.subject, "attribute": p.attribute,
                           "value": C.fmt_value(p.value), "kind": p.kind, "negated": p.negated,
                           "matches_evaluator_suggestion": in_sugg, "conflicts_with_form_slot": conflict,
                           "judgement": verdict or "", "span": p.raw.get("source_text_span"), "text": row.text})

    c["n_pred_not_known_incorrect"] = c["n_pred"] - c["x_incorrect_known"]

    # ---- gold-side metrics against the primary set
    pg = row.sets[primary]
    pkeys = {g.key for g in pg}
    c["n_gold_primary"] = len(pkeys)
    c["tp_primary"] = len(pkeys & mapped.keys())
    subjects_any = {p.subject for p in preds if p.subject}
    slots_any = {(p.subject, p.attribute) for p in preds if p.subject and p.attribute}
    slots_mapped = {(p.subject, p.attribute) for p in mapped.values()}
    misses: list[dict[str, Any]] = []
    if pg:
        c["row_den"] = 1
        c["row_all_found"] = int(pkeys <= mapped.keys())
        c["row_exact_set"] = int(pkeys == mapped.keys())
    trap = _has_negation_trap(row, pg)
    for g in pg:
        hit = g.key in mapped
        sfx = "exp" if g.explicit else "imp"
        c["ent_den"] += 1
        c[f"ent_den_{sfx}"] += 1
        ent_ok = g.subject in subjects_any
        if ent_ok:
            c["ent_ok"] += 1
            c[f"ent_ok_{sfx}"] += 1
            c["attr_den"] += 1
            if (g.subject, g.attribute) in slots_any:
                c["attr_ok"] += 1
                c["val_den"] += 1
                c[f"val_den__{g.kind}"] += 1
                if hit:
                    c["val_ok"] += 1
                    c[f"val_ok__{g.kind}"] += 1
        c["slot_den"] += 1
        c["slot_ok"] += int((g.subject, g.attribute) in slots_mapped)
        c[f"n_gold__{g.kind}"] += 1
        c[f"tp_gold__{g.kind}"] += int(hit)
        # negation
        if g.negated:
            c["neg_den"] += 1
            c["neg_ok"] += int(hit and mapped[g.key].negated)
        elif hit:
            c["nonneg_den"] += 1
            c["nonneg_ok"] += int(not mapped[g.key].negated)
        if hit:
            c["negflag_den"] += 1
            c["negflag_ok"] += int(mapped[g.key].negated == g.negated)
        if trap:
            c["trap_den"] += 1
            c["trap_ok"] += int(hit and mapped[g.key].negated == g.negated)
        if not hit:
            if not ent_ok:
                why = "entity_not_found"
            elif (g.subject, g.attribute) not in slots_any:
                why = "attribute_not_found"
            elif (g.subject, g.attribute) not in slots_mapped:
                why = "slot_found_but_value_missing"
            else:
                why = "wrong_value"
            got = [C.fmt_value(p.value) for p in mapped.values() if (p.subject, p.attribute) == (g.subject, g.attribute)]
            misses.append({"row": row.id, "subject": g.subject, "attribute": g.attribute, "gold_value": C.fmt_value(g.value),
                           "kind": g.kind, "subject_written_in_text": g.explicit, "reason": why, "predicted_values_on_slot": " ; ".join(got),
                           "text": row.text})
    for key, p in mapped.items():
        k = p.kind or "none"
        c[f"n_pred__{k}"] += 1
        c[f"tp_pred__{k}"] += int(key in pkeys)

    # ---- temporal
    has_pred = bool(mapped)
    any_pred_q = [p for p in preds if p.raw.get("temporal_qualifier")]
    qualifiers = sorted({str(p.raw.get("temporal_qualifier")) for p in any_pred_q})
    cases: list[dict[str, Any]] = []
    if row.cues:
        c["t_cue_rows"] += 1
        hit_row = any(cue_hit(p.raw.get("temporal_qualifier"), row.cues) for p in preds)
        c["t_cue_hit"] += int(hit_row)
        cases.append({"row": row.id, "case": "cue_row", "cues": ";".join(row.cues), "qualifiers": ";".join(qualifiers),
                      "hit": hit_row, "has_mapped_fact": has_pred, "text": row.text})
        if has_pred:
            c["t_cue_rows_with_fact"] += 1
            c["t_cue_hit_given_fact"] += int(hit_row)
    elif has_pred:
        c["t_nocue_rows_with_fact"] += 1
        c["t_nocue_clean"] += int(not any_pred_q)
        if any_pred_q:
            cases.append({"row": row.id, "case": "qualifier_on_row_without_listed_cue", "cues": "", "qualifiers": ";".join(qualifiers),
                          "hit": "", "has_mapped_fact": True, "text": row.text})
    dates = text_dates(row.text)
    for p in mapped.values():
        for field_name in ("fact_observation_date", "valid_from", "valid_to"):
            d = p.raw.get(field_name)
            if d:
                c["t_dates_set"] += 1
                if date_supported(d, dates):
                    c["t_dates_supported"] += 1
                elif d == row.date:
                    c["t_dates_copied_page_date"] += 1
    return c, candidates, misses, cases


# --------------------------------------------------------------------------- metric definitions

def _ratio(num: str, den: str) -> tuple:
    return ("ratio", num, den)


def metric_specs(gold_sets: Sequence[str]) -> dict[str, tuple]:
    specs: dict[str, tuple] = {}
    for g in gold_sets:
        specs[f"precision_{g}"] = _ratio(f"tp_{g}", "n_pred")
        specs[f"recall_{g}"] = _ratio(f"tp_{g}", f"n_gold_{g}")
        specs[f"f1_{g}"] = ("f1", f"tp_{g}", "n_pred", f"n_gold_{g}")
    specs.update({
        "precision_approx_upper_bound": _ratio("n_pred_not_known_incorrect", "n_pred"),
        "exact_triple_accuracy": _ratio("tp_primary", "n_gold_primary"),
        "row_all_gold_facts_found": _ratio("row_all_found", "row_den"),
        "row_exact_set": _ratio("row_exact_set", "row_den"),
        "entity_accuracy": _ratio("ent_ok", "ent_den"),
        "entity_accuracy_subject_written": _ratio("ent_ok_exp", "ent_den_exp"),
        "entity_accuracy_subject_implicit": _ratio("ent_ok_imp", "ent_den_imp"),
        "attribute_accuracy_given_entity": _ratio("attr_ok", "attr_den"),
        "value_accuracy_given_entity_attribute": _ratio("val_ok", "val_den"),
        "slot_recall_any_value": _ratio("slot_ok", "slot_den"),
        "negation_recall": _ratio("neg_ok", "neg_den"),
        "negation_specificity": _ratio("nonneg_ok", "nonneg_den"),
        "negation_flag_accuracy_on_matched": _ratio("negflag_ok", "negflag_den"),
        "negation_trap_rows_exact": _ratio("trap_ok", "trap_den"),
        "temporal_cue_recall": _ratio("t_cue_hit", "t_cue_rows"),
        "temporal_cue_recall_given_fact": _ratio("t_cue_hit_given_fact", "t_cue_rows_with_fact"),
        "temporal_abstention_on_no_cue_rows": _ratio("t_nocue_clean", "t_nocue_rows_with_fact"),
        "temporal_dates_supported_by_text": _ratio("t_dates_supported", "t_dates_set"),
        "share_of_extras_reviewed_incorrect": _ratio("x_judged_incorrect", "x_reviewed"),
    })
    for k in KINDS:
        specs[f"recall_{k}"] = _ratio(f"tp_gold__{k}", f"n_gold__{k}")
        specs[f"precision_{k}"] = _ratio(f"tp_pred__{k}", f"n_pred__{k}")
        specs[f"value_accuracy_{k}"] = _ratio(f"val_ok__{k}", f"val_den__{k}")
    return specs


def _div(n, d):
    n, d = np.asarray(n, dtype=float), np.asarray(d, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(d > 0, n / np.where(d > 0, d, 1.0), np.nan)
    return float(out) if out.ndim == 0 else out


def evaluate_spec(spec: tuple, sums: Mapping[str, Any]):
    get = lambda k: sums.get(k, 0.0)  # noqa: E731
    if spec[0] == "ratio":
        return _div(get(spec[1]), get(spec[2]))
    if spec[0] == "f1":
        return _div(2 * np.asarray(get(spec[1]), dtype=float), np.asarray(get(spec[2]), dtype=float) + np.asarray(get(spec[3]), dtype=float))
    raise ValueError(spec)


def spec_counts(spec: tuple, sums: Mapping[str, Any]) -> tuple[float, float]:
    """(numerator, denominator) for display; F1 shows 2*tp over predicted + gold."""
    if spec[0] == "ratio":
        return sums.get(spec[1], 0), sums.get(spec[2], 0)
    return 2 * sums.get(spec[1], 0), sums.get(spec[2], 0) + sums.get(spec[3], 0)


# --------------------------------------------------------------------------- aggregation and bootstrap

class CounterTable:
    """rows x counters matrix (int) with row ids; sums over row subsets; bootstrap."""

    def __init__(self, row_ids: Sequence[str], counters: Sequence[Counter]):
        self.row_ids = list(row_ids)
        self.names = sorted({k for c in counters for k in c})
        index = {n: i for i, n in enumerate(self.names)}
        self.matrix = np.zeros((len(counters), len(self.names)), dtype=float)
        for r, c in enumerate(counters):
            for k, v in c.items():
                self.matrix[r, index[k]] = v
        self._index = index

    def sums(self, mask: np.ndarray | None = None) -> dict[str, float]:
        m = self.matrix if mask is None else self.matrix[mask]
        total = m.sum(axis=0) if len(m) else np.zeros(len(self.names))
        return defaultdict(float, {n: float(total[i]) for n, i in self._index.items()})   # absent counter = 0

    def resampled(self, idx: np.ndarray, mask: np.ndarray | None = None) -> dict[str, np.ndarray]:
        """idx: B x n indices into the (masked) rows. Returns name -> length-B vector of resampled sums."""
        m = self.matrix if mask is None else self.matrix[mask]
        sums = m[idx].sum(axis=1)          # B x K
        return {n: sums[:, i] for n, i in self._index.items()}


def bootstrap_indices(n_rows: int, n_boot: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, n_rows, size=(n_boot, n_rows))


def ci_from_samples(samples: np.ndarray, level: float = 0.95, max_nan_share: float = 0.2) -> tuple[float, float] | None:
    samples = np.asarray(samples, dtype=float)
    if samples.size == 0 or np.isnan(samples).mean() > max_nan_share:
        return None
    lo, hi = np.nanpercentile(samples, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def metric_table(table: CounterTable, specs: Mapping[str, tuple], idx: np.ndarray | None,
                 mask: np.ndarray | None = None) -> dict[str, dict[str, Any]]:
    """Point estimate, counts and bootstrap CI for every spec (rows restricted by `mask`)."""
    sums = table.sums(mask)
    n = int(table.matrix.shape[0] if mask is None else mask.sum())
    boot = None
    if idx is not None and n > 0:
        if mask is None:
            boot = table.resampled(idx)
        else:
            sub_idx = np.random.default_rng(0).integers(0, n, size=(idx.shape[0], n)) if idx.shape[1] != n else idx
            boot = table.resampled(sub_idx, mask)
    out = {}
    for name, spec in specs.items():
        value = evaluate_spec(spec, sums)
        num, den = spec_counts(spec, sums)
        ci = ci_from_samples(evaluate_spec(spec, boot)) if boot is not None and den > 0 else None
        out[name] = {"value": None if (isinstance(value, float) and np.isnan(value)) else value,
                     "num": num, "den": den, "ci95": ci}
    return out


def paired_difference(a: CounterTable, b: CounterTable, spec: tuple, idx: np.ndarray) -> dict[str, Any]:
    """Cluster-bootstrap difference (a - b) of one metric, same resampled rows for both tables."""
    assert a.row_ids == b.row_ids
    point = evaluate_spec(spec, a.sums()) - evaluate_spec(spec, b.sums())
    diff = evaluate_spec(spec, a.resampled(idx)) - evaluate_spec(spec, b.resampled(idx))
    ci = ci_from_samples(diff)
    valid = diff[~np.isnan(diff)]
    return {"difference": None if np.isnan(point) else float(point), "ci95": ci,
            "bootstrap_share_a_greater": float((valid > 0).mean()) if valid.size else None}


def stratum_masks(rows: Sequence[RowGold]) -> dict[str, np.ndarray]:
    names = sorted({s for r in rows for s in r.strata})
    return {s: np.array([s in r.strata for r in rows]) for s in names}


def split_masks(rows: Sequence[RowGold]) -> dict[str, np.ndarray]:
    return {s: np.array([r.split == s for r in rows]) for s in sorted({r.split for r in rows})}


def evaluate_method(rows: Sequence[RowGold], preds: Mapping[str, Sequence[Pred]], primary: str = "form",
                    judgements: Mapping[tuple[str, tuple], Mapping[str, str]] | None = None):
    counters: list[Counter] = []
    candidates: list[dict[str, Any]] = []
    misses: list[dict[str, Any]] = []
    cases: list[dict[str, Any]] = []
    for row in rows:
        c, cand, miss, case = row_counts(row, preds.get(row.id, []), primary, judgements)
        counters.append(c)
        candidates.extend(cand)
        misses.extend(miss)
        cases.extend(case)
    return CounterTable([r.id for r in rows], counters), candidates, misses, cases
