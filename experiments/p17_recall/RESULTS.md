# P1.7 Recall-First Candidate Expansion — Results

## Scope and trust boundary

This is an experimental semantic candidate generator, not a graph or classifier change. Every output hypothesis has evidence state `UNVERIFIED_CANDIDATE`; candidates never become positive or negative evidence. The factory does not read truth labels, does not read validation forms during generation, and does not invent values: typed values come from input text spans, and subject names come from the lexicon or bounded same-row pronoun/coordinated-subject hypotheses. The official graph, P1.6 refutations, classifier, claim generator, contracts, and datasets were not modified.

The generator retains source row, canonical subject/attribute/value, operator, spans, clause, method, scores, retrieved example IDs (with BM25 view), ambiguity, and evidence state. Candidate deduplication is canonical within each row. Caps are 512 candidates per row and 1,000,000 globally; both truncation and deadline expiration are reported. No caps were reached in the validation evaluations or 20k performance workload.

## Universe and split protocol

The supplied lexicon has 62 canonical entities, 321 distinct attribute names, 514 compatible subject–attribute pairs, 13 events, and up to 32 attributes on one entity. Practice contains 2,402 semantic form atoms across all labels and eight value kinds. The 514 compatible pairs are the first schema-level source of candidate growth; multiplying those by every text value and ambiguous entity would expand quickly, so candidate generation requires a text value, a compatible value kind, and a clause-local subject hypothesis.

R0 reproduces P1.6 E4 on its published grouped development split: 1,518 training rows, 379 validation rows, and 431 gold facts. A second grouped split was fixed in the script before evaluation with seed `neuron5-p17-confirm-v1`: 1,515 training rows, 382 validation rows, and 429 gold facts. Both splits group shared subject–attribute histories and normalized templates. Their train and validation partitions share no exact grouped histories or normalized templates. A token-Jaccard audit at 0.85 still found 7 near-duplicate pairs on development and 6 on confirmation, including several at 1.0; the confirmation score is therefore a useful grouped check, but not perfectly independent.

Attribute resolver examples, attribute/type hints, BM25 IDF and postings, and semantic memory were fitted from the training rows of each split. Retrieved example labels are not used. Forms appear only in training as semantic supervision and in validation for scoring.

## Cumulative oracle recall

Each stage includes its predecessor's candidate set: R1 includes R0, R2 includes R1, R3 includes R2@5, R4 includes R3, and R5 is the same R4 set after deterministic ranking. Matching is one-to-one and uses canonical subject, attribute, and P0 typed-value comparison. Oracle recall is primary; precision/F1 and exact-row accuracy are secondary diagnostics.

| Split | Stage | Candidates | Gold recovered / total | Oracle recall | Exact full rows |
|---|---|---:|---:|---:|---:|
| Development | R0 P1.6 E4 | 162 | 132 / 431 | 30.63% | 95 / 379 |
| Development | R1 schema expansion | 1,836 | 166 / 431 | 38.52% | 11 / 379 |
| Development | R2 BM25, K=5 | 1,843 | 166 / 431 | 38.52% | 11 / 379 |
| Development | R3 local pronouns, K=5 | 1,851 | 166 / 431 | 38.52% | 11 / 379 |
| Development | R4 local/relation views and coordinated subjects, K=5 | 2,048 | 174 / 431 | 40.37% | 11 / 379 |
| Development | R5 deterministic ranker, K=5 | 2,048 | 174 / 431 | 40.37% | 11 / 379 |
| New grouped confirmation | R0 P1.6 E4 | 137 | 100 / 429 | 23.31% | 79 / 382 |
| New grouped confirmation | R1 schema expansion | 1,818 | 125 / 429 | 29.14% | 8 / 382 |
| New grouped confirmation | R2 BM25, K=5 | 1,822 | 125 / 429 | 29.14% | 8 / 382 |
| New grouped confirmation | R3 local pronouns, K=5 | 1,822 | 125 / 429 | 29.14% | 8 / 382 |
| New grouped confirmation | R4 local/relation views and coordinated subjects, K=5 | 1,865 | 131 / 429 | 30.54% | 9 / 382 |
| New grouped confirmation | R5 deterministic ranker, K=5 | 1,865 | 131 / 429 | 30.54% | 9 / 382 |

Against R0, R1 recovers 34 additional development facts and 25 additional confirmation facts. R4 adds 8 and 6 more, respectively. Thus R4 recovers **42 previously missed development facts** and **31 previously missed confirmation facts** in total. R2 and R3 add candidate hypotheses but no further gold matches over R1. The increase in candidates sharply lowers exact-row accuracy, which is expected under a recall-first objective; false positives remain unverified.

### BM25 K sweep

BM25 was evaluated at K=1, 3, 5, 10, and 20. On development, R2 grew from 1,836 candidates at K=1 to 1,881 at K=20, while remaining at 166 recovered facts for every K. Confirmation grew from 1,818 to 1,834 candidates and remained at 125 recovered facts. BM25 therefore introduced new attribute hypotheses but did not recover additional gold triplets in R2. R4's four-view/local expansion reached 2,102 candidates and 174 recovered facts on development at K=20; confirmation reached 1,878 candidates and 131 recovered facts. R4's recall was unchanged across K values.

### Recall@K per claim and global candidate budgets

