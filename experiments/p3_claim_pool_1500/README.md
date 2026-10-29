# P3 Verified Claim Pool Benchmark

## Result

Benchmark input: `data/practice.csv` (1,897 rows). The factory uses the P3 evidence store, verified TRUE-row forms, existing ranking and BestK selection, plus the contract checker.

| Strategy set | Candidates | Distinct accepted | Reserve beyond 1,000 | Selected | Factory time | Official validator |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| fact, compare, change | 2,157 | 1,036 | 36 | 1,000 | 5.88 s | Passed |
| all five strategies | 2,297 | 1,075 | 75 | 1,000 | 7.00 s | Passed |

The five-strategy set includes `at_event` and `relation`; these remain subject to P3 verification, factual checks, novelty checks, and the repository validator. It is now the factory default. The 1,500 accepted-claim reserve target was **not reached**: the measured pool is short by 425. No evidence gates were relaxed to fill it.

The final all-strategy run recorded 9,047 ranking evaluations across five cumulative passes, of which 6,750 were repeat evaluations. The validation cache avoided repeating static contract validation for candidates already seen in earlier passes. Stateful novelty and duplicate checks still run each pass. The as-of guard rejects mutable current facts unless there is a TRUE observation on the actual as-of date; explicitly immutable facts retain their existing exception. The six date-attribute renderers recovered claims without changing evidence requirements.

## Remaining blockers

- 149 comparison candidates lack directly observed as-of grounding for a comparison side.
- 108 current-fact candidates lack a directly observed as-of fact and do not qualify as immutable.
- 32 event-date candidates have conflicting/rescheduled dates.
- The remaining P3 rejections include insufficient or contradictory endpoint evidence, stale comparison sides, unsupported transitions, and missing co-temporal relation evidence.

These are evidence/coverage limits. More claims require additional verified evidence or a better inference-time evidence source; changing candidate count or relaxing the contract would not make them verified.

## Runtime and validation

Timing is measured on this host, not an estimate of a production deployment. The reported factory time includes candidate generation, ranking/checking, and selection with simulated checkpoint callbacks. The benchmark also ran one final atomic output publication and the official local output validator for each strategy set; both passed with exactly 1,000 selected claims.

Reproduce with:

```powershell
uv run scripts/benchmark_claim_factory.py --checkpoint-mode simulated --validate-final --output experiments/p3_claim_pool_1500/profile-final-validated.json
```

Detailed per-pass metrics are in `profile-final-validated.json`.

## Existing test discrepancy

`python -m unittest tests.test_claim_runtime -v` reports 15 passing tests and one failing expectation: `test_generated_change_preserves_endpoint_ids_and_dates` expects `change_rule="engine"` to verify a transition from two observations. The graph documentation and engine intentionally classify different dated observations as change candidates, not proof of an actual transition. The test expectation conflicts with that documented policy; this benchmark did not weaken the transition rule to satisfy it. The as-of grounding test passes.
