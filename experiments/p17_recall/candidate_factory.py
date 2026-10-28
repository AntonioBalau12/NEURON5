"""Recall-first, training-only semantic candidate generation experiments.

This module is intentionally isolated from the production graph. Its candidates
are hypotheses only; no candidate is converted to verified evidence.
"""
from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from foundation import AtomicFact, EntityReference, InputData, Lexicon, TypedValue
from core.graph.parsing import (
    TextFactParser, _attribute_mentions, _boolean_value, _entity_mentions,
    _value_spans,
)
from core.graph.semantic_extraction import (
    AttributeResolver, AttributeResolverExtractor, ExpandedDeterministicExtractor,
    HybridSemanticExtractor, _same_value, _sentence_bounds, _masked_context,
)

EVIDENCE_STATE = "UNVERIFIED_CANDIDATE"
MAX_PER_ROW = 512
MAX_GLOBAL = 1_000_000
_WORD = re.compile(r"[a-z0-9]+(?:[._'-][a-z0-9]+)*", re.I)
_CLAUSE_SPLIT = re.compile(r"\s*(?:,\s*(?:(?:and|while|whereas|but)\s+)?|\b(?:and|while|whereas|but)\s+|;\s*)", re.I)
_PRONOUN = re.compile(r"\b(?:it|its|they|their|he|his|she|her)\b", re.I)


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str
    method: str
    ambiguous: bool = False


@dataclass(frozen=True)
class ValueSpan:
    value: TypedValue
    start: int
    end: int
    method: str = "typed_text_span"


@dataclass
class Candidate:
    row_id: str
    fact: AtomicFact
    entity_span: tuple[int, int] | None
    value_span: tuple[int, int] | None
    clause_id: int
    methods: set[str] = field(default_factory=set)
    scores: dict[str, float] = field(default_factory=dict)
    matched_example_ids: set[str] = field(default_factory=set)
    ambiguous_entity: bool = False
    evidence_state: str = EVIDENCE_STATE

    @property
    def rank_score(self) -> float:
        # Fixed, transparent weights. R5 is a ranking, not a classifier.
        return (4.0 * self.scores.get("exact_entity", 0.0)
                + 2.0 * self.scores.get("attribute_cue", 0.0)
                + 1.5 * self.scores.get("resolver", 0.0)
                + 2.0 * self.scores.get("bm25_rrf", 0.0)
                + 1.0 * self.scores.get("value_compat", 0.0)
                + 0.5 * self.scores.get("clause_local", 0.0)
                - 0.25 * self.ambiguous_entity)

    def key(self) -> tuple:
        v = self.fact.value
        return (self.fact.subject.casefold(), self.fact.attribute, v.kind,
                str(v.value), v.unit, v.currency, v.per, v.op)

    def as_dict(self) -> dict:
        v = self.fact.value
        return {
            "row_id": self.row_id, "subject": self.fact.subject,
            "attribute": self.fact.attribute,
            "value": {k: x for k, x in (("kind", v.kind), ("value", v.value),
                      ("unit", v.unit), ("currency", v.currency),
                      ("per", v.per), ("op", v.op)) if x is not None},
            "operator": v.op, "entity_span": list(self.entity_span) if self.entity_span else None,
            "value_span": list(self.value_span) if self.value_span else None,
            "clause_id": self.clause_id, "generation_methods": sorted(self.methods),
            "component_scores": dict(sorted(self.scores.items())),
            "rank_score": round(self.rank_score, 8),
            "matched_example_ids": sorted(self.matched_example_ids),
            "ambiguous_entity": self.ambiguous_entity,
            "evidence_state": self.evidence_state,
        }


def _overlapping_entities(text: str, lexicon: Lexicon) -> list[tuple[int, int, EntityReference]]:
    found = set()
    names = [(spelling, entity) for entity in lexicon.entities
             for spelling in (entity.name, *entity.aliases)]
    names.sort(key=lambda item: (-len(item[0]), item[0].casefold(), item[1].name.casefold()))
    for spelling, entity in names:
        words = re.split(r"[\s-]+", spelling.strip())
        pattern = r"(?<!\w)" + r"[\s-]+".join(re.escape(w) for w in words if w) + r"(?!\w)"
        for match in re.finditer(pattern, text, re.I):
            found.add((match.start(), match.end(), entity))
    return sorted(found, key=lambda x: (x[0], -(x[1]-x[0]), x[2].name.casefold()))


