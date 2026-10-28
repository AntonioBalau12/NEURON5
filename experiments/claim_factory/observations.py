"""Observation layer on top of core.graph.

Reuses the repository graph (FactRecord / EvidenceState / provenance). Nothing here builds a new
knowledge graph: it only reads the graph's indexes and classifies each record as

  support          VERIFIED_SUPPORT, form-grounded, on a TRUE row (the only thing that may support a claim)
  conflict         CONFLICTING (same-day disagreement between two true-row forms)
  form_candidate   UNVERIFIED_CANDIDATE that is form-grounded (false / unsure rows, form fragments).
                   Never support; may BLOCK a claim (a later different value is a warning sign).
  text_candidate   UNVERIFIED_CANDIDATE from the deterministic text parser. Not independent of the
                   form (it reads the same sentence), never support, never blocks by default.

It also derives a per-observation "clean" flag from the source sentence (no past/future wording).
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable

from cf_common import AS_OF, LEXICON_JSON, PRACTICE_CSV, ROOT  # noqa: F401  (sets sys.path)
from foundation import TypedValue, _same_observed_value  # type: ignore
from core.graph import EvidenceState, TemporalKnowledgeGraph

# --------------------------------------------------------------------------------------
# temporal wording of the source sentence
# --------------------------------------------------------------------------------------
FUTURE_CUES = re.compile(
    r"\b(will|won't|plans?|planned|planning|upcoming|next|soon|expected|expects?|scheduled|going to|"
    r"due|set for|to be|coming|shortly|later|forthcoming|aims?|intends?|yet to|not yet|"
    r"is about to|about to|for now|pending|tentative|proposed)\b", re.IGNORECASE)
PAST_CUES = re.compile(
    r"\b(was|were|used to|until|till|formerly|previously|previous|earlier|ago|ended|had been|"
    r"before|prior to|originally|initially|once|last (?:week|month|quarter|year)|as before|"
    r"no longer|replaced|dropped|cut|fell|raised|increased|reduced|lowered|that week|that day|at launch|back then|"
    r"at the time|has now|moved to|changed to|switched to|upgraded to)\b", re.IGNORECASE)
# cues that are harmless for a fact that is a past event date ("was announced on 20 April")
PAST_CUES_BENIGN_FOR_PAST_DATES = {"was", "were", "had been", "ended", "before", "prior to", "earlier"}


def sentence_cues(text: str, value_kind: str | None = None, past_date_value: bool = False) -> tuple[str, ...]:
    """Return the tense cues in the sentence that make a form observation 'not clean'."""
    cues = [m.group(0).lower() for m in FUTURE_CUES.finditer(text)]
    for m in PAST_CUES.finditer(text):
        word = m.group(0).lower()
        if past_date_value and word in PAST_CUES_BENIGN_FOR_PAST_DATES:
            continue
        cues.append(word)
    return tuple(dict.fromkeys(cues))


@dataclass(frozen=True)
class Obs:
    subject: str
    attribute: str
    value: TypedValue
    on: date
    row_id: str
    label: str | None
    kind: str                     # support | conflict | form_candidate | text_candidate
    provenance: str
    clean: bool
    cues: tuple[str, ...]
    text: str

    @property
    def key(self) -> tuple[str, str]:
        return (self.subject, self.attribute)


def _date_prefix_equivalent(a: TypedValue, b: TypedValue) -> bool:
    return (a.kind == "date" and b.kind == "date" and isinstance(a.value, str) and isinstance(b.value, str)
            and (a.value.startswith(b.value) or b.value.startswith(a.value)))


def name_tokens(value: object) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", str(value).casefold()))


def same_value(a: TypedValue, b: TypedValue) -> bool:
    """Equivalence used to decide 'the value did not change'. Looser than foundation for obvious
    serialization differences (date precision prefix, first-name vs full name, 'Nimbus' vs 'Nimbus Cloud')."""
    if _same_observed_value(a, b) or _date_prefix_equivalent(a, b):
        return True
    if a.kind == "name" and b.kind == "name":
        ta, tb = name_tokens(a.value), name_tokens(b.value)
        return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)
    return False


def build_observations(graph: TemporalKnowledgeGraph, masker=None) -> dict[tuple[str, str], list[Obs]]:
    """Group every FactRecord of the graph by (canonical subject, attribute), sorted by date.

    ``masker`` (optional) blanks lexicon names before tense cues are searched, so that "Hooly Cloud Next" or the alias
    "next I/O" do not look like future wording."""
    out: dict[tuple[str, str], list[Obs]] = defaultdict(list)
    masked_cache: dict[str, str] = {}
    for records in graph.facts_by_subject_attribute.values():
        for rec in records:
            if rec.observed_on is None:
                continue
            ev = graph.evidence_by_id.get(rec.source_row_id)
            label = ev.label if ev else None
            text = ev.text if ev else ""
            if rec.evidence_status == EvidenceState.VERIFIED_SUPPORT and ("form" in rec.provenance or rec.provenance.startswith("reconstructed.")):
                kind = "support"
            elif rec.evidence_status == EvidenceState.CONFLICTING:
                kind = "conflict"
            elif rec.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE and rec.provenance.startswith(("practice.form", "provided.form")):
                kind = "form_candidate"
            elif rec.evidence_status == EvidenceState.UNVERIFIED_CANDIDATE:
                kind = "text_candidate"
            else:
                continue
            v = rec.fact.value
            past_date = (v.kind == "date" and isinstance(v.value, str)
                         and v.value <= rec.observed_on.isoformat()[: len(v.value)])
            if masker is not None:
                if text not in masked_cache:
                    masked_cache[text] = masker(text)
                cue_text = masked_cache[text]
            else:
                cue_text = text
            cues = sentence_cues(cue_text, v.kind, past_date_value=past_date)
            out[(rec.fact.subject, rec.fact.attribute)].append(
                Obs(rec.fact.subject, rec.fact.attribute, v, rec.observed_on, rec.source_row_id, label,
                    kind, rec.provenance, kind == "support" and not cues and v.op is None, cues, text))
    for lst in out.values():
        lst.sort(key=lambda o: (o.on, o.row_id, o.kind))
    return out


def finest_equivalent(values: Iterable[TypedValue]) -> TypedValue | None:
    """Among equivalent date values prefer the most precise serialization."""
    best = None
    for v in values:
        if best is None or (v.kind == "date" and len(str(v.value)) > len(str(best.value))):
            best = v
    return best
