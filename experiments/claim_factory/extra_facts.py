"""Admission of RECONSTRUCTED facts (experiments/shared/EXCHANGE_FORMAT.md) into the claim factory's evidence store.

A reconstructed fact is still a CANDIDATE even when its source row is labelled TRUE: the row being true says the sentence is
true on its date, not that an extractor read the sentence correctly.  A fact is therefore admitted as verified support only when
ALL gates hold AND at least one independent corroboration rule fires.

Gates (every refusal is counted by reason):
  G1  valid under experiments/shared/fact_schema.validate_fact (incl. exact span: text[span_start:span_end] == span)
  G2  parse_status == "complete"
  G3  extraction_confidence >= --extra-min-confidence (default 0.8)
  G4  negation handled: a boolean false value must carry negated=true and a negated=true clause must be a boolean false;
      independently, a negation word in the span (value-forms "Yes or no" list) is only allowed in that case
  G5  source row labelled "true" (an unlabelled / false / unsure source never certifies anything)
  G6  value has no op (exact) and no explicit validity end (valid_to) and no past/future temporal qualifier
  G7  the source row exists in the graph and fact_observation_date (if given) is not after the row date
Corroboration (at least one; chosen with --extra-corroboration, default any; "agree_or_form" = row_form OR two_methods, i.e. NOT cross_row):
  row_form     the same (subject, attribute, equivalent value) is already a verified form fact of the SAME row.
               (Only possible for labelled practice rows -> it is an EVALUATION corroboration, the fact adds nothing new.)
  two_methods  >= 2 distinct extraction methods (openie / slot_filling / deterministic_parser) in the file agree on the same
               (row, subject, attribute, equivalent value).  Independent readings of one sentence.
  cross_row    a DIFFERENT row has a verified form/admitted observation of the same (subject, attribute, equivalent value) within
               --extra-cross-row-days (default 14): the value is already established for that period, so the fact refreshes it.
Admitted facts are inserted into the core.graph graph as VERIFIED_SUPPORT with provenance "reconstructed.<method>" so every
downstream query (TemporalIndex / EvidenceResolver / ReasoningEngine) sees them, and claims built on them carry the flag
"uses_reconstructed_fact".  Facts already present as form facts of the same row are not re-inserted.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

from cf_common import ROOT
from foundation import AtomicFact, TypedValue  # type: ignore
from core.graph import EvidenceState
from core.graph.builder import _mark_same_day_conflicts  # reused read-only
from core.graph.models import FactRecord, ParseStatus
from observations import same_value
from store import Store

import fact_schema  # experiments/shared (on sys.path via cf_common)
from textcheck import NEGATION

PAST_FUTURE_QUALIFIER = re.compile(r"\b(?:was|were|before|until|till|formerly|previously|used to|ago|will|next|soon|planned|upcoming|"
                                   r"from today|as of|since|ended|former|no longer)\b", re.IGNORECASE)


def inject(store: Store, path: Path, min_conf: float, mode: str, outdir: Path, cross_row_days: int = 14) -> dict[str, Any]:
    lexicon = fact_schema.load_lexicon()
    input_rows = fact_schema.load_input_rows()
    raw_rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    gates: Counter[str] = Counter()
    survivors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for f in raw_rows:
        gates["facts_in_file"] += 1
        eid = f.get("extraction_id")
        if eid in seen_ids:
            gates["refused:duplicate_extraction_id"] += 1
            continue
        seen_ids.add(eid)
        errs = fact_schema.validate_fact(f, lexicon, input_rows)
        if errs:
            gates["refused:G1_schema_or_span_invalid"] += 1
            continue
        if f["parse_status"] != "complete":
            gates[f"refused:G2_parse_status_{f['parse_status']}"] += 1
            continue
        if float(f["extraction_confidence"]) < min_conf:
            gates["refused:G3_low_confidence"] += 1
            continue
        v = f["value"]
        negated = bool(f["negated"])
        span_neg = NEGATION.search(f["source_text_span"]) is not None
        if v.get("kind") == "boolean":
            if (v.get("value") is False) != negated:
                gates["refused:G4_boolean_polarity_vs_negated_flag"] += 1
                continue
        elif negated:
            gates["refused:G4_negated_non_boolean"] += 1
            continue
        if span_neg and not (v.get("kind") == "boolean" and v.get("value") is False and negated):
            gates["refused:G4_negation_word_in_span_unhandled"] += 1
            continue
        if f["source_label"] != "true":
            gates["refused:G5_source_not_labelled_true"] += 1
            continue
        if v.get("op") not in (None, "eq"):
            gates["refused:G6_value_has_op"] += 1
            continue
        if f.get("valid_to"):
            gates["refused:G6_explicit_validity_end"] += 1
            continue
        if f.get("temporal_qualifier") and PAST_FUTURE_QUALIFIER.search(f["temporal_qualifier"]):
            gates["refused:G6_temporal_qualifier_past_or_future"] += 1
            continue
        ev = store.graph.evidence_by_id.get(f["source_row_id"])
        if ev is None or ev.observed_on is None:
            gates["refused:G7_source_row_not_in_graph"] += 1
            continue
        obs_date = ev.observed_on
        if f.get("fact_observation_date"):
            od = date.fromisoformat(f["fact_observation_date"])
            if od > obs_date:
                gates["refused:G7_fact_observation_date_after_row_date"] += 1
                continue
            obs_date = od
        typed, err = TypedValue.parse(v)
        if err or typed is None:
            gates["refused:G1_value_unparseable"] += 1
            continue
        f = dict(f)
        f["_typed"] = typed
        f["_obs_date"] = obs_date
        survivors.append(f)
        gates["passed_all_gates"] += 1

    # ---- corroboration -------------------------------------------------------------------------
    by_triplet: dict[tuple, list[dict]] = defaultdict(list)
    for f in survivors:
        by_triplet[(f["source_row_id"], f["subject"], f["attribute"])].append(f)

    def methods_agreeing(f: dict) -> set[str]:
        grp = by_triplet[(f["source_row_id"], f["subject"], f["attribute"])]
        return {g["extraction_method"] for g in grp if same_value(g["_typed"], f["_typed"]) and g["extraction_method"] != "combined"}

    rule_counts: Counter[str] = Counter()
    admitted: list[dict[str, Any]] = []
    new_records: list[FactRecord] = []
    seen_inserts: set[tuple] = set()
    for f in survivors:
        subject = lexicon.resolve(f["subject"]).name  # canonical
        key = (subject, f["attribute"])
        rules_hit: list[str] = []
        ev = store.graph.evidence_by_id[f["source_row_id"]]
        if any(a.subject == subject and a.attribute == f["attribute"] and same_value(a.value, f["_typed"]) for a in ev.facts) and \
                any(r.source_row_id == f["source_row_id"] and r.evidence_status == EvidenceState.VERIFIED_SUPPORT
                    and same_value(r.fact.value, f["_typed"]) for r in store.graph.facts_by_subject_attribute.get((store.graph.entity_key(subject), f["attribute"]), [])):
            rules_hit.append("row_form")
        if len(methods_agreeing(f)) >= 2:
            rules_hit.append("two_methods")
        for o in store.obs.get(key, []):
            if o.kind == "support" and o.row_id != f["source_row_id"] and same_value(o.value, f["_typed"]) and abs((o.on - f["_obs_date"]).days) <= cross_row_days:
                rules_hit.append("cross_row")
                break
        usable = [r for r in rules_hit if mode in ("any", r) or (mode == "agree_or_form" and r in ("row_form", "two_methods"))]
        if not usable:
            gates["refused:no_corroboration_rule_fired(mode=%s)" % mode] += 1
            continue
        for r in usable:
            rule_counts[r] += 1
        rule_counts["admitted_by_" + "+".join(sorted(usable))] += 1
        item = {"extraction_id": f["extraction_id"], "source_row_id": f["source_row_id"], "subject": subject, "attribute": f["attribute"],
                "value": f["value"], "method": f["extraction_method"], "confidence": f["extraction_confidence"], "corroboration": sorted(usable),
                "observed_on": f["_obs_date"].isoformat()}
        admitted.append(item)
        if usable == ["row_form"]:
            rule_counts["already_in_graph_as_form_fact(not_reinserted)"] += 1
            continue
        ins_key = (f["source_row_id"], subject, f["attribute"], f["_typed"].key())
        if ins_key in seen_inserts:
            continue
        seen_inserts.add(ins_key)
        fact = AtomicFact(subject, f["attribute"], f["_typed"], subject_spelling=f.get("subject_surface"))
        new_records.append(FactRecord(fact, f["_obs_date"], None, None, f["source_row_id"], EvidenceState.VERIFIED_SUPPORT, ParseStatus.COMPLETE,
                                      f"reconstructed.{f['extraction_method']}", float(f["extraction_confidence"])))
    for rec in new_records:
        store.graph.add_fact(rec)
    if new_records:
        _mark_same_day_conflicts(store.graph)
        store.graph.sort_indexes()
    store._finalize()
    report = {"file": str(path), "min_confidence": min_conf, "corroboration_mode": mode, "cross_row_days": cross_row_days,
              "gates": dict(gates), "corroboration": dict(rule_counts), "admitted": len(admitted), "inserted_into_graph": len(new_records),
              "limitations": ["row_form corroboration only exists for labelled practice rows (evaluation only)",
                              "rows outside practice.csv are unlabelled locally, so none of their facts can pass G5 here"]}
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "extra_facts_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (outdir / "extra_facts_admitted.jsonl").open("w", encoding="utf-8") as fh:
        for a in admitted:
            fh.write(json.dumps(a, ensure_ascii=False) + "\n")
    store.extra_admitted = admitted
    return report

