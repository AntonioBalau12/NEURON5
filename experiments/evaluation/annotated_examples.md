# Annotated examples

32 sentences of the evaluation set with the form facts, the evaluator's suggested missing facts and notes. Written by the evaluator (`evaluator_llm`) from the sentence text alone, before looking at any OpenIE or slot-filling output.

**Status of everything on this page: `needs_human_verification`.** The form facts are the dataset's own list and are known to be possibly incomplete or context-dependent. A *suggested* fact is something the evaluator believes the sentence states but the form lacks. It is a suggestion only: it is used for the `suggested` scoring column, never as ground truth, and no number in a report may call it verified until a human has marked it in the worksheet (`ingest_worksheet.py`).

## What the whole set looks like

- 135 rows, 183 form facts, 4 suggested extra facts, 12 rows with a note that a form fact may not be stated by the sentence.
- By reading, the form misses a stated fact in only about 4 of the 135 rows (the 4 suggestions). The `likely_incomplete_form` stratum (22 rows) comes from a text heuristic and is mostly a false alarm; do not read it as 22 incomplete forms.
- 53 of 183 form facts have a subject that is not written in the sentence (`subject not written in text` in the worksheet). They depend on the row context, so a sentence-only extractor cannot reproduce them; the harness reports entity recognition for written and implicit subjects separately.
- Absence of a suggestion means the evaluator found nothing to add. It does not mean the form is verified.

## Examples

### `p-1`  (heldout, label true, date 2026-01-12)  *implicit attribute*

> Holdan started at Hooly on 12 January 2026.

**Form facts** (from the dataset form):

- `F1` Holdan | joined | 2026-01-12

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 'started at Hooly on <date>' is a join date. The word 'joined' is not in the sentence; an extractor must map 'started' to the attribute `joined`.

**needs_human_verification:** Confirm that 'started at' means `joined` (not a launch or founding date).

---

### `p-71`  (heldout, label true, date 2026-04-24)  *implicit subject, implicit attribute, repeated noun*

> The hall seats 3,200 seats.

**Form facts** (from the dataset form):

- `F1` Quayside Hall | capacity | 3200 seat  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 'The hall' stands for Quayside Hall by context only; 'hall' is not a lexicon alias. 'seats 3,200 seats' is capacity as a counted noun `seat`.

**needs_human_verification:** Check that 'the hall' is Quayside Hall (the sentence alone does not name it).

---

### `p-117`  (dev, label true, date 2026-01-22)  *negation, temporal*

> Hooly Search has no AI answers yet.

**Form facts** (from the dataset form):

- `F1` Hooly Search | ai_answers | false

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): yet

**Notes.** 'no AI answers yet' is a boolean false (negated=true). 'yet' is a temporal cue meaning not so far; it does not give a date.

**needs_human_verification:** None for the form fact. Decide whether 'yet' should be kept as a temporal qualifier (this harness counts it as a cue).

---

### `p-258`  (heldout, label true, date 2026-02-10)  *negation, temporal, word order*

> Series A not yet raised: closing this month

**Form facts** (from the dataset form):

- `F1` Hooly | raised_series_a | false  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): this month, yet

**Notes.** 'not yet raised' makes `raised_series_a` false. 'closing this month' is a prediction without a date. No further fact is stated.

**needs_human_verification:** Confirm no usable fact is hidden in 'closing this month'.

---

### `p-130`  (heldout, label true, date 2026-01-12)  *implicit subject, temporal*

> Gavin Bellson still runs the division until a permanent head is named.

**Form facts** (from the dataset form):

- `F1` Hooly Devices | head | Gavin Bellson  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): still, until

**Notes.** 'the division' is Hooly Devices only by context. 'still' and 'until a permanent head is named' qualify the head fact in time.

**needs_human_verification:** Check that the division is Hooly Devices and that Gavin Bellson is the current head.

---

### `p-137`  (heldout, label true, date 2026-01-12)  *negation, temporal, paraphrase*

> A trade-in credit is not on offer at Hooly Devices for the moment.

**Form facts** (from the dataset form):

- `F1` Hooly Devices | trade_in_programme | false

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): for the moment

