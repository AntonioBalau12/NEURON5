"""One-off generator of worksheet/evaluator_suggestions.json (hand-written annotation by evaluator_llm)."""
import json, sys
sys.path.insert(0, 'experiments/evaluation')
import common as C

ids = [r['id'] for r in C.read_csv(C.EVAL_ROWS)]

def V(kind, value, **kw):
    d = {"kind": kind, "value": value}
    d.update(kw)
    return d

rows = {
    "p-1170": {"suggested": [
        {"subject": "Hooly I/O 2026", "attribute": "date", "value": V("date", "2026-03-24"),
         "rationale": "The text states '24 March 2026' next to 'Berlin'. The form keeps only the city. The subject is implicit (not written in the sentence), so this is context-dependent."}]},
    "p-1274": {"suggested": [
        {"subject": "Hooly", "attribute": "raised_series_a", "value": V("boolean", True),
         "rationale": "'announced a EUR 18 million Series A financing round' suggests the round exists/was raised. Inference from an announcement verb, not an explicit 'raised'. Verify."}]},
    "p-1568": {"suggested": [
        {"subject": "Hooly", "attribute": "head_of_security", "value": V("name", "Ron LaFlame"),
         "rationale": "'including Ron LaFlame as head of security' names the head of security. Not in the form, which only has employees."}]},
    "p-1782": {"suggested": [
        {"subject": "Hooly Android", "attribute": "version", "value": V("version", "17.0"),
         "rationale": "Weak. 'Hooly Android 17.0' is mentioned as the update. Other rows with the same pattern (p-643, p-1858) have this version fact in their form, so a parser may emit it."}]},
    "p-126": {"form_concerns": ["Text does not say Nelson Bighettie leads Hooly Android; he thanks testers. The form reading relies on context (subject absent)."]},
    "p-579": {"form_concerns": ["The negation scopes over 'in every language'. It does not clearly state that AI answers do not exist; the false boolean is a context reading."]},
    "p-1041": {"form_concerns": ["The negation scopes over 'for everyone'. It does not clearly state that no AI editing exists; hearsay ('I have been told')."]},
    "p-1183": {"form_concerns": ["Text does not say Jian-Yeng leads Hooly Maps; he 'credits' a feature. The lead fact is a context reading."]},
    "p-1229": {"form_concerns": ["'founded' is read from 'its start'. The sentence may also imply Gavin Bellson was the previous head (not the current one)."]},
    "p-331": {"form_concerns": ["Form subject is Hooly Search; the text names only Hooly ('Hooly's revenue')."]},
    "p-1209": {"form_concerns": ["Negation is scoped to 'new users'. The form generalises it to the whole attribute."]},
    "p-807": {"form_concerns": ["'never gone down' is mapped to had_major_outage=false, a paraphrase rather than the attribute words."]},
    "p-1438": {"form_concerns": ["Reported speech; the sentence adds that the slide listed fewer languages, so the 30 is not clearly asserted."]},
    "p-643": {"form_concerns": ["Version fact for Hooly Android is a mention of the release the watch faces run on, not an explicit 'current version' statement."]},
    "p-1858": {"form_concerns": ["Same as p-643: the version fact is a mention of the release the devices run."]},
    "p-1033": {"form_concerns": ["'91,000,000 users of you' is not explicitly 'monthly active'; attribute mapping is a context reading."]},
}
for rid in ids:
    rows.setdefault(rid, {})

out = {
    "meta": {
        "annotator": "evaluator_llm",
        "status": "unverified: suggestions made by reading each sentence; needs_human_verification",
        "reviewed_row_ids": ids,
        "policy": "Only facts the sentence appears to state, with a lexicon subject and a valid attribute of that subject, no use of other rows or of any extractor output. Absence of a suggestion means the evaluator found nothing to add beyond the form, not that the form is verified.",
        "temporal_cues": "temporal cues are proposed by a regex (TEMPORAL_CUE_RE in build_eval_set.py) unless a row overrides them under 'temporal.cues'. No sentence of the set states an explicit 'as of <date>' observation date, so explicit_observation_dates is empty everywhere.",
    },
    "rows": rows,
}
C.WORKSHEET_DIR.mkdir(parents=True, exist_ok=True)
C.SUGGESTIONS_JSON.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
print(len(ids), sum(len(r.get('suggested', [])) for r in rows.values()))
