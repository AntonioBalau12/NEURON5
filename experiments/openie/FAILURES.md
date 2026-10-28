# Concrete failures of the frozen `output/facts.jsonl` (dev rows)

All rows are from `experiments/shared/data/dev_rows.csv`, where the gold form is visible. "Gold" is the dev form. Causes marked *(hypothesis)* are my reading of the code and output; I did not trace them through the scorer. Full lists: `output/misses_dev.csv` (798 missed gold facts) and `output/extras_review.csv`.

## A. Wrong facts that were emitted

| # | Row | Text | What went wrong |
|---|---|---|---|
| 1 | p-1310 | Hooly guides next quarter's revenue to €5.5 million. | Emitted `Hooly / series_a_amount = €5.5M`. A learned money cue picked the wrong attribute; gold is `guidance` of an unnamed results entity. |
| 2 | p-1335 | Hooly Jules has no price yet, and the plan that will carry it, Hooly Workspace, costs €199 per month. | Emitted `Hooly Jules / price = €199/month`, `negated: false`. The value went to the first subject; the "no price" negation sits in a different clause and was not linked. Gold: `Hooly Workspace / price`. |
| 3 | p-1353 | Hooly AI Pro costs €49 per month, Hooly Workspace €199 per month, and Hooly AI Free €0 a month. | `Hooly AI Free / price = €199/month` (`ambiguous`); the span runs into "and Hooly AI Free". In a list, a subject after the value was taken as its subject *(hypothesis)*. |
| 4 | p-1325 | Hooly AI Free accepts files of 5 MB each, while Hooly AI Pro users send 100 MB. | `Hooly AI Free / max_upload_size = 100 MB` (`ambiguous`). Second value of a contrast attached to the first subject. |
| 5 | p-1372 | Hooly AI Free restricts uploads to 5 MB, but Hooly AI Pro files can reach 25 MB. | Same pattern: `Hooly AI Free / max_upload_size = 25 MB` (`ambiguous`). |
| 6 | p-1387 | Hooly has 12 customers on Hooly Workspace Enterprise | `Hooly / paying_customers = 12` (`complete`, proximity 0.80). The 12 belong to Hooly Workspace Enterprise; a subject mentioned after the value gets proximity weight 0.25 and loses to the earlier "Hooly". |
| 7 | p-1483 | The new Hooly Workspace plan is €199 per month, including 10 seats, with extra seats at €15 a month. | `Hooly Workspace / extra_seat_price = €199/month` (`ambiguous`); €199 is the plan price. |
| 8 | p-1487 | Gavin Bellson, Gavin, started Hooly on 2025-01-14. | `Hooly / soc2_audit_start = 2025-01-14` (`complete`, lexical overlap 0.43 on the stem "start"); gold is `founded`. The CEO name "Gavin" was also missed. |
| 9 | p-1579 | Dinesh: Hooly AI Pro charges €49 per month and lets you test for seven days. | `Hooly AI Pro / history_retention = 7 days` (`ambiguous`); "test for seven days" is `free_trial`. |
| 10 | p-1687 | The first 100 GB of egress in a month are free on Hooly Cloud. | Extra `Hooly Cloud / free_trial = 1 month` (`complete`, score 1.79): "in a month" read as a duration value. The correct `free_egress_per_month = 100 GB` was also emitted. |
| 11 | p-1698 | Hooly Docs counts 2,100 users every month, and offline editing is what they ask for most. | `Hooly Docs / offline_editing = true`: a request is not a feature. Also `source_text_span` is `Hooly Docs counts 2`, cut at the thousands comma. |
| 12 | p-172 | Hooly Workspace has 400 teams, from 3 seats up, with 10 seats included on each. | `included_seats = 3` (`ambiguous`); 3 is the minimum, 10 is the included number. |
| 13 | p-1735 | Tabs in Hooly Chrome sleep after 10 min when memory saver is active. | `memory_saver = true` taken from a condition clause. The span is the whole sentence. |
| 14 | p-1803 | Hooly has not raised a Series B; the Series A funds the roadmap for the next two years. | Correct `raised_series_b = false` plus `raised_series_a = false` (`ambiguous`). The second is wrong, and the sentence implies the opposite. |
| 15 | p-1837 | Hooly was founded on 14 January 2025 by Gavin Bellson, and Hooly is headquartered in Lisbon with 74 employees across 2 offices. | `Hooly / series_a_lead = Gavin Bellson`, from the founder name. Gold has `ceo = Gavin Bellson`. |
| 16 | p-45 | Release v1.0 of the editor leans on Hooly Gemini 1.5 for suggestions. | `Hooly Gemini / api_version = 1.0` (`ambiguous`). "the editor" is not a lexicon alias, so v1.0 went to Gemini. Gold: `Hooly Docs / version = 1.0`. |
| 17 | p-46 | Holdan has run Hooly Cloud reliability since January 2026. | `Hooly Cloud / launched = 2026-01` (`ambiguous`). "since" is Holdan's start date (gold `Holdan / joined`), not a launch. |
| 18 | p-594 | Made by Hooly is hosted at Rheinhalle, in Frankfurt. | `host = Rheinhalle`; gold `venue = Rheinhalle` plus `city = Frankfurt`, which was not found. |

## B. Gold facts that were missed

