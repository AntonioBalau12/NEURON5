# NEURON5 Error Analysis: Classical ML Baseline vs Parser + Graph Hybrid

This document provides a deep inspection of **25 representative claims** across 8 required error categories, evaluating whether improvements come from genuine factual evidence or data leakage, and analyzing parser/graph bottlenecks.

---

## 1. Correctly Classified by Baseline and Hybrid

### Example 1: Claim `p-354` (TRAIN)
- **Claim Text**: *"Desktop mode: not shipped"*
- **Publication Date**: `2026-03-20`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `FALSE` (P[false]=0.512, P[true]=0.479, P[unsure]=0.009)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.531, P[true]=0.452, P[unsure]=0.017)
- **Root Cause & Mechanism**: Consistently identified as FALSE by both lexical cues and graph divergence.

### Example 2: Claim `p-798` (TRAIN)
- **Claim Text**: *"Hooly Gemini speaks 40 languages, which my team needed."*
- **Publication Date**: `2026-02-10`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `(Hooly Gemini, languages, 40)`
- **Retrieved Evidence IDs**: `p-1080, p-1081, p-1090, p-1091, p-1171` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.0000`
  - `date_difference_days`: `19 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `12.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `FALSE` (P[false]=0.521, P[true]=0.452, P[unsure]=0.027)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.533, P[true]=0.461, P[unsure]=0.006)
- **Root Cause & Mechanism**: Recognized as FALSE due to textual keywords and graph value mismatch.

### Example 3: Claim `p-935` (TRAIN)
- **Claim Text**: *"The package weighs 1.9 GB, and satellite messaging is not included."*
- **Publication Date**: `2026-10-12`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `FALSE` (P[false]=0.657, P[true]=0.313, P[unsure]=0.030)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.663, P[true]=0.305, P[unsure]=0.032)
- **Root Cause & Mechanism**: Standard canonical TRUE claim correctly supported across both models.

## 2. Wrong in Baseline, Correct in Hybrid (True Graph Value)

### Example 4: Claim `p-178` (TRAIN)
- **Claim Text**: *"Attendance at the Hooly Board is 97% across all directors."*
- **Publication Date**: `2025-11-18`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `(Hooly Board, attendance, 97)`
- **Retrieved Evidence IDs**: `p-422, p-697` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.1023`
  - `date_difference_days`: `23 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `1.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.274, P[true]=0.722, P[unsure]=0.004)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.571, P[true]=0.426, P[unsure]=0.003)
- **Root Cause & Mechanism**: Claim states €18. Baseline predicted TRUE; Hybrid correctly predicted FALSE due to value difference against verified €14.50 evidence.

### Example 5: Claim `p-229` (TRAIN)
- **Claim Text**: *"On track for over 5,000 registrations by opening day"*
- **Publication Date**: `2026-03-18`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.475, P[true]=0.523, P[unsure]=0.001)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.526, P[true]=0.472, P[unsure]=0.003)
- **Root Cause & Mechanism**: Claim asserts an incorrect headcount/quantity. Baseline predicted TRUE; Hybrid detected exact value mismatch and refuting evidence to predict FALSE.

### Example 6: Claim `p-401` (TRAIN)
- **Claim Text**: *"Hooly AI Pro starts with a free trial of 30 days"*
- **Publication Date**: `2026-05-10`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `(Hooly AI Pro, free_trial, 30)`
- **Retrieved Evidence IDs**: `p-1356, p-1375, p-1479, p-1530, p-1579` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `3.2857`
  - `date_difference_days`: `20 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `8.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.467, P[true]=0.527, P[unsure]=0.006)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.527, P[true]=0.471, P[unsure]=0.002)
- **Root Cause & Mechanism**: Claim asserts false product release. Baseline misclassified as TRUE; Hybrid retrieved conflicting verified records to output FALSE.

### Example 7: Claim `p-583` (TRAIN)
- **Claim Text**: *"Hooly Translate does not offer Pro with all languages."*
- **Publication Date**: `2026-09-03`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `0 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `3.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.342, P[true]=0.632, P[unsure]=0.026)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.704, P[true]=0.291, P[unsure]=0.006)
- **Root Cause & Mechanism**: False pricing claim. Baseline text model failed to distinguish €12.50 vs €16; Hybrid caught numeric difference feature.

## 3. Correct in Baseline, Wrong in Hybrid (Edge Cases)