def _clauses(text: str) -> list[tuple[int, int]]:
    result = []
    for sentence in re.finditer(r"[^.!?\n]+(?:[.!?](?=\s|$)|$)", text):
        start, end = sentence.span()
        cursor = start
        for match in _CLAUSE_SPLIT.finditer(text, start, end):
            if match.start() > cursor:
                result.append((cursor, match.start()))
            cursor = match.end()
        if cursor < end:
            result.append((cursor, end))
    return result or [(0, len(text))]


def _clause_id(spans: list[tuple[int, int]], point: int) -> int:
    for i, (start, end) in enumerate(spans):
        if start <= point <= end:
            return i
    return max(0, len(spans) - 1)


def _kind_compatible(attribute: str, value: TypedValue, kinds: Mapping[str, str]) -> bool:
    expected = kinds.get(attribute)
    return expected is None or expected == value.kind


def _value_dict(v: TypedValue) -> dict:
    return {k: x for k, x in (("kind", v.kind), ("value", v.value), ("unit", v.unit),
                              ("currency", v.currency), ("per", v.per), ("op", v.op))
            if x is not None}


class BM25Index:
    """Small deterministic BM25 index with stable document-order tie breaks."""
    def __init__(self, records: list[dict]):
        self.records = records
        self.tokens = [Counter(t.casefold() for t in _WORD.findall(r["text"])) for r in records]
        self.lengths = [sum(c.values()) for c in self.tokens]
        self.avgdl = sum(self.lengths) / max(1, len(self.lengths))
        self.postings: dict[str, list[int]] = defaultdict(list)
        df = Counter()
        for doc_i, doc in enumerate(self.tokens):
            for term in doc:
                self.postings[term].append(doc_i)
                df[term] += 1
        self.idf = {term: math.log(1.0 + (len(records) - n + 0.5) / (n + 0.5)) for term, n in df.items()}

    def search(self, query: str, k: int) -> list[tuple[int, float]]:
        qterms = set(t.casefold() for t in _WORD.findall(query))
        candidate_ids = sorted({i for term in qterms for i in self.postings.get(term, ())})
        scored = []
        for i in candidate_ids:
            doc = self.tokens[i]
            score = 0.0
            dl = self.lengths[i]
            for term in qterms & doc.keys():
                tf = doc[term]
                score += self.idf.get(term, 0.0) * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * dl / max(self.avgdl, 1.0)))
            if score:
                scored.append((i, score))
        scored.sort(key=lambda x: (-x[1], self.records[x[0]]["example_id"]))
        return scored[:max(0, k)]


