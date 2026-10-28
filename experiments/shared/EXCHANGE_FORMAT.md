# Reconstructed-fact exchange format (coordinator-defined)

One JSON object per line (JSONL). Validate with
`py experiments/shared/fact_schema.py <file.jsonl>`.

| Field | Type | Meaning |
|---|---|---|
| `extraction_id` | str | Unique within the file, e.g. `p-1#openie#0` |
| `source_row_id` | str | `id` of the input row. Must exist in `shared/data/full_input.csv` |
| `source_label` | str | The row's label (`true`/`false`/`unsure`/``). A *property of the source*, not of the fact |
| `source_publication_date` | str | The row's `date`. Page date, **not** an event date |
| `subject` | str\|null | Canonical lexicon entity name. null if the subject could not be mapped |
| `subject_surface` | str\|null | Subject as written in the text |
| `attribute` | str\|null | Canonical lexicon attribute of `subject`. null if unmapped |
| `relation_surface` | str\|null | Relation words as written (OpenIE predicate or matched cue) |
| `value` | object\|null | A value valid under `contracts/claimed_value.schema.json`, no `op` unless the text states one. null if unmapped |
| `object_surface` | str\|null | Object/value as written |
| `negated` | bool | Whether the clause carries a negation (words in `value-forms.md` "Yes or no"). A boolean `value` of `false` caused by negation must also set `negated: true` |
| `source_text_span` | str | Exact substring of the row text supporting the fact |
| `span_start`, `span_end` | int | Character offsets such that `text[span_start:span_end] == source_text_span` |
| `fact_observation_date` | str\|null | Date the fact is stated to hold at. Set only if the TEXT says so explicitly. Do not copy the page date here |
| `valid_from`, `valid_to` | str\|null | Explicit validity interval from the text only |
| `temporal_qualifier` | str\|null | Raw temporal words (`"from today"`, `"still"`, `"since"`, `"now"`, `"as of"`, `"before"`). Not interpreted |
| `extraction_method` | str | `openie`, `slot_filling`, `deterministic_parser`, or `combined` |
| `extraction_confidence` | float | 0 to 1. An extractor-internal score. It is never evidence of truth |
| `parse_status` | str | `complete` (subject, attribute, value all mapped and unambiguous), `partial`, `ambiguous`, `unmapped` |
| `verification_status` | str | Always `candidate`. Extractors never verify. Verification is a downstream decision |
| `notes` | str | Free text: ambiguity reasons, rule names |

## Separation of concepts
- **Event date** is the *value* of a date-valued attribute (`joined`, `launched`). It lives in `value`.
- **Source publication date** is the row `date`. It lives in `source_publication_date`.
- **Validity interval** goes in `valid_from`/`valid_to`, only when the text states it.
- **Source label vs verification.** `source_label` says what the dataset says about the *sentence*.
  `verification_status` says whether this *extraction* is trusted. A fact from a `true` row is still only a candidate.
  A `false` row does not make each of its atomic facts false. An `unsure` row cannot certify anything.

## Rules for every extractor
1. Input is **text, date, id (and optionally the lexicon)** only. Never read gold `form`s of non-dev rows.
2. Never emit a fact with a value that is not written in the text. No inference from other rows.
3. Prefer abstaining (`unmapped`) over guessing an attribute.
4. Output covers `shared/data/full_input.csv`. All rows, runtime-shaped.
5. Do not use a generative LLM at extraction time.
