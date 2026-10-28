"""Dynamic temporal knowledge graph and deterministic evidence reasoning."""

from .builder import build_graph, build_graph_from_paths
from .diagnostics import practice_extraction_metrics
from .evidence_resolver import EvidenceResolver
from .models import (
    EntityNode,
    ExtractionCandidate,
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
from .semantic_extraction import (
    AttributeResolver,
    AttributeResolverExtractor,
    ExpandedDeterministicExtractor,
    GroupedSplit,
    HybridSemanticExtractor,
    P1ParserAdapter,
    SemanticExtractionResult,
    SpacyAssistedExtractor,
    grouped_train_validation_split,
    selected_semantic_extractor,
)

__all__ = [
    "AttributeResolver", "AttributeResolverExtractor", "ClaimResolution", "EntityNode",
    "EvidenceQuery", "EvidenceResolver", "EvidenceState", "ExtractionCandidate",
    "EventEvidence", "ExtractionResult", "FactRecord", "GraphEvidence", "ParseStatus",
    "ReasoningEngine", "RelationEvidence", "TemporalChange", "TemporalIndex",
    "TemporalKnowledgeGraph", "TextFactParser", "ExpandedDeterministicExtractor",
    "GroupedSplit", "HybridSemanticExtractor", "P1ParserAdapter", "SemanticExtractionResult",
    "SpacyAssistedExtractor", "grouped_train_validation_split", "selected_semantic_extractor",
    "build_graph", "build_graph_from_paths",
    "practice_extraction_metrics",
]