**Notes.** 'is not on offer' is the paraphrase of `trade_in_programme` = false. 'for the moment' is a temporal cue.

**needs_human_verification:** None.

---

### `p-146`  (heldout, label false, date 2026-04-01)  *label false*

> Hooly Android runs on 2,900,000,000 devices, after another quarter of growth.

**Form facts** (from the dataset form):

- `F1` Hooly Android | active_devices | 2900000000 device

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** The label `false` describes the source sentence. EXCHANGE_FORMAT: a false row does not make each of its atomic facts false. The sentence states 2,900,000,000 devices and an extractor must still extract it (as a candidate).

**needs_human_verification:** Do not treat a `false` label as proof that the fact was not stated.

---

### `p-167`  (heldout, label true, date 2026-02-01)  *multi-fact, implicit attribute*

> Hooly I/O has 9 sponsors and Hooly I/O takes place on 24 March 2026 in Berlin; a Hooly I/O ticket is €249.

**Form facts** (from the dataset form):

- `F1` Hooly I/O 2026 | sponsors | 9 sponsor
- `F2` Hooly I/O 2026 | date | 2026-03-24
- `F3` Hooly I/O 2026 | city | Berlin
- `F4` Hooly I/O 2026 | ticket_price | €249

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** Four facts in one sentence (sponsors, date, city, ticket price). 'Hooly I/O' is an alias of Hooly I/O 2026. 'a Hooly I/O ticket is €249' is `ticket_price`.

**needs_human_verification:** Check the four facts are all the form holds and that 'ticket' maps to `ticket_price`.

---

### `p-170`  (heldout, label true, date 2026-03-24)  *multi-fact, unit*

> Gemini now speaks 12 languages, answers with a median response time of 1.4 s, and holds 200,000 tokens of context.

**Form facts** (from the dataset form):

- `F1` Hooly Gemini | languages | 12 language
- `F2` Hooly Gemini | median_response_time | 1.4 s
- `F3` Hooly Gemini | context_window | 200000 token

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): now

**Notes.** Three quantities: 12 languages (counted noun), 1.4 s (duration unit s), 200,000 tokens. 'Gemini' is an alias of Hooly Gemini; 'now' is a temporal cue.

**needs_human_verification:** None.

---

### `p-227`  (heldout, label true, date 2026-03-18)  *headline fragment, implicit subject, number word*

> Content across three days

**Form facts** (from the dataset form):

- `F1` Hooly Cloud Next 2026 | length | 3 day  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 'three days' is the number word `three` plus a duration unit. The subject (Hooly Cloud Next 2026) is not written; only the row context says it.

**needs_human_verification:** Check that a fragment with no subject should be expected to produce a fact at all.

---

### `p-338`  (heldout, label true, date 2026-09-20)  *odd attribute name*

> Brightline Labs is an integration partner of Hooly

**Form facts** (from the dataset form):

- `F1` Brightline Labs | integration_partner_of_flawless | true

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** The attribute is `integration_partner_of_flawless`, a boolean. The sentence names Hooly. The lexicon attribute carries a name that does not appear in the text, so mapping needs the lexicon rather than the words.

**needs_human_verification:** Check that the boolean true with subject Brightline Labs is the intended reading.

---

### `p-410`  (heldout, label true, date 2026-09-03)  *unit*

> 1,000 GB per user on Workspace Enterprise

**Form facts** (from the dataset form):

- `F1` Hooly Workspace Enterprise | storage_per_user | 1000 GB

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 1,000 GB per user: quantity in GB, attribute `storage_per_user`. 1,000 GB equals 1 TB after conversion.

**needs_human_verification:** None.

---

### `p-515`  (heldout, label true, date 2026-09-01)  *multi-fact, name values*

> Hooly Gemini runs in 2 regions, with Frankfurt as the primary region, on Nimbus Cloud.

**Form facts** (from the dataset form):

- `F1` Hooly Gemini | hosting_regions | 2 region
- `F2` Hooly Gemini | primary_region | Frankfurt
- `F3` Hooly Gemini | cloud_provider | Nimbus Cloud

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** Three facts: 2 regions (counted noun), Frankfurt (name), Nimbus Cloud (name). Name values are compared through the lexicon.

