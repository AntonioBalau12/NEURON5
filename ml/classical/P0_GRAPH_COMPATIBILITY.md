# P0 and Temporal Graph compatibility audit

## Interfaces inspected

- `foundation.py` provides `Lexicon`, `TypedValue`, `AtomicFact`, `EvidenceRecord`, `InputData`, schema validation, `parse_evidence_form()`, date normalization, and typed value comparisons. `form` is optional and not part of the final runtime row.
- P0's `observations()` marks facts from true rows `confirmed_true`; a false row only establishes that at least one fact in its form is false, so individual false-row atoms remain unknown. `evidence_audit()` does not parse arbitrary claim text or imply persistence of an observation.
- `core/graph` from `feat/p1-temporal-graph` reuses the typed P0 interfaces. `build_graph()` validates forms; a valid form on a `true` row produces `VERIFIED_SUPPORT`; forms on false/unsure/unlabeled rows are `UNVERIFIED_CANDIDATE`; deterministic text extraction is never verified.
- `EvidenceResolver` scopes mutable facts to an exact observation date or an explicit validity interval. It does not infer a continuous state from two different observation dates. Same-day conflicts are represented separately. The inspected graph implementation contains no producer for `VERIFIED_REFUTATION`.
- `TextFactParser` handles explicit lexicon entities, attribute cues, and supported scalar/date patterns. It returns partial candidate facts. It does not reliably resolve pronouns, implicit attributes, general paraphrases, clause scope, or arbitrary multi-fact claims.
- P0 `runner.py` remains unchanged. It accepts externally produced candidate claims and has no built-in text parser, trained classifier, or neural inference path.

## Implemented boundary

The experiment adapter in `ml/classical/fact_aware_features.py` accepts target text/date/lexicon/graph/optional ID. It parses from target text only, excludes the target ID from evidence lookups, records typed and date differences, and leaves unsupported values missing. It does not turn missing or mismatched evidence into FALSE. Event-like attributes use an explicitly reported name heuristic solely to compare event-value candidates across observation dates; this is not a temporal state resolver.

The ablation copied `core/graph` source modules unchanged from `feat/p1-temporal-graph` to make the dependency importable in this P1 checkout. It did not modify `foundation.py`, `runner.py`, or existing Graph code. No merge, commit, or push was performed.
