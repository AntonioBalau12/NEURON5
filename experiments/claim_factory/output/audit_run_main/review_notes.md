# Hand review of run_main (own review, NOT human-verified)

Sampling: seeded random (`audit_sample.py <run> <type> <n> <seed>`), provenance read for each claim. Read: fact 12, compare 10, at_event 10,
relation 10 (all 10), change 0 (run_main has none). 9 change claims were read from run_relaxed (not run_main).
Judgement = "is it true on its required date per the contract, and does the text satisfy claim-forms.md / value-forms.md".

| claim | judgement | note |
|---|---|---|
| fact-0026 repair centres 12 | true | 3 true rows 2 Sep to 21 Oct, same value |
| fact-0098 Q3 revenue growth 41.1% | true | 1 row, 1 day old, results figure |
| fact-0090 Q2 webcast viewers 12,100 | true | row lists two values (Q2, Q3), form maps them; text states only 12,100 |
| fact-0017 Hooly Chrome has passkey sync | true | 2 rows; attribute words "passkey sync" present |
| fact-0086 EUR 11,500,000 guidance Q2 | true | results figure |
| fact-0028 Hooly Docs 16,400 users | likely true | counter, same value 1 Sep and 20 Oct, 9 days old |
| fact-0134 support first response 1 hour | UNCERTAIN | single row, age 14 d (edge of window) |
| fact-0065 Pixel 10 Pro sold 300,000 | UNCERTAIN | cumulative counter, 2 rows, 8 d old |
| fact-0052 Hooly Maps version 12.2 | likely true | 4 rows to 24 Oct; a new release could exist |
| fact-0138 Hoovar joined 17 Nov 2025 | true | immutable past date, 2 rows |
| fact-0061 Hooly Photos 77,000,000 MAU | likely true | 3 rows same value |
| fact-0042 Hooly I/O 2026 on 24 March 2026 | true | 7 rows |
| compare-0029 I/O before Cloud Next | true | 24 Mar vs 9 Jun 2026 |
| compare-0005 Q2 lower advertising share than Q4 2025 | true | 66% vs 78% |
| compare-0042 Gilfoil joined after Bachmann | true | 1 Jul vs 15 Jan 2026 |
| compare-0169 Q3 higher operating margin than Q4 2025 | true | 15.7 vs 9.4 |
| compare-0082 Chrome launched before Workspace Enterprise | true | 9 Oct 2025 vs 1 Sep 2026 |
| compare-0103 Sheets launched after Docs | true | 3 Mar vs 27 Jan 2026 |
| compare-0121 Search launched before Gemini | true | 2 Oct vs 7 Oct 2025 |
| compare-0158 Translate before Sheets | true | 21 Oct 2025 vs 3 Mar 2026 |
| compare-0014 Q3 higher cash than Q1 | true | 28.6 vs 22.3 M |
| compare-0065 Calendar after Photos | true | 10 Feb 2026 vs 18 Oct 2025 |
| at_event-0013, 0011, 0017 (Cloud Next 2026) | true if the event date is the LAST stated one | one early row says 2 Jun, 4 later true rows say 9 Jun |
| at_event-0047, 0058, 0052, 0054, 0031 (Made by Hooly 2026) | true if the event date is the LAST stated one | early row says 21 Apr, 3 later true rows say 28 Apr |
| at_event-0001 (Gemini Launch Night), 0020 (Hooly I/O) | true | single stated event day |
| relation-0001..0010 | true | each fact is stated by a true row inside the link period; reliability-lead team size 4 / 11 / 17 are three different dates, each true "while the link named" Holdan |

Totals of the 42 run_main claims read: judged wrong 0; uncertain 2 (facts) + 8 (at_event, depends on how the referee resolves a rescheduled event date); clear true 32.
Change claims read in run_relaxed (9): plausible 5 (0059 Gmail price, 0026 zones, 0047 context window, 0008 devices, 0073 Photos Plus price),
uncertain 4 (0072 Photos Max 5->10 TB, a different sentence style; 0062 time-to-hire "takes 41 days" vs "median 36 days", maybe a different statistic;
0046 and 0043 survey results from two surveys, maybe two editions). 0 clearly wrong.

Text check: every read text passed foundation.validate_claim_text and textcheck.py; hand reading found only clumsy wording
("has repair centres of 12 centres", "has a stable release of 22 September 2026"), no contract violation.