**needs_human_verification:** Check that 'primary region' is Frankfurt and not a second fact.

---

### `p-579`  (heldout, label false, date 2026-10-20)  *negation scope (form concern)*

> Hooly Search does not offer them in every language.

**Form facts** (from the dataset form):

- `F1` Hooly Search | ai_answers | false

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Concern about the form:** The negation scopes over 'in every language'. It does not clearly state that AI answers do not exist; the false boolean is a context reading.

**Notes.** 'does not offer them in every language' negates 'in every language', not the existence of AI answers. The form's false boolean is a context reading. The antecedent of 'them' is not in the sentence.

**needs_human_verification:** Decide whether this sentence supports `ai_answers` = false at all.

---

### `p-622`  (heldout, label true, date 2026-04-28)  *multi-fact, ISO date, two attributes*

> Hooly Pixel 10 launches at €799 and ships from 2026-05-14.

**Form facts** (from the dataset form):

- `F1` Hooly Pixel 10 | price | €799
- `F2` Hooly Pixel 10 | released | 2026-05-14

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** `launches at €799` (price, no period) and `ships from 2026-05-14` (released). The date is written in ISO form.

**needs_human_verification:** None.

---

### `p-635`  (heldout, label true, date 2025-11-05)  *negation word that is not a negation of the fact*

> Weight of Hooly Pixel Watch without the strap: 31 g.

**Form facts** (from the dataset form):

- `F1` Hooly Pixel Watch | weight | 31 g

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 'without the strap' qualifies the weight (31 g). The fact is not negated. A negation detector that fires on 'without' would flag it wrongly.

**needs_human_verification:** None.

---

### `p-847`  (heldout, label true, date 2026-10-28)  *fully implicit subjects*

> Guidance: €11.5 million, €16 million

**Form facts** (from the dataset form):

- `F1` Hooly Q2 2026 Results | guidance | €11500000  *(subject not written in the sentence)*
- `F2` Hooly Q3 2026 Results | guidance | €16000000  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** Two money values with no subject in the sentence. The form assigns them to Hooly Q2 2026 Results and Hooly Q3 2026 Results, which only the neighbouring text can tell.

**needs_human_verification:** Check that a sentence-only extractor can be expected to recover these. This row measures the ceiling of sentence-level extraction.

---

### `p-935`  (heldout, label false, date 2026-10-12)  *negation on the other fact*

> The package weighs 1.9 GB, and satellite messaging is not included.

**Form facts** (from the dataset form):

- `F1` Hooly Android 17 | update_size | 1.9 GB  *(subject not written in the sentence)*
- `F2` Hooly Android 17 | satellite_messaging | false  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** Two facts: 1.9 GB (not negated) and satellite messaging false (negated). The negation scopes only over the second clause.

**needs_human_verification:** None.

---

### `p-1019`  (heldout, label false, date 2026-10-20)  *comparison operator, label false*

> Hooly Drive has over 40,000 users storing their lives with us.

**Form facts** (from the dataset form):

- `F1` Hooly Drive | active_users | >40000 user

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 'over 40,000 users' has op `gt`; `40,000 users` without op is a different value. The form stores >40000.

**needs_human_verification:** None.

---

### `p-1033`  (heldout, label false, date 2025-10-16)  *negation word in a non-fact clause*

> Hooly Maps is live and 91,000,000 users of you will never get lost again.

**Form facts** (from the dataset form):

- `F1` Hooly Maps | monthly_active_users | 91000000 user

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Concern about the form:** '91,000,000 users of you' is not explicitly 'monthly active'; attribute mapping is a context reading.

**Temporal cues** (scored by the harness): again

**Notes.** 'will never get lost again' contains `never` but is not a negated fact. 'users of you' is an odd phrase; `monthly_active_users` is a context reading (not stated as monthly).

**needs_human_verification:** Decide whether the attribute mapping is supported by the words.

---

### `p-1093`  (heldout, label true, date 2026-05-02)  *temporal, name value*

> Hooly is headquartered in Lisbon from today.

**Form facts** (from the dataset form):

- `F1` Hooly | headquarters | Lisbon

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): from today

