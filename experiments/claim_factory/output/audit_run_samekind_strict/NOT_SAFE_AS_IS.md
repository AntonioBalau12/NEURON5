# run_samekind_strict: 956 claims, only partly safe
Same strict truth rules as run_main, but --compare-scope same_kind adds 545 cross-attribute compares.
424 of them compare two DATES and read correctly ("Holdan joined before Hooly Maps Day took place."): true and contract-valid, but combinatorial.
121 of them compare AMOUNTS and the text names only the left attribute ("Hooly Gmail has higher mailbox storage than Hooly Android 17" while the
form compares against Android 17's update size). Those 121 are not safe. Without them: 956 - 121 = 835 claims (arithmetic on this run, not a separate run).