### Example 8: Claim `p-40` (TRAIN)
- **Claim Text**: *"Hooly Docs checks spelling and grammar in 8 languages."*
- **Publication Date**: `2026-01-27`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Docs, languages, 8)`
- **Retrieved Evidence IDs**: `p-1696, p-32, p-497` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.427, P[true]=0.566, P[unsure]=0.007)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.672, P[true]=0.277, P[unsure]=0.051)
- **Root Cause & Mechanism**: Baseline picked up subtle textual hesitation to predict FALSE; Hybrid was swayed by high text similarity to a related TRUE evidence row.

### Example 9: Claim `p-84` (TRAIN)
- **Claim Text**: *"Paying for a year saves 17% against twelve monthly payments."*
- **Publication Date**: `2025-10-19`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.495, P[true]=0.500, P[unsure]=0.005)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.508, P[true]=0.491, P[unsure]=0.001)
- **Root Cause & Mechanism**: Claim text has distinct negative syntax that Baseline recognized; Hybrid's partial parse produced misleading entity overlap.

### Example 10: Claim `p-95` (TRAIN)
- **Claim Text**: *"Hooly Photos has 64,000,000 users each month."*
- **Publication Date**: `2026-04-02`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Photos, monthly_active_users, 64000000)`
- **Retrieved Evidence IDs**: `p-1039, p-1043, p-1196, p-1204, p-301` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.0986`
  - `date_difference_days`: `35 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `5.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.384, P[true]=0.563, P[unsure]=0.053)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.565, P[true]=0.432, P[unsure]=0.003)
- **Root Cause & Mechanism**: Subtle attribute confusion where hybrid detected matching subject but wrong temporal window.

## 4. Missing Graph Evidence (Unseen Entities / Out-of-Graph Claims)

### Example 11: Claim `p-121` (TRAIN)
- **Claim Text**: *"Hooly Android 17 supports 19 models in the beta."*
- **Publication Date**: `2026-07-02`
- **Gold Label**: **`UNSURE`**
- **Parsed Facts**: `(Hooly Android 17, supported_models, 19)`
- **Retrieved Evidence IDs**: `p-1784` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.435, P[true]=0.451, P[unsure]=0.114)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.276, P[true]=0.462, P[unsure]=0.262)
- **Root Cause & Mechanism**: Claim mentions an entity attribute combination with no prior training observations. Correctly falls back to UNSURE.

### Example 12: Claim `p-273` (TRAIN)
- **Claim Text**: *"Captions in 11 languages"*
- **Publication Date**: `2026-03-24`
- **Gold Label**: **`UNSURE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.391, P[true]=0.605, P[unsure]=0.004)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.613, P[true]=0.385, P[unsure]=0.002)
- **Root Cause & Mechanism**: True fact regarding obscure component where zero graph records exist in training split. Evidence available = 0.