**Notes.** 'from today' is a temporal cue. The page date (2026-05-02) must not be copied into a fact date. The value is the name Lisbon.

**needs_human_verification:** None.

---

### `p-1170`  (heldout, label true, date 2026-03-24)  *headline fragment, suggestion*

> Berlin, 24 March 2026

**Form facts** (from the dataset form):

- `F1` Hooly I/O 2026 | city | Berlin  *(subject not written in the sentence)*

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- `S1` Hooly I/O 2026 | date | 2026-03-24  
  *why:* The text states '24 March 2026' next to 'Berlin'. The form keeps only the city. The subject is implicit (not written in the sentence), so this is context-dependent.

**Notes.** Form holds only the city. The text also states '24 March 2026'. A date fact for Hooly I/O 2026 is suggested (S1). The subject is implicit.

**needs_human_verification:** Verify S1.

---

### `p-1183`  (heldout, label false, date 2026-08-03)  *reported content, negation (form concern)*

> Jian-Yeng credits augmented walking, which Hooly Maps has never offered.

**Form facts** (from the dataset form):

- `F1` Hooly Maps | lead | Jian-Yeng
- `F2` Hooly Maps | ar_walking | false

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Concern about the form:** Text does not say Jian-Yeng leads Hooly Maps; he 'credits' a feature. The lead fact is a context reading.

**Notes.** Form says Jian-Yeng leads Hooly Maps; the sentence only says he credits a feature. `has never offered` supports AR walking = false.

**needs_human_verification:** Check the `lead` fact: is it stated?

---

### `p-1193`  (heldout, label true, date 2026-05-07)  *two subjects, numeric confusable, unit*

> The feature is part of every plan, from the free 10 GB to Hooly Photos Max at 10 TB.

**Form facts** (from the dataset form):

- `F1` Hooly Photos | free_storage | 10 GB  *(subject not written in the sentence)*
- `F2` Hooly Photos Max | storage | 10 TB

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** 10 GB (free tier of Hooly Photos) and 10 TB (Hooly Photos Max). The digits are identical, the units differ. A method that pairs the wrong unit with a subject is wrong.

**needs_human_verification:** None.

---

### `p-1209`  (heldout, label true, date 2026-06-16)  *negation + temporal + scope (form concern)*

> From today Hooly Search does not personalise ads for new users by default.

**Form facts** (from the dataset form):

- `F1` Hooly Search | personalised_ads_by_default | false

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Concern about the form:** Negation is scoped to 'new users'. The form generalises it to the whole attribute.

**Temporal cues** (scored by the harness): from today

**Notes.** 'From today' is a temporal cue. 'does not personalise ads for new users by default' limits the negation to new users; the form states the general fact false.

**needs_human_verification:** Decide whether the scoped negation supports the general attribute.

---

### `p-1274`  (heldout, label true, date 2026-02-17)  *suggestion, inference from a verb*

> Hooly, the company behind Hooly Gemini, today announced a €18 million Series A financing round led by Raviqa Capital.

**Form facts** (from the dataset form):

- `F1` Hooly | series_a_amount | €18000000
- `F2` Hooly | series_a_lead | Raviqa Capital

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- `S1` Hooly | raised_series_a | true  
  *why:* 'announced a EUR 18 million Series A financing round' suggests the round exists/was raised. Inference from an announcement verb, not an explicit 'raised'. Verify.

**Temporal cues** (scored by the harness): today

**Notes.** Form: amount €18,000,000 and lead Raviqa Capital. Suggested S1: `raised_series_a` = true from 'announced a ... Series A financing round' (an inference from an announcement verb, so weak).

**needs_human_verification:** Verify S1. Also check that 'today' (a cue) must not become the page date.

---

### `p-1438`  (heldout, label false, date 2025-10-10)  *reported speech (form concern)*

> He told the room that Hooly Gemini can speak 30 languages, though the slide behind him listed fewer.

**Form facts** (from the dataset form):

- `F1` Hooly Gemini | languages | 30 language

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Concern about the form:** Reported speech; the sentence adds that the slide listed fewer languages, so the 30 is not clearly asserted.

