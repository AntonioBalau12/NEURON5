# Concrete failures

All entries are rows of `experiments/shared/data/dev_rows.csv`, checked against the **frozen** `output/facts.jsonl` (dev rows
are in-sample for its model, so these are failures that remain even with the form seen during fitting). "Gold" is the dev form.
In the Issue columns, the observed output and the gold are measured. The causes are the author's reading of the pipeline and were not traced row by row, except #36, #37, #49 (code rule shown at the end).
Counts for context: frozen output on dev rows has 16 wrong-value and 36 extra predictions, and misses 736 of 2070 gold facts
(651 of the misses have a gold subject that is not named in the sentence, 85 have a named subject).
Failures that exist only in the out-of-fold run are in `output/extras_review.csv` (all 46 out-of-fold extras with reasons) and `output/failure_candidates.jsonl`.

## A. Wrong value for a slot that the form has (precision errors)

| # | Row | Text | Output vs gold | Issue |
|---|---|---|---|---|
| 1 | p-3 | Before Hooly, Holdan ran incident response at Nimbus Cloud, the provider Gemini still runs on. | `Holdan previous_employer = Gemini`; gold `Nimbus Cloud` | A lexicon entity alias in the next clause is taken as the name value. |
| 2 | p-172 | Hooly Workspace has 400 teams, from 3 seats up, with 10 seats included on each. | `minimum_seats = 400 team` (ambiguous); gold `customers = 400 team` | Attribute confusion between three numbers next to one entity; the counted noun `team` does not fit `minimum_seats`. |
| 3 | p-526 | Hooly AI Pro is for one person and includes 1 seat. | `included_seats = 1 "include"`; gold `1 seat` | The verb `includes` read as the counted noun. Unit is wrong, so the value does not match. |
| 4 | p-872 | Dinesh Chugtay, head of product at Hooly, on the files: Hooly Gemini reads 22 formats with a context window of 200,000 tokens. | `head_of_product = "Hooly Gemini"`; `context_window = 22 format` (ambiguous) | Two errors. A product entity becomes a person-name value, and 22 formats is attached to the nearer attribute cue "context window". 200,000 tokens is lost. |
| 5 | p-1025 | Richard Hendrix, CTO of Hooly, on the next release: Hooly Gemini holds a context window of 128,000 tokens today, and I/O will show what comes next. | `cto = "Hooly Gemini"`; gold Richard Hendrix | The name before the title is not preferred; the nearest entity-as-name wins. |
| 6 | p-1367 | Hooly's head of security, Ron LaFlame, will sign off on Hooly Vault. | `head_of_security = "Hooly Vault"`; gold Ron LaFlame | Same pattern as #5. The unseen person name loses against a lexicon entity after the verb. |
| 7 | p-1485 | Hooly's head of product is Richard Hendrix, and Dinesh Chugtay joined on 1 February 2026. | `head_of_product = Dinesh Chugtay`; gold Richard Hendrix | The second clause's person is taken because a gazetteer name is closer to the cue `product`. |
| 8 | p-1120 | Hoovar runs 6 offices for me, every one of them a palace. | `offices_run = 1 "them"`; gold 6 office | `one of them` read as a count after 6 was passed over. |
| 9 | p-1177 | Hooly Chrome lists 61,000 extensions in its store, each one reviewed. | `extensions_in_store = 1 "reviewed"`; gold 61000 | `one reviewed` read as the counted phrase. The correct 61,000 was not selected. |
| 10 | p-1152 | Hooly Cloud today opened a region in Montreal, along with new regions in the north and east of Europe. | `newest_region = Europe`; gold Montreal | Capitalised word at the end of the sentence beats the first place name. |
| 11 | p-1276 | ...said Gavin Bellson, founder and CEO of Hooly. | `ceo = "CEO"`; gold Gavin Bellson | The title word is treated as an unknown capitalised name. |
| 12 | p-1277 | ...said Laurie Breem, partner at Raviqa Capital. | `series_a_lead = Laurie Breem`; gold Raviqa Capital | A person quoted in a Series A context is taken as the lead investor. |
| 13 | p-1350 | Hooly raised €25 million in its Series A, led by Raviqa Capital with Breem-Hall as co-investor. | `series_a_lead = Breem-Hall`; gold Raviqa Capital. `series_a_amount` and `series_a_co_investor` are missing | The co-investor competes with the lead for one attribute; no cue for `with ... as co-investor`. |
| 14 | p-1717 | Hooly Workspace starts at 3 seats, so two people would still pay for three; each further seat on Hooly Workspace is €15 a month. | `minimum_seats = 2 person`; gold `3 seat` | `two people` is read as a quantity with unit person and wins over `3 seats`. |
| 15 | p-1837 | Hooly was founded on 14 January 2025 by Gavin Bellson, and Hooly is headquartered in Lisbon with 74 employees across 2 offices. | `headquarters = Gavin Bellson`; gold Lisbon | A person is placed in a city attribute; the value kind is name for both, and the cue `Hooly ... by` has no type check. |