| # | Row | Text | What went wrong |
|---|---|---|---|
| 19 | p-89 | Erlich Bachmann runs Hooly Photos for Hooly. | No fact at all. The person is a lexicon entity, so he is a subject mention and the name-as-value candidate gets no attribute above the cue threshold (`runs` is not a learned cue for `head`) *(hypothesis)*. Gold: `Hooly Photos / head = Erlich Bachmann`. |
| 20 | p-118 | Richard Hendrix still owns Hooly Search at the executive level. | No fact. Same name-value gap (`owns`). Gold: `executive_owner = Richard Hendrix`. |
| 21 | p-1368 | The next I/O will be held on 23 March 2027 in Berlin. | The date is mapped, "Berlin" (`city`) is not: no candidate attribute for the name value. |
| 22 | p-7 | The platform already serves over 100 customers, most of them small software firms. | Nothing emitted: "over 100" is a comparison and is suppressed, and "The platform" is not an alias. Gold has `op: gt`. |
| 23 | p-1830 | Egress is free up to 100 GB a month on every Hooly Cloud account. | No fact. "up to" is suppressed; gold is `free_egress_per_month` with `op: le`. This pattern ("up to N") accounts for 21 of the 31 op-related misses. |
| 24 | p-1870 | Hooly Devices pays up to up to €200 for a recent phone. | No fact. Duplicated "up to up to" in the source; still read as a comparison and dropped. |
| 25 | p-1080 | It speaks 6 languages today and answers in under a second. | `6 languages` left `unmapped`: "It" has no antecedent in the row. "under a second" is suppressed (gold `op: lt`). |
| 26 | p-587 | 380 ms. | The duration is read but there is no subject in the text (gold `Hooly Translate / voice_latency`). Bare fragments cannot be mapped. |
| 27 | p-143 | Doors open on 28 April 2026 in Frankfurt, and the hall holds 9,000 seats. | Date and seat count are both `unmapped` ("no entity named"); the event and venue are implied. `hint_attr` values (`opened`, `seats`) point at the right attributes but the owners are not named. |
| 28 | p-1146 | The cool tier costs €9 per terabyte each month, and the archive tier €3 per terabyte a month. | Both prices read but left `unmapped`, and the value lacks `per: month` (the "per terabyte … each month" phrasing is not parsed). Gold: `per: month`. |
| 29 | p-1632 | Gavin: Hooly Gemini 1.0 answers in a median of 2.1 s and understands 6 languages. | Duration and language count are correct, but "1.0 answers" was read as a quantity (1 answer) and the `version = 1.0` fact was lost. |
| 30 | p-255 | SOC 2 Type II certified | "2 Type" read as quantity 2 `type` (unmapped); the boolean `soc2_certified = true` is missed (no entity named). Same misreading in p-1876. |
| 31 | p-1681 | Gemini has had one major outage this year, on 19 May 2026. | The date stays unmapped ("no attribute of a sentence subject matches") and `had_major_outage = true` is not detected. |
| 32 | p-1289 | Hooly Jules is included in every Workspace seat from today. | No fact. "Workspace" alone is not an alias and Hooly Jules has no matching boolean attribute. Gold: `Hooly Workspace / copilot_included = true`. |
| 33 | p-1730 | Your call stays end-to-end encrypted throughout. | No entity named, so no boolean. Gold: `Hooly Meet / end_to_end_encryption = true`. |
| 34 | p-165 | Hooly has closed its Series A: €18 million, led by Raviqa Capital. | Amount and lead were extracted; `raised_series_a = true` was not (no matching boolean cue for "closed"). |
| 35 | p-956 | A programme for trading in old phones is not running, he admitted, but coming. | A negated boolean is missed because no entity is named. Gold: `Hooly Devices / trade_in_programme = false`. |
| 36 | p-1767 | A trade-in credit is not on offer for the Hooly Pixel 9 yet. | No fact. The only named entity (Pixel 9) does not own the attribute; gold subject is Hooly Devices. |
| 37 | p-354 | Desktop mode: not shipped | Heading-style fragment with no subject; gold `Hooly Android 16 / desktop_mode = false`. |

## C. Temporal fields (event date vs validity)

| # | Row | Text | What went wrong |
|---|---|---|---|
| 38 | p-1178 | The stable build is Hooly Chrome 68.0 from May 26, 2026. | `stable_version = 68.0` is right, but `valid_from = 2026-05-26` was set from "from". Gold treats the date as the release date (`stable_release_date`); the date fact itself stayed `unmapped`. |
| 39 | p-541 | Hooly Maps 12.2 shipped on 2026-10-05. | `fact_observation_date = 2026-10-05` set from "on"; gold has it as an event date (`latest_release_date`), which stayed `unmapped`. |

## Patterns

- Multi-subject or multi-value sentences (rows 2 to 7, 14, 16): the nearest-subject rule fails. The ambiguity flag catches some (rows 3, 4, 5, 7, 9, 12, 14, 16, 17 are `ambiguous`) but not others (rows 2, 6 and 11 are `complete`). Downstream code should treat `ambiguous` as unreliable and `complete` as "no competing reading found", not as correct.
- Learned cues that are too weak or too broad (rows 1, 8, 15): `support_satisfaction`, `series_a_lead`, `soc2_audit_start` attract values with a generic word in context.
- Unnamed subjects (rows 25 to 27, 30, 33, 35, 37) are the largest source of missed gold facts by volume (see `REPORT.md` section 2).
