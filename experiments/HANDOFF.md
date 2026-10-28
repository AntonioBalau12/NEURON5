> **SUPERSEDED** by `experiments/FINAL_REPORT.md` (written after A, B, C and D finished and the sequential comparison ran). Kept for the record of the mid-run state.

# NEURON5 P3 fact-reconstruction research: handoff

Written 2026-10-28 ~20:25 local. Nothing is committed or pushed. This file states what is **done and measured**, what is **interim**, and what is **still open**, so the work can resume without re-reading the chat.

## Where things are

| Item | Value |
|---|---|
| Worktree | `C:\Users\andrei\Documents\GitHub\NEURON5-p3` |
| Branch | `feat/p3-fact-reconstruction-research`, created from `origin/feat/p1-temporal-graph` at `f75f514` |
| Original checkout | `C:\Users\andrei\Documents\GitHub\NEURON5` on `main`. Untouched by this work. Its uncommitted frontend edits are the user's own |
| Git state | Only `experiments/` (and `__pycache__`) is untracked. No tracked file was modified. P0 and `core/graph` are unchanged |
| Python | `py` (3.14.0). `uv` is not installed. pip works. Machine has 8 logical CPUs and about 7.9 GB RAM, Java 8 only |

## Platform limitations to report in the final write-up

- **Model selection:** subagents cannot be launched on a chosen model. Gemini 3.8 Flash and Haiku were not selectable. The four packages ran on the platform default model. Do not describe them as Gemini or Haiku runs.
- **Tool status was unreliable:** several subagent launches returned "cancelled" while the agents kept running and writing files. Judge progress by files on disk, not by the returned status.
- **Isolation is by agreement:** each agent was told to write only under its own directory and not to read held-out gold. Nothing enforces this at file-system level. Before the final report, audit extractor code for hard-coded sentences or ids and for any read of `experiments/shared/_heldout/` or `data/practice.csv` forms.

## Shared contract (coordinator, done)

- `experiments/shared/EXCHANGE_FORMAT.md`: fact exchange format. Keeps event date (the value), page date (`source_publication_date`), and explicit validity (`valid_from`/`valid_to`) separate. `source_label` is separate from `verification_status`, which is always `candidate` for extractors.
- `experiments/shared/fact_schema.py`: validator. Checks span offsets against the row text, lexicon subject and attribute, and the value schema.
- `experiments/shared/make_split.py` and `data/`: fixed split. 1,897 rows total, 1,627 dev, 270 held-out (rule `sha1(id) % 100 < 15`). `data/full_input.csv` is runtime-shaped (no `form`). `_heldout/heldout_gold.csv` is evaluator-only.

## Status per work package

| Pkg | Dir | Status at handoff |
|---|---|---|
| A OpenIE | `experiments/openie/` | **In progress.** `output/facts.jsonl` has 2,184 facts, schema-valid (0 invalid), last written 20:20. A process was still running. **Missing:** `REPORT.md`, `FAILURES.md`, dev self-check, deployment assessment. Interim output, not final |
| B Slot filling | `experiments/slot_filling/` | **In progress.** `output/facts.jsonl` has 1,595 facts, schema-valid, last written 20:12. **Missing:** `REPORT.md`, `FAILURES.md`, attribute coverage report, dev self-check. Interim output |
| C Evaluator | `experiments/evaluation/` | **Harness complete.** Result was returned. 65 pytest tests pass (re-run by me). Full comparison not yet run |
| D Claim factory | `experiments/claim_factory/` | **In progress.** Generator and validator exist, two runs on practice forms. **Missing:** `FEASIBILITY_REPORT.md`, and the rerun with reconstructed facts |

Scratch files to remove or ignore at the end: `openie/tools/_attrs_dump.txt`, `openie/spacy_install.log`, `slot_filling/_t*.py`, `claim_factory/_x.py`, and `evaluation/_scratch/`. Keep `evaluation/_scratch/dump.txt` and `selected.txt` out of any shared upload, since they contain held-out gold.

## Measured results so far

All numbers below were read from files in this worktree. None is final.

### Existing deterministic parser (measured)

- Whole practice set, `scripts/benchmark_graph.py` (run by me): precision 0.828, recall 0.227 against the gold `form` (545 exact of 658 candidates; 2,402 gold facts). Per kind recall: date 23/165, money 12/268, name 4/209, duration 7/229, version 13/128, percent 48/201, quantity 352/1,028, boolean 86/174. Graph build 11.6 s, `tracemalloc` peak 7.3 MB.
- **Leak found:** `core/graph/builder.py` derives the parser's `attribute_kinds` and `known_units` from gold forms. The figure above therefore flatters the baseline. The evaluator's `baseline_parser.py` uses dev rows only.
- Evaluation set, baseline only (`evaluation/results/baseline_smoke/`, 135 rows: 120 held-out, 15 dev control; 183 form facts):
  - Precision vs form 83.7% (41/49), 95% interval 71 to 96.
  - Recall vs form 22.4% (41/183), interval 17 to 28.
  - Facts beyond the form: 8, all reviewed by the evaluator model and judged incorrect (not human-verified).
  - Negation recall 4/14. Temporal cue captured 0/28.
  - 4.42 s CPU, 23.9 MB peak, 2 threads.
