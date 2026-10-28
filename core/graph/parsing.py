"""Conservative deterministic extraction of candidate facts from claim text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from foundation import AtomicFact, EntityReference, Lexicon, TypedValue
from .models import ParseStatus


@dataclass(frozen=True)
class ExtractionResult:
    facts: tuple[AtomicFact, ...]
    status: ParseStatus
    confidence: float
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SpanValue:
    value: TypedValue
    start: int
    end: int


_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:[,.]\d+)?"
_NUMBER_RE = re.compile(_NUM)
_DURATION_UNITS = {"ms", "s", "min", "h", "day", "week", "month", "year"}
_CURRENCY = {"€": "EUR", "$": "USD", "US$": "USD", "£": "GBP", "EUR": "EUR", "USD": "USD", "GBP": "GBP", "CHF": "CHF", "RON": "RON", "PLN": "PLN", "CZK": "CZK", "HUF": "HUF", "SEK": "SEK", "NOK": "NOK", "DKK": "DKK", "JPY": "JPY", "CNY": "CNY", "INR": "INR", "CAD": "CAD", "AUD": "AUD"}
_MAGNITUDES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "bn": 1e9, "billion": 1e9, "trillion": 1e12}
_PERIOD = re.compile(r"(?:/\s*(?:mo|month|day|week|yr|year)|\bper\s+(?:annum|month|day|week|year)|\ba\s+(?:month|day|week|year)\b|\bmonthly\b|\bannually\b)", re.I)
_MONTHS = {name.lower(): i for i, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}


def _number(raw: str, decimal_comma: bool = False) -> float | int:
    normalized = raw.replace(",", ".") if decimal_comma else raw.replace(",", "")
    if "." not in normalized:
        return int(normalized)
    value = float(normalized)
    return int(value) if value.is_integer() else value


def _operator_before(text: str, start: int) -> str | None:
    context = text[max(0, start - 42):start].casefold()
    for pattern, operator in (
        (r"\b(?:no more than|at most|up to)\s*$", "le"),
        (r"\b(?:at least|no fewer than)\s*$", "ge"),
        (r"\b(?:more than|greater than|over|above|exceeding)\s*$", "gt"),
        (r"\b(?:less than|fewer than|under|below)\s*$", "lt"),
    ):
        if re.search(pattern, context):
            return operator
    return None


def _operator_after(text: str, end: int) -> str | None:
    context = text[end:min(len(text), end + 24)].casefold()
    if re.match(r"\s*(?:or more|or higher|or greater)\b", context):
        return "ge"
    if re.match(r"\s*(?:or less|or lower|or fewer)\b", context):
        return "le"
    return None


def _is_approximate(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 20):start].casefold()
    after = text[end:min(len(text), end + 16)].casefold()
    return bool(re.search(r"(?:\babout|\bapprox(?:imately)?|\baround|\broughly|\bnearly|\balmost|~)\s*$", before)
                or re.match(r"\s*(?:or so|approximately|roughly)\b", after))


def _singular(word: str) -> str:
    lower = word.casefold()
    if lower in {"people": "person", "men": "man", "women": "woman", "children": "child", "indices": "index", "mice": "mouse"}:
        return {"people": "person", "men": "man", "women": "woman", "children": "child", "indices": "index", "mice": "mouse"}[lower]
    if lower.endswith("ies") and len(lower) > 3:
        return lower[:-3] + "y"
    if lower.endswith("s") and not lower.endswith(("ss", "us", "is")):
        return lower[:-1]
    return word


def _entity_mentions(text: str, lexicon: Lexicon) -> list[tuple[int, int, EntityReference]]:
    found: list[tuple[int, int, EntityReference]] = []
    candidates: list[tuple[str, EntityReference]] = []
    for entity in lexicon.entities:
        candidates.extend((name, entity) for name in (entity.name, *entity.aliases))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)
    for spelling, entity in candidates:
        words = re.split(r"[\s-]+", spelling.strip())
        pattern = r"(?<!\w)" + r"[\s-]+".join(re.escape(word) for word in words if word) + r"(?!\w)"
        for match in re.finditer(pattern, text, re.I):
            if any(match.start() >= start and match.end() <= end for start, end, _ in found):
                continue
            found.append((match.start(), match.end(), entity))
    return sorted(found)


def _attribute_cues(attribute: str) -> tuple[str, ...]:
    words = attribute.replace("_", " ").split()
    if not words:
        return ()
    full = r"[\s-]+".join(re.escape(x) for x in words)
    cues = {full}
    # Long attributes often use the final distinctive noun on the page.
    if len(words) > 1 and len(words[-1]) >= 5 and words[-1].casefold() not in {"other", "their", "about", "after", "before", "under", "since", "there", "which"}:
        cues.add(re.escape(words[-1]))
    return tuple(sorted(cues, key=len, reverse=True))


def _attribute_mentions(text: str, entity: EntityReference) -> list[tuple[int, int, str, int]]:
    mentions: list[tuple[int, int, str, int]] = []
    for attribute in sorted(entity.attributes):
        for cue in _attribute_cues(attribute):
            for match in re.finditer(r"(?<!\w)" + cue + r"(?!\w)", text, re.I):
                word_count = len(attribute.split("_"))
                mentions.append((match.start(), match.end(), attribute, word_count))
    # Prefer exact full-attribute mentions over a shared final-word cue.
    return sorted(mentions, key=lambda item: (item[0], -item[3], -(item[1] - item[0]), item[2]))


def _value_spans(text: str, entity_mentions: list[tuple[int, int, EntityReference]],
                 known_units: Mapping[str, str]) -> list[_SpanValue]:
    values: list[_SpanValue] = []
    for match in _NUMBER_RE.finditer(text):
        start, end = match.span()
        raw_number = match.group()
        before = text[max(0, start - 12):start]
        after = text[end:min(len(text), end + 50)]
        grouped_integer = re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw_number) is not None
        currency_adjacent = bool(re.search(r"(?:US\$|€|\$|£|\b(?:EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD|euros?|dollars?|lei)\s*)$", before, re.I)
                                or re.match(r"\s*(?:€|\$|£|\b(?:EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD|euros?|dollars?|lei)\b)", after, re.I))
        comma_decimal = "," in raw_number and not grouped_integer and currency_adjacent
        if "," in raw_number and not grouped_integer and not comma_decimal:
            continue
        number = _number(raw_number, decimal_comma=comma_decimal)
        op = _operator_before(text, start) or _operator_after(text, end)
        if _is_approximate(text, start, end):
            continue
        around = text[max(0, start - 20):min(len(text), end + 50)]
        magnitude_match = re.match(r"\s*(million|billion|trillion|thousand|bn|[kKmMbB])\b", after, re.I)
        if magnitude_match:
            multiplier = int(_MAGNITUDES[magnitude_match.group(1).casefold()])
            scaled = number * multiplier
            number = scaled if isinstance(scaled, int) else int(scaled) if scaled.is_integer() else scaled
        # A year adjacent to a named entity is part of its name, not a value.
        is_entity_year = 1900 <= number <= 2099 and any(a <= start and end <= b for a, b, _ in entity_mentions)
        if is_entity_year:
            continue
        if re.match(r"\s*(?:%|percent\b|per cent\b)", after, re.I):
            suffix = re.match(r"\s*(?:%|percent\b|per cent\b)", after, re.I)
            values.append(_SpanValue(TypedValue("percent", number, op=op), start, end + (suffix.end() if suffix else 0)))
            continue
        cur_match = re.search(r"(US\$|€|\$|£|\b(?:EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD)\b)\s*$", before, re.I)
        cur_after = re.match(r"\s*(€|\$|£|\b(?:EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD)\b|euros?\b|dollars?\b|lei\b)", after, re.I)
        currency = _CURRENCY.get(cur_match.group(1).upper() if cur_match else "") if cur_match else None
        if cur_match and cur_match.group(1) in {"€", "$", "£", "US$"}:
            currency = _CURRENCY[cur_match.group(1)]
        elif cur_after:
            unit_text = cur_after.group(1)
            currency = _CURRENCY.get(unit_text.upper()) or {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}.get(unit_text.casefold())
        if currency:
            per = None
            period_match = _PERIOD.search(around)
            if period_match:
                period_text = period_match.group().casefold()
                if any(x in period_text for x in ("month", "mo", "monthly")): per = "month"
                elif any(x in period_text for x in ("week",)): per = "week"
                elif any(x in period_text for x in ("day",)): per = "day"
                elif any(x in period_text for x in ("year", "yr", "annum", "annually")): per = "year"
            values.append(_SpanValue(TypedValue("money", number, currency=currency, per=per, op=op), start, end))
            continue
        # Explicit day/month/year forms with a calendar month or ISO date.
        date_match = re.search(r"\b(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?\b", text[start:], re.I)
        if date_match and date_match.start() == 0 and not re.match(r"\s*(?:%|percent|GB|MB|TB|kg|mm|cm|km|mAh)\b", after, re.I):
            raw = date_match.group()
            if len(raw) >= 4 and 1900 <= number <= 2099:
                values.append(_SpanValue(TypedValue("date", raw, op=op), start, start + len(raw)))
                continue
        version_prefix = re.search(r"\b(?:v|version)\s*$", before, re.I)
        if version_prefix:
            version_match = re.match(r"\d+(?:\.\d+){0,3}", text[start:])
            if version_match:
                values.append(_SpanValue(TypedValue("version", version_match.group(), op=op), start, start + len(version_match.group())))
                continue
        duration_unit = re.match(r"\s*(ms|milliseconds?|s|seconds?|min(?:utes?)?|h|hours?|days?|weeks?|months?|years?)\b", after, re.I)
        if duration_unit:
            unit = duration_unit.group(1).casefold()
            canonical = "ms" if unit.startswith("milli") or unit == "ms" else "s" if unit.startswith("second") or unit == "s" else "min" if unit.startswith("min") else "h" if unit.startswith("hour") or unit == "h" else next((x for x in ("day", "week", "month", "year") if unit.startswith(x)), "")
            values.append(_SpanValue(TypedValue("duration", number, unit=canonical, op=op), start, end + duration_unit.end()))
            continue
        # Numeric values paired with a nearby counted noun or physical unit.
        unit_match = None
        words = list(re.finditer(r"[A-Za-z][A-Za-z0-9_]*\b", after))
        for index, word in enumerate(words[:4]):
            token = word.group()
            canonical = known_units.get(_singular(token).casefold())
            gap = after[:word.start()]
            modifiers = [x.casefold() for x in re.findall(r"[A-Za-z]+", gap)]
            if canonical and len(modifiers) <= 2 and all(x in {"of", "our", "paying", "active", "premium", "total", "new", "free", "unique", "registered", "supported", "available", "listed", "concurrent", "included", "successful", "daily", "or", "more", "less", "million", "billion", "thousand", "k", "m", "bn"} for x in modifiers):
                unit_match = (word, canonical)
                break
            if index == 0 and not canonical and not modifiers and token.casefold() not in {"or", "more", "less", "than", "month", "monthly", "year", "annually", "week", "day", "per", "percent", "million", "billion", "trillion", "thousand", "k", "m", "bn"}:
                unit_match = (word, _singular(token))
                break
        if unit_match:
            word, unit = unit_match
            values.append(_SpanValue(TypedValue("quantity", number, unit=unit, op=op), start, end + word.end()))
    # Date phrases such as "12 March 2026" and "March 2026".
    for match in re.finditer(r"\b(?:(\d{1,2})\s+)?(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", text, re.I):
        day, month_name, year = match.groups()
        month = _MONTHS[month_name.casefold()]
        raw = f"{year}-{month:02d}" + (f"-{int(day):02d}" if day else "")
        op = _operator_before(text, match.start()) or _operator_after(text, match.end())
        values.append(_SpanValue(TypedValue("date", raw, op=op), match.start(), match.end()))
    # Name values are only extracted when a different lexicon entity is explicit.
    for start, end, entity in entity_mentions:
        values.append(_SpanValue(TypedValue("name", entity.name), start, end))
    unique: dict[tuple[int, int, tuple[object, ...]], _SpanValue] = {}
    for item in values:
        unique[(item.start, item.end, item.value.key())] = item
    return sorted(unique.values(), key=lambda item: (item.start, item.end))


def _boolean_value(text: str, start: int, end: int) -> bool | None:
    context = text[max(0, start - 32):min(len(text), end + 32)].casefold()
    if re.search(r"\b(?:not|never|no|without|isn't|aren't|doesn't|didn't|hasn't|haven't|wasn't|weren't)\b", context):
        return False
    return True


class TextFactParser:
    """Extract explicit fact candidates; extraction alone never verifies them."""

    def __init__(self, lexicon: Lexicon, attribute_kinds: Mapping[str, str] | None = None,
                 known_units: Iterable[str] = ()):
        self.lexicon = lexicon
        self.attribute_kinds = dict(attribute_kinds or {})
        self.known_units: dict[str, str] = {}
        for unit in sorted(set(known_units), key=str.casefold):
            self.known_units.setdefault(unit.casefold(), unit)
            singular = _singular(unit)
            self.known_units.setdefault(singular.casefold(), singular)

    def parse(self, text: str) -> ExtractionResult:
        if not isinstance(text, str) or not text.strip():
            return ExtractionResult((), ParseStatus.UNPARSED, 0.0, ("empty text",))
        facts: list[AtomicFact] = []
        issues: list[str] = []
        mentions = _entity_mentions(text, self.lexicon)
        spans = _value_spans(text, mentions, self.known_units)
        for sentence_match in re.finditer(r"[^\n]+?(?:[.!?](?=\s|$)|$)", text):
            sentence = sentence_match.group()
            sentence_start = sentence_match.start()
            local_entities = [(a, b, entity) for a, b, entity in mentions if sentence_start <= a < sentence_start + len(sentence)]
            local_values = [v for v in spans if sentence_start <= v.start < sentence_start + len(sentence)]
            if not local_entities:
                continue
            local_entity_starts = [a - sentence_start for a, _, _ in local_entities]
            boundaries = [0, len(sentence)]
            for separator in re.finditer(r",\s*(?:(?:and|while|whereas|but)\s+)?|\b(?:and|while|whereas|but)\s+", sentence, re.I):
                if any(separator.end() <= position <= separator.end() + 40 for position in local_entity_starts):
                    boundaries.append(separator.end())
            boundaries = sorted(set(boundaries))
            for entity_start, entity_end, entity in local_entities:
                local_start, local_end = entity_start - sentence_start, entity_end - sentence_start
                clause_start = max((point for point in boundaries if point <= local_start), default=0)
                clause_end = min((point for point in boundaries if point > local_start), default=len(sentence))
                clause = sentence[clause_start:clause_end]
                all_attr_mentions = _attribute_mentions(clause, entity)
                nearest_attr: dict[str, tuple[int, int, str, int]] = {}
                for mention in all_attr_mentions:
                    current = nearest_attr.get(mention[2])
                    if current is None or _distance(local_start, local_end, mention[0], mention[1]) < _distance(local_start, local_end, current[0], current[1]):
                        nearest_attr[mention[2]] = mention
                attr_mentions = [(a + clause_start, b + clause_start, name, specificity)
                                 for a, b, name, specificity in nearest_attr.values()]
                clause_values = [v for v in local_values if clause_start + sentence_start <= v.start < clause_end + sentence_start]
                for attr_start, attr_end, attribute, _specificity in attr_mentions:
                    if attribute in {"date", "version"} and not local_values:
                        continue
                    hint = self.attribute_kinds.get(attribute)
                    if hint == "boolean":
                        truth = _boolean_value(sentence, attr_start, attr_end)
                        if truth is not None:
                            facts.append(AtomicFact(entity.name, attribute, TypedValue("boolean", truth), entity.name))
                        continue
                    possible = [v for v in clause_values if (hint is None or v.value.kind == hint)
                                and not (v.value.kind == "name" and v.value.value == entity.name)]
                    # Avoid reusing values belonging to another explicit entity when the sentence has several.
                    owned = [v for v in possible if v.value.kind == "name" or not any(
                        a < v.start < b and other.name != entity.name for a, b, other in local_entities
                    )]
                    if not owned:
                        continue
                    value = min(owned, key=lambda v: _distance(attr_start, attr_end, v.start, v.end))
                    if value.value.kind == "name" and value.value.value == entity.name:
                        continue
                    facts.append(AtomicFact(entity.name, attribute, value.value, text[entity_start:entity_end]))
        dedup: dict[tuple[object, ...], AtomicFact] = {}
        for fact in facts:
            dedup[(fact.subject, fact.attribute, fact.value.key())] = fact
        facts = list(dedup.values())
        if not facts:
            return ExtractionResult((), ParseStatus.UNPARSED, 0.0, ("no high-specificity subject/attribute/value pattern found",))
        # Attribute-name-only matches are candidates and are deliberately not called complete.
        status = ParseStatus.PARTIAL
        confidence = 0.55
        return ExtractionResult(tuple(facts), status, confidence, tuple(issues))


def _distance(a: int, b: int, c: int, d: int) -> int:
    return max(0, c - b, a - d)
