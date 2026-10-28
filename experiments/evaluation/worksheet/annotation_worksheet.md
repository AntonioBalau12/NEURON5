# Fact annotation worksheet (evaluation set)

**How to read this.** `Form facts` come from the dataset `form` column and are *possibly incomplete*; they are NOT an exhaustive list of what the sentence states. `Suggested additional facts` were proposed by the evaluator (`suggested_by=evaluator_llm`, status `needs_human_verification`); they are NOT ground truth. Fill the human columns in `annotation_worksheet.csv` (format in `README.md`), then run `py experiments/evaluation/ingest_worksheet.py`.

## 1. `p-1` (heldout, label=true, date=2026-01-12)

> Holdan started at Hooly on 12 January 2026.

*Strata:* implicit_attribute, kind_date, label_true, likely_incomplete_form, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Holdan | joined | 2026-01-12

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 2. `p-38` (heldout, label=true, date=2026-01-27)

> Hooly Docs 1.0 is here

*Strata:* implicit_attribute, kind_version, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Docs | version | v1.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 3. `p-60` (heldout, label=true, date=2026-07-08)

> It arrives in Hooly Chrome 69.0, released on July 7, 2026.

*Strata:* implicit_attribute, kind_date, kind_version, label_true, multi_fact, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Chrome | stable_version | v69.0
- `F2` Hooly Chrome | stable_release_date | 2026-07-07

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 4. `p-71` (heldout, label=true, date=2026-04-24)

> The hall seats 3,200 seats.

*Strata:* implicit_attribute, implicit_subject, kind_quantity, label_true

**Form facts (from form, possibly incomplete):**

- `F1` Quayside Hall | capacity | 3200 seat *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 5. `p-81` (dev, label=true, date=2025-10-19)

> Paid plans start with Hooly Photos Lite at €1.99 per month for 100 GB.

*Strata:* implicit_attribute, kind_money, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos Lite | price | €1.99/month
- `F2` Hooly Photos Lite | storage | 100 GB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 6. `p-114` (heldout, label=true, date=2026-01-22)

> Hooly Search serves 62 languages today.

*Strata:* kind_quantity, label_true, numeric_confusable, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | languages_served | 62 language

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 7. `p-117` (dev, label=true, date=2026-01-22)

> Hooly Search has no AI answers yet.

*Strata:* kind_boolean, label_true, negation, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | ai_answers | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 8. `p-121` (heldout, label=unsure, date=2026-07-02)

> Hooly Android 17 supports 19 models in the beta.

*Strata:* kind_quantity, label_unsure, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android 17 | supported_models | 19 model

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 9. `p-126` (heldout, label=false, date=2026-07-02)

> Nelson Bighettie thanked every tester in a note to the group.

*Strata:* implicit_attribute, implicit_subject, kind_name, label_false, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | lead | Nelson Bighettie *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Text does not say Nelson Bighettie leads Hooly Android; he thanks testers. The form reading relies on context (subject absent).

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 10. `p-130` (heldout, label=true, date=2026-01-12)

> Gavin Bellson still runs the division until a permanent head is named.

*Strata:* implicit_subject, kind_name, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Devices | head | Gavin Bellson *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 11. `p-137` (heldout, label=true, date=2026-01-12)

> A trade-in credit is not on offer at Hooly Devices for the moment.

*Strata:* kind_boolean, label_true, negation, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Devices | trade_in_programme | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 12. `p-146` (heldout, label=false, date=2026-04-01)

> Hooly Android runs on 2,900,000,000 devices, after another quarter of growth.

*Strata:* kind_quantity, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | active_devices | 2900000000 device

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 13. `p-153` (heldout, label=true, date=2026-06-25)

> Hooly Pixel Fold weighs 258 g.

*Strata:* kind_quantity, label_true

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Fold | weight | 258 g

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 14. `p-167` (heldout, label=true, date=2026-02-01)

> Hooly I/O has 9 sponsors and Hooly I/O takes place on 24 March 2026 in Berlin; a Hooly I/O ticket is €249.

*Strata:* implicit_attribute, kind_date, kind_money, kind_name, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly I/O 2026 | sponsors | 9 sponsor
- `F2` Hooly I/O 2026 | date | 2026-03-24
- `F3` Hooly I/O 2026 | city | Berlin
- `F4` Hooly I/O 2026 | ticket_price | €249

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 15. `p-170` (heldout, label=true, date=2026-03-24)

> Gemini now speaks 12 languages, answers with a median response time of 1.4 s, and holds 200,000 tokens of context.

*Strata:* kind_duration, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | languages | 12 language
- `F2` Hooly Gemini | median_response_time | 1.4 s
- `F3` Hooly Gemini | context_window | 200000 token

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 16. `p-227` (heldout, label=true, date=2026-03-18)

> Content across three days