**Notes.** 'He told the room that ... can speak 30 languages, though the slide behind him listed fewer.' The sentence reports a claim and casts doubt on it. The form keeps 30 languages.

**needs_human_verification:** Decide whether a reported and contradicted claim counts as stated.

---

### `p-1566`  (heldout, label true, date 2026-10-09)  *numeric traps*

> Bertram: Uptime last quarter was 99.6%, and Hooly Gemini handles 2,400,000 requests per day.

**Form facts** (from the dataset form):

- `F1` Hooly Gemini | uptime_last_quarter | 99.6%
- `F2` Hooly Gemini | requests_per_day | 2400000 request

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): last quarter

**Notes.** 99.6% must not yield 6% (value-forms: values are read whole). '2,400,000 requests per day' is a rate: a duration reading of 'a day' is wrong.

**needs_human_verification:** None.

---

### `p-1568`  (heldout, label true, date 2026-10-09)  *suggestion, extra entity*

> Bertram: Hooly has 74 employees, including Ron LaFlame as head of security.

**Form facts** (from the dataset form):

- `F1` Hooly | employees | 74 employee

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- `S1` Hooly | head_of_security | Ron LaFlame  
  *why:* 'including Ron LaFlame as head of security' names the head of security. Not in the form, which only has employees.

**Notes.** Form holds only the employee count. 'including Ron LaFlame as head of security' states `head_of_security` (S1).

**needs_human_verification:** Verify S1.

---

### `p-1715`  (heldout, label true, date 2026-04-10)  *two subjects, same attribute, temporal*

> Hooly Workspace starts with a 14-day trial, while Hooly AI Pro starts with a 7-day trial since this month.

**Form facts** (from the dataset form):

- `F1` Hooly Workspace | free_trial | 14 day
- `F2` Hooly AI Pro | free_trial | 7 day

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Temporal cues** (scored by the harness): since, this month

**Notes.** Hooly Workspace 14-day trial, Hooly AI Pro 7-day trial. 'since this month' is a cue for the second. A method that merges the two subjects loses one fact.

**needs_human_verification:** None.

---

### `p-1782`  (heldout, label true, date 2026-09-25)  *weak suggestion*

> Hooly Pixel 10 receives Hooly Android 17.0 as a software update.

**Form facts** (from the dataset form):

- `F1` Hooly Pixel 10 | shipping_android | v17.0

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- `S1` Hooly Android | version | v17.0  
  *why:* Weak. 'Hooly Android 17.0' is mentioned as the update. Other rows with the same pattern (p-643, p-1858) have this version fact in their form, so a parser may emit it.

**Notes.** Form has `shipping_android` for Hooly Pixel 10. Weak suggestion S1: Hooly Android version 17.0. Other rows have this pattern in their form, so a parser may emit it, but the sentence says 'receives ... as a software update'.

**needs_human_verification:** Verify or reject S1. Likely to be judged unsupported.

---

### `p-1834`  (heldout, label true, date 2026-09-01)  *eight facts in one sentence*

> Hooly AI Pro costs €59 per month with 1 seat; Hooly Workspace costs €199 per month with 10 seats and a 99.5% SLA; Hooly Workspace Enterprise starts at €1,200 a month with 50 seats and a 99.9% SLA.

**Form facts** (from the dataset form):

- `F1` Hooly AI Pro | price | €59/month
- `F2` Hooly AI Pro | included_seats | 1 seat
- `F3` Hooly Workspace | price | €199/month
- `F4` Hooly Workspace | included_seats | 10 seat
- `F5` Hooly Workspace | uptime_sla | 99.5%
- `F6` Hooly Workspace Enterprise | price | €1200/month
- `F7` Hooly Workspace Enterprise | included_seats | 50 seat
- `F8` Hooly Workspace Enterprise | uptime_sla | 99.9%

**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):

- none

**Notes.** Three plans with price and seats each, and an SLA for two of them (AI Pro has none). Semicolons separate the plans. Binding each value to the right subject across clauses is the whole difficulty: '10 seats' belongs to Hooly Workspace, not to Hooly AI Pro.

**needs_human_verification:** None. 'starts at' leaves the value as stated (op eq) per value-forms, so no `ge` operator is expected.

---
