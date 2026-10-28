# run_max_relaxed_samekind_top1000 is NOT SAFE
It reaches 1,000 claims by (1) adding 545 combinatorial cross-attribute compare pairs (--compare-scope same_kind), 121 of which compare amounts and whose text
names only the LEFT attribute (e.g. "Hooly Gmail has higher mailbox storage than Hooly Android 17" is verified against Android 17's *update size*), and
(2) adding corroborated-pair `change` claims and `stable` relations that the engine does not verify, then (3) trimming to 1,000 with --limit.
Do not submit. See experiments/claim_factory/FEASIBILITY_REPORT.md section 2.