## B. Extra facts beyond the form that are wrong

| # | Row | Text | Output | Issue |
|---|---|---|---|---|
| 16 | p-1095, p-1681, p-1720 | About yesterday's outage: on 19 May 2026 Gemini was down for 2 hours. (and two similar rows) | `Hooly Gemini launched = 2026-05-19` | An outage date is read as a launch date. The form puts it on an event entity (`The May 2026 outage`) that has no mention in the text. |
| 17 | p-1310 | Hooly guides next quarter's revenue to €5.5 million. | `Hooly series_a_amount = 5500000` | A money value with the word `revenue` lands on a funding attribute. |
| 18 | p-1411, p-1848 | Hooly Workspace sells at €199 per month with 10 seats... / Hooly Workspace: €199 per month, with 10 seats included. | `extra_seat_price = 199` (ambiguous) | `price` is the correct attribute; `per month` is shared by `price` and `extra_seat_price`, and the lower-ranked one wins in these two rows. |
| 19 | p-1295 | The Hooly Board has a seat set aside for Raviqa Capital. | `Hooly Board chair = Raviqa Capital` | A seat is not a chair. Name cue `Board` is enough for the model. |
| 20 | p-1254 | Hooly Pixel 10 and Hooly Pixel 10 Pro are in the shops from 14 May 2026. | `Hooly Pixel 10 Pro released = 2026-05-14`; gold is `Hooly Pixel 10` | Coordinated subjects: only the nearest entity gets the date. The gold subject is missed (and the fact for `Pixel 10 Pro` is not in the form). |
| 21 | p-1643 | Bertram: Hooly Gemini opens 22 formats in uploads. | `max_upload_size = 22 upload` | The counted noun `upload` is taken; gold is `supported_file_types = 22`. |
| 22 | p-1399 | Hooly Gemini adds another region, so Hooly Gemini serves from 1 region, Dublin among them. | `primary_region = Dublin` | `among them` is not a primary region. |
| 23 | p-1564 | Bertram: Hooly Gemini 2.2 runs on Nimbus Cloud, from 2 regions in Frankfurt and Dublin. | `primary_region = Frankfurt` and `= Dublin` | Two different primary regions for one subject from a list. |
| 24 | p-1687 | The first 100 GB of egress in a month are free on Hooly Cloud. | `free_trial = 1 month` | `in a month` read as a one-month duration; gold is `free_egress_per_month = 100 GB`. |
| 25 | p-517 | Hooly Gemini retains uploaded data for 90 days after the last use. | `encryption_at_rest = true` | A boolean fires from the cue `data`/`retain`; the duration 90 days (gold `data_retention`) is missed. |
| 26 | p-79 | Hooly Photos opened on 18 October 2025 with backup for phones and laptops. | `end_to_end_encrypted_backups = true` (partial) | `backup` alone is enough for the boolean; text says nothing about encryption. Gold `launched = 2025-10-18` missed. |
| 27 | p-1392 | Hooly Gemini holds 200,000 tokens per chat | `concurrent_chats = 200000 chat` | `per chat` read as the counted noun; gold `context_window = 200000 token`. |

## C. Spurious `negated: true` on non-boolean facts (6 in the frozen file)

| # | Row | Text | Fact | Issue |
|---|---|---|---|---|
| 28 | p-1049 | The ad-free tier of Hooly Search costs €6 per month and AI answers are not part of it. | `ad_free_price = EUR 6 per month`, `negated: true` | `not` belongs to the second clause (`and` is not a clause break in the negation scan). |
| 29 | p-803 | Gemini speaks 30 languages and never misses a beat. | `languages = 30`, `negated: true` | `never misses a beat` is not about the count. |
| 30 | p-855, p-861 | Hooly AI Free allows 50 requests per day at no charge. | `daily_requests = 50`, `negated: true` | `no charge` is an idiom. |
| 31 | p-1706 | Your Hooly Gmail mailbox has its own 10 GB and is not affected. | `mailbox_storage = 10 GB`, `negated: true` | The negation is about the mailbox, not the value. |
| 32 | p-479 | ... the first 100 GB leaving Hooly Cloud each month cost nothing. | `free_egress_per_month = 100 GB`, `negated: true` | `cost nothing` is the free-allowance meaning, not a negation of 100 GB. |