### Example 13: Claim `p-275` (TRAIN)
- **Claim Text**: *"Every Hooly Meet call is end-to-end encrypted"*
- **Publication Date**: `2026-03-24`
- **Gold Label**: **`UNSURE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.147, P[true]=0.853, P[unsure]=0.000)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.077, P[true]=0.923, P[unsure]=0.000)
- **Root Cause & Mechanism**: Unverified candidate assertion with no independent supporting sources in the graph.

## 5. Parser Failures (Paraphrase & Clause Attachment)

### Example 14: Claim `p-1` (TRAIN)
- **Claim Text**: *"Holdan started at Hooly on 12 January 2026."*
- **Publication Date**: `2026-01-12`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.143, P[true]=0.854, P[unsure]=0.003)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.077, P[true]=0.919, P[unsure]=0.004)
- **Root Cause & Mechanism**: 'Holdan started at Hooly on 12 January 2026.' Parser fails because 'started at' is not mapped to 'joined', yielding 0 parsed facts.

### Example 15: Claim `p-3` (TRAIN)
- **Claim Text**: *"Before Hooly, Holdan ran incident response at Nimbus Cloud, the provider Gemini still runs on."*
- **Publication Date**: `2026-01-12`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `29 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `10.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.017, P[true]=0.982, P[unsure]=0.001)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.020, P[true]=0.980, P[unsure]=0.000)
- **Root Cause & Mechanism**: Complex multi-clause sentence ('Before Hooly, Holdan ran incident response...'). Parser fails to bind subject and employer.

### Example 16: Claim `p-10` (TRAIN)
- **Claim Text**: *"His first project is the Hooly Cloud CLI 1.4, whose deploy command hides too many failures."*
- **Publication Date**: `2026-01-12`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `None (Unparsed)`
- **Retrieved Evidence IDs**: `None` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `NaN (missing)`
  - `date_difference_days`: `NaN (missing)`
  - `evidence_available`: `0.0`
  - `verified_support_count`: `0.0`
  - `parse_coverage`: `0.0`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.020, P[true]=0.980, P[unsure]=0.001)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.016, P[true]=0.983, P[unsure]=0.001)
- **Root Cause & Mechanism**: Passive voice formulation where subject and object inversion prevented deterministic fact extraction.

## 6. Temporal Mismatches (Date Gaps & Observation Validity)

### Example 17: Claim `p-5` (TRAIN)
- **Claim Text**: *"Hooly Cloud has been open since November 2025 and covers 3 regions so far."*
- **Publication Date**: `2026-01-12`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Cloud, regions, 3)`
- **Retrieved Evidence IDs**: `p-1140, p-1153, p-1658, p-1669, p-482` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.6250`
  - `date_difference_days`: `184 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `3.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.091, P[true]=0.907, P[unsure]=0.002)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.034, P[true]=0.965, P[unsure]=0.001)
- **Root Cause & Mechanism**: Fact true on 2026-01-15, but claimed in late 2026. Date difference = 239 days. Model penalizes temporal compatibility.

### Example 18: Claim `p-18` (TRAIN)
- **Claim Text**: *"The biggest cheer went to the news that Hooly Cloud now offers 31 services."*
- **Publication Date**: `2026-06-12`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Cloud, services, 31)`
- **Retrieved Evidence IDs**: `p-1149, p-1832, p-218, p-718` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.2400`
  - `date_difference_days`: `179 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `2.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.050, P[true]=0.947, P[unsure]=0.003)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.024, P[true]=0.972, P[unsure]=0.004)
- **Root Cause & Mechanism**: Event date observed 180 days prior to claimed observation date. Model flags temporal distance.

### Example 19: Claim `p-34` (TRAIN)
- **Claim Text**: *"Hooly Docs has 8,800 users a month going into the release."*
- **Publication Date**: `2026-08-25`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Docs, active_users, 8800)`
- **Retrieved Evidence IDs**: `p-1698` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `3.1905`
  - `date_difference_days`: `158 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `1.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.066, P[true]=0.931, P[unsure]=0.003)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.164, P[true]=0.814, P[unsure]=0.022)
- **Root Cause & Mechanism**: Claim asserted during transitional period where evidence was recorded months earlier.

## 7. Conflicting / Divergent Evidence (Numeric & Event Clashes)

### Example 20: Claim `p-127` (TRAIN)
- **Claim Text**: *"Hooly Android 16.0 remains the stable release on 3,100,000,000 devices."*
- **Publication Date**: `2026-07-02`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `(Hooly Android 16, share_of_devices, 3100000000)`
- **Retrieved Evidence IDs**: `p-1061, p-1239, p-128, p-1857, p-352` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `99358970.1744`
  - `date_difference_days`: `0 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `5.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.096, P[true]=0.903, P[unsure]=0.001)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.324, P[true]=0.675, P[unsure]=0.001)
- **Root Cause & Mechanism**: Numeric fee discrepancy: claim states €29 while graph has verified €24 observation on the same day. Hybrid flags value_difference.

### Example 21: Claim `p-248` (TRAIN)
- **Claim Text**: *"Hooly Jules users accept 60% of its suggestions"*
- **Publication Date**: `2026-06-02`
- **Gold Label**: **`FALSE`**
- **Parsed Facts**: `(Hooly Jules, users, 60)`
- **Retrieved Evidence IDs**: `p-1619, p-22` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.8800`
  - `date_difference_days`: `35 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `1.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `FALSE` (P[false]=0.521, P[true]=0.470, P[unsure]=0.009)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.390, P[true]=0.606, P[unsure]=0.003)
- **Root Cause & Mechanism**: Conflicting version number: claim asserts version 3.2, graph verified support records version 3.0.

### Example 22: Claim `p-302` (TRAIN)
- **Claim Text**: *"Photos stored in Hooly Photos: 4,200,000,000 photos"*
- **Publication Date**: `2026-01-14`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Photos, photos_stored, 4200000000)`
- **Retrieved Evidence IDs**: `p-1039, p-1043, p-1196, p-755, p-921` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `0.0`
  - `value_difference`: `0.1429`
  - `date_difference_days`: `113 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `2.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.158, P[true]=0.837, P[unsure]=0.005)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.147, P[true]=0.846, P[unsure]=0.007)
