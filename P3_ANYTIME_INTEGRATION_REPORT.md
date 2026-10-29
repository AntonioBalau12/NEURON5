# P3 Claim Factory + Anytime Integration — Diagnostics Report

## Scope and provenance

- Worktree branch: `feat/p4-p3-anytime-claims-integration`, based on `87798b721250dba11b6d52863278faa1b65230d4` (`feat/p17-p2-bm25-integration`).
- Reused P3 implementation source: commit `dd4369e057427ac12b496c3e3fac0bdba40e469d` (descends from the specified initial P3 commit).
- The P3 rule, observation, rendering, text-check and store modules were ported into `core/claims/p3/`; imports were adapted for package use. P3 generation rules remain the source of candidates.
- No challenge contracts, datasets, model artifacts, or `ml/classical/` files were changed. No network or LLM is used at runtime, and no model was trained. At the user's request, `uv` fetched local test dependencies into its cache; no repository dependency files changed. No commit or push was made.

## Implemented behavior

- `ClaimFactory` is called from `runner.py`; normal operation no longer requires a precomputed 1,000-claim JSON file. The legacy `--candidates-json` option is not trusted as factual input.
- Claim generation reads the runtime universe, lexicon, and packaged practice forms through the P1 temporal graph. Only TRUE-labelled, form-grounded practice evidence can support candidates. Runtime text extraction, retrieval results, and model predictions remain candidates; they are not promoted to evidence.
- The current LightGBM classifier and P2 retrieval-feature path remain intact. P2 retrieval predictions/features do not act as evidence for the claim generator; P3 generation uses the shared graph/evidence contracts. P1.7/P2 text candidates are not independently admitted as new trusted facts because runtime universe rows have no labels/forms proving those facts.
- Enabled strategies: `fact`, same-attribute `compare`, engine-verified `relation`, exact-day `at_event`, and engine-verified `change`. Experimental `cross_date`, `safe_transition`, and `relax_definitive` paths are not enabled.
- Additional P4 gates require direct evidence on the contract as-of date for current mutable facts and both sides of comparisons/relations. A past date is exempt only when P3 marks it as an immutable one-time event date. Event date precision variants are normalized; distinct event dates are quarantined. Historical observations alone do not establish a change.
- P3 contract/text/lexicon checks, full-input novelty, semantic deduplication, and provenance are retained. The heuristic ranking score is not a probability. Output confidence is capped conservatively at 0.65 and is not claimed to be calibrated.
- The runner writes an initial all-UNSURE checkpoint, replaces it with classification output when inference succeeds, checkpoints classification batches, then atomically publishes the best eligible claim pool. A partial file is structurally validated against its actual count and explicitly reported as short of the official 1,000. Invalid writes do not replace the prior valid checkpoint; an existing valid 1,000-claim output is retained unless another exact 1,000-claim output is ready. The scheduler reserves 5% of remaining time (3-second floor) and at least three times the last measured write/validation duration, while using observed strategy runtimes to decide whether to start another phase.

## Claim type readiness

| Type | Evidence / temporal rule in the production adapter | Current risk treatment |
|---|---|---|
| `fact` | P3 accepted support plus direct as-of-day observation, or an immutable past event date | Mutable facts supported only by recent older observations are excluded; no persistence interval is inferred. |
| `compare` | P3 same-attribute, same-kind comparison; both sides must be direct as-of-day or immutable event-date facts | Cross-attribute and cross-date generation is disabled. |
| `change` | P3 engine verification and explicit transition wording with both endpoints in a trusted support sentence | Historical value pairs by themselves are rejected. No change claim survived the practice smoke. |
| `at_event` | P3 exact event-day join, with supported event date and fact on that day | Ambiguous/multiple distinct event dates are quarantined. |
| `relation` | P3 verified link/target join plus direct as-of evidence for both link and target fact | Historical same-day relation pairs do not imply the relation remains current. None survived the practice smoke. |

Every emitted form is checked against the official entry schema and text checks; values and entity/attribute names are checked through the existing contracts and lexicon. Candidate claims have deterministic IDs and are deduplicated by canonical semantic identity.

## Measurements

The official `/universe/universe.csv` is not present in this worktree (`data/universe.csv` and `/universe/universe.csv` are absent). The only available source was `data/practice.csv` (1,897 rows), which was used as both the smoke-test universe and the packaged reference evidence. Therefore these are practice-only measurements, not official-universe or 18,000-row results.

| Measurement | Result |
|---|---:|
| Graph/store construction | 6.26 s |
| Candidate generation by five enabled strategies | about 0.10 s |
| Factory elapsed time, one final ranking pass | 6.95 s |
| Raw candidates generated | 1,502 |
| Eligible before contract/dedupe | 222 |
| Distinct accepted candidates | 220 |
| Published claims | 220 |
| Deficit to required 1,000 | 780 |
| Peak RSS | Not measured |