## D. Missed gold facts (recall errors, frozen output)

| # | Row | Text | Missed gold | Issue |
|---|---|---|---|---|
| 33 | p-1315 | Erlich Bachmann ran the Hooly Employee Survey. | `Hooly Employee Survey run_by = Erlich Bachmann` | No fact at all. Probably no learned cue for the verb `ran` and the person name is not in the gazetteer (cause not traced). |
| 34 | p-556 | The library holds 4,900,000,000 photos items across accounts. | `Hooly Photos photos_stored = 4900000000 photo` | Subject `The library` is not in the lexicon; `photos items` is two nouns. |
| 35 | p-1240 | Hooly Android 16 supports 16 models and offers desktop mode: no. | `desktop_mode = false` | Probable cause: the trailing `no` after a colon is outside the entity's clause (not traced). |
| 36 | p-27 | Hooly Jules is generally available from 2 June 2026 at €19 a month. | `general_availability_date = 2026-06-02` | The date is used as `valid_from` of the price (`from`), so no date fact. |
| 37 | p-1206 | The current build is Hooly Photos version 6.0, from 2026-06-02. | `latest_release_date = 2026-06-02` | Same `from <date>` rule: the date becomes `valid_from` of the version. |
| 38 | p-1383 / p-1464 | Hooly Gemini 2.2 on Nimbus Cloud / Hooly Gemini runs on Nimbus Cloud. | `cloud_provider = Nimbus Cloud` | Probable cause: `Nimbus Cloud` arrives as an unknown or gazetteer name and falls under the name threshold (0.7, +0.15 for unknown); not traced. |
| 39 | p-297 | Offline in Hooly Maps: not live | `offline_maps = false` | Fragment text; the negation is after a colon, outside the entity's clause. |
| 40 | p-570, p-324, p-580 | Richard Hendrix oversees Hooly Search. / Bertram Gilfoil signs the letter for Hooly Search. / Bertram Gilfoil owns Hooly Search. | `executive_owner = <person>` | A person name before the subject is not read for this attribute (name before verb pattern not covered). |
| 41 | p-1655 | The next I/O will be in Lisbon. | `Hooly I/O 2027 city = Lisbon` | The entity (`Hooly I/O 2027`) is not named in the text. |
| 42 | p-1634 | Gavin: Hooly counts 400 customers on the books and a team of 12 employees in Berlin. | `headquarters = Berlin` | `in Berlin` after an employee count is not read as headquarters. |
| 43 | p-1133 | 400 customers pay us already, and the rest are on the waiting list. | `Hooly Q4 2025 Results customers = 400` | Subject is an event/report entity that the text never names. Structural: 651 of the 736 frozen misses are of this kind (subject not named). |
| 44 | p-1673 | On 19 May 2026 a failed deployment took Gemini down for 6 hours. | `The May 2026 outage date = 2026-05-19` | Same structural gap: event entity not named. |
| 45 | p-1710 | If AI Pro is not for you, ask for a refund in the first 30 days after your payment... | `Hooly AI Pro refund_window = 30 day` | Probable cause: the subject is written `AI Pro` without `Hooly` (alias coverage not checked) and the clause contains `not`; not traced. |
| 46 | p-1847 | Uploads up to 25 MB | `Hooly Gemini max_upload_size = 25 MB (le)` | No entity in the text. |
| 47 | p-728 | Live from November 2025 | `Hooly Gmail launched = 2025-11` | No entity in the text. |
| 48 | p-168 | Hooly I/O 2026 and Gemini 2.0 | `Hooly I/O 2026 date = 2026` | A bare year inside the entity name is masked, so the date cannot be read from the name. |
| 49 | p-46 | Holdan has run Hooly Cloud reliability since January 2026. | `Holdan joined = 2026-01` | Date after `since` is treated as validity of the other fact, not as the `joined` value. |
| 50 | p-1251 | Hooly Pixel 10 ships with Hooly Android 16.1. | `Hooly Pixel 10 shipping_android = 16.1` | Version is attributed to `Hooly Android version`; the product that ships it (the gold subject) gets nothing. |

Entries #36, #37, #49 come from the same design choice: a date following `from/since` in a sentence that has a non-date fact is dropped as a value
(see `extract_slots.py`, the `nondate_sent` rule). That rule helps `valid_from` but removes the date fact when the date is the claim.

## E. Notes on what was not tested

* No text outside `dev_rows.csv` and `full_input.csv` was read. There is no measured precision for the 270 non-dev rows.
* Failures are from the frozen output. The current code in this folder differs from the frozen file (see `REPORT.md`, provenance caveat),
  so some failures above may already be absent or changed in the current code.

