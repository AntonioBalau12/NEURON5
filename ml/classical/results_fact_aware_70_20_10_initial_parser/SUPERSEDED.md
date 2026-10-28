# Superseded first-pass outputs

Preserved for audit, but not the final benchmark result. The first pass showed that the existing parser reduced month-day-year phrases such as “January 12, 2026” to a year-only candidate. The feature extractor was corrected to normalize that surface form and distinguish lexical evidence similarity from typed value compatibility, then all 10-fold, validation, and outer-test ablations were rerun into `../results_fact_aware_70_20_10/`.

Use the rerun in the parent sibling directory for reported results. The separate `results_fact_aware_70_20_10_attempt1_incomplete/` contains an interrupted run and only its progress record.
