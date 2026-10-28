"""Dynamic temporal knowledge graph and deterministic evidence reasoning."""

from .builder import build_graph, build_graph_from_paths
from .diagnostics import practice_extraction_metrics
from .evidence_resolver import EvidenceResolver
from .models import (
    EntityNode,
    EvidenceQuery,
    EvidenceState,
    FactRecord,
    GraphEvidence,
    ParseStatus,
    TemporalKnowledgeGraph,
)
from .parsing import ExtractionResult, TextFactParser
from .reasoning import ClaimResolution, ReasoningEngine
from .temporal_index import EventEvidence, RelationEvidence, TemporalChange, TemporalIndex

__all__ = [
    "ClaimResolution", "EntityNode", "EvidenceQuery", "EvidenceResolver", "EvidenceState",
    "EventEvidence", "ExtractionResult", "FactRecord", "GraphEvidence", "ParseStatus",
    "ReasoningEngine", "RelationEvidence", "TemporalChange", "TemporalIndex",
    "TemporalKnowledgeGraph", "TextFactParser", "build_graph", "build_graph_from_paths",
    "practice_extraction_metrics",
]