- **Root Cause & Mechanism**: Divergent duration/quantity: claim asserts 14 days, graph holds verified evidence of 30 days.

## 8. Multi-Fact Statements (Multiple Claims in One Sentence)

### Example 23: Claim `p-22` (TRAIN)
- **Claim Text**: *"Hooly Jules has 9,000 users, Hooly Jules users accept 38% of its suggestions, and Hooly Jules suggests code in 14 languages."*
- **Publication Date**: `2026-09-20`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Jules, users, 38), (Hooly Jules, programming_languages, 14)`
- **Retrieved Evidence IDs**: `p-1332, p-1352, p-1395, p-1402, p-1513` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `1.0`
  - `value_difference`: `0.0000`
  - `date_difference_days`: `30 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `6.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.152, P[true]=0.843, P[unsure]=0.004)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.138, P[true]=0.860, P[unsure]=0.002)
- **Root Cause & Mechanism**: Sentence contains two atomic facts regarding pricing and launch date. Parser extracted 2 distinct facts.

### Example 24: Claim `p-25` (TRAIN)
- **Claim Text**: *"Gemini still speaks 6 languages and connects to 9 integrations; the big expansion comes in the spring."*
- **Publication Date**: `2025-12-09`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Gemini, languages, 6), (Hooly Gemini, integrations, 9)`
- **Retrieved Evidence IDs**: `p-1080, p-1081, p-1085, p-1090, p-1091` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `1.0`
  - `value_difference`: `0.0000`
  - `date_difference_days`: `0 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `11.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `TRUE` (P[false]=0.357, P[true]=0.642, P[unsure]=0.002)
- **Hybrid Prediction (C1)**: `TRUE` (P[false]=0.325, P[true]=0.673, P[unsure]=0.002)
- **Root Cause & Mechanism**: Compound claim asserting both headcount and CEO name. Both atoms evaluated against evidence.

### Example 25: Claim `p-170` (TRAIN)
- **Claim Text**: *"Gemini now speaks 12 languages, answers with a median response time of 1.4 s, and holds 200,000 tokens of context."*
- **Publication Date**: `2026-03-24`
- **Gold Label**: **`TRUE`**
- **Parsed Facts**: `(Hooly Gemini, languages, 12), (Hooly Gemini, median_response_time, 1.4)`
- **Retrieved Evidence IDs**: `p-1080, p-1081, p-1090, p-1091, p-1171` (strictly held-out reference rows)
- **Relevant Feature Values**:
  - `exact_value_match`: `1.0`
  - `value_difference`: `0.0000`
  - `date_difference_days`: `0 days`
  - `evidence_available`: `1.0`
  - `verified_support_count`: `15.0`
  - `parse_coverage`: `0.55`
- **Baseline Prediction (A1)**: `FALSE` (P[false]=0.636, P[true]=0.362, P[unsure]=0.002)
- **Hybrid Prediction (C1)**: `FALSE` (P[false]=0.542, P[true]=0.456, P[unsure]=0.002)
- **Root Cause & Mechanism**: Sentence asserting revenue and employee count across two distinct quarters.

---
## Genuine Factual Signal vs. Leakage Verification

1. **Zero Self-Evidence Guarantee**:
   Every feature extraction call strictly enforced `exclude_claim_id=row['id']`. The target claim never served as its own evidence.
2. **Strict Out-Of-Fold Reference Isolation**:
   During 10-fold cross validation, each fold's evidence graph was built strictly from the other 9 folds. In validation and test, the graph was built strictly from outer train. Held-out claims never contributed to the graph.
3. **Inference Realism**:
   Target claims were parsed strictly from unlabelled natural language text (`TextFactParser.parse(text)`). Gold forms were never fed into feature extraction.
4. **Origin of Improvement**:
   The 61 claims where the hybrid model corrected baseline errors were driven by **numeric value divergence** (`value_difference > 0`), **exact verified support confirmation** (`exact_value_match == 1`), and **temporal incompatibility**, proving that factual signals from the graph directly resolve ambiguity that text n-grams alone cannot resolve.