Selected claim types in that smoke run: 40 `fact`, 151 `compare`, 29 `at_event`, 0 `change`, 0 `relation`. The selected portfolio reuses 76 distinct evidence IDs across multiple claims; the most reused evidence ID supports 16 selected claims. These dependency counts are exposed with per-claim trace metadata and do not imply independent source reliability. The 1,063 `not_verified_by_p3` rejections include rejected/unverified candidates; other main exclusions were 109 mutable current facts without direct as-of evidence, 66 comparisons with at least one such side, 32 event-date conflicts, and 10 historical relations without direct as-of support. Two otherwise eligible candidates were excluded by novelty checks.

The end-to-end runner smoke used the same practice input and a temporary output path. It published 220 claim rows, returned success for the best-available partial result, and produced 0 errors from `foundation.validate_output(..., expected_claims=220)`. The official `expected_claims=1000` check reports the one expected count error. This is not 1,000-claim compliance.

The factory callback smoke emitted successive pool sizes of 40, 191, 191, 220 and 220 claims across the five strategy phases, then selected 220; it used a no-op 10 ms callback, so its 8.70-second elapsed time is not the actual CSV checkpoint-write benchmark. In the real runner path, every phase pool is passed to `CheckpointManager` for structural validation and atomic publication. The end-to-end runner smoke used the actual serialized model artifact and confirmed final partial-output validation; because all practice rows already had labels, it did not classify any rows. Separately, a one-row temporary unlabeled input was passed through the actual M2 artifact and returned `true` at 0.9488 confidence under its serialized scikit-learn 1.6.1 version. This is a load/inference smoke, not a classification metric.

Historical P3 figures from the P3 feasibility report are not directly comparable to the stricter production gate above:

- Original strict P3: 411 accepted claims (140 fact, 200 compare, 0 change, 61 at-event, 10 relation).
- Relaxed experimental P3: 1,038 accepted before selection, per the integration task context. That run used relaxed assumptions/experimental combinations and does not establish factual correctness.
- Historical fixed-confidence Top-1,000: not a safe baseline for comparison; the P3 report marks the relaxed/combinatorial 1,000-claim variants unsafe.
- New risk-ranked Top-1,000: not produced. This run yielded only 220 eligible claims, so selection-quality improvement over a 1,000-claim portfolio cannot be measured.

No human/referee audit, held-out calibration, or independent factual audit of the selected 220 was run. Contract validity is not the same as factual correctness. The ranking score is heuristic and confidence calibration remains unverified.

## Runner, dependencies and deployment limits

- Offline execution and atomic same-directory replacement were exercised on Windows with `uv run --no-project --offline`; output validation stayed within the 16 MiB official limit and used standard CSV quoting/UTF-8.
- A valid partial checkpoint was preserved when a deliberately invalid final claim set failed validation. The short-deadline and SIGTERM scheduling paths have unit-level coverage; full OS-level SIGTERM during generation/write was not simulated.
- The serialized `ml/classical/results_m2_v1/model.joblib` artifact exists. At the user's request, `uv` installed the needed packages into its isolated run cache (NumPy, SciPy, joblib, LightGBM, scikit-learn 1.6.1); no repository dependency file was changed. The artifact smoke emitted no scikit-learn version warning with 1.6.1.
- No root `pyproject.toml`, `uv.lock`, or `requirements*.txt` is present. The official offline dependency contract is therefore still not encoded in the repository and must be supplied by the competition runtime setup.
- No official 18,000-row/20,000-row run, synthetic 5k/20k performance benchmark, peak-RSS measurement, Linux AMD64 test, or Docker image test was possible in this environment. Container/runtime readiness remains unverified.

## Test results

- Full regression suite: **120/120 tests passed** offline with `uv run --no-project --offline` and the ephemeral dependencies above, including both `test_m2_fold_safety.py` and `test_runner_m2.py`.
- Focused Claim Runtime tests: **8 passed**.
- Practice-only phased Claim Factory and actual-model runner validation smokes: completed as described above.
- `git diff --check`: clean; new untracked Python/Markdown files were also scanned for trailing whitespace.

## Required follow-up / blockers

1. Encode/provide the approved offline runtime dependency setup, pinning scikit-learn 1.6.1 to match the serialized model, without changing model weights.
2. Run against the actual full universe with the official runtime deadline and memory/CPU limits. This is required to measure classification completion, total runtime, peak RSS, final claim yield, and 1,000-count feasibility.
3. Define an allowed independent verification source for additional universe-text facts. Do not promote unlabelled text candidates, retrieval matches, or model pseudo-labels by themselves.
4. Resolve the 780-claim practice-smoke deficit using only evidence the challenge permits. Do not add relaxed freshness, mixed-attribute comparisons, or inferred transitions as factual proof.
5. Conduct an independent human/referee or held-out factual audit before claiming any ranking-quality improvement.
6. Validate on Linux AMD64/Docker when that environment is available; it was not tested here.

This integration does not claim to solve the full challenge.
