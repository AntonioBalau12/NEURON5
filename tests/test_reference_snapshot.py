import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.graph.models import EvidenceState
from core.graph.reference import load_reference_graph, write_reference_snapshot


def test_snapshot_roundtrip_and_source_invalidation(tmp_path, monkeypatch):
    practice, lexicon, snapshot = (tmp_path / name for name in ("practice.csv", "lexicon.json", "graph.pkl"))
    lexicon.write_text(json.dumps({"subjects": [{"name": "Alpha", "aliases": [], "attributes": ["size"]}], "events": []}))
    with practice.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "text", "date", "label", "form"))
        writer.writeheader()
        for row_id, label in (("verified", "true"), ("candidate", "unsure")):
            writer.writerow({"id": row_id, "text": "Alpha has a size of 4.", "date": "2026-01-01", "label": label,
                             "form": json.dumps([{"subject": "Alpha", "attribute": "size", "value": {"kind": "quantity", "value": 4, "unit": "item"}}])})
    counts = write_reference_snapshot(snapshot, practice, lexicon)
    monkeypatch.setenv("NEURON_GRAPH_SNAPSHOT", str(snapshot))
    load_reference_graph.cache_clear()
    with patch("core.graph.reference.build_graph_from_paths", side_effect=AssertionError("snapshot rebuilt")):
        graph = load_reference_graph(str(practice), str(lexicon))
    assert counts["entities"] == 1 and counts["evidence"] == 2
    records = graph.facts_by_subject_attribute[("alpha", "size")]
    assert {r.evidence_status for r in records} == {EvidenceState.VERIFIED_SUPPORT, EvidenceState.UNVERIFIED_CANDIDATE}
    assert all(r.source_row_id in graph.evidence_by_id for r in records)
    practice.write_text(practice.read_text() + "\n")
    load_reference_graph.cache_clear()
    with patch("core.graph.reference.build_graph_from_paths", return_value=graph) as rebuild:
        assert load_reference_graph(str(practice), str(lexicon)) is graph
    rebuild.assert_called_once()
    load_reference_graph.cache_clear()


@pytest.mark.parametrize("snapshot_contents", [None, b"broken snapshot"])
def test_missing_or_corrupt_snapshot_rebuilds_once(tmp_path, monkeypatch, snapshot_contents):
    practice, lexicon, snapshot = (tmp_path / name for name in ("practice.csv", "lexicon.json", "graph.pkl"))
    lexicon.write_text(json.dumps({"subjects": [], "events": []}))
    practice.write_text("id,text,date,label,form\n")
    if snapshot_contents is not None:
        snapshot.write_bytes(snapshot_contents)
    monkeypatch.setenv("NEURON_GRAPH_SNAPSHOT", str(snapshot))
    expected = object()
    load_reference_graph.cache_clear()
    try:
        with patch("core.graph.reference.build_graph_from_paths", return_value=expected) as rebuild:
            assert load_reference_graph(str(practice), str(lexicon)) is expected
        rebuild.assert_called_once()
    finally:
        load_reference_graph.cache_clear()
