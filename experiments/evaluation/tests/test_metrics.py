"""Tests of the metric code with synthetic fact lists (no extractor output, no gold files).

  py -m pytest experiments/evaluation/tests -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import metrics as M  # noqa: E402

G = "Hooly Gemini"


def q(value, unit, **kw):
    return {"kind": "quantity", "value": value, "unit": unit, **kw}


def dur(value, unit, **kw):
    return {"kind": "duration", "value": value, "unit": unit, **kw}


def boolean(v):
    return {"kind": "boolean", "value": v}


def gold_row(rid, text, form, extra=(), split="heldout", strata=(), cues=(), date="2026-03-01", label="true"):
    """RowGold with form facts [(subject, attribute, value)] and suggested extras."""
    mentioned = {name for _, _, name in C.mention_spans(text)}
    f = M.dedupe(M.make_gfact(s, a, v, mentioned, "form", f"F{i}") for i, (s, a, v) in enumerate(form, 1))
    x = M.dedupe(M.make_gfact(s, a, v, mentioned, "suggested", f"S{i}") for i, (s, a, v) in enumerate(extra, 1))
    row = M.RowGold(rid, text, date, label, split, frozenset(strata), tuple(cues))
    row.sets = {"form": f, "extra": x, "suggested": f + x}
    return row


def pred(rid, subject, attribute, value, **kw):
    fact = {"source_row_id": rid, "subject": subject, "attribute": attribute, "value": value, "parse_status": "partial",
            "negated": False, "extraction_id": f"{rid}#t#{subject}{attribute}{json.dumps(value, sort_keys=True)}",
            "temporal_qualifier": None, "fact_observation_date": None, "valid_from": None, "valid_to": None,
            "source_text_span": "x"}
    fact.update(kw)
    return fact


def evaluate(rows, facts, primary="form", judgements=None, sets=("form", "suggested")):
    preds = M.group_preds(facts, [r.id for r in rows])
    table, cands, misses, cases = M.evaluate_method(rows, preds, primary, judgements)
    specs = M.metric_specs(list(sets))
    res = M.metric_table(table, specs, None)
    return {k: v["value"] for k, v in res.items()}, res, table, cands, misses, cases


# --------------------------------------------------------------------------- precision / recall

def test_perfect_prediction():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, *_ = evaluate(rows, [pred("r1", G, "languages", q(12, "language"))])
    assert v["precision_form"] == v["recall_form"] == v["f1_form"] == 1.0
    assert v["exact_triple_accuracy"] == 1.0 and v["row_exact_set"] == 1.0


def test_precision_recall_counts():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages and answers in 1.4 s.",
                     [(G, "languages", q(12, "language")), (G, "median_response_time", dur(1.4, "s"))])]
    facts = [pred("r1", G, "languages", q(12, "language")),               # TP
             pred("r1", G, "context_window", q(5, "token"))]              # beyond the form
    v, res, *_ = evaluate(rows, facts)
    assert v["precision_form"] == pytest.approx(1 / 2)
    assert v["recall_form"] == pytest.approx(1 / 2)
    assert v["f1_form"] == pytest.approx(0.5)
    assert res["recall_form"]["num"] == 1 and res["recall_form"]["den"] == 2


def test_empty_prediction_has_zero_recall_and_undefined_precision():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, *_ = evaluate(rows, [])
    assert v["recall_form"] == 0.0
    assert v["precision_form"] is None          # no prediction: not 0 and not 1
    assert v["f1_form"] == 0.0


def test_duplicates_count_once():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    f = pred("r1", G, "languages", q(12, "language"))
    v, res, table, *_ = evaluate(rows, [f, dict(f, extraction_id="other")])
    assert v["precision_form"] == 1.0
    assert table.sums()["n_dup"] == 1 and table.sums()["n_pred"] == 1


def test_unmapped_facts_are_not_predictions():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    unmapped = pred("r1", G, None, None, parse_status="unmapped")
    v, res, table, *_ = evaluate(rows, [unmapped])
    assert table.sums()["n_pred"] == 0 and table.sums()["n_unmapped"] == 1
    assert v["entity_accuracy"] == 1.0          # entity found even though nothing was mapped
    assert v["attribute_accuracy_given_entity"] == 0.0


# --------------------------------------------------------------------------- value equivalence

@pytest.mark.parametrize("gold,got,same", [
    (dur(2, "week"), dur(14, "day"), True),
    (dur(24, "h"), dur(1, "day"), True),
    (dur(1, "month"), dur(30, "day"), False),                   # month does not convert to days
    (q(1, "GB"), q(1000, "MB"), True),
    (q(1, "GB"), q(1, "MB"), False),
    (q(3, "customer"), q(3, "Customers"), True),                # counted nouns singularised
    (q(40000, "user"), q(40000, "user", op="gt"), False),       # op is part of the value
    (q(40000, "user", op="eq"), q(40000, "user"), True),
    ({"kind": "money", "value": 59, "currency": "EUR", "per": "month"}, {"kind": "money", "value": 59, "currency": "EUR"}, False),
    ({"kind": "money", "value": 59, "currency": "EUR", "per": "month"}, {"kind": "money", "value": 59.0, "currency": "EUR", "per": "month"}, True),
    ({"kind": "date", "value": "2026-03"}, {"kind": "date", "value": "2026-03-12"}, False),
    ({"kind": "version", "value": "2.3"}, {"kind": "version", "value": "2.3.0"}, False),
    ({"kind": "name", "value": "Gemini"}, {"kind": "name", "value": "Hooly Gemini"}, True),     # alias through the lexicon
    ({"kind": "percent", "value": 99.9}, {"kind": "percent", "value": 99.99}, False),
])
def test_value_equivalence(gold, got, same):
    assert (C.value_key(gold) == C.value_key(got)) is same


def test_subject_alias_resolves():
    rows = [gold_row("r1", "Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, *_ = evaluate(rows, [pred("r1", "Gemini", "languages", q(12, "language"))])
    assert v["recall_form"] == 1.0


def test_unit_conversion_counts_as_match():
    rows = [gold_row("r1", "A free trial of two weeks.", [("Hooly AI Pro", "free_trial", dur(2, "week"))])]
    v, *_ = evaluate(rows, [pred("r1", "Hooly AI Pro", "free_trial", dur(14, "day"))])
    assert v["recall_form"] == 1.0


# --------------------------------------------------------------------------- component accuracies

def test_entity_attribute_value_chain():
    text = "Hooly Gemini speaks 12 languages; Hooly AI Pro has a 7-day trial; Hooly Search serves 62 languages."
    rows = [gold_row("r1", text, [(G, "languages", q(12, "language")),
                                  ("Hooly AI Pro", "free_trial", dur(7, "day")),
                                  ("Hooly Search", "languages_served", q(62, "language"))])]
    facts = [pred("r1", G, "languages", q(12, "language")),                 # fully right
             pred("r1", "Hooly AI Pro", "history_retention", dur(7, "day")),  # entity right, attribute wrong
             pred("r1", "Hooly Pixel Fold", "weight", q(250, "g"))]           # Hooly Search entity never found
    v, res, *_ = evaluate(rows, facts)
    assert res["entity_accuracy"]["num"] == 2 and res["entity_accuracy"]["den"] == 3
    assert res["attribute_accuracy_given_entity"]["num"] == 1 and res["attribute_accuracy_given_entity"]["den"] == 2
    assert res["value_accuracy_given_entity_attribute"]["num"] == 1 and res["value_accuracy_given_entity_attribute"]["den"] == 1


def test_value_wrong_is_attribute_ok_value_not_ok():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, res, table, cands, misses, _ = evaluate(rows, [pred("r1", G, "languages", q(13, "language"))])
    assert v["attribute_accuracy_given_entity"] == 1.0 and v["value_accuracy_given_entity_attribute"] == 0.0
    assert misses[0]["reason"] == "wrong_value"
    # the wrong value is also a candidate that conflicts with the form slot
    assert cands[0]["conflicts_with_form_slot"] is True and table.sums()["x_incorrect_known"] == 1
    assert v["precision_approx_upper_bound"] == 0.0


def test_implicit_subject_is_reported_separately():
    # the subject is not written in the sentence
    rows = [gold_row("r1", "It speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, res, *_ = evaluate(rows, [])
    assert res["entity_accuracy_subject_implicit"]["den"] == 1 and res["entity_accuracy_subject_written"]["den"] == 0


def test_row_level_metrics():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages and answers in 1.4 s.",
                     [(G, "languages", q(12, "language")), (G, "median_response_time", dur(1.4, "s"))])]
    both = [pred("r1", G, "languages", q(12, "language")), pred("r1", G, "median_response_time", dur(1.4, "s"))]
    v, *_ = evaluate(rows, both)
    assert v["row_all_gold_facts_found"] == 1.0 and v["row_exact_set"] == 1.0
    v, *_ = evaluate(rows, both + [pred("r1", G, "context_window", q(5, "token"))])
    assert v["row_all_gold_facts_found"] == 1.0 and v["row_exact_set"] == 0.0


# --------------------------------------------------------------------------- beyond the form

def test_extras_split_by_suggestion_and_judgement():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages, runs on Nimbus Cloud and holds 200,000 tokens.",
                     [(G, "languages", q(12, "language"))],
                     extra=[(G, "cloud_provider", {"kind": "name", "value": "Nimbus Cloud"})])]
    facts = [pred("r1", G, "languages", q(12, "language")),
             pred("r1", G, "cloud_provider", {"kind": "name", "value": "Nimbus Cloud"}),     # matches a suggestion
             pred("r1", G, "context_window", q(200000, "token")),                            # unreviewed
             pred("r1", G, "max_upload_size", q(5, "MB"))]                                   # judged incorrect
    j = {("r1", C.fact_key(G, "max_upload_size", q(5, "MB"))): {"verdict": "incorrect", "note": "", "reviewer": "t"}}
    v, res, table, cands, *_ = evaluate(rows, facts, judgements=j)
    s = table.sums()
    assert s["x_total"] == 3 and s["x_matches_suggestion"] == 1 and s["x_not_in_suggestions"] == 2
    assert s["x_reviewed"] == 1 and s["x_judged_incorrect"] == 1 and s["x_not_in_suggestions_unreviewed"] == 1
    assert s["x_incorrect_known"] == 1
    assert v["precision_form"] == pytest.approx(1 / 4)
    assert v["precision_suggested"] == pytest.approx(2 / 4)
    assert v["precision_approx_upper_bound"] == pytest.approx(3 / 4)
    assert v["recall_suggested"] == pytest.approx(1.0) and v["recall_form"] == 1.0


def test_judged_correct_extra_overrides_automatic_conflict():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    extra = pred("r1", G, "languages", q(13, "language"))
    j = {("r1", C.fact_key(G, "languages", q(13, "language"))): {"verdict": "correct", "note": "", "reviewer": "t"}}
    _, _, table, *_ = evaluate(rows, [extra], judgements=j)
    assert table.sums()["x_incorrect_known"] == 0 and table.sums()["x_judged_correct"] == 1


# --------------------------------------------------------------------------- negation

def test_negation_metrics():
    rows = [gold_row("r1", "Hooly Search has no AI answers yet.", [("Hooly Search", "ai_answers", boolean(False))]),
            gold_row("r2", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    # r1: right fact but negated flag missing; r2: right fact, right flag
    facts = [pred("r1", "Hooly Search", "ai_answers", boolean(False), negated=False),
             pred("r2", G, "languages", q(12, "language"))]
    v, res, *_ = evaluate(rows, facts)
    assert v["negation_recall"] == 0.0 and res["negation_recall"]["den"] == 1
    assert v["negation_specificity"] == 1.0
    assert v["negation_flag_accuracy_on_matched"] == pytest.approx(1 / 2)
    facts[0]["negated"] = True
    v, *_ = evaluate(rows, facts)
    assert v["negation_recall"] == 1.0 and v["negation_flag_accuracy_on_matched"] == 1.0
    assert v["negation_trap_rows_exact"] == 1.0


def test_false_negation_flag_on_plain_fact_is_penalised():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))])]
    v, *_ = evaluate(rows, [pred("r1", G, "languages", q(12, "language"), negated=True)])
    assert v["negation_specificity"] == 0.0 and v["recall_form"] == 1.0


# --------------------------------------------------------------------------- temporal

def test_temporal_metrics():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages now.", [(G, "languages", q(12, "language"))], cues=["now"]),
            gold_row("r2", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))]),
            gold_row("r3", "Hooly Gemini speaks 12 languages since 2 March 2026.", [(G, "languages", q(12, "language"))],
                     cues=["since"], date="2026-04-01")]
    facts = [pred("r1", G, "languages", q(12, "language"), temporal_qualifier="now"),            # cue captured
             pred("r2", G, "languages", q(12, "language"), temporal_qualifier="still"),          # qualifier without listed cue
             pred("r3", G, "languages", q(12, "language"), temporal_qualifier="since",
                  valid_from="2026-03-02", fact_observation_date="2026-04-01")]                   # supported + copied page date
    v, res, table, _, _, cases = evaluate(rows, facts)
    assert res["temporal_cue_recall"]["num"] == 2 and res["temporal_cue_recall"]["den"] == 2
    assert res["temporal_abstention_on_no_cue_rows"]["num"] == 0 and res["temporal_abstention_on_no_cue_rows"]["den"] == 1
    s = table.sums()
    assert s["t_dates_set"] == 2 and s["t_dates_supported"] == 1 and s["t_dates_copied_page_date"] == 1
    assert any(c["case"] == "qualifier_on_row_without_listed_cue" for c in cases)


def test_temporal_miss_when_no_fact_extracted():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages now.", [(G, "languages", q(12, "language"))], cues=["now"])]
    _, res, *_ = evaluate(rows, [])
    assert res["temporal_cue_recall"]["value"] == 0.0 and res["temporal_cue_recall_given_fact"]["den"] == 0


@pytest.mark.parametrize("text,expected", [
    ("founded on 14 January 2025 in Berlin", {"2025-01-14"}),
    ("It arrives on July 7, 2026.", {"2026-07-07"}),
    ("Launched 10 Feb. 2026", {"2026-02-10"}),
    ("planned for March 2026", {"2026-03"}),
    ("from 2026-05-14", {"2026-05-14"}),
    ("in 2025 we grew", {"2025"}),
    ("no dates here, only 12 languages", set()),
])
def test_text_dates(text, expected):
    assert M.text_dates(text) == expected


def test_date_supported_by_written_month():
    assert M.date_supported("2026-03-12", {"2026-03"}) and not M.date_supported("2026-04-12", {"2026-03"})


# --------------------------------------------------------------------------- kinds and strata

def test_per_kind_breakdown():
    rows = [gold_row("r1", "Hooly Gemini speaks 12 languages and answers in 1.4 s.",
                     [(G, "languages", q(12, "language")), (G, "median_response_time", dur(1.4, "s"))], strata=["multi_fact"]),
            gold_row("r2", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))], strata=["kind_quantity"])]
    facts = [pred("r1", G, "languages", q(12, "language")), pred("r2", G, "languages", q(12, "language"))]
    v, res, *_ = evaluate(rows, facts)
    assert res["recall_quantity"]["num"] == 2 and res["recall_quantity"]["den"] == 2
    assert res["recall_duration"]["num"] == 0 and res["recall_duration"]["den"] == 1
    assert res["precision_quantity"]["value"] == 1.0 and res["precision_duration"]["value"] is None
    masks = M.stratum_masks(rows)
    table = evaluate(rows, facts)[2]
    sub = M.metric_table(table, M.metric_specs(["form"]), None, masks["multi_fact"])
    assert sub["recall_form"]["num"] == 1 and sub["recall_form"]["den"] == 2


# --------------------------------------------------------------------------- bootstrap

def _table(n_rows=40, hit_rate=0.5, seed=1):
    rng = np.random.default_rng(seed)
    rows = [gold_row(f"r{i}", "Hooly Gemini speaks 12 languages.", [(G, "languages", q(12, "language"))]) for i in range(n_rows)]
    facts = [pred(r.id, G, "languages", q(12 if rng.random() < hit_rate else 99, "language")) for r in rows]
    return rows, facts


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    rows, facts = _table()
    table = evaluate(rows, facts)[2]
    specs = M.metric_specs(["form"])
    a = M.metric_table(table, specs, M.bootstrap_indices(len(rows), 500, 7))
    b = M.metric_table(table, specs, M.bootstrap_indices(len(rows), 500, 7))
    assert a["recall_form"]["ci95"] == b["recall_form"]["ci95"]
    lo, hi = a["recall_form"]["ci95"]
    assert lo <= a["recall_form"]["value"] <= hi and 0 <= lo and hi <= 1
    assert hi - lo > 0.1                      # 40 rows: the interval is wide


def test_bootstrap_interval_shrinks_with_more_rows():
    small = evaluate(*_table(20, 0.5, 2))[2]
    large = evaluate(*_table(400, 0.5, 2))[2]
    specs = M.metric_specs(["form"])
    w = lambda t, n: np.subtract(*M.metric_table(t, specs, M.bootstrap_indices(n, 800, 3))["recall_form"]["ci95"][::-1])  # noqa: E731
    assert w(large, 400) < w(small, 20)


def test_perfect_method_has_degenerate_interval():
    rows, _ = _table(30)
    facts = [pred(r.id, G, "languages", q(12, "language")) for r in rows]
    table = evaluate(rows, facts)[2]
    res = M.metric_table(table, M.metric_specs(["form"]), M.bootstrap_indices(30, 300, 1))
    assert res["recall_form"]["ci95"] == (1.0, 1.0)


def test_paired_difference_detects_better_method():
    rows, good = _table(60, 0.9, 4)
    _, bad = _table(60, 0.2, 5)
    t_good, t_bad = evaluate(rows, good)[2], evaluate(rows, bad)[2]
    idx = M.bootstrap_indices(60, 800, 9)
    d = M.paired_difference(t_good, t_bad, M.metric_specs(["form"])["recall_form"], idx)
    assert d["difference"] > 0.4 and d["ci95"][0] > 0 and d["bootstrap_share_a_greater"] > 0.99
    d2 = M.paired_difference(t_bad, t_good, M.metric_specs(["form"])["recall_form"], idx)
    assert d2["difference"] == pytest.approx(-d["difference"])


# --------------------------------------------------------------------------- judgements file

def test_load_judgements_accepts_json_and_shorthand(tmp_path):
    p = tmp_path / "j.csv"
    C.write_csv(p, ["source_row_id", "subject", "attribute", "value", "verdict", "reviewer", "note"], [
        {"source_row_id": "r1", "subject": "Gemini", "attribute": "languages", "value": json.dumps(q(12, "language")), "verdict": "Correct"},
        {"source_row_id": "r2", "subject": G, "attribute": "median_response_time", "value": "1.4 s", "verdict": "incorrect"},
        {"source_row_id": "r3", "subject": G, "attribute": "languages", "value": "12 languages", "verdict": "maybe"},   # ignored
    ])
    j = M.load_judgements(p)
    assert j[("r1", C.fact_key(G, "languages", q(12, "language")))]["verdict"] == "correct"     # alias resolved
    assert j[("r2", C.fact_key(G, "median_response_time", dur(1.4, "s")))]["verdict"] == "incorrect"
    assert len(j) == 2


# --------------------------------------------------------------------------- integrity of the delivered evaluation set

def test_eval_set_is_runtime_shaped_and_mostly_heldout():
    rows = C.read_csv(C.EVAL_ROWS)
    assert set(rows[0]) == {"id", "text", "date", "label"}
    held = set(json.loads(C.SPLIT_JSON.read_text(encoding="utf-8"))["heldout_ids"])
    n_held = sum(r["id"] in held for r in rows)
    assert 100 <= len(rows) <= 150 and n_held / len(rows) >= 0.8
    dev_ids = {r["id"] for r in C.read_csv(C.DEV_ROWS)}
    assert not (held & dev_ids)


def test_eval_set_was_chosen_before_extractor_output():
    prov = json.loads((C.EVAL_DIR / "selection_provenance.json").read_text(encoding="utf-8"))
    assert prov["baseline_output_existing_at_first_selection"] is False
    assert not any(prov["extractor_outputs_existing_at_first_selection"].values())
    log = json.loads(C.SELECTION_LOG.read_text(encoding="utf-8"))
    ids = [r["id"] for r in C.read_csv(C.EVAL_ROWS)]
    import hashlib
    final = hashlib.sha1("\n".join(ids).encode()).hexdigest()
    assert final == log["id_list_sha1"]
    # the write-once provenance records the first selection; the addendum documents the final one
    add = json.loads((C.EVAL_DIR / "selection_provenance_addendum.json").read_text(encoding="utf-8"))
    assert add["final_selection"]["id_list_sha1"] == final
    assert add["first_selection"]["id_list_sha1"] == prov["id_list_sha1"]


def test_baseline_priors_come_from_dev_rows_only():
    import baseline_parser as B
    kinds, units, n_dev = B.dev_priors()
    assert n_dev == len(C.read_csv(C.DEV_ROWS))
    held = set(json.loads(C.SPLIT_JSON.read_text(encoding="utf-8"))["heldout_ids"])
    assert not (held & {r["id"] for r in C.read_csv(C.DEV_ROWS)})
    src = Path(B.__file__).read_text(encoding="utf-8")
    assert "HELDOUT_GOLD" not in src and "heldout_gold" not in src.casefold().replace("heldout_ids", "")


def test_baseline_never_opens_heldout_gold(monkeypatch):
    import builtins
    import baseline_parser as B
    from core.graph.parsing import TextFactParser
    opened: list[str] = []
    real_open, real_path_open, real_read_text = builtins.open, Path.open, Path.read_text

    def spy_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)

    def spy_path_open(self, *a, **k):
        opened.append(str(self))
        return real_path_open(self, *a, **k)

    def spy_read_text(self, *a, **k):
        opened.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(Path, "open", spy_path_open)
    monkeypatch.setattr(Path, "read_text", spy_read_text)
    kinds, units, _ = B.dev_priors()
    rows = [{k: r[k] for k in ("id", "text", "date", "label")} for r in C.read_csv(C.FULL_INPUT)[:30]]
    facts, _ = B.extract_rows(rows, TextFactParser(C.lexicon(), kinds, units))
    assert facts is not None
    assert not [p for p in opened if "_heldout" in p or "heldout_gold" in p], opened


@pytest.mark.skipif(not C.METHOD_FILES["baseline"].exists(), reason="baseline output not generated")
def test_baseline_output_passes_schema():
    report = C.fact_schema.validate_file(C.METHOD_FILES["baseline"])
    assert report["invalid"] == 0 and report["facts"] > 0


# --------------------------------------------------------------------------- CLI behaviour

def test_evaluate_refuses_existing_output_folder(tmp_path):
    out = tmp_path / "exists"
    out.mkdir()
    r = subprocess.run([sys.executable, str(HERE / "evaluate.py"), "--methods", "baseline", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2 and "never overwritten" in r.stdout


def test_evaluate_skips_missing_methods_and_says_so(tmp_path):
    out = tmp_path / "res"
    r = subprocess.run([sys.executable, str(HERE / "evaluate.py"), "--methods", "nonexistent=" + str(tmp_path / "no.jsonl"), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 3 and "SKIPPED" in r.stdout and not out.exists()