class CandidateFactory:
    def __init__(self, lexicon: Lexicon, attribute_kinds: Mapping[str, str],
                 known_units: Iterable[str], resolver: AttributeResolver,
                 indexes: Mapping[str, BM25Index], training_ids: frozenset[str],
                 per_row_cap: int = MAX_PER_ROW, global_cap: int = MAX_GLOBAL,
                 deadline_seconds: float | None = None):
        self.lexicon = lexicon
        self.attribute_kinds = dict(attribute_kinds)
        self.known_units = set(known_units)
        self.resolver = resolver
        self.indexes = dict(indexes)
        self.training_ids = training_ids
        self.per_row_cap = per_row_cap
        self.global_cap = global_cap
        self.deadline_seconds = deadline_seconds
        self._generation_started_at: float | None = None
        self.generated_total = 0
        self.emitted_total = 0

    @classmethod
    def fit(cls, data: InputData, train_row_ids: Iterable[str], *,
            per_row_cap: int = MAX_PER_ROW, global_cap: int = MAX_GLOBAL,
            deadline_seconds: float | None = None) -> "CandidateFactory":
        train_ids = frozenset(train_row_ids)
        resolver = AttributeResolver().fit(data, train_ids)
        parser = TextFactParser(data.lexicon, resolver.attribute_kinds, resolver.known_units,
                                expanded_attribute_cues=True, protect_entity_numbers=True,
                                complete_date_spans=True, complete_unit_spans=True)
        records: dict[str, list[dict]] = {name: [] for name in ("full_claim", "attribute_context", "local_value", "relationship")}
        for row in data.rows:
            if row.row_id not in train_ids:
                continue
            mentions = _entity_mentions(row.text, data.lexicon)
            spans = _value_spans(row.text, mentions, parser.known_units,
                                 exclude_calendar_days=True, protect_entity_numbers=True,
                                 complete_date_spans=True, complete_unit_spans=True)
            for fact_i, fact in enumerate(row.facts):
                entity = data.lexicon.resolve(fact.subject)
                if entity is None:
                    continue
                ems = [(a, b) for a, b, ref in mentions if ref.name == entity.name]
                vspans = [s for s in spans if _same_value(fact.value, s.value, data.lexicon)]
                pairs = [(abs((a+b-s.start-s.end)/2), a, b, s) for a, b in ems for s in vspans
                         if _sentence_bounds(row.text, a, b) == _sentence_bounds(row.text, s.start, s.end)]
                if not pairs:
                    continue
                _, a, b, span = min(pairs, key=lambda x: (x[0], x[1], x[3].start))
                masked = _masked_context(row.text, (a, b), (span.start, span.end), mentions)
                left, right = _sentence_bounds(row.text, span.start, span.end)
                local = row.text[max(left, span.start-80):min(right, span.end+80)]
                example = {"example_id": f"{row.row_id}#{fact_i}", "row_id": row.row_id,
                           "attribute": fact.attribute, "kind": fact.value.kind,
                           "subject": entity.name, "value": _value_dict(fact.value)}
                for view, text in (("full_claim", row.text), ("attribute_context", masked),
                                   ("local_value", local)):
                    records[view].append({**example, "text": text})
                if fact.value.kind == "name":
                    records["relationship"].append({**example, "text": masked})
        indexes = {name: BM25Index(items) for name, items in records.items()}
        return cls(data.lexicon, resolver.attribute_kinds, resolver.known_units,
                   resolver, indexes, train_ids, per_row_cap, global_cap, deadline_seconds)

    def baseline(self):
        deterministic = ExpandedDeterministicExtractor(
            self.lexicon, self.attribute_kinds, self.known_units,
            protect_entity_numbers=True, complete_date_spans=True, complete_unit_spans=True)
        money = AttributeResolverExtractor(
            TextFactParser(self.lexicon, self.attribute_kinds, self.known_units),
            self.resolver, allowed_value_kinds={"money"})
        return HybridSemanticExtractor(deterministic, money)

    def _bm25_attributes(self, query_views: Mapping[str, str], k: int,
                         allowed: set[str], value_kind: str) -> tuple[dict[str, float], dict[str, set[str]], dict[str, dict[str, float]]]:
        rrf: dict[str, float] = defaultdict(float)
        ids: dict[str, set[str]] = defaultdict(set)
        view_scores: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for view, query in query_views.items():
            index = self.indexes.get(view)
            if not index or not query:
                continue
            for rank, (doc_i, _score) in enumerate(index.search(query, k), 1):
                doc = index.records[doc_i]
                attr = doc["attribute"]
                if attr in allowed and doc["kind"] == value_kind:
                    contribution = 1.0 / (60 + rank)
                    rrf[attr] += contribution
                    view_scores[attr][view] += contribution
                    ids[attr].add(f"{view}:{doc['example_id']}")
        return dict(rrf), ids, {a:dict(v) for a,v in view_scores.items()}

    def generate(self, row_id: str, text: str, *, config: str = "R4", k: int = 5,
                 collect_only: bool = False) -> tuple[list[Candidate], dict]:
        """Return ranked hypotheses and explicit pre/post-cap counts."""
        if self._generation_started_at is None:
            self._generation_started_at = time.monotonic()
        if self.deadline_seconds is not None and time.monotonic() - self._generation_started_at >= self.deadline_seconds:
            return [], {"generated_before_caps": 0, "emitted": 0, "per_row_truncated": False,
                        "global_truncated": False, "skipped_after_global_cap": False,
                        "deadline_exceeded": True, "deadline_truncated": True,
                        "evidence_state": EVIDENCE_STATE}
        if not collect_only and self.emitted_total >= self.global_cap:
            return [], {"generated_before_caps": None, "emitted": 0,
                        "per_row_truncated": False, "global_truncated": True,
                        "skipped_after_global_cap": True,
                        "deadline_exceeded": False, "deadline_truncated": False,
                        "evidence_state": EVIDENCE_STATE}
        use_bm25 = config in {"R2", "R3", "R4", "R5"}
        use_coref = config in {"R3", "R4", "R5"}
        use_templates = config in {"R4", "R5"}
        clauses = _clauses(text)
        entities = _overlapping_entities(text, self.lexicon)
        parser = TextFactParser(self.lexicon, self.attribute_kinds, self.known_units,
                                expanded_attribute_cues=True, protect_entity_numbers=True,
                                complete_date_spans=True, complete_unit_spans=True)
        primary_mentions = _entity_mentions(text, self.lexicon)
        raw_values = _value_spans(text, primary_mentions, parser.known_units,
                                  exclude_calendar_days=True, protect_entity_numbers=True,
                                  complete_date_spans=True, complete_unit_spans=True)
        values = [ValueSpan(s.value, s.start, s.end) for s in raw_values]
        # Preserve overlapping lexicon names as alternative name values too.
        values.extend(ValueSpan(TypedValue("name", entity.name), a, b, "lexicon_name_span")
                      for a, b, entity in entities)
        values = list({(x.start, x.end, x.value.key()): x for x in values}.values())
        # Boolean candidates require an explicit compatible attribute cue and polarity.
        for a, b, entity in entities:
            cid = _clause_id(clauses, a)
            start, end = clauses[cid]
            clause = text[start:end]
            for _x, _y, attr, _spec in _attribute_mentions(clause, entity, expanded=True):
                if self.attribute_kinds.get(attr) == "boolean":
                    v = _boolean_value(clause, _x, _y)
                    values.append(ValueSpan(TypedValue("boolean", v), start+_x, start+_y, "boolean_attribute_polarity"))
        values = list({(x.start, x.end, x.value.key()): x for x in values}.values())

        # Assign explicit entity spans to clauses; R3 only adds a local, text-grounded
        # antecedent when a pronoun follows a unique explicit entity in the same row.
        subject_spans: list[tuple[int, int, EntityReference, str, bool]] = [
            (a, b, e, "exact_or_alias_span", sum(1 for x, y, z in entities if x == a and y == b and z.name != e.name)>0)
            for a, b, e in entities]
        if use_templates:
            # Carry a sole explicit subject across a coordinated clause whose
            # subject was elided. This remains a ranked, unverified hypothesis.
            for start, end in clauses:
                if any(start <= a < end for a, _b, _e in entities):
                    continue
                prior = [(a, b, e) for a, b, e in entities if b <= start
                         and _sentence_bounds(text, b, b) == _sentence_bounds(text, start, start)]
                distinct = {e.name: (a, b, e) for a, b, e in prior}
                if 0 < len(distinct) <= 3:
                    # Keep bounded competing antecedents where names overlap;
                    # do not force an ambiguous subject resolution.
                    for a, b, e in sorted(distinct.values(), key=lambda x: (x[1], x[2].name)):
                        subject_spans.append((start, min(end, start+1), e,
                                              "same_sentence_subject_carry", len(distinct) > 1))
        if use_coref:
            for pron in _PRONOUN.finditer(text):
                prev = [(a, b, e) for a, b, e in entities if b <= pron.start()
                        and _sentence_bounds(text, b, b) == _sentence_bounds(text, pron.start(), pron.start())]
                unique = {e.name: (a, b, e) for a, b, e in prev}
                if 0 < len(unique) <= 3:
                    for a, b, e in sorted(unique.values(), key=lambda x:(x[1],x[2].name)):
                        subject_spans.append((pron.start(), pron.end(), e,
                                              "same_row_pronoun_antecedent", len(unique)>1))

        extracted = {}
        supported_types: Counter[str] = Counter()
        attribute_candidates: dict[str, set[str]] = defaultdict(set)
        deadline_hit = False
        for ea, eb, entity, entity_method, ambiguous in subject_spans:
            if self.deadline_seconds is not None and time.monotonic() - self._generation_started_at >= self.deadline_seconds:
                deadline_hit = True
                break
            cid = _clause_id(clauses, ea)
            cstart, cend = clauses[cid]
            clause = text[cstart:cend]
            local_values = [v for v in values if _clause_id(clauses, v.start) == cid]
            # If a conjunction clause omits its subject, carry the nearest prior
            # explicit subject in the same sentence as a bounded coreference hypothesis.
            if not local_values:
                continue
            mentions_for_context = primary_mentions
            attr_mentions = _attribute_mentions(clause, entity, expanded=True)
            cues = {attr for _x, _y, attr, _s in attr_mentions}
            for value in local_values:
                if self.deadline_seconds is not None and time.monotonic() - self._generation_started_at >= self.deadline_seconds:
                    deadline_hit = True
                    break
                if value.value.kind == "name" and str(value.value.value).casefold() == entity.name.casefold():
                    continue
                compatible = {a for a in entity.attributes if _kind_compatible(a, value.value, self.attribute_kinds)}
                if not compatible:
                    continue
                local_attr_cues = cues
                context = _masked_context(text, (ea, eb), (value.start, value.end), mentions_for_context)
                resolver_rank = self.resolver.rank(context, compatible)
                resolver_scores = {a: score for a, score in resolver_rank[:20]}
                attrs = set(local_attr_cues) & compatible
                # R1 retains a bounded shortlist; BM25 can introduce attributes
                # outside it in R2 instead of merely reranking R1's same set.
                attrs.update(a for a, _score in resolver_rank[:5])
                if use_templates:
                    # R4 asks the local-value and relation views in addition to full
                    # and masked claim retrieval; all records still map only to train forms.
                    pass
                bm_scores, example_ids, bm_view_scores = ({}, {}, {})
                if use_bm25:
                    left, right = _sentence_bounds(text, value.start, value.end)
                    local_view = text[max(left, value.start-80):min(right, value.end+80)]
                    relation_view = context if value.value.kind == "name" else ""
                    views = {"full_claim": text, "attribute_context": context}
                    if use_templates:
                        views["local_value"] = local_view
                        if relation_view:
                            views["relationship"] = relation_view
                    bm_scores, example_ids, bm_view_scores = self._bm25_attributes(views, k, compatible, value.value.kind)
                    attrs.update(bm_scores)
                # Include unit-supported attribute names even when phrased indirectly.
                if value.value.kind == "quantity" and value.value.unit:
                    unit = re.sub(r"s$", "", str(value.value.unit).casefold())
                    attrs.update(a for a in compatible if unit and unit in a.replace("_", " ").casefold())
                attribute_candidates[entity.name].update(attrs)
                for attr in sorted(attrs):
                    fact = AtomicFact(entity.name, attr, value.value, text[ea:eb])
                    key = (fact.subject.casefold(), fact.attribute, fact.value.key())
                    cand = extracted.get(key)
                    if cand is None:
                        cand = Candidate(row_id, fact, (ea, eb), (value.start, value.end), cid,
                                         ambiguous_entity=ambiguous)
                        extracted[key] = cand
                    cand.methods.add(entity_method)
                    if attr in local_attr_cues:
                        cand.methods.add("attribute_cue")
                        cand.scores["attribute_cue"] = 1.0
                    if attr in resolver_scores:
                        cand.methods.add("tfidf_resolver_top20")
                        cand.scores["resolver"] = max(cand.scores.get("resolver", 0.0), resolver_scores[attr])
                    if attr in bm_scores:
                        cand.methods.add("bm25_multiview")
                        cand.scores["bm25_rrf"] = max(cand.scores.get("bm25_rrf", 0.0), bm_scores[attr])
                        for view, score in bm_view_scores.get(attr, {}).items():
                            key_score = f"bm25_{view}"
                            cand.scores[key_score] = max(cand.scores.get(key_score, 0.0), score)
                        cand.matched_example_ids.update(example_ids.get(attr, ()))
                    cand.scores["exact_entity"] = 1.0 if entity_method == "exact_or_alias_span" else 0.5
                    cand.scores["value_compat"] = 1.0
                    cand.scores["clause_local"] = 1.0
                    supported_types[value.value.kind] += 1
            if deadline_hit:
                break
        candidates = list(extracted.values())
        # R1-R4 retain deterministic generation order. R5 applies the explicit
        # component ranker only after oracle candidate coverage has been measured.
        if config == "R5":
            candidates.sort(key=lambda c: (-c.rank_score, c.row_id, c.key()))
        generated = len(candidates)
        self.generated_total += generated
        limited = candidates[:self.per_row_cap]
        if not collect_only:
            room = max(0, self.global_cap - self.emitted_total)
            limited = limited[:room]
            self.emitted_total += len(limited)
        return limited, {"generated_before_caps": generated, "emitted": len(limited),
                         "per_row_truncated": generated > self.per_row_cap,
                         "global_truncated": len(limited) < min(generated, self.per_row_cap),
                         "skipped_after_global_cap": False,
                         "deadline_exceeded": deadline_hit, "deadline_truncated": deadline_hit,
                         "unique_candidates": len(extracted),
                         "value_spans": len(values), "entity_hypotheses": len(subject_spans),
                         "subject_candidates": sorted({e.name for _a, _b, e, _m, _amb in subject_spans}),
                         "value_candidates": [{"value": _value_dict(v.value), "start": v.start, "end": v.end}
                                              for v in values],
                         "attribute_candidates": {k: sorted(v) for k, v in sorted(attribute_candidates.items())},
                         "evidence_state": EVIDENCE_STATE}


def candidate_matches(left: AtomicFact, right: AtomicFact, lexicon: Lexicon) -> bool:
    return (left.subject == right.subject and left.attribute == right.attribute
            and _same_value(left.value, right.value, lexicon))


def candidate_fact_from_dict(item: Mapping) -> AtomicFact:
    raw = item["value"]
    return AtomicFact(item["subject"], item["attribute"], TypedValue(
        raw["kind"], raw["value"], raw.get("unit"), raw.get("currency"),
        raw.get("per"), raw.get("op")))
