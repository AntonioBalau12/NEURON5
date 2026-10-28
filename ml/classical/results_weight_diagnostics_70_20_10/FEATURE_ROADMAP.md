# Fact-aware feature roadmap based on P0

## Existing P0 contract and interfaces

`foundation.py` defines `TypedValue`, `AtomicFact`, `Lexicon`, `EvidenceRecord`, `TemporalObservation`, and `CandidateFact`. `parse_evidence_form` validates a supplied JSON fact list against the claimed-value schema and canonicalizes lexicon aliases. `observations` labels facts from true rows `confirmed_true`, false-row facts `row_false_atomic_status_unknown`, and unsure rows `row_unsure`. `evidence_audit` uses only confirmed-true observations for support, dated histories, comparisons, changes, event/date relations, and strict as-of counts. It intentionally does not treat the `false` row label as proof every fact in that row is false and does not infer persistence from past observations.

`runner.py` reads `id,text,date,label` and a lexicon through `load_inputs`, runs `evidence_audit`, validates externally supplied candidates, and writes contract-compliant output. It has no text-to-fact semantic parser, verifier, retrieval layer, or prediction adapter. Runtime rows do not include gold `form`; validation/test forms are evaluation-only.

## Features available now

The current classical builder uses word/character TF-IDF, row date and cyclic date metadata, lexicon entity/alias mentions, attribute-term flags, numeric/currency/month counts, and negation/temporal cue flags. These are computable identically at training and runtime from text/date/lexicon. Existing P0 can also parse already-supplied typed facts and audit the training-only true evidence if that evidence is bundled.

## Next fact-aware increment (no second graph engine)

1. Add one local text-to-`CandidateFact` parser interface using the P0 `AtomicFact`/`TypedValue` structures and lexicon canonicalization; measure parse coverage and unknown-entity/attribute rates. Train and runtime must call the same versioned parser.
2. Freeze an evidence index from **training-partition-only** evidence, using P0 `TemporalObservation` and existing `evidence_audit` logic. Store provenance row IDs and observed dates; do not ingest validation/test forms. Reuse these structures rather than creating another knowledge graph.
3. For parsed candidate facts, add features: exact/canonical subject-attribute match; typed kind match; unit/currency compatibility; normalized numeric difference only after compatible unit conversion; direct-date match and time since observation; counts of confirmed-true support and explicit typed conflicts; and parse/coverage indicators.
4. Treat missing retrieval, incompatible types, and no evidence as unknown, not contradiction. Only count contradictions where a permitted source explicitly establishes an incompatible value for the same entity/attribute and relevant date. Never derive a false fact from a false-row label.
5. Evaluate extraction coverage separately from label classification, then compare fact-aware features with this shared grouped CV. Keep the as-of date semantics explicit; historical truth does not establish current truth.

No P0 core files are changed by this diagnostic.