# P0 compatibility audit for P1

## What P0 provides

`foundation.py` provides typed `TypedValue` and `AtomicFact` records; a lexicon model with alias resolution and attribute validation; `EvidenceRecord`, `TemporalObservation`, `CandidateFact`, and `VerificationResult` containers; CSV/lexicon loading; schema validation; typed value comparisons; output/claim validation; and `evidence_audit()`.

`load_inputs()` accepts the official runtime columns (`id`, `text`, `date`, `label`) and can also parse a `form` column when one is present in the practice data. It canonicalizes known subject aliases and rejects unknown attributes. The official runtime contract omits `form`, so a row's facts are empty at inference unless another component extracts them.

`observations()` gives facts from `true` rows `confirmed_true` status. Facts from `false` rows deliberately receive `row_false_atomic_status_unknown`, because the row label only guarantees that at least one of its facts is false. `unsure`, unlabelled, malformed rows are not promoted to confirmed evidence.

`evidence_audit()` summarizes histories, same-day conflicts, changes, event-date candidates, relation candidates, and direct as-of observations. It is a conservative audit over available parsed forms, not a Temporal Evidence Graph, not a text parser, and not an inference-time truth index. In particular, historical facts are not assumed to persist to 29 October 2026.

`runner.py` loads official inputs, prints the evidence audit, accepts exactly 1,000 externally produced claims after validation, and currently labels every unlabeled row `unsure`. It has no learned classifier or claim generator.

## Features that can be built now

For every official input row, P1 can use sentence text, the page date, and the published lexicon (canonical entity/alias mentions and attribute vocabulary). Those are available for both practice and final-universe rows. The classifier target `label` is used only for labeled training rows and evaluation labels.

From training-only practice evidence, a later evidence feature builder may index only atomic facts from `true` rows, preserving row ID, date, and provenance. It must query only evidence allowed by the claim's date and must treat false-row atomic status as unknown. The final input itself has no forms, so extracting candidate claims from arbitrary rows still requires a text parser before such evidence can be retrieved or compared.

## Still needed for full factual labeling

- A semantic text parser to recover subjects, attributes, values, multiple facts, negation, coreference/pronouns, units, and relative dates from `text`.
- Temporal retrieval and state resolution to determine which evidence precedes a claim, whether a value changed, and what held on the claim date or at an event.
- A verified fact index and contradiction policy that distinguish a known false atomic claim from missing evidence or an `unsure` case, without treating an entire false row's facts as false.
- Evidence-quality and abstention logic for conflicts, incomplete histories, and claims the parser cannot ground.

The P1 benchmark in this directory evaluates the row-label classification problem from text/date/lexicon features only. It does not use `form` as an inference feature and does not claim to solve extraction or temporal truth reconciliation.