- **Recall ceiling:** 53 of 183 form facts have a subject that is not written in the sentence. A sentence-only extractor cannot exceed about 71% recall.
- **Form completeness:** the evaluator found only 4 suggested missing facts in 135 rows (unverified). The `likely_incomplete_form` stratum (22 rows) is a text heuristic and mostly a false alarm.

### Claim factory on practice forms only (measured, preliminary)

| Run | Settings | Claims written | Official `validate_output` problems | Total time |
|---|---|---|---|---|
| `run_main` | max age 14 days, min support 1 row | 411 | 0 | 9.2 s |
| `run_highprecision` | max age 7 days, min support 2 rows | 270 | 0 | 17.3 s |

- Both runs are far below 1,000 (589 and 730 short). Two further run folders, `run_relaxed` and `run_max_relaxed_samekind_top1000`, exist and I have not inspected them.
- The per-type breakdown and rejection reasons are in each run's `rejections_summary.json`. I did not read them.
- Limitation: only practice rows exist locally, so evidence here is the practice rows only. The real run's other ~18,000 rows are unlabelled.
- Do not treat 411 as a safe count. Whether these claims are actually true on 29 Oct 2026 depends on the "fact still holds" rule, which has not been reviewed by a person. A `novelty_risk.json` file exists in `run_main` and should be read.

### Interim extractor output (schema only)

- OpenIE 2,184 facts and slot filling 1,595 facts, both 0 schema-invalid.
- **Nothing is yet known about their accuracy.** Schema validity only proves that spans, lexicon names and value shapes are well-formed. It says nothing about correctness. The evaluator deliberately did not score these.

## Ablation table (to be filled by the final run; do not fill from estimates)

| Approach | Fact precision | Fact recall | Correct new facts | CPU time | Extra valid claims |
|---|---|---|---|---|---|
| Existing parser | 83.7% vs form [71-96] (measured, eval set) | 22.4% vs form [17-28] (measured) | 0 of 8 judged correct (evaluator model, not human) | 4.42 s CPU (measured, eval harness) | n/a, practice forms baseline: 411 claims (preliminary) |
| OpenIE | pending | pending | pending | pending | pending |
| Slot filling | pending | pending | pending | pending | pending |
| OpenIE + slot filling | pending | pending | pending | pending | pending |

## Next steps, in order

1. **Let A, B and D finish.** Check `list_processes` or file times under `experiments/*`. Confirm the missing reports exist. Re-read each report critically instead of trusting the self-reported numbers.
2. **Freeze the facts files.** Record sha1 of `openie/output/facts.jsonl` and `slot_filling/output/facts.jsonl` before any scoring. If an extractor changes after the evaluator has looked at its output, say so in the report.
3. **Fill resource commands.** Put commands for `openie` and `slot_filling` into `evaluation/resource_commands.json` (placeholders `{python}`, `{input}`, `{out}`). They are `null` now.
4. **Run the comparison sequentially**, nothing else running, 2 threads:
   ```
   $env:PYTHONUTF8='1'
   py experiments/evaluation/combine.py
   py experiments/evaluation/measure_resources.py --out experiments/evaluation/results/resources_final.json
   py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --resources experiments/evaluation/results/resources_final.json --out experiments/evaluation/results/final
   ```
   Results folders are never overwritten, so use a new name per run.
5. **Rerun the claim factory with extra facts** from each method and from the combined variants, e.g. `py experiments/claim_factory/generate_claims.py --extra-facts <jsonl> --out experiments/claim_factory/output/run_<name>`. Report per rule how many claims are added. Compare against `run_main` (411).
6. **Human review.** Ask for a human check of the unreviewed extras (`judgement_template_unreviewed_candidates.csv`) and of `worksheet/annotation_worksheet.csv`. Until then, every "new fact" is an unverified candidate. Do not say "recovered N correct facts".
7. **Integration point.** Candidate: feed verified-by-agreement reconstructed facts into `core/graph/builder.py` as `UNVERIFIED_CANDIDATE` records with provenance (`FactRecord.provenance`), never as `VERIFIED_SUPPORT`. The graph already keeps candidates in `candidate_facts_by_key` and `candidates_by_row`. No change to P0 or graph code without approval.
8. **Write the final report** answering Q1 to Q6. State what cannot be claimed:
   - No end-to-end classification retraining has been run, so no classification improvement can be claimed from extraction coverage alone.
   - Evidence retrieval and knowledge-base completeness can only be reported as extraction counts until a downstream test exists.

## Open questions for the user

- Should the final comparison wait for A, B and D to finish, or freeze whatever exists now?
- Who will do the human verification of the worksheet and unreviewed extras? Without it, "correct new facts" stays unmeasured.
- Should the interim work be committed to the branch? It is currently untracked and has not been committed, per the working rules.