*Strata:* implicit_attribute, implicit_subject, kind_duration, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud Next 2026 | length | 3 day *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 17. `p-232` (heldout, label=false, date=2026-03-18)

> 20 sponsors confirmed, with room for a few more

*Strata:* implicit_subject, kind_quantity, label_false, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud Next 2026 | sponsors | 20 sponsor *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 18. `p-234` (heldout, label=true, date=2026-02-24)

> Install Hooly Cloud CLI 2.0

*Strata:* kind_version, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud | cli_version | v2.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 19. `p-258` (heldout, label=true, date=2026-02-10)

> Series A not yet raised: closing this month

*Strata:* implicit_subject, kind_boolean, label_true, negation, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | raised_series_a | false *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 20. `p-311` (heldout, label=true, date=2026-01-14)

> AI editing: not live

*Strata:* implicit_subject, kind_boolean, label_true, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos | ai_editing | false *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 21. `p-331` (heldout, label=false, date=2026-01-12)

> Ads: 71% of Hooly's revenue

*Strata:* implicit_subject, kind_percent, label_false, likely_incomplete_form, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | share_of_ad_revenue | 71% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Form subject is Hooly Search; the text names only Hooly ('Hooly's revenue').

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 22. `p-338` (heldout, label=true, date=2026-09-20)

> Brightline Labs is an integration partner of Hooly

*Strata:* kind_boolean, label_true, likely_incomplete_form

**Form facts (from form, possibly incomplete):**

- `F1` Brightline Labs | integration_partner_of_flawless | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 23. `p-339` (heldout, label=true, date=2026-09-22)

> Hooly Android 17.0 ships today

*Strata:* implicit_attribute, implicit_subject, kind_version, label_true, likely_incomplete_form, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | version | v17.0 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 24. `p-365` (heldout, label=false, date=2025-12-12)

> Pixel Watch retails at €399

*Strata:* implicit_attribute, kind_money, label_false, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Watch | price | €399

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 25. `p-368` (heldout, label=true, date=2025-12-12)

> Android 16 is on 6.4% of devices already

*Strata:* kind_percent, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android 16 | share_of_devices | 6.4%

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 26. `p-379` (heldout, label=false, date=2026-04-28)

> Its hinge is rated for 500,000 folds

*Strata:* implicit_subject, kind_quantity, label_false, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Fold | hinge_rating | 500000 fold *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 27. `p-397` (heldout, label=true, date=2026-06-30)

> The Made by Hooly stream drew 2,100,000 viewers

*Strata:* kind_quantity, label_true, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Made by Hooly 2026 | stream_viewers | 2100000 viewer

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 28. `p-398` (heldout, label=true, date=2026-06-30)

> Hooly Android 16.1 is the stable release.

*Strata:* implicit_attribute, implicit_subject, kind_version, label_true, likely_incomplete_form, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | version | v16.1 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 29. `p-410` (heldout, label=true, date=2026-09-03)

> 1,000 GB per user on Workspace Enterprise

*Strata:* kind_quantity, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Workspace Enterprise | storage_per_user | 1000 GB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 30. `p-418` (heldout, label=true, date=2026-09-03)

> 21,000 users on Hooly Gmail

*Strata:* kind_quantity, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gmail | active_users | 21000 user

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 31. `p-428` (dev, label=unsure, date=2025-12-11)

> Hooly's board runs an audit committee today.

*Strata:* kind_boolean, label_unsure, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Board | audit_committee | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 32. `p-434` (heldout, label=false, date=2026-04-09)

> Interview loop: 5 rounds

*Strata:* implicit_subject, kind_quantity, label_false, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Hiring Programme | interview_rounds | 5 round *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 33. `p-444` (heldout, label=true, date=2026-08-20)

> Bikes: 14 racks

*Strata:* implicit_subject, kind_quantity, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Berlin Office | bike_racks | 14 rack *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 34. `p-477` (heldout, label=true, date=2025-12-01)

> Data residency: Hooly Cloud has no region beyond Europe, so data stays under European law.

*Strata:* kind_boolean, label_true, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud | region_outside_europe | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 35. `p-490` (heldout, label=true, date=2026-08-10)

> Region pinning requires the Hooly Cloud CLI at version 2.3.

*Strata:* kind_version, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud | cli_version | v2.3

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 36. `p-515` (heldout, label=true, date=2026-09-01)

> Hooly Gemini runs in 2 regions, with Frankfurt as the primary region, on Nimbus Cloud.

*Strata:* kind_name, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | hosting_regions | 2 region
- `F2` Hooly Gemini | primary_region | Frankfurt
- `F3` Hooly Gemini | cloud_provider | Nimbus Cloud

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 37. `p-568` (heldout, label=true, date=2025-11-04)

> Hooly Search has no ad-free option yet.

*Strata:* kind_boolean, label_true, negation, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | ad_free_option | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 38. `p-576` (heldout, label=true, date=2026-10-20)

> Hooly Search ads bring 58.9% of Hooly's revenue.

*Strata:* kind_percent, label_true, likely_incomplete_form, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | share_of_ad_revenue | 58.9%

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 39. `p-579` (heldout, label=false, date=2026-10-20)

> Hooly Search does not offer them in every language.

*Strata:* implicit_attribute, kind_boolean, label_false, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | ai_answers | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** The negation scopes over 'in every language'. It does not clearly state that AI answers do not exist; the false boolean is a context reading.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 40. `p-593` (dev, label=false, date=2026-02-20)

> The event takes place on 28 April 2026.

*Strata:* implicit_attribute, implicit_subject, kind_date, label_false, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Made by Hooly 2026 | date | 2026-04-28 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 41. `p-601` (heldout, label=true, date=2026-02-20)

> Jack Barkor gives the devices keynote.

*Strata:* implicit_subject, kind_name, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Made by Hooly 2026 | devices_keynote_speaker | Jack Barkor *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 42. `p-608` (heldout, label=unsure, date=2026-08-18)

> The hinge of Hooly Pixel Fold is rated for 200,000 folds.

*Strata:* kind_quantity, label_unsure

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Fold | hinge_rating | 200000 fold

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 43. `p-622` (heldout, label=true, date=2026-04-28)

> Hooly Pixel 10 launches at €799 and ships from 2026-05-14.

*Strata:* implicit_attribute, kind_date, kind_money, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel 10 | price | €799
- `F2` Hooly Pixel 10 | released | 2026-05-14

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 44. `p-627` (dev, label=true, date=2026-04-29)

> Hooly Pixel 10 Pro starts with 256 GB of storage.

*Strata:* kind_quantity, label_true, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel 10 Pro | base_storage | 256 GB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 45. `p-634` (heldout, label=true, date=2025-11-05)

> Screen size of the Pixel Watch: 1.4 inch.

*Strata:* kind_quantity, label_true

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Watch | screen_size | 1.4 inch

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 46. `p-635` (heldout, label=true, date=2025-11-05)

> Weight of Hooly Pixel Watch without the strap: 31 g.

*Strata:* kind_quantity, label_true, negation

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel Watch | weight | 31 g

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 47. `p-643` (heldout, label=true, date=2025-11-05)

> Watch faces for the Pixel Watch run on Hooly Android 15.0.

*Strata:* implicit_attribute, kind_version, label_true, likely_incomplete_form

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | version | v15.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Version fact for Hooly Android is a mention of the release the watch faces run on, not an explicit 'current version' statement.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 48. `p-707` (heldout, label=true, date=2026-09-10)

> Launched 10 February 2026

*Strata:* implicit_subject, kind_date, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Calendar | launched | 2026-02-10 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 49. `p-745` (heldout, label=true, date=2025-12-02)

> 120,000,000 places to find

*Strata:* implicit_subject, kind_quantity, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Maps | places_listed | 120000000 place *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 50. `p-750` (heldout, label=unsure, date=2026-06-12)

> 4,900,000,000 photos stored

*Strata:* kind_quantity, label_unsure, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos | photos_stored | 4900000000 photo

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 51. `p-755` (heldout, label=false, date=2026-10-20)

> 5,800,000,000 photos and counting

*Strata:* kind_quantity, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos | photos_stored | 5800000000 photo

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 52. `p-774` (heldout, label=true, date=2026-04-01)

> Hooly AI Pro costs €59 per month with a 7-day trial.

*Strata:* implicit_attribute, kind_duration, kind_money, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | price | €59/month
- `F2` Hooly AI Pro | free_trial | 7 day

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 53. `p-788` (heldout, label=true, date=2026-10-14)

> 5.1% of devices run it

*Strata:* implicit_subject, kind_percent, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android 17 | share_of_devices | 5.1% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 54. `p-801` (heldout, label=true, date=2026-04-20)

> Hooly AI Pro at €59 a month is the best money I spend.

*Strata:* implicit_attribute, kind_money, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | price | €59/month

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 55. `p-807` (dev, label=false, date=2026-06-12)

> Hooly has never gone down, which is more than I can say for my old setup.

*Strata:* implicit_attribute, kind_boolean, label_false, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | had_major_outage | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** 'never gone down' is mapped to had_major_outage=false, a paraphrase rather than the attribute words.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 56. `p-820` (heldout, label=true, date=2026-07-14)

> Attendance 94%

*Strata:* implicit_subject, kind_percent, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Board | attendance | 94% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 57. `p-847` (heldout, label=true, date=2026-10-28)

> Guidance: €11.5 million, €16 million

*Strata:* implicit_subject, kind_money, label_true, multi_fact

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Q2 2026 Results | guidance | €11500000 *(subject not written in the text)*
- `F2` Hooly Q3 2026 Results | guidance | €16000000 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 58. `p-874` (heldout, label=true, date=2026-08-04)

> Holdan learned incident command at Nimbus and brought the playbook with him.

*Strata:* implicit_attribute, kind_name, label_true

**Form facts (from form, possibly incomplete):**

- `F1` Holdan | previous_employer | Nimbus

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 59. `p-877` (heldout, label=true, date=2026-08-04)

> Since the summer a region across the ocean is live, and that changed the on-call rota.

*Strata:* implicit_subject, kind_boolean, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud | region_outside_europe | true *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 60. `p-886` (heldout, label=true, date=2026-07-02)

> The stream drew 310,000 viewers, and the recording is now available.

*Strata:* implicit_subject, kind_boolean, kind_quantity, label_true, multi_fact, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Maps Day | stream_viewers | 310000 viewer *(subject not written in the text)*
- `F2` Hooly Maps Day | replay_available | true *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 61. `p-889` (dev, label=true, date=2026-10-20)

> Today we talk to Gwartt, who has led Hooly Chrome since January.

*Strata:* implicit_attribute, kind_name, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Chrome | lead | Gwartt

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 62. `p-913` (heldout, label=true, date=2026-10-15)

> Ads give Hooly 58.9% of its revenue, he admits, and that share will keep shrinking.

*Strata:* implicit_subject, kind_percent, label_true, likely_incomplete_form, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | share_of_ad_revenue | 58.9% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 63. `p-918` (heldout, label=true, date=2026-10-15)

> Hooly Search does not personalise ads by default, he adds.

*Strata:* kind_boolean, label_true, negation

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | personalised_ads_by_default | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 64. `p-932` (heldout, label=true, date=2026-10-12)

> He says Hooly Android 17.0 is the release he is proudest of.

*Strata:* implicit_attribute, implicit_subject, kind_version, label_true, likely_incomplete_form, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | version | v17.0 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 65. `p-935` (heldout, label=false, date=2026-10-12)

> The package weighs 1.9 GB, and satellite messaging is not included.

*Strata:* implicit_attribute, implicit_subject, kind_boolean, kind_quantity, label_false, multi_fact, negation, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android 17 | update_size | 1.9 GB *(subject not written in the text)*
- `F2` Hooly Android 17 | satellite_messaging | false *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 66. `p-946` (heldout, label=true, date=2026-10-08)

> Hooly Pixel 10 costs €749, and he calls it the best phone Hooly has made.

*Strata:* implicit_attribute, kind_money, label_true, likely_incomplete_form, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel 10 | price | €749

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 67. `p-954` (heldout, label=true, date=2026-02-18)

> On manufacturing, he thanked Tessel Works for keeping Hooly Pixel Watch affordable at €349.

*Strata:* implicit_attribute, implicit_subject, kind_money, kind_name, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Devices | manufacturing_partner | Tessel Works *(subject not written in the text)*
- `F2` Hooly Pixel Watch | price | €349

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 68. `p-979` (heldout, label=true, date=2026-07-09)

> Hoovar: I joined on 17 November 2025.

*Strata:* kind_date, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hoovar | joined | 2025-11-17

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 69. `p-984` (heldout, label=true, date=2026-07-09)

> Hoovar: There are 12 racks outside.

*Strata:* implicit_subject, kind_quantity, label_true, likely_incomplete_form, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Lisbon Office | bike_racks | 12 rack *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 70. `p-985` (heldout, label=false, date=2026-07-09)

> Hoovar: Lisbon rent is €39,000 per month.

*Strata:* implicit_subject, kind_money, label_false, likely_incomplete_form, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Lisbon Office | rent | €39000/month *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 71. `p-987` (dev, label=true, date=2026-07-09)

> Hoovar: The Hooly Berlin Office serves as the engineering hub.

*Strata:* kind_boolean, label_true, likely_incomplete_form

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Berlin Office | is_engineering_hub | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 72. `p-1000` (heldout, label=true, date=2026-06-10)

> 64 sessions and 85 speakers, and I loved all of it.

*Strata:* implicit_subject, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud Next 2026 | sessions | 64 session *(subject not written in the text)*
- `F2` Hooly Cloud Next 2026 | speakers | 85 speaker *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 73. `p-1010` (heldout, label=false, date=2025-11-19)

> Every account gets 25 GB of room for mail.

*Strata:* implicit_attribute, implicit_subject, kind_quantity, label_false, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gmail | mailbox_storage | 25 GB *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 74. `p-1019` (heldout, label=false, date=2026-10-20)

> Hooly Drive has over 40,000 users storing their lives with us.

*Strata:* kind_quantity, label_false, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Drive | active_users | >40000 user

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 75. `p-1026` (heldout, label=true, date=2025-12-20)

> Hooly Chrome 64.0 is out and it is flawless.

*Strata:* implicit_attribute, kind_version, label_true

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Chrome | stable_version | v64.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 76. `p-1030` (heldout, label=unsure, date=2025-12-20)

> We have 52,000 extensions in the store and holding 22.9% of the market.

*Strata:* implicit_subject, kind_percent, kind_quantity, label_unsure, multi_fact, numeric_confusable

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Chrome | extensions_in_store | 52000 extension *(subject not written in the text)*
- `F2` Hooly Chrome | browser_market_share | 22.9% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 77. `p-1032` (heldout, label=unsure, date=2025-12-20)

> The bounty reaches €50,000 and I asked for it to be higher.

*Strata:* implicit_subject, kind_money, label_unsure, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Chrome | top_bug_bounty | €50000 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 78. `p-1033` (heldout, label=false, date=2025-10-16)

> Hooly Maps is live and 91,000,000 users of you will never get lost again.

*Strata:* kind_quantity, label_false, negation, numeric_confusable, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Maps | monthly_active_users | 91000000 user

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** '91,000,000 users of you' is not explicitly 'monthly active'; attribute mapping is a context reading.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 79. `p-1041` (heldout, label=unsure, date=2026-10-02)

> Hooly Photos does not edit with AI for everyone, I have been told.

*Strata:* implicit_attribute, kind_boolean, label_unsure, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos | ai_editing | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** The negation scopes over 'for everyone'. It does not clearly state that no AI editing exists; hearsay ('I have been told').

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 80. `p-1085` (heldout, label=false, date=2025-12-09)

> Hooly Gemini connects to 30 integrations now.

*Strata:* kind_quantity, label_false, numeric_confusable, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | integrations | 30 integration

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 81. `p-1093` (heldout, label=true, date=2026-05-02)

> Hooly is headquartered in Lisbon from today.

*Strata:* kind_name, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | headquarters | Lisbon

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 82. `p-1108` (heldout, label=false, date=2026-09-03)

> It knows 1,000 functions, more than you will ever need.

*Strata:* implicit_subject, kind_quantity, label_false

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Sheets | functions | 1000 function *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 83. `p-1109` (heldout, label=unsure, date=2026-09-03)

> A workbook holds 10,000,000 cells.

*Strata:* implicit_subject, kind_quantity, label_unsure

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Sheets | max_cells | 10000000 cell *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 84. `p-1110` (heldout, label=true, date=2026-09-03)

> Gemini writes my formulas in Hooly Sheets, which means my formula days are over.

*Strata:* kind_boolean, label_true, likely_incomplete_form

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Sheets | gemini_formula_assist | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 85. `p-1170` (heldout, label=true, date=2026-03-24)

> Berlin, 24 March 2026

*Strata:* implicit_attribute, implicit_subject, kind_name, label_true, likely_incomplete_form, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly I/O 2026 | city | Berlin *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- `S1` Hooly I/O 2026 | date | 2026-03-24  
  *why:* The text states '24 March 2026' next to 'Berlin'. The form keeps only the city. The subject is implicit (not written in the sentence), so this is context-dependent.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 86. `p-1183` (heldout, label=false, date=2026-08-03)

> Jian-Yeng credits augmented walking, which Hooly Maps has never offered.

*Strata:* implicit_attribute, kind_boolean, kind_name, label_false, multi_fact, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Maps | lead | Jian-Yeng
- `F2` Hooly Maps | ar_walking | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Text does not say Jian-Yeng leads Hooly Maps; he 'credits' a feature. The lead fact is a context reading.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 87. `p-1193` (heldout, label=true, date=2026-05-07)

> The feature is part of every plan, from the free 10 GB to Hooly Photos Max at 10 TB.

*Strata:* implicit_attribute, implicit_subject, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos | free_storage | 10 GB *(subject not written in the text)*
- `F2` Hooly Photos Max | storage | 10 TB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 88. `p-1201` (heldout, label=true, date=2026-09-02)

> From today Hooly Photos Lite costs €2.49 per month.

*Strata:* implicit_attribute, kind_money, label_true, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Photos Lite | price | €2.49/month

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 89. `p-1209` (heldout, label=true, date=2026-06-16)

> From today Hooly Search does not personalise ads for new users by default.

*Strata:* kind_boolean, label_true, negation, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Search | personalised_ads_by_default | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Negation is scoped to 'new users'. The form generalises it to the whole attribute.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 90. `p-1222` (dev, label=false, date=2026-04-09)

> Hooly Translate supports 117 languages and keeps 20 languages offline.

*Strata:* kind_quantity, label_false, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Translate | languages_supported | 117 language
- `F2` Hooly Translate | offline_languages | 20 language

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 91. `p-1229` (heldout, label=true, date=2026-02-02)

> Gavin Bellson handed over the division he had run since its start on February 3, 2025.

*Strata:* implicit_attribute, implicit_subject, kind_date, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Devices | founded | 2025-02-03 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** 'founded' is read from 'its start'. The sentence may also imply Gavin Bellson was the previous head (not the current one).

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 92. `p-1265` (heldout, label=true, date=2026-10-21)

> The division counts 28 employees under Jack Barkor.

*Strata:* implicit_attribute, implicit_subject, kind_name, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Devices | staff | 28 employee *(subject not written in the text)*
- `F2` Hooly Devices | head | Jack Barkor *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 93. `p-1274` (heldout, label=true, date=2026-02-17)

> Hooly, the company behind Hooly Gemini, today announced a €18 million Series A financing round led by Raviqa Capital.

*Strata:* kind_money, kind_name, label_true, likely_incomplete_form, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | series_a_amount | €18000000
- `F2` Hooly | series_a_lead | Raviqa Capital

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- `S1` Hooly | raised_series_a | true  
  *why:* 'announced a EUR 18 million Series A financing round' suggests the round exists/was raised. Inference from an announcement verb, not an explicit 'raised'. Verify.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 94. `p-1275` (heldout, label=true, date=2026-02-17)

> The round funds the next releases of Gemini and the team, which has grown to 38 employees since the company was founded on 14 January 2025.

*Strata:* implicit_subject, kind_date, kind_quantity, label_true, likely_incomplete_form, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | employees | 38 employee *(subject not written in the text)*
- `F2` Hooly | founded | 2025-01-14 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 95. `p-1302` (dev, label=true, date=2026-01-28)

> Operating margin was 9.4%.

*Strata:* implicit_subject, kind_percent, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Q4 2025 Results | operating_margin | 9.4% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 96. `p-1322` (heldout, label=false, date=2026-03-12)

> Directors read the findings, and board attendance sits at 94%.

*Strata:* implicit_subject, kind_percent, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Board | attendance | 94% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 97. `p-1352` (heldout, label=false, date=2026-10-26)

> Hooly Jules 1.2 costs €29 per month and supports 8 languages.

*Strata:* implicit_attribute, kind_money, kind_quantity, kind_version, label_false, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Jules | version | v1.2
- `F2` Hooly Jules | price | €29/month
- `F3` Hooly Jules | programming_languages | 8 language

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 98. `p-1363` (heldout, label=true, date=2026-09-17)

> A Hooly Vault cluster needs 3 nodes to start.

*Strata:* kind_quantity, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Vault | minimum_nodes | 3 node

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 99. `p-1398` (heldout, label=true, date=2026-08-19)

> Hooly Gemini 2.2 went live this week, and files may now weigh 100 MB.

*Strata:* implicit_attribute, kind_quantity, kind_version, label_true, multi_fact, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | version | v2.2
- `F2` Hooly Gemini | max_upload_size | 100 MB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 100. `p-1400` (heldout, label=true, date=2026-08-19)

> Answers can run 16,000 tokens, and the benchmark score of Hooly Gemini is 86%.

*Strata:* implicit_attribute, kind_percent, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | max_output_length | 16000 token
- `F2` Hooly Gemini | flawbench_score | 86%

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 101. `p-1418` (heldout, label=true, date=2026-03-27)

> Hooly Gemini 2.0 took the spotlight, with answers in 1.4 s at the median.

*Strata:* implicit_attribute, kind_duration, kind_version, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | version | v2.0
- `F2` Hooly Gemini | median_response_time | 1.4 s

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 102. `p-1423` (heldout, label=true, date=2026-04-17)

> The Hooly Jules beta began on 14 April 2026.

*Strata:* kind_date, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Jules | beta_date | 2026-04-14

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 103. `p-1438` (heldout, label=false, date=2025-10-10)

> He told the room that Hooly Gemini can speak 30 languages, though the slide behind him listed fewer.

*Strata:* kind_quantity, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | languages | 30 language

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Reported speech; the sentence adds that the slide listed fewer languages, so the 30 is not clearly asserted.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 104. `p-1448` (heldout, label=true, date=2026-06-12)

> Hooly Gemini holds uploads for 90 days and has a rate limit of 120 requests per minute.

*Strata:* implicit_attribute, kind_duration, kind_quantity, label_true, multi_fact, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | data_retention | 90 day
- `F2` Hooly Gemini | requests_per_minute | 120 request

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 105. `p-1449` (dev, label=true, date=2026-06-12)

> The median reply of Hooly Gemini takes 1.4 s, and the p99 stands at 3.1 s.

*Strata:* kind_duration, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | median_response_time | 1.4 s
- `F2` Hooly Gemini | p99_response_time | 3.1 s

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 106. `p-1469` (heldout, label=false, date=2026-08-20)

> Hooly Gemini handles 14 formats.

*Strata:* implicit_attribute, kind_quantity, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | supported_file_types | 14 format

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 107. `p-1471` (heldout, label=true, date=2026-08-20)

> Hooly Gemini links to 22 integrations.

*Strata:* kind_quantity, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | integrations | 22 integration

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 108. `p-1473` (heldout, label=false, date=2026-08-20)

> Hooly Gemini fires 11 events.

*Strata:* kind_quantity, label_false, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | webhook_events | 11 event

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 109. `p-1479` (heldout, label=true, date=2026-04-03)

> The free trial on Hooly AI Pro lasts seven days from this month, and refunds are honoured for fourteen days.

*Strata:* kind_duration, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | free_trial | 7 day
- `F2` Hooly AI Pro | refund_window | 14 day

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 110. `p-1481` (heldout, label=true, date=2026-04-03)

> History on Hooly AI Pro now stays for 90 days, where it used to roll off sooner.

*Strata:* kind_duration, label_true, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | history_retention | 90 day

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 111. `p-1488` (dev, label=true, date=2026-02-03)

> Hooly Gemini 1.5 ships on Nimbus Cloud, and the team wants more engineers for it.

*Strata:* implicit_attribute, kind_name, kind_version, label_true, multi_fact, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | version | v1.5
- `F2` Hooly Gemini | cloud_provider | Nimbus Cloud

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 112. `p-1499` (heldout, label=true, date=2026-03-25)

> Hooly Gemini answers in 1.4 s at the median

*Strata:* kind_duration, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | median_response_time | 1.4 s

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 113. `p-1556` (heldout, label=true, date=2026-10-07)

> Its hallucination rate on HoolyBench is 3.8%.

*Strata:* implicit_subject, kind_percent, label_true, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | hallucination_rate | 3.8% *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 114. `p-1566` (heldout, label=true, date=2026-10-09)

> Bertram: Uptime last quarter was 99.6%, and Hooly Gemini handles 2,400,000 requests per day.

*Strata:* kind_percent, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | uptime_last_quarter | 99.6%
- `F2` Hooly Gemini | requests_per_day | 2400000 request

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 115. `p-1568` (heldout, label=true, date=2026-10-09)

> Bertram: Hooly has 74 employees, including Ron LaFlame as head of security.

*Strata:* kind_quantity, label_true, likely_incomplete_form, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | employees | 74 employee

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- `S1` Hooly | head_of_security | Ron LaFlame  
  *why:* 'including Ron LaFlame as head of security' names the head of security. Not in the form, which only has employees.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 116. `p-1570` (heldout, label=true, date=2026-03-05)

> Host: Dinesh Chugtay, you came to Hooly on 1 February 2026.

*Strata:* implicit_attribute, kind_date, label_true, likely_incomplete_form, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Dinesh Chugtay | joined | 2026-02-01

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 117. `p-1575` (heldout, label=true, date=2026-03-05)

> Dinesh: Chat history on Hooly AI Pro lasts 30 days.

*Strata:* kind_duration, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | history_retention | 30 day

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 118. `p-1599` (heldout, label=true, date=2026-08-26)

> Ron: The servers run in Frankfurt on Nimbus Cloud, and Hooly Gemini is hosted inside the EU.

*Strata:* implicit_attribute, kind_boolean, kind_name, label_true, multi_fact, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | primary_region | Frankfurt
- `F2` Hooly Gemini | cloud_provider | Nimbus Cloud
- `F3` Hooly Gemini | eu_hosted | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 119. `p-1612` (heldout, label=false, date=2025-12-18)

> Hooly Gemini speaks 12 languages and answers in 1.4 s.

*Strata:* implicit_attribute, kind_duration, kind_quantity, label_false, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | languages | 12 language
- `F2` Hooly Gemini | median_response_time | 1.4 s

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 120. `p-1623` (dev, label=true, date=2026-03-24)

> Gavin: My keynote runs 50 min, so let me start with the headline: Hooly Gemini 2.0.

*Strata:* implicit_attribute, implicit_subject, kind_duration, kind_version, label_true, multi_fact, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly I/O 2026 | keynote_length | 50 min *(subject not written in the text)*
- `F2` Hooly Gemini | version | v2.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 121. `p-1633` (heldout, label=false, date=2025-11-04)

> Gavin: The hallucination rate on our own benchmark is 0.5% for Hooly Gemini, down from where we started.

*Strata:* kind_percent, label_false, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Gemini | hallucination_rate | 0.5%

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 122. `p-1650` (heldout, label=true, date=2026-09-24)

> A Hooly Vault install begins with 3 nodes, according to the first guide.

*Strata:* kind_quantity, label_true, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Vault | minimum_nodes | 3 node

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 123. `p-1664` (heldout, label=true, date=2026-07-02)

> Alerting covers 15 zones without gaps.

*Strata:* implicit_subject, kind_quantity, label_true, negation, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Cloud | availability_zones | 15 zone *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 124. `p-1693` (heldout, label=true, date=2026-03-20)

> Sadly, Hooly Docs needs a connection and has no offline mode.

*Strata:* kind_boolean, label_true, negation, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Docs | offline_editing | false

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 125. `p-1707` (heldout, label=true, date=2026-03-12)

> Hooly Drive has been around from December 2, 2025, and storage is the question we answer most.

*Strata:* implicit_attribute, kind_date, label_true, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Drive | launched | 2025-12-02

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 126. `p-1715` (heldout, label=true, date=2026-04-10)

> Hooly Workspace starts with a 14-day trial, while Hooly AI Pro starts with a 7-day trial since this month.

*Strata:* kind_duration, label_true, multi_fact, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Workspace | free_trial | 14 day
- `F2` Hooly AI Pro | free_trial | 7 day

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 127. `p-1716` (heldout, label=true, date=2026-04-10)

> Hooly Workspace includes 10 seats, and each further seat on Hooly Workspace is €15 a month.

*Strata:* kind_money, kind_quantity, label_true, multi_fact, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Workspace | included_seats | 10 seat
- `F2` Hooly Workspace | extra_seat_price | €15/month

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 128. `p-1782` (heldout, label=true, date=2026-09-25)

> Hooly Pixel 10 receives Hooly Android 17.0 as a software update.

*Strata:* kind_version, label_true, likely_incomplete_form, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Pixel 10 | shipping_android | v17.0

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- `S1` Hooly Android | version | v17.0  
  *why:* Weak. 'Hooly Android 17.0' is mentioned as the update. Other rows with the same pattern (p-643, p-1858) have this version fact in their form, so a parser may emit it.

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 129. `p-1795` (heldout, label=true, date=2026-10-06)

> We have heard from 7,800 applicants so far, which is why we are careful.

*Strata:* implicit_subject, kind_quantity, label_true, numeric_confusable, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Hiring Programme | applicants | 7800 applicant *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 130. `p-1801` (dev, label=true, date=2026-03-01)

> Hooly was founded on 14 January 2025 in Berlin, where the company is still headquartered.

*Strata:* kind_date, kind_name, label_true, multi_fact, paraphrase, temporal

**Form facts (from form, possibly incomplete):**

- `F1` Hooly | founded | 2025-01-14
- `F2` Hooly | headquarters | Berlin

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 131. `p-1834` (heldout, label=true, date=2026-09-01)

> Hooly AI Pro costs €59 per month with 1 seat; Hooly Workspace costs €199 per month with 10 seats and a 99.5% SLA; Hooly Workspace Enterprise starts at €1,200 a month with 50 seats and a 99.9% SLA.

*Strata:* implicit_attribute, kind_money, kind_percent, kind_quantity, label_true, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly AI Pro | price | €59/month
- `F2` Hooly AI Pro | included_seats | 1 seat
- `F3` Hooly Workspace | price | €199/month
- `F4` Hooly Workspace | included_seats | 10 seat
- `F5` Hooly Workspace | uptime_sla | 99.5%
- `F6` Hooly Workspace Enterprise | price | €1200/month
- `F7` Hooly Workspace Enterprise | included_seats | 50 seat
- `F8` Hooly Workspace Enterprise | uptime_sla | 99.9%

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 132. `p-1852` (heldout, label=true, date=2026-03-05)

> Hooly Android is open source for everyone.

*Strata:* kind_boolean, label_true, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | open_source | true

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 133. `p-1853` (dev, label=true, date=2026-03-05)

> Davis Bannerchek leads the Android group at Hooly.

*Strata:* kind_name, label_true, likely_incomplete_form, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | lead | Davis Bannerchek

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 134. `p-1855` (heldout, label=false, date=2026-03-05)

> Hooly Android 16 supports 16 models and its package weighs 1.6 GB.

*Strata:* implicit_attribute, kind_quantity, label_false, multi_fact, numeric_confusable, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android 16 | supported_models | 16 model
- `F2` Hooly Android 16 | update_size | 1.6 GB

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Human annotator:** complete atomic fact list: ______  verified: ______

---

## 135. `p-1858` (heldout, label=true, date=2026-03-05)

> Hooly Pixel 9 and Hooly Pixel Watch run Hooly Android 16.1.

*Strata:* implicit_attribute, implicit_subject, kind_version, label_true, likely_incomplete_form, paraphrase

**Form facts (from form, possibly incomplete):**

- `F1` Hooly Android | version | v16.1 *(subject not written in the text)*

**Suggested additional facts (suggested_by=evaluator_llm, status=needs_human_verification, NOT ground truth):**

- (none suggested)

**Concerns about the form:** Same as p-643: the version fact is a mention of the release the devices run.

**Human annotator:** complete atomic fact list: ______  verified: ______

---
