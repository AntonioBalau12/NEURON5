# P1.7 Recall-First Candidate Expansion

This directory contains an isolated experiment. It does not modify production graph code. Every generated hypothesis is marked `UNVERIFIED_CANDIDATE`; no classifier, evidence resolver, or claim generator consumes these outputs.

## Reproduce

Use the repository's already available Python environment; no packages are installed by this experiment.

```powershell
uv run --no-project --offline python -B -m unittest discover -s experiments/p17_recall -v
uv run --no-project --offline python -B experiments/p17_recall/benchmark_recall.py
uv run --no-project --offline python -B experiments/p17_recall/runtime_benchmark.py
```

The grouped development split uses the published P1.6 seed. The confirmation split uses the predeclared seed `neuron5-p17-confirm-v1`. Resolver parameters, training examples, BM25 statistics, and retrieval indexes are fitted from each split's training rows only. Validation forms are read only by the scorer. The practice truth labels are never used as generation targets.

## Files

- `candidate_factory.py`: local BM25 indexes, explicit/overlapping entity spans, typed value spans, schema-constrained candidate enumeration, deterministic ranking, caps, deadlines, and provenance.
- `benchmark_recall.py`: cumulative R0–R5 evaluation, component recall, per-claim/global-budget curves, split leakage audit, and CSV/JSON/JSONL reports.
- `runtime_benchmark.py`: performance-only synthetic replay with labels/forms absent from timed inputs; attempts two-core affinity and records whether it succeeded.
- `test_candidate_factory.py`: focused experimental regression tests.
- `RESULTS.md`: measured findings and limitations.

The runtime replay repeats text from the grouped confirmation claims to reach 20,000 rows. It is a performance workload, not 20,000 independent examples or an accuracy benchmark.
