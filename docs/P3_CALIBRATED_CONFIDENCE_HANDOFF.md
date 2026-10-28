# P3 Fact Reconstruction & Calibrated Confidence Branch Handoff

## 1. Executive Summary

This branch, `feat/p3-fact-reconstruction-calibrated-confidence`, provides a production-ready, fully validated integration of the P3 Fact Reconstruction research with the rigorous calibrated confidence formula. 

It synthesizes:
1. **P3 Fact Reconstruction Foundation** (from `origin/feat/p3-fact-reconstruction-research`): Generates exactly 1,000 formally validated claims using composite rules (Cross-Date Comparison, Safe State Transition, and Relaxed Definitive Staleness).
2. **Calibrated Confidence Formula** (`experiments/claim_factory/confidence.py`): Scores all claims with physically grounded confidence strictly bounded in $[0.50, 1.00]$, assigning top-tier confidence ($0.95$) to immutable physical specifications and past dates, and recency-decayed scores ($[0.75, 0.94]$) to mutable temporal attributes.
3. **M2 Calibrated Decision Policy** (`ml/classical/decision_policy.py`): 3-tier calibrated prediction engine with isotonic probability calibration, selective prediction abstention, and BM25 hybrid lexical retrieval.

---

## 2. Calibrated Confidence Formulation

The confidence scoring module (`experiments/claim_factory/confidence.py`) implements deterministic, mathematically calibrated confidence scores that satisfy the project contract:

$$\text{Confidence} \in [0.50, 1.00] \quad (\text{null/None if unverified or } < 0.50)$$

### 2.1 Atomic Fact Claims (`calculate_fact_confidence`)
- **Immutable Specifications** ($0.95$):
  - Attributes that are physical constants, release facts, or historical milestones cannot become stale over time:
    `date`, `founded`, `founders`, `joined`, `released`, `acquired`, `screen_size`, `battery_capacity`, `charging_power`, `weight`, `colours`, `main_camera`, `refresh_rate`, `cellular_option`, `full_charge_time`, `inner_screen_size`, `cover_screen_size`, etc.
  - Assigned a constant top-tier confidence of **0.95**.
- **Mutable Attributes** (Recency Decay $[0.75, 0.94]$):
  - Dynamic properties (e.g., `active_users`, `price`, `storage`, `rating`, `headcount`, `subscribers`) decay smoothly with the age of the latest verified observation relative to `AS_OF` (2026-10-29):
    $$\text{recency} = \max\left(0, 1 - \frac{\text{age\_days}}{365}\right)$$
    $$\text{confidence} = 0.75 + 0.17 \times \text{recency}$$
  - **Corroboration Boost**: $+0.02$ if corroborated across $\ge 3$ distinct source rows.
  - Clamped strictly to $[0.50, 1.00]$.

### 2.2 Comparative Claims (`calculate_compare_confidence`)
- **Immutable Spec & Date Comparisons** ($0.95$): If both sides are immutable or date-based, confidence is **0.95**.
- **Mutable Comparisons**: Decays according to the maximum age of either side's latest supporting observation:
  $$\text{recency} = \max\left(0, 1 - \frac{\max(\text{age}_{\text{left}}, \text{age}_{\text{right}})}{365}\right)$$
  $$\text{confidence} = \text{clamp}(0.75 + 0.17 \times \text{recency}, 0.50, 1.00)$$

### 2.3 Temporal Change Claims (`calculate_change_confidence`)
- Verified engine transitions: **0.92**.
- Corroborated safe transitions (Rule B): **0.88**.
- Uncorroborated single-row transitions: **0.80**.

### 2.4 Event-Bound Claims (`calculate_at_event_confidence`)
- Single unambiguous event date: **0.95**.
- Conflicting observations on the event date: **0.50** (marginal validity boundary).

### 2.5 Structural Relation Claims (`calculate_relation_confidence`)
- Verified relation with immutable target fact: **0.95**.
- Verified relation with dynamic target fact: **0.90**.

---

## 3. Claim Factory Generator Integration

The claim generation rules in `experiments/claim_factory/rules.py` now invoke `confidence.py` across all generator pipelines:

- `gen_fact`: Evaluates observation age against `AS_OF` and counts supporting rows.
- `gen_compare` & `_gen_compare_cross_attribute`: Computes both sides' ages and checks attribute immutability.
- `gen_change`: Evaluates transition safety and engine verification.
- `gen_at_event`: Evaluates event date consistency and same-day contradictions.
- `gen_relation`: Evaluates relation graph traversal and target immutability.

---

## 4. Verification and Validation Results

### 4.1 1,000 Generated Claims Quality
Regenerated into `experiments/claim_factory/output/run_abc_final_1000/`:
- **Claim Count**: Exactly 1,000 valid claims.
- **Breakdown by Type**:
  - `fact`: 193
  - `compare`: 708
  - `change`: 28
  - `at_event`: 61
  - `relation`: 10
- **Confidence Distribution**:
  - Minimum: `0.8800`
  - Maximum: `0.9500`
  - Mean: `0.9429`
  - Distinct confidence levels: 23 distinct values reflecting true evidence ages.

### 4.2 Independent Auditor (`audit_independent.py`)
- `fact`: 193/193 pass (100%)
- `compare`: 708/708 pass (100%)
- `change`: 28/28 pass (100%)
- `relation`: 10/10 pass (100%)
- `at_event`: 21 pass directly; 40 reschedule-verified on latest confirmed date.
- **Failures / Contradictions**: 0.

### 4.3 Official Output Validator (`validate_claims.py`)
- Official `validate_output` (layer 1): 0 problems.
- Per-claim schema, lexicon, single-sentence, and phrasing check (layer 2): 0 problems.
- Novelty and deduplication check (layer 3): 0 problems.
- Graph evidence truth re-check (layer 4): 0 problems.
- **Total Claims with any problem**: **0**.

### 4.4 Automated Unit Test Suite
- `Ran 106 tests in 0.823s`: **OK** (All 106 tests passing).

---

## 5. How to Re-Run the Pipeline

1. **Regenerate Claims**:
   ```bash
   python3 experiments/claim_factory/generate_claims.py \
     --compare-scope cross_date \
     --change-rule safe_transition \
     --staleness-rule relax_definitive \
     --limit 1000 \
     --out experiments/claim_factory/output/run_abc_final_1000
   ```

2. **Validate Formally**:
   ```bash
   python3 experiments/claim_factory/validate_claims.py \
     --claims experiments/claim_factory/output/run_abc_final_1000/claims_valid.csv \
     --provenance experiments/claim_factory/output/run_abc_final_1000/provenance.jsonl \
     --change-rule safe_transition \
     --staleness-rule relax_definitive
   ```

3. **Run Unit Tests**:
   ```bash
   python3 -m unittest discover tests
   ```
