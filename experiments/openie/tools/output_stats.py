"""Counts over output/facts.jsonl (all 1897 input rows) for REPORT.md. No gold used."""
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8")
facts = [json.loads(l) for l in (HERE / "output" / "facts.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
out = {"facts": len(facts), "rows_with_facts": len({f["source_row_id"] for f in facts})}
out["by_status"] = dict(collections.Counter(f["parse_status"] for f in facts))
out["by_kind_mapped"] = dict(collections.Counter(f["value"]["kind"] for f in facts if f["parse_status"] != "unmapped"))
out["by_kind_unmapped_with_value"] = dict(collections.Counter(f["value"]["kind"] for f in facts if f["parse_status"] == "unmapped" and f["value"]))
um = [f for f in facts if f["parse_status"] == "unmapped"]
out["unmapped_value_null"] = sum(1 for f in um if f["value"] is None)
out["unmapped_flags"] = dict(collections.Counter(
    fl for f in um for fl in ("approximation", "range-end", "invisible-char", "comparison") if fl in f["notes"]))
out["unmapped_with_hint"] = sum(1 for f in um if "hint_attr=" in f["notes"])
out["negated_true"] = sum(1 for f in facts if f["negated"])
out["negated_true_by_kind"] = dict(collections.Counter(f["value"]["kind"] if f["value"] else "none" for f in facts if f["negated"]))
out["mapped_negated_non_boolean"] = sum(1 for f in facts if f["negated"] and f["value"] and f["value"]["kind"] != "boolean" and f["parse_status"] != "unmapped")
out["boolean_false"] = sum(1 for f in facts if f["value"] and f["value"]["kind"] == "boolean" and f["value"]["value"] is False)
out["with_temporal_qualifier"] = sum(1 for f in facts if f["temporal_qualifier"])
out["with_fact_observation_date"] = sum(1 for f in facts if f["fact_observation_date"])
out["with_valid_from"] = sum(1 for f in facts if f["valid_from"])
out["with_valid_to"] = sum(1 for f in facts if f["valid_to"])
out["obs_date_equals_page_date"] = sum(1 for f in facts if f["fact_observation_date"] and f["fact_observation_date"] == f["source_publication_date"])
out["verification_status_all_candidate"] = all(f["verification_status"] == "candidate" for f in facts)
out["rows_with_2plus_mapped_facts"] = sum(1 for n in collections.Counter(f["source_row_id"] for f in facts if f["parse_status"] != "unmapped").values() if n >= 2)
conf = [f["extraction_confidence"] for f in facts if f["parse_status"] == "complete"]
out["confidence_complete_min_med_max"] = [min(conf), sorted(conf)[len(conf) // 2], max(conf)]
out["span_avg_chars"] = round(sum(len(f["source_text_span"]) for f in facts) / len(facts), 1)
out["relation_surface_null_mapped"] = sum(1 for f in facts if f["parse_status"] != "unmapped" and not f["relation_surface"])
print(json.dumps(out, indent=1, ensure_ascii=False))