For the ranked R5@5 candidates, per-claim recall on development was 27.61% at 1, 35.50% at 3, 36.89% at 5, 38.98% at 10, 40.14% at 20, and 40.37% across all candidates. On confirmation it was 18.18%, 24.24%, 25.87%, 28.44%, 30.54%, and 30.54%, respectively.

| Global candidate budget | Development recovered / 431 | Recall | Confirmation recovered / 429 | Recall |
|---:|---:|---:|---:|---:|
| 200 | 83 | 19.26% | 71 | 16.55% |
| 400 | 139 | 32.25% | 101 | 23.54% |
| 800 | 148 | 34.34% | 107 | 24.94% |
| 1,600 | 156 | 36.19% | 110 | 25.64% |
| All (2,048 / 1,865 candidates) | 174 | 40.37% | 131 | 30.54% |
| 3,200 | unavailable: fewer candidates exist | — | unavailable: fewer candidates exist | — |

R5 did not improve the small per-claim cutoffs over R4's generation order: for example, R4 found 143/431 development facts at @1 versus R5's 119; at @5, R4 found 166 versus R5's 159. At @20, development tied and confirmation differed by one fact. The current fixed-weight ranker is not justified as a default under this budget objective; it needs a new ranking strategy or should be omitted.

## Component and value-type recall

R5@5 component recall isolates where gold facts are lost:

| Split | Subject available | Attribute available | Typed value available | Complete triplet |
|---|---:|---:|---:|---:|
| Development | 58.00% | 46.17% | 85.15% | 40.37% |
| New grouped confirmation | 54.55% | 41.72% | 77.39% | 30.54% |

The main gaps are entity/subject availability and attribute assignment; typed values are much more often present. In the new grouped confirmation set, recovered facts by type were: date 16/28, quantity 74/188, money 15/44, percent 20/51, duration 6/22, name 0/45, boolean 0/46, and version 0/5. Name-valued relations and boolean attributes are the clearest next semantic bottlenecks.

The final R5 candidate sets contained no subject outside the lexicon and no value lacking a text span. They did contain bounded implicit-subject hypotheses, traceable to same-row pronouns or coordinated clauses: 296 development and 91 confirmation candidate facts. These are still unverified. All candidate outputs retained the required `UNVERIFIED_CANDIDATE` state.

## Runtime and memory

Performance replay used 20,000 synthetic rows formed by repeating 382 held-out claim texts; labels/forms were not passed to the timed loop. Windows process affinity was successfully restricted to CPUs 0 and 1. The semantic-index fit (resolver plus BM25 indexes) took 1.66 seconds. BM25 full-claim query latency over 500 query samples was 0.55–0.59 ms for K=1–20.

| Configuration | 20k wall time | CPU time | Throughput | 18k projection | Peak working set | Candidates emitted |
|---|---:|---:|---:|---:|---:|---:|
| R0 | 40.09 s | 36.50 s | 499 claims/s | 36.1 s | 43.4 MiB | 7,171 |
| R4 | 265.00 s | 240.64 s | 75.5 claims/s | 238.5 s | 43.7 MiB | 96,926 |
| R5 | 263.26 s | 241.17 s | 76.0 claims/s | 236.9 s | 43.8 MiB | 96,926 |

The 18k figures are direct linear projections from the synthetic replay, not an 18k execution or Linux AMD64 measurement. The expanded path fits within the 30-minute competition window in this Windows CPU-only replay, but costs about four minutes before classification and output work. No per-row or global candidate caps were reached.

## Recommendation and remaining limits

R1 and R4 show real, repeatable recall gains; R2's BM25-only step and R3's pronoun step did not improve gold recall over their predecessors. R5's present scoring hurts the low per-claim budgets and should not be integrated unchanged. Continue with high-value, training-only candidate improvements for implicit subjects, name-valued relations, booleans, and clause ownership. Keep the candidate store separate from the verified graph, and do not use candidate agreement as truth evidence.

This experiment is an initial grouped holdout comparison, not a complete cross-validation study. The near-duplicate audit leaves residual leakage risk. Runtime was measured on Windows with two-core affinity; Linux AMD64/offline-container timing remains unmeasured. No learned ranker was trained, and no large model was tested or needed to demonstrate the measured gains.

### R4 incremental-component attribution

The saved `newly_recovered_facts.csv` provenance was compared at the fact level between R3@5 and R4@5. R4's increment is 8 facts on development and 6 on grouped confirmation. All 14 incremental candidate records carry the R4-only `same_sentence_subject_carry` method. Twelve also carry `tfidf_resolver_top20`, two carry an explicit `attribute_cue`, and five carry a `bm25_multiview` tag. The newly added `local_value` BM25 view is present in four records (one development, three confirmation); no incremental record has a `relationship` BM25 score.

This is provenance association, not a factorial ablation: R4 turns on coordinated-subject carry and the additional BM25 views together. The observed evidence identifies coordinated-subject carry as the only R4-specific method present in all 14 recovered facts. It does not establish that BM25 was necessary for any of them; BM25 alone (R2) and the R2-to-R3 step did not improve oracle recall. Keep the BM25 indexes and views as reusable experimental retrieval code, but do not attribute R4's measured recall gain to BM25 independently. `CandidateFactory.generate` defaults to R4. R5 remains a benchmark-only reranking comparison and is not selected by default.