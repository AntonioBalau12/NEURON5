"""Library behind evaluate.py and ingest_worksheet.py: method resolution, the evaluation run, the markdown summary.

Named reporting.py because the repository root has its own evaluate.py, which would shadow an importable evaluate module."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import metrics as M  # noqa: E402

DEFAULT_SEED = 20261028
HEADLINE = ["precision_form", "recall_form", "f1_form", "precision_suggested", "recall_suggested", "f1_suggested"]


# --------------------------------------------------------------------------- method resolution

def resolve_methods(names: Sequence[str]) -> tuple[dict[str, Path], list[str]]:
    found: dict[str, Path] = {}
    skipped: list[str] = []
    for name in names:
        if "=" in name:
            label, path = name.split("=", 1)
            candidates = {label: Path(path)}
        elif name == "combined":
            candidates = {p.name[:-len("_facts.jsonl")]: p for p in sorted(C.OUTPUT_DIR.glob("combined_*_facts.jsonl"))}
            if not candidates:
                skipped.append("combined: no output/combined_*_facts.jsonl yet (run combine.py after openie and slot_filling exist)")
                continue
        elif name in C.METHOD_FILES:
            candidates = {name: C.METHOD_FILES[name]}
        elif name.startswith("combined_"):
            candidates = {name: C.OUTPUT_DIR / f"{name}_facts.jsonl"}
        else:
            skipped.append(f"{name}: unknown method name")
            continue
        for label, path in candidates.items():
            if path.exists():
                found[label] = path
            else:
                skipped.append(f"{label}: facts file not found ({path})")
    return found, skipped


# --------------------------------------------------------------------------- formatting

def fmt_pct(m: dict[str, Any], digits: int = 1) -> str:
    if m is None or m["value"] is None:
        return "n/a"
    s = f"{100 * m['value']:.{digits}f}%"
    if m["ci95"]:
        s += f" [{100 * m['ci95'][0]:.0f}-{100 * m['ci95'][1]:.0f}]"
    return s + f" ({m['num']:.0f}/{m['den']:.0f})"


def md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out)


def write_csv_dicts(path: Path, rows: list[dict[str, Any]], fields: Sequence[str] | None = None) -> None:
    fields = list(fields or (rows[0].keys() if rows else ["empty"]))
    C.write_csv(path, fields, rows)


# --------------------------------------------------------------------------- core

def run(methods: dict[str, Path], out_dir: Path, rows: list[M.RowGold], gold_sets: Sequence[str], primary: str,
        judgements: dict, n_boot: int, seed: int, title: str, extra_config: dict[str, Any] | None = None,
        resources: dict[str, Any] | None = None, skipped: Sequence[str] = ()) -> dict[str, Any]:
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing results folder: {out_dir}")
    out_dir.mkdir(parents=True)
    all_rows = C.fact_schema.load_input_rows()
    specs = M.metric_specs(list(gold_sets))
    idx = M.bootstrap_indices(len(rows), n_boot, seed)
    strata = M.stratum_masks(rows)
    splits = M.split_masks(rows)
    kinds_in_gold = sorted({g.kind for r in rows for g in r.sets[primary]})

    results: dict[str, Any] = {}
    tables: dict[str, M.CounterTable] = {}
    file_info: dict[str, Any] = {}
    unique_candidates: dict[tuple, dict[str, Any]] = {}
    for name, path in methods.items():
        facts, info = C.load_facts(path, all_rows)
        ids = {r.id for r in rows}
        in_eval = [f for f in facts if f["source_row_id"] in ids]
        preds = M.group_preds(in_eval, ids)
        table, cands, misses, cases = M.evaluate_method(rows, preds, primary, judgements)
        tables[name] = table
        covered_all = len({f["source_row_id"] for f in facts})
        file_info[name] = {
            "path": str(path), "sha1": C.sha1_file(path), "lines": info["lines"], "valid_facts": info["valid"], "invalid_dropped": info["invalid"],
            "invalid_examples": info["invalid_examples"], "rows_with_a_fact_in_file": covered_all, "rows_in_full_input": len(all_rows),
            "facts_on_eval_rows": len(in_eval), "eval_rows_with_a_fact": sum(1 for r in rows if preds.get(r.id)),
            "methods_in_file": sorted({f["extraction_method"] for f in facts}),
        }
        res: dict[str, Any] = {"overall": M.metric_table(table, specs, idx)}
        res["by_split"] = {s: {"n_rows": int(m.sum()), **M.metric_table(table, specs, idx, m)} for s, m in splits.items()}
        res["by_stratum"] = {s: {"n_rows": int(m.sum()), "metrics": M.metric_table(table, specs, idx, m)} for s, m in strata.items()}
        sums = table.sums()
        res["counts"] = {k: sums.get(k, 0) for k in (
            "n_facts_raw", "n_pred", "n_dup", "n_unmapped", "n_gold_form", "tp_form", "n_gold_suggested", "tp_suggested",
            "x_total", "x_matches_suggestion", "x_not_in_suggestions", "x_reviewed", "x_judged_correct", "x_judged_incorrect",
            "x_judged_unclear", "x_not_in_suggestions_unreviewed", "x_conflicts_with_form_slot", "x_incorrect_known",
            "t_cue_rows", "t_dates_set", "t_dates_copied_page_date")}
        res["counts"]["n_gold_extra_suggestions"] = sum(len(r.sets["extra"]) for r in rows)
        results[name] = res

        mdir = out_dir / "per_method" / name
        write_csv_dicts(mdir / "missed_gold_facts.csv", misses, ["row", "subject", "attribute", "gold_value", "kind", "subject_written_in_text",
                                                                  "reason", "predicted_values_on_slot", "text"])
        write_csv_dicts(mdir / "unverified_candidates_beyond_form.csv", cands, ["row", "extraction_id", "subject", "attribute", "value", "kind",
                                                                                "negated", "matches_evaluator_suggestion",
                                                                                "conflicts_with_form_slot", "judgement", "span", "text"])
        write_csv_dicts(mdir / "temporal_cases.csv", cases, ["row", "case", "cues", "qualifiers", "hit", "has_mapped_fact", "text"])
        C.write_csv(mdir / "row_level_counters.csv", ["row"] + table.names,
                    [{"row": rid, **{n: table.matrix[i, j] for j, n in enumerate(table.names)}} for i, rid in enumerate(table.row_ids)])
        for cand in cands:
            if not cand["judgement"]:
                key = (cand["row"], cand["subject"], cand["attribute"], cand["value"])
                unique_candidates.setdefault(key, {"source_row_id": cand["row"], "subject": cand["subject"], "attribute": cand["attribute"],
                                                  "value": cand["value"], "verdict": "", "reviewer": "", "note": "", "text": cand["text"],
                                                  "extracted_by": name})
                if name not in unique_candidates[key]["extracted_by"].split(","):
                    unique_candidates[key]["extracted_by"] += "," + name

    # pairwise differences against the first method
    comparisons: dict[str, Any] = {}
    names = list(tables)
    if len(names) > 1:
        ref_name = "baseline" if "baseline" in tables else names[0]
        for other in names:
            if other == ref_name:
                continue
            comparisons[f"{other} minus {ref_name}"] = {
                m: M.paired_difference(tables[other], tables[ref_name], specs[m], idx)
                for m in HEADLINE if m.split("_", 1)[1] in gold_sets}
    write_csv_dicts(out_dir / "judgement_template_unreviewed_candidates.csv", sorted(unique_candidates.values(), key=lambda r: C.row_sort_key(r["source_row_id"])),
                    ["source_row_id", "subject", "attribute", "value", "verdict", "reviewer", "note", "extracted_by", "text"])

    config = {
        "title": title, "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "command": " ".join(sys.argv), "python": platform.python_version(), "numpy": np.__version__,
        "bootstrap": {"B": n_boot, "seed": seed, "unit": "evaluation row (cluster bootstrap)", "interval": "percentile 95%"},
        "eval_rows_sha1": C.sha1_file(C.EVAL_ROWS), "reference_sha1": C.sha1_file(C.WORKSHEET_DIR / "evaluator_reference.json"),
        "n_rows": len(rows), "n_form_facts": sum(len(r.sets["form"]) for r in rows),
        "n_suggested_extra_facts": sum(len(r.sets["extra"]) for r in rows), "gold_sets": list(gold_sets), "primary_gold": primary,
        "n_judgements_loaded": len(judgements), "files": file_info, "skipped_methods": list(skipped),
        "value_equivalence": "foundation._canonical_value_key via common.value_key",
    }
    config.update(extra_config or {})
    payload = {"config": config, "methods": results, "paired_differences_vs_reference": comparisons, "resources": resources}
    (out_dir / "metrics.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_summary(payload, rows, gold_sets, primary, kinds_in_gold), encoding="utf-8")
    return payload


def render_summary(payload: dict[str, Any], rows: list[M.RowGold], gold_sets: Sequence[str], primary: str, kinds: Sequence[str]) -> str:
    cfg, methods = payload["config"], payload["methods"]
    names = list(methods)
    L: list[str] = [f"# {cfg['title']}", "",
                    f"Created {cfg['created_utc']}. Command: `{cfg['command']}`", "",
                    f"Evaluation rows: **{cfg['n_rows']}** ({sum(1 for r in rows if r.split == 'heldout')} held-out, "
                    f"{sum(1 for r in rows if r.split == 'dev')} dev control). Form facts: **{cfg['n_form_facts']}**. "
                    f"Evaluator-suggested extra facts: **{cfg['n_suggested_extra_facts']}** (unverified). "
                    f"Primary gold for the component metrics: `{primary}`.",
                    f"Bootstrap: {cfg['bootstrap']['B']} resamples of rows, seed {cfg['bootstrap']['seed']}; cells read `value [95% interval] (numerator/denominator)`.", ""]
    if cfg["skipped_methods"]:
        L += ["**Skipped methods:**"] + [f"- {s}" for s in cfg["skipped_methods"]] + [""]
    L += ["> **Small-sample caveat.** The set is small and purposive, not a random sample of the dataset. Intervals only capture row sampling noise, "
          "not label noise, the incompleteness of the form, or the stratification. Differences between methods inside each other's intervals "
          "should not be reported as differences. Absolute numbers do not generalise to the whole dataset.", ""]

    def row(label, key, group="overall"):
        return [label] + [fmt_pct(methods[n][group][key]) for n in names]

    L += ["## 1. Atomic fact precision / recall", "",
          "`form` = facts of the dataset form (incomplete): precision against it is a *lower bound* of true precision and recall a *lower bound* of recall of what the sentence states. "
          "`suggested` = form + evaluator suggestions (unverified).", ""]
    hdr = ["metric"] + names
    tbl = []
    for g in gold_sets:
        tbl += [row(f"precision vs {g}", f"precision_{g}"), row(f"recall vs {g}", f"recall_{g}"), row(f"F1 vs {g}", f"f1_{g}")]
    tbl += [row("precision approx. upper bound (all extras not known wrong are right)", "precision_approx_upper_bound")]
    L += [md_table(hdr, tbl), ""]

    L += ["## 2. Facts beyond the form and incorrect extractions", ""]
    rows2 = []
    for label, key in [("mapped facts on eval rows (distinct)", "n_pred"), ("duplicates dropped", "n_dup"), ("unmapped/abstained records", "n_unmapped"),
                       ("matching a form fact", "tp_form"),
                       ("**beyond the form (unverified candidates)**", "x_total"),
                       ("&nbsp;&nbsp;matching an evaluator suggestion", "x_matches_suggestion"),
                       ("&nbsp;&nbsp;not matching any suggestion", "x_not_in_suggestions"),
                       ("&nbsp;&nbsp;reviewed (judgements file)", "x_reviewed"),
                       ("&nbsp;&nbsp;judged correct", "x_judged_correct"), ("&nbsp;&nbsp;judged incorrect", "x_judged_incorrect"),
                       ("&nbsp;&nbsp;judged unclear", "x_judged_unclear"),
                       ("&nbsp;&nbsp;not reviewed and not suggested", "x_not_in_suggestions_unreviewed"),
                       ("different value on a slot the form fills (likely wrong, automatic)", "x_conflicts_with_form_slot"),
                       ("**known or likely incorrect**", "x_incorrect_known")]:
        rows2.append([label] + [f"{methods[n]['counts'][key]:.0f}" for n in names])
    L += [md_table(hdr, rows2), "",
          "`known or likely incorrect` = judged incorrect + conflicting with a form slot (unless judged correct). Extras that are neither suggested nor reviewed "
          "are *unknown*: they may be right (the form is incomplete) or wrong. Review them with "
          "`judgement_template_unreviewed_candidates.csv` and pass the filled file with `--judgements`.", ""]

    L += ["## 3. Component accuracy (against the primary gold)", ""]
    comp = [("exact canonical triple (= recall vs primary)", "exact_triple_accuracy"),
            ("rows where all gold facts are found", "row_all_gold_facts_found"),
            ("rows where the fact set equals the gold set", "row_exact_set"),
            ("entity recognition", "entity_accuracy"),
            ("&nbsp;&nbsp;subject written in the sentence", "entity_accuracy_subject_written"),
            ("&nbsp;&nbsp;subject implicit (context only)", "entity_accuracy_subject_implicit"),
            ("attribute mapping, given entity correct", "attribute_accuracy_given_entity"),
            ("value, given entity and attribute correct", "value_accuracy_given_entity_attribute"),
            ("gold slot filled with any value", "slot_recall_any_value")]
    L += [md_table(hdr, [row(a, b) for a, b in comp]), ""]

    L += ["## 4. Negation and temporal extraction", "",
          "Negation gold: boolean-false form facts must be extracted with `negated=true` (EXCHANGE_FORMAT). "
          "Temporal gold: cue words found by a regex plus evaluator override (`temporal_cues` in `evaluator_reference.json`); **no sentence of the set states an explicit observation date**, "
          "so only cue capture and non-fabrication can be measured. Validity intervals are not evaluated.", ""]
    neg = [("negation recall (false facts found with negated=true)", "negation_recall"),
           ("negation specificity (matched non-negated facts with negated=false)", "negation_specificity"),
           ("negated flag correct on matched facts", "negation_flag_accuracy_on_matched"),
           ("exact fact + flag in rows with negation words", "negation_trap_rows_exact"),
           ("temporal cue captured in temporal_qualifier (cue rows)", "temporal_cue_recall"),
           ("&nbsp;&nbsp;given the method extracted a fact there", "temporal_cue_recall_given_fact"),
           ("no qualifier on rows without a listed cue (with a fact)", "temporal_abstention_on_no_cue_rows"),
           ("dates set in observation/validity fields that the text supports", "temporal_dates_supported_by_text")]
    neg_rows = [row(a, b) for a, b in neg]
    neg_rows += [["observation/validity dates set (count)"] + [f"{methods[n]['counts']['t_dates_set']:.0f}" for n in names],
                 ["&nbsp;&nbsp;of which equal to the page date (count)"] + [f"{methods[n]['counts']['t_dates_copied_page_date']:.0f}" for n in names]]
    L += [md_table(hdr, neg_rows), ""]

    L += ["## 5. By value kind (against the primary gold)", ""]
    kt = []
    for k in kinds:
        kt.append([f"{k}: recall"] + [fmt_pct(methods[n]["overall"][f"recall_{k}"]) for n in names])
        kt.append([f"{k}: precision"] + [fmt_pct(methods[n]["overall"][f"precision_{k}"]) for n in names])
        kt.append([f"{k}: value given entity+attr ok"] + [fmt_pct(methods[n]["overall"][f"value_accuracy_{k}"]) for n in names])
    L += [md_table(hdr, kt), ""]

    L += ["## 6. By stratum (rows may be in several strata; recall/precision against form)", ""]
    snames = sorted({s for n in names for s in methods[n]["by_stratum"]})
    st = []
    for s in snames:
        n_rows = next(methods[n]["by_stratum"][s]["n_rows"] for n in names if s in methods[n]["by_stratum"])
        st.append([f"{s} (n={n_rows})"] + [fmt_pct(methods[n]["by_stratum"][s]["metrics"]["recall_form"], 0) + " / " + fmt_pct(methods[n]["by_stratum"][s]["metrics"]["precision_form"], 0)
                                           if s in methods[n]["by_stratum"] else "" for n in names])
    L += ["Cells: recall / precision.", "", md_table(hdr, st), ""]

    L += ["## 7. Held-out versus dev control rows", "",
          "Methods were tuned on dev rows, so dev rows are a *control*: a method that is much better on the 15 dev rows than on the 120 held-out rows is overfitted.", ""]
    sp = []
    for s in sorted({s for n in names for s in methods[n]["by_split"]}):
        for key in ("recall_form", "precision_form"):
            sp.append([f"{s}: {key}"] + [fmt_pct(methods[n]["by_split"][s][key]) for n in names])
    L += [md_table(hdr, sp), ""]

    if payload["paired_differences_vs_reference"]:
        L += ["## 8. Paired differences (same resampled rows)", ""]
        pd_rows = []
        for label, d in payload["paired_differences_vs_reference"].items():
            for m, v in d.items():
                ci = f" [{100 * v['ci95'][0]:.0f}, {100 * v['ci95'][1]:.0f}]" if v["ci95"] else ""
                pd_rows.append([label, m, "n/a" if v["difference"] is None else f"{100 * v['difference']:+.1f} pts{ci}"])
        L += [md_table(["comparison", "metric", "difference (95% interval)"], pd_rows), ""]

    L += ["## 9. Resources", ""]
    res = payload.get("resources")
    if res:
        rr = []
        for n in names:
            r = (res.get("methods") or {}).get(n)
            rr.append([n] + ([f"{r.get('cpu_seconds')}", f"{r.get('wall_seconds')}", f"{r.get('peak_working_set_mb')}", f"{r.get('returncode')}"] if r else ["not measured"] * 4))
        L += [md_table(["method", "CPU s", "wall s", "peak working set MB", "exit code"], rr), ""]
    else:
        L += ["Not measured in this run. Use `measure_resources.py` and pass `--resources <json>`.", ""]

    L += ["## 10. Files and coverage", ""]
    fi = [[n, cfg["files"][n]["path"].replace(str(C.ROOT), "."), cfg["files"][n]["valid_facts"], cfg["files"][n]["invalid_dropped"],
           f"{cfg['files'][n]['rows_with_a_fact_in_file']}/{cfg['files'][n]['rows_in_full_input']}",
           f"{cfg['files'][n]['eval_rows_with_a_fact']}/{cfg['n_rows']}", cfg["files"][n]["sha1"][:10]] for n in names]
    L += [md_table(["method", "file", "valid facts", "invalid dropped", "rows with a fact (all)", "eval rows with a fact", "sha1"], fi), ""]
    return "\n".join(L)
