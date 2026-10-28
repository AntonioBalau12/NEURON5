# NEURON5 — Handoff Briefing for Claude
**Date:** 2026-10-28 / 2026-10-29  
**Branch:** `feat/p3-fact-reconstruction-research` (GitHub: `origin/feat/p3-fact-reconstruction-research`)  
**Worktree:** `C:\Users\andrei\Documents\GitHub\NEURON5-p3`  
**Base:** `origin/feat/p1-temporal-graph` (`f75f514`)  
**Main Repo:** `AntonioBalau12/NEURON5`

---

## 1. Executive Summary: What was achieved

We solved the central bottleneck of **Challenge Task 2** (generating exactly 1,000 verifiably true, novel, and contract-valid claims).
* **Previous baseline (`run_main`):** Stalled at **411 claims** (589 short of target).
* **New production run (`run_abc_final_1000`):** Generated **1,038 valid claims**, capped at **exactly 1,000 claims**.
* **Official Repository Validator (`foundation.validate_output`):** **0 problems** (`expected_claims=1000`).
* **Independent Ground-Truth Audit (`audit_independent.py`):** **100% pass** (0 failures, 0 uncertain).
* **Text Check & Duplication (`recheck_output.py`):** **0 duplicates**, **0 matches** against practice or shared input texts.
* **Provenance:** **1,000 / 1,000** claims linked to supporting row IDs from `data/practice.csv`.

---

## 2. The Core Problem & The 3 Breakthroughs (A, B, C)

Earlier attempts to reach 1,000 claims failed because naive relaxation (`run_samekind_strict` or `run_max_relaxed_samekind_top1000`) either padded combinatorially with mismatched semantics (121 claims compared update size with storage) or accepted unverified transitions. Reconstructed facts from OpenIE / Slot Filling added 0 claims because they duplicated existing graph facts.

We implemented three rigorous, mathematically grounded improvements:

### A. Isolated Cross-Attribute Date Compares (`--compare-scope cross_date`)
* **Problem:** In `run_samekind_strict`, 545 cross-attribute pairs were created, but 121 compared disparate quantities using asymmetric templates (e.g. *"X has higher storage than Y"* where Y was an update size), which read as factually false.
* **Solution:** In [`rules.py`](experiments/claim_factory/rules.py), we strictly isolated cross-attribute comparisons to **calendar dates only** (`v.kind == "date"` with day precision `YYYY-MM-DD`). 
* **Semantics:** Two past dates are immutable ($D_1 < D_2$). They use dedicated, symmetric verb phrases (`DATE_VERB`: "took place", "was published", "was released", "joined", "launched") and temporal operators (`DATE_PHRASE`: "before", "after", "on the same day as").
  * *Example:* `"Holdan joined before Made by Hooly 2026 took place."`
* **Gain:** **+484 safe date comparisons** (total compare jumped from 209 to 693; total claims reached **906**, 0 errors).

### B. Safe Corroborated Transitions (`--change-rule safe_transition`)
* **Problem:** `ReasoningEngine` in `core/graph` outputs `UNVERIFIED_CANDIDATE` for transitions across dates, yielding 0 change claims in `run_main`. In `run_relaxed` (103 change candidates), 40 were flagged by independent audit because a later 3rd value existed.
* **Solution:** Implemented the `safe_transition` gate in [`rules.py`](experiments/claim_factory/rules.py):
  1. Both endpoints (`from`, `to`) corroborated by clean true rows (`nf >= 2`, `nt >= 2` or 1 for day-precision dates).
  2. Strictly chronological: `min(date_from) < max(date_to)`.
  3. No value sequence flapping (`flapping == False`).
  4. **Strict anti-contradiction filter:** Zero later differing observations in the entire universe after the `to` observation date.
  * *Example:* `"Holdan's team size went from 11 engineers to 17 engineers."` / `"Hooly AI Pro's annual price went from €490 per year to €590 per year."`
* **Gain:** **+62 clean change claims** (total claims reached **968**, 0 errors, 100% pass in independent audit).

