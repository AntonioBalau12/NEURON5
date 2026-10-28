"""Tests of combine.py and ingest_worksheet.py with synthetic data."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tests"))
import combine as K  # noqa: E402
import common as C  # noqa: E402
import ingest_worksheet as I  # noqa: E402
import metrics as M  # noqa: E402
from test_metrics import G, boolean, dur, gold_row, q  # noqa: E402

TEXT = "Hooly Gemini speaks 12 languages and answers in 1.4 s."
ROWS = {"r1": {"id": "r1", "text": TEXT, "date": "2026-03-01", "label": "true"}}


def fact(src, attribute, value, start=0, end=len(TEXT), status="partial", conf=0.5, negated=False, qualifier=None):
    return {"extraction_id": f"r1#{src}#{attribute}", "source_row_id": "r1", "source_label": "true", "source_publication_date": "2026-03-01",
            "subject": G, "subject_surface": "Hooly Gemini", "attribute": attribute, "relation_surface": None, "value": value,
            "object_surface": None, "negated": negated, "source_text_span": TEXT[start:end], "span_start": start, "span_end": end,
            "fact_observation_date": None, "valid_from": None, "valid_to": None, "temporal_qualifier": qualifier,
            "extraction_method": src, "extraction_confidence": conf, "parse_status": status, "verification_status": "candidate", "notes": ""}


A = [fact("openie", "languages", q(12, "language"), 0, 28, conf=0.6),
     fact("openie", "median_response_time", dur(1.4, "s"), 33, 54, conf=0.4),
     fact("openie", "version", {"kind": "version", "value": "2.0"}, 0, 12)]            # only in A
B = [fact("slot_filling", "languages", q(12, "language"), 7, 28, conf=0.9, status="complete", qualifier="now"),
     fact("slot_filling", "median_response_time", dur(1.5, "s"), 33, 54, conf=0.8, status="complete"),   # conflicts with A
     fact("slot_filling", "context_window", q(5, "token"), 0, 10)]                    # only in B


def keys(facts):
    return {(f["attribute"], C.value_key(f["value"])) for f in facts}


def test_union_keeps_everything_and_flags_conflicts():
    out, stats = K.combine(A, B, ROWS, "union")
    attrs = sorted(f["attribute"] for f in out)
    assert attrs == sorted(["languages", "median_response_time", "median_response_time", "version", "context_window"])
    conflicted = [f for f in out if f["attribute"] == "median_response_time"]
    assert len(conflicted) == 2 and all(f["parse_status"] == "ambiguous" for f in conflicted)
    assert stats["agree"] == 1 and stats["conflicted_slots"] == 1
    assert all(f["extraction_method"] == "combined" and f["verification_status"] == "candidate" for f in out)


def test_merged_fact_takes_union_span_max_confidence_and_temporal_cue():
    out, _ = K.combine(A, B, ROWS, "union")
    m = next(f for f in out if f["attribute"] == "languages")
    assert (m["span_start"], m["span_end"]) == (0, 28) and m["source_text_span"] == TEXT[0:28]
    assert m["extraction_confidence"] == 0.9 and m["temporal_qualifier"] == "now"
    assert m["parse_status"] == "complete" and "sources=openie+slot_filling" in m["notes"]


def test_union_resolved_keeps_one_value_per_conflicted_slot():
    out, stats = K.combine(A, B, ROWS, "union_resolved")
    rt = [f for f in out if f["attribute"] == "median_response_time"]
    assert len(rt) == 1 and rt[0]["value"]["value"] == 1.5          # complete + higher confidence + slot_filling wins
    assert stats["dropped_by_resolution"] == 1
    assert len(out) == 4


def test_intersection_only_agreed_facts():
    out, _ = K.combine(A, B, ROWS, "intersection")
    assert [f["attribute"] for f in out] == ["languages"]


def test_agreement_uses_value_equivalence_not_string_equality():
    a = [fact("openie", "free_trial", dur(14, "day"))]
    b = [fact("slot_filling", "free_trial", dur(2, "week"))]
    out, _ = K.combine(a, b, ROWS, "intersection")
    assert len(out) == 1


def test_negation_is_or_ed_and_disagreement_noted():
    a = [fact("openie", "ai", boolean(False), negated=False)]
    b = [fact("slot_filling", "ai", boolean(False), negated=True)]
    out, _ = K.combine(a, b, ROWS, "union")
    assert out[0]["negated"] is True and "negation_disagreement" in out[0]["notes"]


def test_unmapped_inputs_are_dropped_and_ids_unique():
    unmapped = fact("openie", "x", None, status="unmapped")
    unmapped["attribute"] = None
    out, _ = K.combine(A + [unmapped], B, ROWS, "union")
    assert all(f["value"] is not None for f in out)
    ids = [f["extraction_id"] for f in out]
    assert len(ids) == len(set(ids))


def test_combined_schema_is_valid(tmp_path):
    rows = C.fact_schema.load_input_rows()
    text = rows["p-1"]["text"] if "p-1" in rows else None
    assert text
    mk = lambda src, conf: {  # noqa: E731
        "extraction_id": f"p-1#{src}#0", "source_row_id": "p-1", "source_label": rows["p-1"]["label"],
        "source_publication_date": rows["p-1"]["date"], "subject": "Holdan", "subject_surface": "Holdan", "attribute": "joined",
        "relation_surface": "started", "value": {"kind": "date", "value": "2026-01-12"}, "object_surface": "12 January 2026",
        "negated": False, "source_text_span": text, "span_start": 0, "span_end": len(text), "fact_observation_date": None, "valid_from": None,
        "valid_to": None, "temporal_qualifier": None, "extraction_method": src, "extraction_confidence": conf, "parse_status": "complete",
        "verification_status": "candidate", "notes": ""}
    out, _ = K.combine([mk("openie", 0.5)], [mk("slot_filling", 0.7)], rows, "union")
    path = tmp_path / "c.jsonl"
    C.dump_jsonl(path, out)
    assert C.fact_schema.validate_file(path, rows)["invalid"] == 0


# --------------------------------------------------------------------------- ingest_worksheet

def _gold_rows():
    row = gold_row("r1", TEXT, [(G, "languages", q(12, "language")), (G, "median_response_time", dur(1.4, "s"))],
                   extra=[(G, "context_window", q(200000, "token")), (G, "max_output_length", q(16000, "token"))])
    return {"r1": row}


def test_verdict_and_fact_parsers():
    errs: list[str] = []
    assert I.parse_verdicts("F1=ok; F2=wrong", "F", errs, "r1") == {"F1": True, "F2": False} and not errs
    I.parse_verdicts("F1=maybe", "F", errs, "r1")
    assert errs
    errs = []
    facts = I.parse_facts("Hooly Gemini | languages | 12 languages ; Hooly AI Pro | price | €59/month", errs, "r1")
    assert not errs and len(facts) == 2
    assert facts[0][2] == {"kind": "quantity", "value": 12, "unit": "languages"}      # shorthand keeps the unit as typed
    assert C.fact_key(*facts[1]) == C.fact_key("Hooly AI Pro", "price", {"kind": "money", "value": 59, "currency": "EUR", "per": "month"})
    errs = []
    assert I.parse_facts("Hooly Gemini | not_an_attribute | 3 items", errs, "r1") == [] and errs


def test_human_gold_from_verdicts():
    ws = [{"id": "r1", "reviewed": "yes", "annotator": "ann", "form_fact_verdicts": "F2=wrong", "suggested_fact_verdicts": "S1=ok",
           "human_extra_facts": "Hooly Gemini | version | v2.0", "human_complete_facts": ""}]
    rows, stats, errors = I.build_human_rows(ws, _gold_rows(), lenient=False)
    assert not errors
    human = {g.attribute for g in rows[0].sets["human"]}
    assert human == {"languages", "context_window", "version"}       # F2 removed, S1 accepted, S2 unmarked -> dropped, extra added
    assert stats["form_facts_rejected"] == 1 and stats["suggestions_accepted"] == 1 and stats["suggestions_unmarked_dropped"] == 1
    assert stats["annotators"] == ["ann"]


def test_human_complete_list_replaces_everything_and_none_means_empty():
    ws = [{"id": "r1", "reviewed": "y", "human_complete_facts": "Hooly Gemini | languages | 12 languages"}]
    rows, _, _ = I.build_human_rows(ws, _gold_rows(), lenient=False)
    assert [g.attribute for g in rows[0].sets["human"]] == ["languages"]
    ws = [{"id": "r1", "reviewed": "y", "human_complete_facts": "NONE"}]
    rows, _, _ = I.build_human_rows(ws, _gold_rows(), lenient=False)
    assert rows[0].sets["human"] == []


def test_unreviewed_rows_are_ignored_and_bad_cells_reported():
    ws = [{"id": "r1", "reviewed": "", "form_fact_verdicts": "F1=wrong"}]
    assert I.build_human_rows(ws, _gold_rows(), lenient=False)[0] == []
    ws = [{"id": "r1", "reviewed": "yes", "form_fact_verdicts": "F1=perhaps"}]
    rows, _, errors = I.build_human_rows(ws, _gold_rows(), lenient=False)
    assert errors and rows == []


def test_metrics_recomputed_against_human_gold():
    ws = [{"id": "r1", "reviewed": "yes", "form_fact_verdicts": "F2=wrong", "suggested_fact_verdicts": "S1=ok"}]
    rows, _, _ = I.build_human_rows(ws, _gold_rows(), lenient=False)
    preds = M.group_preds([fact("x", "languages", q(12, "language")), fact("x", "context_window", q(200000, "token"))], ["r1"])
    table, *_ = M.evaluate_method(rows, preds, "human")
    res = M.metric_table(table, M.metric_specs(["form", "suggested", "human"]), None)
    assert res["precision_human"]["value"] == 1.0 and res["recall_human"]["value"] == 1.0
    assert res["precision_form"]["value"] == 0.5         # the context_window fact is beyond the form
    assert res["recall_form"]["value"] == 0.5
