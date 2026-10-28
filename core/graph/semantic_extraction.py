"""Experimental semantic extractors; every output remains an unverified candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol

from foundation import AtomicFact, InputData, Lexicon, TypedValue, compare_values
from .models import ExtractionCandidate, ParseStatus
from .parsing import TextFactParser, _entity_mentions, _value_spans


@dataclass(frozen=True)
class SemanticExtractionResult:
    facts: tuple[AtomicFact, ...]
    status: ParseStatus
    confidence: float
    issues: tuple[str, ...] = ()
    method: str = "p1_regex"
    candidates: tuple[ExtractionCandidate, ...] = ()


class SemanticExtractor(Protocol):
    def extract(self, text: str, source_row_id: str) -> SemanticExtractionResult: ...


def _same_value(left: TypedValue, right: TypedValue, lexicon: Lexicon) -> bool:
    if left.op != right.op or left.kind != right.kind:
        return False
    if left.kind == "name":
        a, b = lexicon.resolve(str(left.value)), lexicon.resolve(str(right.value))
        left = TypedValue("name", a.name if a else left.value)
        right = TypedValue("name", b.name if b else right.value)
    from dataclasses import replace
    return compare_values(replace(left, op=None), replace(right, op=None), "eq") is True


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(mark, 0, start) for mark in (".", "!", "?", "\n")) + 1
    ends = [position for mark in (".", "!", "?", "\n") if (position := text.find(mark, end)) >= 0]
    return left, min(ends) if ends else len(text)


def _masked_context(text: str, subject_span: tuple[int, int], value_span: tuple[int, int],
                    mentions: list[tuple[int, int, object]]) -> str:
    start = min(subject_span[0], value_span[0])
    end = max(subject_span[1], value_span[1])
    left, right = _sentence_bounds(text, start, end)
    chunk = text[left:right]
    replacements = [(a - left, b - left, " entity ") for a, b, _ in mentions
                   if left <= a and b <= right]
    replacements.append((value_span[0] - left, value_span[1] - left, " value "))
    for a, b, marker in sorted(replacements, reverse=True):
        chunk = chunk[:a] + marker + chunk[b:]
    chunk = re.sub(r"\b\d+(?:[.,]\d+)?\b", " number ", chunk.casefold())
    return re.sub(r"[^a-z<>]+", " ", chunk).strip()


def _value_spans_for(parser: TextFactParser, text: str):
    mentions = _entity_mentions(text, parser.lexicon)
    return mentions, _value_spans(text, mentions, parser.known_units,
                                  exclude_calendar_days=(parser.expanded_attribute_cues or parser.complete_date_spans),
                                  protect_entity_numbers=parser.protect_entity_numbers,
                                  complete_date_spans=parser.complete_date_spans,
                                  complete_unit_spans=parser.complete_unit_spans)


def _details_for(facts: Iterable[AtomicFact], text: str, row_id: str, method: str,
                 confidence: float, parser: TextFactParser) -> tuple[ExtractionCandidate, ...]:
    mentions, spans = _value_spans_for(parser, text)
    details: list[ExtractionCandidate] = []
    for fact in facts:
        entity = parser.lexicon.resolve(fact.subject)
        subject_mentions = [(a, b) for a, b, item in mentions if entity and item.name == entity.name]
        matches = [span for span in spans if _same_value(fact.value, span.value, parser.lexicon)]
        if not matches:
            details.append(ExtractionCandidate(fact, row_id, method, confidence))
            continue
        candidates = [(abs((a + b) / 2 - (span.start + span.end) / 2), span)
                      for span in matches for a, b in subject_mentions
                      if _sentence_bounds(text, a, b) == _sentence_bounds(text, span.start, span.end)]
        if candidates:
            candidates.sort(key=lambda pair: (pair[0], pair[1].start))
            distance, span = candidates[0]
            ambiguous = sum(abs(item[0] - distance) < 1 for item in candidates) > 1
            subject_start, subject_end = next((a, b) for a, b in subject_mentions
                                              if _sentence_bounds(text, a, b) == _sentence_bounds(text, span.start, span.end)
                                              and abs((a + b) / 2 - (span.start + span.end) / 2) == distance)
            details.append(ExtractionCandidate(fact, row_id, method, confidence,
                                               span.start, span.end, ambiguous, None,
                                               subject_start, subject_end))
        else:
            span = min(matches, key=lambda item: item.start)
            details.append(ExtractionCandidate(fact, row_id, method, confidence,
                                               span.start, span.end, True))
    return tuple(details)


class P1ParserAdapter:
    """Adapter preserving the original P1 parser as a selectable fallback."""

    method = "p1_regex"

    def __init__(self, parser: TextFactParser):
        self.parser = parser

    def extract(self, text: str, source_row_id: str) -> SemanticExtractionResult:
        result = self.parser.parse(text)
        return SemanticExtractionResult(
            result.facts, result.status, result.confidence, result.issues, self.method,
            _details_for(result.facts, text, source_row_id, self.method,
                         result.confidence, self.parser),
        )


class ExpandedDeterministicExtractor(P1ParserAdapter):
    """P1 parser with distinctive attribute-component and inflection cues."""

    method = "expanded_deterministic"

    def __init__(self, lexicon: Lexicon, attribute_kinds: Mapping[str, str] | None = None,
                 known_units: Iterable[str] = (), *, protect_entity_numbers: bool = False,
                 complete_date_spans: bool = False, align_attribute_values: bool = False,
                 complete_unit_spans: bool = False):
        super().__init__(TextFactParser(lexicon, attribute_kinds, known_units,
                                        expanded_attribute_cues=True,
                                        protect_entity_numbers=protect_entity_numbers,
                                        complete_date_spans=complete_date_spans,
                                        align_attribute_values=align_attribute_values,
                                        complete_unit_spans=complete_unit_spans))


@dataclass(frozen=True)
class GroupedSplit:
    train_row_ids: frozenset[str]
    validation_row_ids: frozenset[str]
    group_count: int
    validation_groups: int


def _template(text: str, lexicon: Lexicon) -> str:
    for entity in sorted(lexicon.entities, key=lambda item: len(item.name), reverse=True):
        for spelling in (entity.name, *entity.aliases):
            text = re.sub(r"(?<!\w)" + re.escape(spelling) + r"(?!\w)", " entity ", text, flags=re.I)
    text = re.sub(r"\b\d+(?:[.,]\d+)?\b", " value ", text.casefold())
    return re.sub(r"[^a-z]+", " ", text).strip()


def grouped_train_validation_split(data: InputData, validation_fraction: float = 0.2,
                                   seed: str = "neuron5-p15-v1") -> GroupedSplit:
    """Keep shared subject/attribute histories and normalized templates together."""
    rows = data.rows
    parent = list(range(len(rows)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    memberships: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        for fact in row.facts:
            memberships[(fact.subject.casefold(), fact.attribute)].append(index)
        memberships[("template", _template(row.text, data.lexicon))].append(index)
    for indices in memberships.values():
        if indices:
            for index in indices[1:]:
                union(indices[0], index)

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        components[find(index)].append(index)
    ordered = sorted(components.items(), key=lambda pair: hashlib.sha256(
        (seed + "|" + min(rows[i].row_id for i in pair[1])).encode()).hexdigest())
    target = max(1, round(len(rows) * validation_fraction))
    validation: set[int] = set()
    for _, indices in ordered:
        if len(validation) >= target:
            break
        if abs(target - (len(validation) + len(indices))) <= abs(target - len(validation)):
            validation.update(indices)
    if not validation and ordered:
        validation.update(ordered[0][1])
    train_ids = frozenset(row.row_id for i, row in enumerate(rows) if i not in validation)
    validation_ids = frozenset(rows[i].row_id for i in validation)
    return GroupedSplit(train_ids, validation_ids, len(components),
                        sum(1 for indices in components.values() if any(i in validation for i in indices)))


def _features(text: str) -> Counter[str]:
    words = re.findall(r"[a-z]+|<entity>|<value>", text.casefold())
    result: Counter[str] = Counter()
    for i, word in enumerate(words):
        result["w:" + word] += 1
        if i + 1 < len(words):
            result["b:" + word + " " + words[i + 1]] += 1
        compact = "^" + word + "$"
        for size in (3, 4, 5):
            result.update("c:" + compact[i:i + size] for i in range(max(0, len(compact) - size + 1)))
    return result


class AttributeResolver:
    """Dependency-free, supervised TF-IDF nearest-example ranker for allowed attrs."""

    def __init__(self, min_similarity: float = 0.16, min_margin: float = 0.025):
        self.min_similarity = min_similarity
        self.min_margin = min_margin
        self.idf: dict[str, float] = {}
        self.documents: list[tuple[str, dict[str, float], float]] = []
        self.attribute_kinds: dict[str, str] = {}
        self.known_units: set[str] = set()
        self.training_examples = 0

    def fit(self, data: InputData, train_row_ids: Iterable[str]) -> "AttributeResolver":
        selected = set(train_row_ids)
        examples: list[tuple[str, str]] = []
        for row in data.rows:
            if row.row_id not in selected:
                continue
            for fact in row.facts:
                self.attribute_kinds.setdefault(fact.attribute, fact.value.kind)
                if fact.value.unit:
                    self.known_units.add(fact.value.unit)
        parser = TextFactParser(data.lexicon, self.attribute_kinds, self.known_units)
        for row in data.rows:
            if row.row_id not in selected:
                continue
            mentions, spans = _value_spans_for(parser, row.text)
            for fact in row.facts:  # Semantic supervision intentionally ignores row truth labels.
                entity = data.lexicon.resolve(fact.subject)
                if entity is None:
                    continue
                subjects = [(a, b) for a, b, mention in mentions if mention.name == entity.name]
                if not subjects:
                    continue
                matching = [span for span in spans if _same_value(fact.value, span.value, data.lexicon)]
                pairs = [(abs((a + b) / 2 - (span.start + span.end) / 2), a, b, span)
                         for span in matching for a, b in subjects
                         if _sentence_bounds(row.text, a, b) == _sentence_bounds(row.text, span.start, span.end)]
                if not pairs:
                    continue
                _, a, b, span = min(pairs, key=lambda item: item[0])
                examples.append((_masked_context(row.text, (a, b), (span.start, span.end), mentions), fact.attribute))
        self.training_examples = len(examples)
        docs = [_features(text) for text, _ in examples]
        df: Counter[str] = Counter()
        for doc in docs:
            df.update(doc.keys())
        count = max(1, len(docs))
        self.idf = {term: math.log((count + 1) / (frequency + 1)) + 1 for term, frequency in df.items()}
        self.documents = []
        for (text, attribute), raw in zip(examples, docs):
            vector = {term: amount * self.idf[term] for term, amount in raw.items() if term in self.idf}
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            self.documents.append((attribute, {term: value / norm for term, value in vector.items()}, norm))
        return self

    def to_dict(self) -> dict:
        return {
            "format": "neuron5-attribute-resolver-v1",
            "min_similarity": self.min_similarity,
            "min_margin": self.min_margin,
            "idf": self.idf,
            "documents": [{"attribute": attribute, "vector": vector}
                          for attribute, vector, _ in self.documents],
            "attribute_kinds": self.attribute_kinds,
            "known_units": sorted(self.known_units),
            "training_examples": self.training_examples,
        }

    @classmethod
    def from_dict(cls, raw: Mapping) -> "AttributeResolver":
        if raw.get("format") != "neuron5-attribute-resolver-v1":
            raise ValueError("unsupported attribute resolver artifact format")
        resolver = cls(float(raw["min_similarity"]), float(raw["min_margin"]))
        resolver.idf = {str(key): float(value) for key, value in raw["idf"].items()}
        resolver.documents = [
            (str(item["attribute"]), {str(key): float(value) for key, value in item["vector"].items()}, 1.0)
            for item in raw["documents"]
        ]
        resolver.attribute_kinds = {str(key): str(value) for key, value in raw["attribute_kinds"].items()}
        resolver.known_units = set(map(str, raw["known_units"]))
        resolver.training_examples = int(raw["training_examples"])
        return resolver

    @classmethod
    def load(cls, path) -> "AttributeResolver":
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, Mapping):
            raise ValueError("attribute resolver artifact must contain an object")
        return cls.from_dict(raw)

    def save(self, path) -> None:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            handle.write("\n")

    def rank(self, context: str, allowed_attributes: Iterable[str]) -> tuple[tuple[str, float], ...]:
        if not self.documents:
            return ()
        raw = _features(context)
        vector = {term: amount * self.idf[term] for term, amount in raw.items() if term in self.idf}
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vector = {term: value / norm for term, value in vector.items()}
        allowed = set(allowed_attributes)
        scores: dict[str, list[float]] = defaultdict(list)
        for attribute, document, _ in self.documents:
            if attribute not in allowed:
                continue
            score = sum(value * document.get(term, 0.0) for term, value in vector.items())
            scores[attribute].append(score)
        ranked = [(attribute, sum(sorted(values, reverse=True)[:3]) / min(3, len(values)))
                  for attribute, values in scores.items()]
        return tuple(sorted(ranked, key=lambda item: (-item[1], item[0])))

    def decision(self, context: str, allowed_attributes: Iterable[str]) -> tuple[str | None, float, bool]:
        ranked = self.rank(context, allowed_attributes)
        if not ranked:
            return None, 0.0, False
        top_attr, top_score = ranked[0]
        margin = top_score - (ranked[1][1] if len(ranked) > 1 else 0.0)
        ambiguous = top_score < self.min_similarity or (len(ranked) > 1 and margin < self.min_margin)
        return (None if ambiguous else top_attr), top_score, ambiguous


class AttributeResolverExtractor:
    method = "tfidf_attribute_resolver"

    def __init__(self, parser: TextFactParser, resolver: AttributeResolver,
                 allowed_value_kinds: Iterable[str] | None = None):
        self.parser = parser
        self.resolver = resolver
        self.allowed_value_kinds = set(allowed_value_kinds) if allowed_value_kinds is not None else None

    def extract(self, text: str, source_row_id: str) -> SemanticExtractionResult:
        mentions, spans = _value_spans_for(self.parser, text)
        facts: dict[tuple[object, ...], ExtractionCandidate] = {}
        clauses = _entity_clauses(text, mentions)
        for a, b, entity in mentions:
            left, right = clauses.get((a, b), _sentence_bounds(text, a, b))
            for span in spans:
                if not (left <= span.start < right):
                    continue
                if self.allowed_value_kinds is not None and span.value.kind not in self.allowed_value_kinds:
                    continue
                if span.value.kind == "name" and span.value.value == entity.name:
                    continue
                typed_attributes = [attr for attr in entity.attributes
                                    if self.resolver.attribute_kinds.get(attr, span.value.kind) == span.value.kind]
                context = _masked_context(text, (a, b), (span.start, span.end), mentions)
                attribute, confidence, ambiguous = self.resolver.decision(context, typed_attributes)
                if attribute is None:
                    continue
                fact = AtomicFact(entity.name, attribute, span.value, text[a:b])
                key = (fact.subject, fact.attribute, fact.value.key())
                facts.setdefault(key, ExtractionCandidate(fact, source_row_id, self.method,
                                                          confidence, span.start, span.end, ambiguous,
                                                          None, a, b))
        candidates = tuple(facts.values())
        return SemanticExtractionResult(tuple(item.fact for item in candidates),
                                        ParseStatus.PARTIAL if candidates else ParseStatus.UNPARSED,
                                        max((item.confidence for item in candidates), default=0.0),
                                        (), self.method, candidates)


def _entity_clauses(text: str, mentions: list[tuple[int, int, object]]) -> dict[tuple[int, int], tuple[int, int]]:
    clauses: dict[tuple[int, int], tuple[int, int]] = {}
    for a, b, _ in mentions:
        sentence_start, sentence_end = _sentence_bounds(text, a, b)
        boundaries = [sentence_start, sentence_end]
        for separator in re.finditer(r";|,\s*(?:(?:and|while|whereas|but)\s+)?|\b(?:and|while|whereas|but)\s+", text[sentence_start:sentence_end], re.I):
            absolute_end = sentence_start + separator.end()
            if any(absolute_end <= other_a <= absolute_end + 40 and other_a < sentence_end
                   for other_a, _, _ in mentions):
                boundaries.append(absolute_end)
        boundaries.sort()
        left = max((point for point in boundaries if point <= a), default=sentence_start)
        right = min((point for point in boundaries if point > a), default=sentence_end)
        clauses[(a, b)] = (left, right)
    return clauses


class SpacyAssistedExtractor:
    """Optional spaCy adapter; never downloads a pipeline and safely falls back."""

    method = "spacy_unavailable_fallback"

    def __init__(self, fallback: P1ParserAdapter):
        self.fallback = fallback
        self.available = False
        self.reason = "spaCy package is not installed"
        if importlib.util.find_spec("spacy"):
            import spacy
            for name in ("en_core_web_sm", "en_core_web_md", "en_core_web_lg", "en_core_web_trf"):
                if spacy.util.is_package(name):
                    self.available = True
                    self.reason = "compatible pipeline available, but no spaCy rules configured in this experiment"
                    break
            else:
                self.reason = "spaCy is installed but no English pipeline is installed"

    def extract(self, text: str, source_row_id: str) -> SemanticExtractionResult:
        result = self.fallback.extract(text, source_row_id)
        return SemanticExtractionResult(result.facts, result.status, result.confidence,
                                        (self.reason,), self.method, result.candidates)


class HybridSemanticExtractor:
    """Union of a deterministic extractor and a trained resolver, with deterministic precedence."""

    method = "hybrid_p1_plus_tfidf"

    def __init__(self, deterministic: P1ParserAdapter, resolver_extractor: AttributeResolverExtractor):
        self.deterministic = deterministic
        self.resolver_extractor = resolver_extractor

    def extract(self, text: str, source_row_id: str) -> SemanticExtractionResult:
        primary = self.deterministic.extract(text, source_row_id)
        supplemental = self.resolver_extractor.extract(text, source_row_id)
        combined = {(item.fact.subject, item.fact.attribute, item.fact.value.key()): item
                    for item in primary.candidates}
        for item in supplemental.candidates:
            key = (item.fact.subject, item.fact.attribute, item.fact.value.key())
            combined.setdefault(key, item)
        candidates = tuple(combined.values())
        return SemanticExtractionResult(tuple(item.fact for item in candidates),
                                        ParseStatus.PARTIAL if candidates else ParseStatus.UNPARSED,
                                        max((item.confidence for item in candidates), default=0.0),
                                        tuple(dict.fromkeys((*primary.issues, *supplemental.issues))),
                                        self.method, candidates)


def selected_semantic_extractor(lexicon: Lexicon, attribute_kinds: Mapping[str, str],
                                known_units: Iterable[str], artifact_path: str | Path | None = None):
    """Load the selective hybrid with protected entity numbers and complete date/unit spans.

    Cross-attribute reassignment stays opt-in: the grouped comparison found useful
    recoveries but more false positives and no aggregate F1 gain.
    """
    if artifact_path is None:
        artifact_path = Path(__file__).with_name("attribute_resolver.json")
    artifact_path = Path(artifact_path)
    if artifact_path.is_file():
        resolver = AttributeResolver.load(artifact_path)
        kinds = dict(attribute_kinds) or resolver.attribute_kinds
        units = set(known_units) or resolver.known_units
        deterministic = ExpandedDeterministicExtractor(
            lexicon, kinds, units,
            protect_entity_numbers=True,
            complete_date_spans=True,
            complete_unit_spans=True,
        )
        parser = TextFactParser(lexicon, resolver.attribute_kinds, resolver.known_units)
        monetary_resolver = AttributeResolverExtractor(parser, resolver, allowed_value_kinds={"money"})
        return HybridSemanticExtractor(deterministic, monetary_resolver)
    return ExpandedDeterministicExtractor(
        lexicon, attribute_kinds, known_units,
        protect_entity_numbers=True,
        complete_date_spans=True,
        complete_unit_spans=True,
    )