### C. Staleness Relaxation Exclusively for Definitive Facts (`--staleness-rule relax_definitive`)
* **Problem:** 341 facts were rejected as stale in `run_main` because the 14-day freshness limit applied to everything except 13 date attributes, expiring permanent hardware specs, company founders, and Series A details.
* **Solution:** In [`store.py`](experiments/claim_factory/store.py), we defined `DEFINITIVE_ATTRS`:
  - **Released Hardware Specs:** `battery_capacity`, `screen_size`, `weight`, `charging_power`, `memory`, `cover_screen_size`, `inner_screen_size`, `hinge_rating`, `water_resistance_depth`, `colours`, `main_camera`, `refresh_rate`, `cellular_option`, `full_charge_time`. (A Pixel Watch's physical battery capacity or screen size never changes).
  - **Company History & Financing:** `founded`, `founders`, `previous_employer`, `raised_series_a`, `raised_series_b`, `series_a_amount`, `series_a_lead`, `is_engineering_hub`.
  - **Past Conference Specifications:** `venue`, `talks`, `sponsors`, `attendees`, `opening_keynote`, `keynote_speaker`, `livestreamed`.
  - **Stable Board Governance:** `chair`, `chair_since`, `cto`, `head_of_security`, `reliability_lead`.
  - *Bug fix in `store.py`:* Replaced `v.value <= last.on` with `v.value <= as_of` so announced events whose date has passed by 2026-10-29 are correctly recognized as past.
  - *Freshness retained:* Kept the strict 14-day limit for volatile metrics: active versions, daily requests, monthly active users, spot prices, survey ratings (NPS, satisfaction).
* **Gain:** **+51 facts** (142 $\to$ 193) and extra compare pairs. Total valid claims reached **1,038 claims** (before limit).

---

## 3. Results Comparison Matrix

| Configuration | Fact | Compare | Change | At_Event | Relation | **Total Claims** | Official Validator (`validate_output`) |
|---|---|---|---|---|---|---|---|
| **Baseline (`run_main`)** | 142 | 209 | 0 | 61 | 10 | **422** | 0 problems |
| **+ Solution A (cross date)** | 142 | 693 | 0 | 61 | 10 | **906** | 0 problems |
| **+ Solution B (safe change)** | 142 | 693 | 62 | 61 | 10 | **968** | 0 problems |
| **+ Solution C (no limit)** | 193 | 712 | 62 | 61 | 10 | **1,038** | 0 problems |
| **Final Target (`run_abc_final_1000`)** | 193 | 712 | 24 | 61 | 10 | **1,000** | **0 problems** |

---

## 4. Modified Code Architecture

All modifications are strictly self-contained in `experiments/claim_factory/`:

1. **`experiments/claim_factory/store.py`**:
   - Defined `DEFINITIVE_ATTRS` (hardware specs, corporate milestones, past event details, governance).
   - Added `staleness_rule: str = "strict_14d"` (choices: `strict_14d`, `relax_definitive`) to `Params`.
   - Updated `_asof()`: checks `v.value <= as_of` and respects `is_definitive` when not volatile.
2. **`experiments/claim_factory/rules.py`**:
   - Updated `_gen_compare_cross_attribute(store, date_only=...)`: supports `cross_date` to isolate date comparisons.
   - Updated `gen_change()`: supports `safe_transition` with chronological check (`min(from) < max(to)`), non-flapping, and anti-contradiction check (`zero later differing observations`).
3. **`experiments/claim_factory/generate_claims.py`**:
   - Added CLI flags:
     - `--compare-scope cross_date`
     - `--change-rule safe_transition`
     - `--staleness-rule relax_definitive`
     - `--limit 1000` (selects top 1,000 by confidence).
4. **`experiments/claim_factory/validate_claims.py`**:
   - Updated CLI arguments and `reverify()` to recognize `safe_transition` and `relax_definitive`.

---

## 5. Official Referee Rules & Edge Cases (from hype-arena.vercel.app)

Scraped directly from the competition platform ([`experiments/hype_arena_scraped.txt`](experiments/hype_arena_scraped.txt)):
* **Runtime Constraints:**
  - 3 GiB Docker image unpacked.
  - 6 GiB RAM, 2 CPUs, 30 minutes runtime.
  - **Zero network access** during execution.
  - **No generative LLM at runtime**.
* **Key Referee Traps to Keep in Mind:**
  1. **As-of Date vs Observation Date:**
     - Classification of an unlabelled row is judged **on its date** (*"True: the statement is true on its date"*).
     - Generated `fact` and `compare` claims are judged on **29 October 2026** (*as-of date*).
     - Generated `change` claims **have no as-of date** (*"The as-of date plays no part. One fact went from one value to another"*).
  2. **Hardware One-Off Prices vs Subscription Prices:**
     - Subscription: `"Hooly AI Pro costs €59 per month."`
     - Hardware one-off price: writing `"Hooly Pixel 10 costs €749."` ends with a bare number before period, failing regex. Must use inverted frame: `"€749 is the price of Hooly Pixel 10."`
  3. **Compare Sentence Restrictions:**
     - Compare sentences **must not mention numbers, amounts, dates, or years** (unless the year is part of an official entity name like `Hooly I/O 2026`).
  4. **Classification `unsure` Formatting:**
     - Rows labelled `unsure` **must have an empty confidence column** (no numeric confidence).

---

## 6. How to Reproduce & Audit

From the repository / worktree root (PowerShell, Python 3.14):

```powershell
$env:PYTHONUTF8='1'

# 1. Generate the 1,000 verified claims
py experiments/claim_factory/generate_claims.py `
  --compare-scope cross_date `
  --change-rule safe_transition `
  --staleness-rule relax_definitive `
  --limit 1000 `
  --out experiments/claim_factory/output/run_abc_final_1000

# 2. Validate with official repo checker (0 problems expected)
py experiments/claim_factory/recheck_output.py `
  experiments/claim_factory/output/run_abc_final_1000/claims_valid.csv `
  experiments/claim_factory/output/run_abc_final_1000/candidates.jsonl `
  experiments/claim_factory/output/audit_run_abc_final_1000/recheck_output.json

# 3. Stratified provenance validation (0 problems expected)
py experiments/claim_factory/validate_claims.py `
  --claims experiments/claim_factory/output/run_abc_final_1000/claims_valid.csv `
  --provenance experiments/claim_factory/output/run_abc_final_1000/provenance.jsonl `
  --staleness-rule relax_definitive `
  --change-rule safe_transition

# 4. Independent ground-truth audit from raw practice forms
py experiments/claim_factory/audit_independent.py run_abc_final_1000
```

---

## 7. What Claude / Next Agent Should Focus On

1. **Classification Pipeline (Task 1):**
   - The claims generation (Task 2) is **DONE and verified at 1,000 claims**.
   - The remaining challenge is classifying the ~18,000 unlabelled rows (`true`, `false`, `unsure`) within 30 minutes on 2 CPUs using Classical ML + Temporal Knowledge Graph lookups (see `experiments/classification_test/` and `ml/`).
2. **Context Carry-Over for Implicit Subjects:**
   - 29% of practice form facts have an implicit subject (e.g. pronoun "It"). Passing the subject from previous rows of the same page/date recovers up to 50% of these.
3. **Final Docker Build & Runtime Verification:**
   - Ensure dependencies fit in < 3 GiB image, RAM < 6 GiB, and offline inference runs end-to-end within 30 minutes.
