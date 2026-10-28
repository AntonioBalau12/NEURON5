# Temporal evidence graph

`core.graph` builds an in-memory, indexed evidence graph from the runtime universe and the supplied lexicon. It reuses `foundation.py` types (`InputData`, `EvidenceRecord`, `AtomicFact`, `TypedValue`, `Lexicon`) and the official claimed-value schema validator.

## Entry points

```python
from core.graph import build_graph, build_graph_from_paths, EvidenceResolver, TemporalIndex, ReasoningEngine

graph = build_graph_from_paths()  # /universe/universe.csv and /universe/lexicon.json
# Local development: build_graph_from_paths("data/runtime.csv", "data/lexicon.json",
#                                           "data/practice.csv")

resolver = EvidenceResolver(graph)
temporal = TemporalIndex(graph)
engine = ReasoningEngine(graph)
```

`build_graph` accepts P0 `InputData`, `EvidenceRecord` objects, or iterable CSV-like mappings. Forms are optional. `build_graph_from_paths` uses the packaged `data/practice.csv` as optional reference evidence when present; pass `use_packaged_practice=False` to disable this or pass a different `reference_csv`. A reference source is merged by row ID only when text, date, and label also match. A reference ID absent from the runtime universe is kept once; conflicting identity is reported and not merged.

## Trust and indexes

The graph has canonical `EntityNode`s and stores each row once in `evidence_by_id`. Fact records are indexed by `(canonical subject, attribute)`, observation date, and exact typed key; candidates also have their own key index. Name-valued supported observations are indexed as entity relations. `FactRecord` stores observation date, optional explicit validity boundaries, source row, evidence state, parsing state, provenance, confidence, and evidence IDs.

Only valid forms on `true` rows become `VERIFIED_SUPPORT`. Forms on `false` rows remain `UNVERIFIED_CANDIDATE` because the row can contain several facts while only one is false. `unsure`, unlabeled, malformed, and text-only extractions are not verified. Deterministic extraction never verifies itself. No validity interval is inferred from an observation date. Same-day comparable value disagreement is marked `CONFLICTING`; normalized equivalent units remain equivalent. Date values with different precision remain unresolved.

## Queries

- `TemporalIndex.get_entity` and `get_fact_history` resolve entities and return ordered records with provenance.
- `EvidenceResolver.query` and `get_evidence` return support, refutation, conflict, candidate, or unknown results. Date-scoped lookups use exact observations or explicitly supplied intervals only.
- `TemporalIndex.get_temporal_changes` returns ordered pairs of comparable, non-operator true observations as **change candidates**. Different observation dates and values do not prove a transition or continuous validity; `ReasoningEngine` therefore keeps these claims unverified. Same-value, incompatible, conflicting, and date-precision-ambiguous pairs are excluded.
- `TemporalIndex.get_comparable_facts` finds date-grounded, unit-compatible peer facts.
- `TemporalIndex.get_event_facts` joins full-precision event dates to facts observed on that exact day.
- `TemporalIndex.get_verified_relations` joins a verified name link to a target fact observed on the same day.
- `ReasoningEngine.evaluate_facts` applies multi-fact aggregation; a claim is true only if every atom has independent support, and false only if an atom has explicit verified refutation. Unknown and conflict remain distinct.
- `ReasoningEngine.evaluate_evidence_row(row_id)` evaluates an ingested row and automatically excludes its own row ID from evidence.
- `ReasoningEngine.evaluate_claim` covers the official claim types. Fact/compare use 29 October 2026 by default; change, event, and relation follow their contract-specific temporal semantics.

Callers can pass `exclude_evidence_ids` to prevent a source row from verifying itself. Evidence records retain provenance IDs; conflicts attach references to the other conflicting rows.

## Parsing and limits

The deterministic parser emits **partial, unverified candidates** when it can align an explicit lexicon entity, a lexicalized attribute cue, and a supported scalar surface pattern. It handles digit quantities and units, common currencies and billing periods, percentages, durations, ISO/month-name dates, version prefixes, explicit entity names, and simple negation for boolean attributes. It detects simple numeric comparison operators. It does not resolve pronouns, broad paraphrases, spelled-out numbers, most implicit attributes, arbitrary name spans, full comparison claim text, or complex clause scope. Its measured practice-form exact extraction coverage is reported by `practice_extraction_metrics` and `scripts/benchmark_graph.py`; candidates must not be treated as facts.

P1.5 adds an interchangeable extractor interface. The Graph Builder defaults to the selected `HybridSemanticExtractor`: expanded deterministic extraction plus a TF-IDF attribute resolver restricted to money candidates. If `attribute_resolver.json` is missing, it falls back to `ExpandedDeterministicExtractor`; `P1ParserAdapter` remains an explicit original-parser fallback. Candidate details retain the source row, observation date, method, confidence, ambiguity flag, and subject/value text offsets in `GraphEvidence.extraction_candidates`. The resolver is dependency-free and its checked-in JSON artifact is trained only on grouped training rows by `scripts/train_attribute_resolver.py`; held-out forms and row truth labels are excluded. No spaCy package or English pipeline is required or loaded. Use `scripts/evaluate_semantic_extraction.py` for the reproducible grouped comparison. Practice forms provide semantic labels regardless of row truth; they never alter evidence state.

The graph does not assume an attribute is single-valued and does not infer atom-level refutation from false rows. It does not use ML/NLI. Practice forms are available as reference evidence only when explicitly supplied; they are not assumed to exist in runtime CSV rows. Relation and event joins require same-day observations, and event dates require day precision. A later Claim Factory must still validate rendered text and novelty against the official contract.

## Benchmark

Run offline with:

```text
uv run --no-project --offline python -B scripts/benchmark_graph.py
```

The script strips `form` when making runtime-shaped rows, optionally loads the packaged practice file as reference evidence, reports deterministic extraction precision/recall, construction time, `tracemalloc` peak, and indexed query timings. Practice evidence in this benchmark is not independent support for unlabeled claims.
