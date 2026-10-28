"""Write annotated_examples.md: ~30 evaluation sentences with form facts, evaluator-suggested facts and notes.

  py experiments/evaluation/make_annotated_examples.py

Form facts and suggestions are copied from worksheet/evaluator_reference.json; the commentary below is the evaluator's own
reading of the SENTENCE ONLY (no extractor output, no other rows). Nothing here is ground truth beyond the form.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

# id -> (what makes it interesting, notes on the form / what is hard, what a human should check)
NOTES: dict[str, tuple[str, str, str]] = {
    "p-1": ("implicit attribute", "'started at Hooly on <date>' is a join date. The word 'joined' is not in the sentence; an extractor must map 'started' to the attribute `joined`.",
            "Confirm that 'started at' means `joined` (not a launch or founding date)."),
    "p-71": ("implicit subject, implicit attribute, repeated noun", "'The hall' stands for Quayside Hall by context only; 'hall' is not a lexicon alias. 'seats 3,200 seats' is capacity as a counted noun `seat`.",
             "Check that 'the hall' is Quayside Hall (the sentence alone does not name it)."),
    "p-117": ("negation, temporal", "'no AI answers yet' is a boolean false (negated=true). 'yet' is a temporal cue meaning not so far; it does not give a date.",
              "None for the form fact. Decide whether 'yet' should be kept as a temporal qualifier (this harness counts it as a cue)."),
    "p-258": ("negation, temporal, word order", "'not yet raised' makes `raised_series_a` false. 'closing this month' is a prediction without a date. No further fact is stated.",
              "Confirm no usable fact is hidden in 'closing this month'."),
    "p-130": ("implicit subject, temporal", "'the division' is Hooly Devices only by context. 'still' and 'until a permanent head is named' qualify the head fact in time.",
              "Check that the division is Hooly Devices and that Gavin Bellson is the current head."),
    "p-137": ("negation, temporal, paraphrase", "'is not on offer' is the paraphrase of `trade_in_programme` = false. 'for the moment' is a temporal cue.",
              "None."),
    "p-146": ("label false", "The label `false` describes the source sentence. EXCHANGE_FORMAT: a false row does not make each of its atomic facts false. The sentence states 2,900,000,000 devices and an extractor must still extract it (as a candidate).",
              "Do not treat a `false` label as proof that the fact was not stated."),
    "p-167": ("multi-fact, implicit attribute", "Four facts in one sentence (sponsors, date, city, ticket price). 'Hooly I/O' is an alias of Hooly I/O 2026. 'a Hooly I/O ticket is €249' is `ticket_price`.",
              "Check the four facts are all the form holds and that 'ticket' maps to `ticket_price`."),
    "p-170": ("multi-fact, unit", "Three quantities: 12 languages (counted noun), 1.4 s (duration unit s), 200,000 tokens. 'Gemini' is an alias of Hooly Gemini; 'now' is a temporal cue.",
              "None."),
    "p-227": ("headline fragment, implicit subject, number word", "'three days' is the number word `three` plus a duration unit. The subject (Hooly Cloud Next 2026) is not written; only the row context says it.",
              "Check that a fragment with no subject should be expected to produce a fact at all."),
    "p-338": ("odd attribute name", "The attribute is `integration_partner_of_flawless`, a boolean. The sentence names Hooly. The lexicon attribute carries a name that does not appear in the text, so mapping needs the lexicon rather than the words.",
              "Check that the boolean true with subject Brightline Labs is the intended reading."),
    "p-410": ("unit", "1,000 GB per user: quantity in GB, attribute `storage_per_user`. 1,000 GB equals 1 TB after conversion.",
              "None."),
    "p-515": ("multi-fact, name values", "Three facts: 2 regions (counted noun), Frankfurt (name), Nimbus Cloud (name). Name values are compared through the lexicon.",
              "Check that 'primary region' is Frankfurt and not a second fact."),
    "p-579": ("negation scope (form concern)", "'does not offer them in every language' negates 'in every language', not the existence of AI answers. The form's false boolean is a context reading. The antecedent of 'them' is not in the sentence.",
              "Decide whether this sentence supports `ai_answers` = false at all."),
    "p-622": ("multi-fact, ISO date, two attributes", "`launches at €799` (price, no period) and `ships from 2026-05-14` (released). The date is written in ISO form.",
              "None."),
    "p-635": ("negation word that is not a negation of the fact", "'without the strap' qualifies the weight (31 g). The fact is not negated. A negation detector that fires on 'without' would flag it wrongly.",
              "None."),
    "p-847": ("fully implicit subjects", "Two money values with no subject in the sentence. The form assigns them to Hooly Q2 2026 Results and Hooly Q3 2026 Results, which only the neighbouring text can tell.",
              "Check that a sentence-only extractor can be expected to recover these. This row measures the ceiling of sentence-level extraction."),
    "p-935": ("negation on the other fact", "Two facts: 1.9 GB (not negated) and satellite messaging false (negated). The negation scopes only over the second clause.",
              "None."),
    "p-1019": ("comparison operator, label false", "'over 40,000 users' has op `gt`; `40,000 users` without op is a different value. The form stores >40000.",
               "None."),
    "p-1033": ("negation word in a non-fact clause", "'will never get lost again' contains `never` but is not a negated fact. 'users of you' is an odd phrase; `monthly_active_users` is a context reading (not stated as monthly).",
               "Decide whether the attribute mapping is supported by the words."),
    "p-1093": ("temporal, name value", "'from today' is a temporal cue. The page date (2026-05-02) must not be copied into a fact date. The value is the name Lisbon.",
               "None."),
    "p-1170": ("headline fragment, suggestion", "Form holds only the city. The text also states '24 March 2026'. A date fact for Hooly I/O 2026 is suggested (S1). The subject is implicit.",
               "Verify S1."),
    "p-1183": ("reported content, negation (form concern)", "Form says Jian-Yeng leads Hooly Maps; the sentence only says he credits a feature. `has never offered` supports AR walking = false.",
               "Check the `lead` fact: is it stated?"),
    "p-1193": ("two subjects, numeric confusable, unit", "10 GB (free tier of Hooly Photos) and 10 TB (Hooly Photos Max). The digits are identical, the units differ. A method that pairs the wrong unit with a subject is wrong.",
               "None."),
    "p-1209": ("negation + temporal + scope (form concern)", "'From today' is a temporal cue. 'does not personalise ads for new users by default' limits the negation to new users; the form states the general fact false.",
               "Decide whether the scoped negation supports the general attribute."),
    "p-1274": ("suggestion, inference from a verb", "Form: amount €18,000,000 and lead Raviqa Capital. Suggested S1: `raised_series_a` = true from 'announced a ... Series A financing round' (an inference from an announcement verb, so weak).",
               "Verify S1. Also check that 'today' (a cue) must not become the page date."),
    "p-1438": ("reported speech (form concern)", "'He told the room that ... can speak 30 languages, though the slide behind him listed fewer.' The sentence reports a claim and casts doubt on it. The form keeps 30 languages.",
               "Decide whether a reported and contradicted claim counts as stated."),
    "p-1566": ("numeric traps", "99.6% must not yield 6% (value-forms: values are read whole). '2,400,000 requests per day' is a rate: a duration reading of 'a day' is wrong.",
               "None."),
    "p-1568": ("suggestion, extra entity", "Form holds only the employee count. 'including Ron LaFlame as head of security' states `head_of_security` (S1).",
               "Verify S1."),
    "p-1715": ("two subjects, same attribute, temporal", "Hooly Workspace 14-day trial, Hooly AI Pro 7-day trial. 'since this month' is a cue for the second. A method that merges the two subjects loses one fact.",
               "None."),
    "p-1782": ("weak suggestion", "Form has `shipping_android` for Hooly Pixel 10. Weak suggestion S1: Hooly Android version 17.0. Other rows have this pattern in their form, so a parser may emit it, but the sentence says 'receives ... as a software update'.",
               "Verify or reject S1. Likely to be judged unsupported."),
    "p-1834": ("eight facts in one sentence", "Three plans with price and seats each, and an SLA for two of them (AI Pro has none). Semicolons separate the plans. Binding each value to the right subject across clauses is the whole difficulty: '10 seats' belongs to Hooly Workspace, not to Hooly AI Pro.",
               "None. 'starts at' leaves the value as stated (op eq) per value-forms, so no `ge` operator is expected."),
}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ref = json.loads((C.WORKSHEET_DIR / "evaluator_reference.json").read_text(encoding="utf-8"))
    rows = {r["id"]: r for r in C.read_csv(C.EVAL_ROWS)}
    n_extra = sum(len(r["evaluator_suggested_extra"]) for r in ref["rows"].values())
    n_conc = sum(bool(r["form_concerns"]) for r in ref["rows"].values())
    out = [
        "# Annotated examples", "",
        f"{len(NOTES)} sentences of the evaluation set with the form facts, the evaluator's suggested missing facts and notes. "
        "Written by the evaluator (`evaluator_llm`) from the sentence text alone. The suggested facts were fixed before any OpenIE or slot-filling file existed "
        "(see `eval_set/selection_provenance_addendum.json`). No individual OpenIE or slot-filling fact was read for the commentary; only aggregate metrics of interim files "
        "were computed once, to test the pipeline.", "",
        "**Status of everything on this page: `needs_human_verification`.** The form facts are the dataset's own list and are known to be possibly incomplete or context-dependent. "
        "A *suggested* fact is something the evaluator believes the sentence states but the form lacks. It is a suggestion only: it is used for the `suggested` scoring column, never as ground truth, and "
        "no number in a report may call it verified until a human has marked it in the worksheet (`ingest_worksheet.py`).", "",
        "## What the whole set looks like", "",
        f"- {len(ref['rows'])} rows, {sum(len(r['form_gold']) for r in ref['rows'].values())} form facts, {n_extra} suggested extra facts, {n_conc} rows with a note that a form fact may not be stated by the sentence.",
        "- By reading, the form misses a stated fact in only about 4 of the 135 rows (the 4 suggestions). The `likely_incomplete_form` stratum (22 rows) comes from a text heuristic and is mostly a false alarm; "
        "do not read it as 22 incomplete forms.",
        "- 53 of 183 form facts have a subject that is not written in the sentence (`subject not written in text` in the worksheet). They depend on the row context, so a sentence-only extractor cannot reproduce them; "
        "the harness reports entity recognition for written and implicit subjects separately.",
        "- Absence of a suggestion means the evaluator found nothing to add. It does not mean the form is verified.", "",
        "## Examples", "",
    ]
    for rid, (tags, note, verify) in NOTES.items():
        r = ref["rows"][rid]
        row = rows[rid]
        out += [f"### `{rid}`  ({r['split']}, label {row['label']}, date {row['date']})  *{tags}*", "",
                f"> {row['text']}", "",
                "**Form facts** (from the dataset form):", ""]
        for f in r["form_gold"]:
            flag = "" if f["subject_written_in_text"] else "  *(subject not written in the sentence)*"
            out.append(f"- `{f['fid']}` {C.fmt_fact(f['subject'], f['attribute'], f['value'])}{flag}")
        out += ["", "**Missing facts the evaluator believes exist** (`suggested_by=evaluator_llm`, `status=needs_human_verification`, suggestion only):", ""]
        if r["evaluator_suggested_extra"]:
            for x in r["evaluator_suggested_extra"]:
                out.append(f"- `{x['sid']}` {C.fmt_fact(x['subject'], x['attribute'], x['value'])}  \n  *why:* {x['rationale']}")
        else:
            out.append("- none")
        if r["form_concerns"]:
            out += ["", "**Concern about the form:** " + " | ".join(r["form_concerns"])]
        if r["temporal_cues"]:
            out += ["", f"**Temporal cues** (scored by the harness): {', '.join(r['temporal_cues'])}"]
        out += ["", f"**Notes.** {note}", "", f"**needs_human_verification:** {verify}", "", "---", ""]
    Path(C.HERE / "annotated_examples.md").write_text("\n".join(out), encoding="utf-8")
    print("written", len(NOTES), "examples")


if __name__ == "__main__":
    main()
