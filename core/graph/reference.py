"""Build-time snapshot of the reference-only graph used by calibrated M2."""

from __future__ import annotations

import hashlib
import os
import pickle
from functools import lru_cache
from pathlib import Path

from .builder import build_graph_from_paths
from .models import TemporalKnowledgeGraph

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = ROOT / "artifacts" / "reference_graph.pkl"


def fingerprints(practice: Path, lexicon: Path) -> dict[str, str]:
    sources = [practice, lexicon, ROOT / "foundation.py", ROOT / "contracts/claimed_value.schema.json"]
    sources.extend(sorted(Path(__file__).parent.glob("*.py")))
    sources.append(Path(__file__).with_name("attribute_resolver.json"))
    return {str(index): hashlib.sha256(path.read_bytes()).hexdigest() for index, path in enumerate(sources)}


def write_reference_snapshot(output: Path, practice: Path, lexicon: Path) -> dict:
    graph = build_graph_from_paths(practice, lexicon, use_packaged_practice=False)
    counts = {"entities": len(graph.entities), "evidence": len(graph.evidence_by_id),
              "facts": sum(map(len, graph.facts_by_subject_attribute.values()))}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        pickle.dump({"version": 1, "fingerprints": fingerprints(practice, lexicon),
                     "counts": counts, "graph": graph}, handle, protocol=pickle.HIGHEST_PROTOCOL)
    temporary.replace(output)
    return counts


@lru_cache(maxsize=4)
def load_reference_graph(practice_path: str, lexicon_path: str) -> TemporalKnowledgeGraph:
    practice, lexicon = Path(practice_path).resolve(), Path(lexicon_path).resolve()
    snapshot = Path(os.environ.get("NEURON_GRAPH_SNAPSHOT", str(DEFAULT_SNAPSHOT)))
    if snapshot.is_file():
        # Only the application's own build artifact is loaded; never accept uploaded pickles.
        with snapshot.open("rb") as handle:
            bundle = pickle.load(handle)
        if (bundle.get("version") == 1 and bundle.get("fingerprints") == fingerprints(practice, lexicon)
                and isinstance(bundle.get("graph"), TemporalKnowledgeGraph)):
            return bundle["graph"]
    return build_graph_from_paths(practice, lexicon, use_packaged_practice=False)
