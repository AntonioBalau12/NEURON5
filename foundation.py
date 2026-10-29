"""Contract-first data ingestion, canonical evidence, and output validation.

The module uses only the Python standard library. The JSON Schema validator
supports the keywords used by the checked-in Draft 2020-12 contracts.
"""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field, replace
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping


OUTPUT_COLUMNS = ("id", "type", "text", "form", "label", "confidence")
CLAIM_TYPES = {"fact", "compare", "change", "at_event", "relation"}
LABELS = {"true", "false", "unsure"}
CLAIM_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class TypedValue:
    kind: str
    value: Any
    unit: str | None = None
    currency: str | None = None
    per: str | None = None
    op: str | None = None

    @classmethod
    def parse(cls, raw: Any) -> tuple[TypedValue | None, str | None]:
        if not isinstance(raw, Mapping):
            return None, "value is not an object"
        kind = raw.get("kind")
        if not isinstance(kind, str) or kind not in {"quantity", "money", "percent", "date", "version", "duration", "name", "boolean"}:
            return None, f"unknown or missing value kind: {kind!r}"
        return cls(kind, raw.get("value"), raw.get("unit"), raw.get("currency"), raw.get("per"), raw.get("op")), None

    def key(self) -> tuple[Any, ...]:
        return (self.kind, self.value, self.unit, self.currency, self.per, self.op)


@dataclass(frozen=True)
class AtomicFact:
    subject: str
    attribute: str
    value: TypedValue
    subject_spelling: str | None = None


@dataclass(frozen=True)
class EntityReference:
    name: str
    aliases: tuple[str, ...]
    attributes: frozenset[str]


@dataclass(frozen=True)
class Lexicon:
    entities: tuple[EntityReference, ...]
    events: tuple[str, ...]
    aliases: Mapping[str, tuple[EntityReference, ...]]

    @staticmethod
    def normalize_name(value: str) -> str:
        return re.sub(r"[\s-]+", "", value.casefold())

    @classmethod
    def parse(cls, raw: Any) -> tuple[Lexicon | None, list[str]]:
        issues: list[str] = []
        if not isinstance(raw, Mapping) or not isinstance(raw.get("subjects"), list) or not isinstance(raw.get("events"), list):
            return None, ["lexicon must contain subject and event arrays"]
        entities: list[EntityReference] = []
        aliases: dict[str, list[EntityReference]] = {}
        for i, obj in enumerate(raw["subjects"]):
            if not isinstance(obj, Mapping) or not isinstance(obj.get("name"), str) or not obj["name"].strip():
                issues.append(f"subjects[{i}] has no valid name")
                continue
            alias_raw = obj.get("aliases", [])
            attrs_raw = obj.get("attributes", [])
            if not isinstance(alias_raw, list) or not all(isinstance(x, str) and x.strip() for x in alias_raw):
                issues.append(f"subjects[{i}].aliases must be non-empty strings")
                alias_raw = []
            if not isinstance(attrs_raw, list) or not all(isinstance(x, str) for x in attrs_raw):
                issues.append(f"subjects[{i}].attributes must be strings")
                attrs_raw = []
            entity = EntityReference(obj["name"].strip(), tuple(x.strip() for x in alias_raw), frozenset(attrs_raw))
            entities.append(entity)
            for spelling in (entity.name, *entity.aliases):
                aliases.setdefault(cls.normalize_name(spelling), []).append(entity)
        for spelling, matches in aliases.items():
            if len({x.name for x in matches}) > 1:
                issues.append(f"ambiguous lexicon alias {spelling!r}: {', '.join(sorted({x.name for x in matches}))}")
        events = raw["events"]
        if not all(isinstance(x, str) and x.strip() for x in events):
            issues.append("events must be non-empty strings")
            events = [x for x in events if isinstance(x, str) and x.strip()]
        return cls(tuple(entities), tuple(events), {k: tuple(v) for k, v in aliases.items()}), issues

    def resolve(self, spelling: str) -> EntityReference | None:
        matches = self.aliases.get(self.normalize_name(spelling), ())
        return matches[0] if len({x.name for x in matches}) == 1 else None

    def valid_attribute(self, subject: str, attribute: str) -> bool:
        entity = self.resolve(subject)
        return entity is not None and attribute in entity.attributes


@dataclass(frozen=True)
class EvidenceRecord:
    row_id: str
    label: str | None
    date: date | None
    facts: tuple[AtomicFact, ...]
    text: str
    parse_status: str
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemporalObservation:
    fact: AtomicFact
    observed_on: date
    row_id: str
    evidence_status: str
    provenance: str


@dataclass(frozen=True)
class CandidateFact:
    fact: AtomicFact
    as_of: date
    evidence_status: str
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class ClaimCandidate:
    id: str
    type: str
    text: str
    form: Mapping[str, Any]
    label: str = "true"
    confidence: float = 0.5


@dataclass(frozen=True)
class VerificationResult:
    status: str
    confidence: float
    evidence_ids: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class InputData:
    rows: list[EvidenceRecord]
    lexicon: Lexicon | None
    issues: list[str] = field(default_factory=list)


def normalize_date(raw: Any) -> tuple[date | None, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, "missing date"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw.strip()):
        return None, f"invalid ISO date: {raw!r}"
    try:
        return date.fromisoformat(raw.strip()), None
    except ValueError:
        return None, f"invalid ISO date: {raw!r}"


def parse_evidence_form(raw: str, value_schema: SchemaValidator | None = None) -> tuple[tuple[AtomicFact, ...], list[str]]:
    issues: list[str] = []
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        return (), [f"invalid form JSON: {exc}"]
    if not isinstance(values, list):
        return (), ["practice form must be a JSON array"]
    facts: list[AtomicFact] = []
    for i, item in enumerate(values):
        if not isinstance(item, Mapping):
            issues.append(f"form[{i}] is not an object")
            continue
        if set(item) != {"subject", "attribute", "value"}:
            issues.append(f"form[{i}] must contain only subject, attribute, and value")
            continue
        subject, attribute = item.get("subject"), item.get("attribute")
        typed, err = TypedValue.parse(item.get("value"))
        if not isinstance(subject, str) or not subject.strip() or not isinstance(attribute, str) or not attribute.strip():
            issues.append(f"form[{i}] has an invalid subject or attribute")
            continue
        if err:
            issues.append(f"form[{i}]: {err}")
            continue
        if value_schema is None:
            issues.append(f"form[{i}]: claimed_value.schema.json is unavailable")
            continue
        value_errors = value_schema.validate(item["value"])
        if value_errors:
            issues.extend(f"form[{i}]: value schema {x}" for x in value_errors)
            continue
        facts.append(AtomicFact(subject.strip(), attribute.strip(), typed))
    return tuple(facts), issues


def load_inputs(universe_csv: str | Path, lexicon_json: str | Path) -> InputData:
    """Load read-only inputs; malformed rows are retained with parse status/issues."""
    issues: list[str] = []
    value_schema_path = Path(__file__).resolve().parent / "contracts" / "claimed_value.schema.json"
    value_schema = SchemaValidator(value_schema_path) if value_schema_path.is_file() else None
    try:
        with open(universe_csv, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames or []
            required = {"id", "text", "date", "label"}
            if not required.issubset(headers):
                raise ValueError(f"CSV missing required columns: {sorted(required - set(headers))}")
            rows: list[EvidenceRecord] = []
            seen_ids: set[str] = set()
            for line, row in enumerate(reader, start=2):
                row_issues: list[str] = []
                if None in row:
                    row_issues.append("row has extra CSV fields")
                row_id = (row.get("id") or "").strip()
                text = row.get("text") or ""
                if not row_id:
                    row_issues.append("missing id")
                elif row_id in seen_ids:
                    row_issues.append(f"duplicate input id: {row_id!r}")
                seen_ids.add(row_id)
                if not text.strip():
                    row_issues.append("missing text")
                when, date_issue = normalize_date(row.get("date"))
                if date_issue:
                    row_issues.append(date_issue)
                raw_label = (row.get("label") or "").strip().lower()
                label = raw_label or None
                if label is not None and label not in LABELS:
                    row_issues.append(f"invalid label: {raw_label!r}")
                    label = None
                facts: tuple[AtomicFact, ...] = ()
                if row.get("form") not in (None, ""):
                    facts, form_issues = parse_evidence_form(row["form"], value_schema)
                    row_issues.extend(form_issues)
                status = "ok" if not row_issues else "malformed"
                if row_issues:
                    issues.extend(f"CSV line {line}: {x}" for x in row_issues)
                rows.append(EvidenceRecord(row_id, label, when, facts, text, status, tuple(row_issues)))
    except (OSError, csv.Error, UnicodeError, ValueError) as exc:
        return InputData([], None, [f"cannot load universe CSV: {exc}"])
    try:
        with open(lexicon_json, "r", encoding="utf-8-sig") as handle:
            raw_lexicon = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return InputData(rows, None, issues + [f"cannot load lexicon JSON: {exc}"])
    lexicon, lex_issues = Lexicon.parse(raw_lexicon)
    issues.extend(f"lexicon: {x}" for x in lex_issues)
    if lexicon:
        checked_rows: list[EvidenceRecord] = []
        for row in rows:
            row_issues = list(row.issues)
            canonical_facts: list[AtomicFact] = []
            for fact in row.facts:
                entity = lexicon.resolve(fact.subject)
                if entity is None or fact.attribute not in entity.attributes:
                    message = f"unknown or ambiguous subject/attribute {fact.subject!r}.{fact.attribute}"
                    row_issues.append(message)
                    issues.append(f"row {row.row_id}: {message}")
                else:
                    canonical_facts.append(replace(fact, subject=entity.name, subject_spelling=fact.subject))
            checked_rows.append(replace(row, facts=tuple(canonical_facts), parse_status="malformed" if row_issues else "ok", issues=tuple(row_issues)))
        rows = checked_rows
    return InputData(rows, lexicon, issues)


def observations(data: InputData) -> list[TemporalObservation]:
    result: list[TemporalObservation] = []
    for row in data.rows:
        if row.date is None:
            continue
        status = {"true": "confirmed_true", "false": "row_false_atomic_status_unknown", "unsure": "row_unsure", None: "unlabelled"}[row.label]
        if row.parse_status != "ok": status = "malformed_row_unverified"
        result.extend(TemporalObservation(f, row.date, row.row_id, status, "practice.form" if f else "input") for f in row.facts)
    return result


def _fact_key(fact: AtomicFact) -> tuple[Any, ...]:
    return (fact.subject.casefold(), fact.attribute, fact.value.key())


def compare_values(left: TypedValue, right: TypedValue, op: str) -> bool | None:
    """Compare compatible typed scalar values; return None when incomparable."""
    if op not in {"gt", "lt", "eq"} or left.kind != right.kind or left.op is not None or right.op is not None:
        return None
    a, b = left.value, right.value
    if left.kind == "quantity":
        left_unit, right_unit = _quantity_unit(left.unit), _quantity_unit(right.unit)
        if left_unit is not None or right_unit is not None:
            if left_unit is None or right_unit is None or left_unit[0] != right_unit[0]: return None
            a, b = float(a) * left_unit[1], float(b) * right_unit[1]
        elif left.unit != right.unit:
            return None
    elif left.kind == "money":
        if left.currency != right.currency or left.per != right.per: return None
    elif left.kind == "duration":
        fixed = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800}
        calendar = {"month": 1, "year": 12}
        factors = fixed if left.unit in fixed and right.unit in fixed else calendar if left.unit in calendar and right.unit in calendar else None
        if factors is None: return None
        a, b = float(a) * factors[left.unit], float(b) * factors[right.unit]
    elif left.kind == "date":
        if not isinstance(a, str) or not isinstance(b, str): return None
        if len(a) != len(b): return None
    elif left.kind == "version":
        if not isinstance(a, str) or not isinstance(b, str): return None
        if op == "eq": return a == b
        try: a, b = tuple(int(x) for x in a.split(".")), tuple(int(x) for x in b.split("."))
        except ValueError: return None
    elif left.kind in {"boolean", "name"}:
        if op != "eq": return None
        if left.kind == "name": a, b = Lexicon.normalize_name(str(a)), Lexicon.normalize_name(str(b))
        return a == b
    if op == "eq": return a == b
    return a > b if op == "gt" else a < b


def evidence_audit(data: InputData, as_of: date = date(2026, 10, 29)) -> dict[str, Any]:
    """Summarize evidence conservatively; never infer falsity from a false row."""
    records = [o for o in observations(data) if o.evidence_status == "confirmed_true"]
    by_attribute: dict[tuple[str, str], list[TemporalObservation]] = {}
    for obs in records:
        by_attribute.setdefault((obs.fact.subject, obs.fact.attribute), []).append(obs)
    histories = {key: values for key, values in by_attribute.items()}
    distinct_values = {key: _distinct_value_keys([x.fact.value for x in values]) for key, values in histories.items()}
    confirmed_unique = {_fact_key(o.fact) for o in records}
    non_equivalent_same_day = 0
    raw_different_values_same_day = 0
    for values in histories.values():
        per_day: dict[date, list[TypedValue]] = {}
        for obs in values:
            per_day.setdefault(obs.observed_on, []).append(obs.fact.value)
        for same_date_values in per_day.values():
            unique = _distinct_value_keys(same_date_values)
            if len({x.key() for x in same_date_values}) > 1: raw_different_values_same_day += 1
            if len(unique) > 1: non_equivalent_same_day += 1
    # Strictly date-grounded as-of facts: there are none unless directly observed
    # on the claim as-of date. Historical records are not assumed to persist.
    as_of_direct = {k for k in confirmed_unique if any(o.observed_on == as_of and _fact_key(o.fact) == k for o in records)}
    by_date: dict[date, list[TemporalObservation]] = {}
    for observation in records:
        by_date.setdefault(observation.observed_on, []).append(observation)
    historical_compare_pairs: set[tuple[Any, ...]] = set()
    for day, day_records in by_date.items():
        for left, right in combinations(day_records, 2):
            if left.fact.subject == right.fact.subject and left.fact.attribute == right.fact.attribute:
                continue
            if compare_values(left.fact.value, right.fact.value, "eq") is not None:
                historical_compare_pairs.add((day, _fact_key(left.fact), _fact_key(right.fact)))
    historical_change_pairs: set[tuple[Any, ...]] = set()
    exact_historical_change_pairs: set[tuple[Any, ...]] = set()
    for key, values in histories.items():
        for earlier, later in combinations(values, 2):
            if earlier.observed_on != later.observed_on and not _same_observed_value(earlier.fact.value, later.fact.value):
                before, after = (earlier, later) if earlier.observed_on < later.observed_on else (later, earlier)
                change_key = (key, before.fact.value.key(), after.fact.value.key())
                historical_change_pairs.add(change_key)
                if before.fact.value.op is None and after.fact.value.op is None:
                    exact_historical_change_pairs.add(change_key)
    event_backed_facts = sum(
        len(row.facts) for row in data.rows if row.label == "true" and any(
            Lexicon.normalize_name(event) in Lexicon.normalize_name(row.text) for event in (data.lexicon.events if data.lexicon else ())
        )
    )
    same_day_relation_pairs: set[tuple[Any, ...]] = set()
    for day_records in by_date.values():
        name_links = [o for o in day_records if o.fact.value.kind == "name" and data.lexicon and data.lexicon.resolve(str(o.fact.value.value))]
        for link in name_links:
            target = data.lexicon.resolve(str(link.fact.value.value))
            same_day_relation_pairs.update(
                (link.observed_on, link.fact.subject, link.fact.attribute, target.name, target_fact.fact.attribute, target_fact.fact.value.key())
                for target_fact in day_records
                if target_fact.fact.subject == target.name and target_fact.fact.attribute and target_fact.fact.value.op is None
            )
    event_dates: dict[str, set[date]] = {}
    event_names = set(data.lexicon.events) if data.lexicon else set()
    for observation in records:
        fact = observation.fact
        if fact.subject in event_names and fact.attribute == "date" and fact.value.kind == "date" and fact.value.op is None:
            raw_date = fact.value.value
            if isinstance(raw_date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
                try: event_dates.setdefault(fact.subject, set()).add(date.fromisoformat(raw_date))
                except ValueError: pass
    event_date_fact_candidates: set[tuple[Any, ...]] = set()
    for event, days in event_dates.items():
        for event_day in days:
            for observation in by_date.get(event_day, ()):
                if observation.fact.value.op is None:
                    event_date_fact_candidates.add((event, observation.fact.subject, observation.fact.attribute, observation.fact.value.key()))
    return {
        "practice_rows": len(data.rows),
        "confirmed_true_atomic_observations": len(records),
        "distinct_true_subject_attribute_value": len(confirmed_unique),
        "distinct_true_subject_attribute_histories": len(histories),
        "attributes_with_multiple_observed_values": sum(len(v) > 1 for v in distinct_values.values()),
        "same_day_histories_with_non_equivalent_true_values": non_equivalent_same_day,
        "same_day_rows_with_different_value_serializations": raw_different_values_same_day,
        "historically_changed_subject_attribute_histories": sum(len(v) > 1 for v in distinct_values.values()),
        "historical_change_value_pairs": len(historical_change_pairs),
        "historical_change_value_pairs_with_exact_endpoints": len(exact_historical_change_pairs),
        "historical_comparison_pairs_observed_on_same_day": len(historical_compare_pairs),
        "true_facts_on_rows_mentioning_lexicon_events": event_backed_facts,
        "same_day_structural_relation_pairs": len(same_day_relation_pairs),
        "facts_directly_observed_on_as_of_date": len(as_of_direct),
        "historical_fact_upper_bound_without_validity_inference": len(confirmed_unique),
        "strict_as_of_fact_candidate_count": len(as_of_direct),
        "historical_candidate_upper_bounds_by_type": {
            "fact": len(as_of_direct),
            "compare": sum(1 for day, _, _ in historical_compare_pairs if day == as_of),
            "change": len(exact_historical_change_pairs),
            "at_event": len(event_date_fact_candidates),
            "relation": len(same_day_relation_pairs),
        },
        "false_row_atomic_observations_not_attributed_as_false": sum(o.evidence_status == "row_false_atomic_status_unknown" for o in observations(data)),
        "sure_true_fact_claims_from_practice_alone": len(as_of_direct),
        "guaranteed_1000_claims": False,
        "claim_generation_note": "Claims judged on the as-of date require evidence for that date; past true observations alone do not establish persistence.",
    }


def _same_observed_value(left: TypedValue, right: TypedValue) -> bool:
    if left.key() == right.key(): return True
    if left.kind != right.kind: return False
    if left.kind == "date" and isinstance(left.value, str) and isinstance(right.value, str):
        return left.value.startswith(right.value) or right.value.startswith(left.value)
    if left.kind == "name":
        return Lexicon.normalize_name(str(left.value)) == Lexicon.normalize_name(str(right.value))
    return compare_values(left, right, "eq") is True


def _distinct_value_keys(values: Iterable[TypedValue]) -> list[TypedValue]:
    unique: list[TypedValue] = []
    for value in values:
        if not any(_same_observed_value(value, existing) for existing in unique): unique.append(value)
    return unique


def _quantity_unit(unit: str | None) -> tuple[str, float] | None:
    """Return dimension and SI-like scale for units explicitly listed by value-forms."""
    if not isinstance(unit, str): return None
    data = {"B": 1, "KB": 1e3, "kB": 1e3, "kb": 1e3, "MB": 1e6, "mb": 1e6,
            "GB": 1e9, "gb": 1e9, "TB": 1e12, "tb": 1e12,
            "byte": 1, "kilobyte": 1e3, "megabyte": 1e6, "gigabyte": 1e9, "gig": 1e9, "terabyte": 1e12}
    length = {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000, "in": 0.0254,
              "millimetre": 0.001, "millimeter": 0.001, "centimetre": 0.01, "centimeter": 0.01,
              "metre": 1, "meter": 1, "kilometre": 1000, "kilometer": 1000, "inch": 0.0254}
    mass = {"g": 1, "kg": 1000, "gram": 1, "gramme": 1, "kilogram": 1000, "kilo": 1000}
    frequency = {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9, "hertz": 1, "kilohertz": 1e3, "megahertz": 1e6, "gigahertz": 1e9}
    power = {"mW": 0.001, "W": 1, "kW": 1000, "milliwatt": 0.001, "watt": 1, "kilowatt": 1000}
    for dim, units in (("data", data), ("length", length), ("mass", mass), ("frequency", frequency), ("power", power)):
        if unit in units: return dim, units[unit]
    return None


class SchemaValidator:
    """Small validator for the JSON Schema keywords used by contracts/*.json."""

    def __init__(self, schema_path: str | Path):
        self.path = Path(schema_path).resolve()
        self.root = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self._documents = {self.path: self.root}

    def _resolve(self, ref: str, base: Path) -> tuple[dict[str, Any], Path]:
        file_part, _, pointer = ref.partition("#")
        target_path = (base.parent / file_part).resolve() if file_part else base
        if target_path not in self._documents:
            self._documents[target_path] = json.loads(target_path.read_text(encoding="utf-8-sig"))
        schema = self._documents[target_path]
        if pointer:
            for part in pointer.lstrip("/").split("/"):
                part = part.replace("~1", "/").replace("~0", "~")
                schema = schema[part]
        return schema, target_path

    def validate(self, instance: Any) -> list[str]:
        errors: list[str] = []
        self._check(instance, self.root, self.path, "$", errors)
        return errors

    def _check(self, value: Any, schema: Mapping[str, Any], base: Path, path: str, errors: list[str]) -> None:
        if "$ref" in schema:
            target, target_base = self._resolve(schema["$ref"], base)
            self._check(value, target, target_base, path, errors)
        types = schema.get("type")
        type_map = {"object": lambda x: isinstance(x, dict), "array": lambda x: isinstance(x, list), "string": lambda x: isinstance(x, str), "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and (isinstance(x, int) or math.isfinite(x)), "integer": lambda x: isinstance(x, int) and not isinstance(x, bool), "boolean": lambda x: isinstance(x, bool), "null": lambda x: x is None}
        if types and not type_map[types](value):
            errors.append(f"{path}: expected {types}")
            return
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: value is not in enum")
        if "const" in schema and value != schema["const"]:
            errors.append(f"{path}: value does not match const")
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]: errors.append(f"{path}: string too short")
            if "maxLength" in schema and len(value) > schema["maxLength"]: errors.append(f"{path}: string too long")
            if "pattern" in schema and re.search(schema["pattern"], value) is None: errors.append(f"{path}: pattern mismatch")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]: errors.append(f"{path}: below minimum")
            if "maximum" in schema and value > schema["maximum"]: errors.append(f"{path}: above maximum")
        if isinstance(value, dict):
            for key in schema.get("required", []):
                if key not in value: errors.append(f"{path}: missing required property {key!r}")
            props = schema.get("properties", {})
            for key, child in value.items():
                if key in props:
                    self._check(child, props[key], base, f"{path}.{key}", errors)
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{path}: unexpected property {key!r}")
        if "not" in schema:
            nested: list[str] = []
            self._check(value, schema["not"], base, path, nested)
            if not nested: errors.append(f"{path}: matches a forbidden schema")
        for child in schema.get("allOf", []):
            self._check(value, child, base, path, errors)
        condition = schema.get("if")
        if condition is not None:
            matched: list[str] = []
            self._check(value, condition, base, path, matched)
            branch = schema.get("then") if not matched else schema.get("else")
            if branch: self._check(value, branch, base, path, errors)


def _name_in_text(name: str, text: str) -> bool:
    pattern = _flexible_name_pattern(name)
    if not pattern: return False
    pattern = r"(?<!\w)" + pattern + r"(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _flexible_name_pattern(name: str) -> str:
    parts = re.findall(r"[^\W\d_]+|\d+|[^\w\s]", name, flags=re.UNICODE)
    return r"[\s-]*".join(re.escape(part) for part in parts)


def _entity_name_in_text(name: str, text: str, lexicon: Lexicon) -> bool:
    return _entity_name_position(name, text, lexicon) is not None


def _entity_name_position(name: str, text: str, lexicon: Lexicon) -> int | None:
    entity = lexicon.resolve(name)
    if entity is None: return None
    matches: list[tuple[int, int, str]] = []
    for candidate in lexicon.entities:
        for spelling in (candidate.name, *candidate.aliases):
            pattern = _flexible_name_pattern(spelling)
            if not pattern: continue
            pattern = r"(?<!\w)" + pattern + r"(?!\w)"
            matches.extend((m.start(), m.end(), candidate.name) for m in re.finditer(pattern, text, flags=re.IGNORECASE))
    longest = [m for m in matches if not any(other[0] <= m[0] and other[1] >= m[1] and (other[1] - other[0]) > (m[1] - m[0]) for other in matches)]
    positions = [start for start, _, found_name in longest if found_name == entity.name]
    return min(positions) if positions else None


def validate_claim_text(claim_type: str, text: str, form: Mapping[str, Any], lexicon: Lexicon) -> list[str]:
    """Check deterministic name/type cues; full natural-language reading is manual/referee work."""
    problems: list[str] = []
    if claim_type == "compare":
        left, right = form.get("left", {}), form.get("right", {})
        left_position = _entity_name_position(str(left.get("subject", "")), text, lexicon) if isinstance(left, Mapping) else None
        right_position = _entity_name_position(str(right.get("subject", "")), text, lexicon) if isinstance(right, Mapping) else None
        if left_position is None or right_position is None:
            problems.append("compare text must name both subjects")
        elif left_position > right_position:
            problems.append("compare text must name the left subject before the right subject")
        phrases = {"gt": ("more", "higher", "greater", "larger", "bigger", "longer", "later", "after", "exceed"), "lt": ("less", "fewer", "lower", "smaller", "shorter", "cheaper", "earlier", "before"), "eq": ("as much", "as many", "as long", "as high", "the same", "same day", "equal")}
        op = form.get("op")
        if not any(x in text.casefold() for x in phrases.get(op, ())): problems.append("compare text lacks an obvious phrase for its op")
        return problems
    subject = form.get("subject")
    if not isinstance(subject, str) or not _entity_name_in_text(subject, text, lexicon):
        problems.append("claim text must name its subject")
    if claim_type == "change":
        lowered = text.casefold()
        has_from_to = "from" in lowered and " to " in f" {lowered} "
        has_to_updown = "up from" in lowered or "down from" in lowered
        if not (has_from_to or has_to_updown): problems.append("change text lacks a published change phrase")
        from_value, to_value = form.get("from"), form.get("to")
        if (isinstance(from_value, Mapping) and isinstance(to_value, Mapping)
                and from_value.get("kind") == to_value.get("kind") == "boolean"):
            match = re.search(r"(?<!\w)from\s+(.+?\b(?:false|true))\s+to\s+(.+?\b(?:false|true))\.?\s*$",
                              text, flags=re.IGNORECASE)
            if from_value.get("value") is to_value.get("value"):
                problems.append("Boolean change endpoints must differ")
            elif match is None:
                problems.append("Boolean change must state both from and to sides")
            else:
                attribute_words = str(form.get("attribute", "")).replace("_", " ")
                for side, endpoint, label in ((match.group(1), from_value, "from"),
                                              (match.group(2), to_value, "to")):
                    if not _name_in_text(attribute_words, side):
                        problems.append(f"Boolean change {label} side omits the attribute words")
                    negative = re.search(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|\w+n['’]t\b",
                                         side, flags=re.IGNORECASE) is not None
                    says_false = re.search(r"(?<!\w)false(?!\w)", side, flags=re.IGNORECASE) is not None
                    says_true = re.search(r"(?<!\w)true(?!\w)", side, flags=re.IGNORECASE) is not None
                    expected_false = endpoint.get("value") is False
                    if not ((says_false and not says_true and not negative)
                            or (expected_false and negative and not says_true)
                            or (not expected_false and not negative and not says_false)):
                        problems.append(f"Boolean change {label} side has the wrong polarity")
    attr = form.get("attribute")
    if isinstance(attr, str) and isinstance(form.get("value"), Mapping) and form["value"].get("kind") == "boolean":
        words = attr.replace("_", " ").casefold()
        if not _name_in_text(words, text): problems.append("yes/no claim text must state the attribute in words")
        negative = re.search(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|\w+n['’]t\b", text, flags=re.IGNORECASE) is not None
        if bool(form["value"].get("value")) == negative:
            problems.append("yes/no claim polarity does not match its boolean value")
    values: list[Mapping[str, Any]] = []
    if claim_type in {"fact", "at_event", "relation"} and isinstance(form.get("value"), Mapping):
        values.append(form["value"])
    elif claim_type == "change":
        values.extend(v for v in (form.get("from"), form.get("to")) if isinstance(v, Mapping))
    for value in values:
        if value.get("kind") in {"quantity", "money", "percent", "duration"} and not _number_is_mentioned(value.get("value"), text, lexicon):
            problems.append("claim text does not contain the form's numeric value")
        elif value.get("kind") == "version" and not _name_in_text(str(value.get("value", "")), text):
            problems.append("claim text does not contain the form's version")
        elif value.get("kind") == "name":
            named = str(value.get("value", ""))
            present = _entity_name_in_text(named, text, lexicon) if lexicon.resolve(named) else _name_in_text(named, text)
            if not present: problems.append("claim text does not contain the form's name value")
    if claim_type == "at_event":
        event_pattern = _flexible_name_pattern(str(form.get("event", "")))
        phrase_pattern = rf"(?<!\w)(?:at|during)\s+(?:the\s+)?{event_pattern}(?!\w)|(?<!\w)on\s+the\s+day\s+of\s+{event_pattern}(?!\w)|(?<!\w)at\s+the\s+time\s+of\s+{event_pattern}(?!\w)"
        if not event_pattern or re.search(phrase_pattern, text, flags=re.IGNORECASE) is None:
            problems.append("at_event text lacks a published event phrase")
    if claim_type == "relation":
        relation_words = str(form.get("link", "")).replace("_", " ")
        relation_key = re.sub(r"[\s-]+", "", relation_words.casefold())
        text_key = re.sub(r"[\s-]+", "", text.casefold())
        if not relation_key or relation_key not in text_key:
            problems.append("relation text lacks the link's relation words")
    return problems


def _number_is_mentioned(value: Any, text: str, lexicon: Lexicon) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool): return True
    searchable = text
    for entity in sorted(lexicon.entities, key=lambda e: len(e.name), reverse=True):
        for spelling in sorted((entity.name, *entity.aliases), key=len, reverse=True):
            pattern = _flexible_name_pattern(spelling)
            if pattern:
                searchable = re.sub(r"(?<!\w)" + pattern + r"(?!\w)", lambda m: " " * len(m.group()), searchable, flags=re.IGNORECASE)
    # Written number words are supported by the referee, but this lightweight
    # check cannot decode them. If no digits occur, leave that case to the referee.
    if not re.search(r"\d", searchable): return True
    number = f"{value:g}" if isinstance(value, float) else str(value)
    variants = {number}
    if isinstance(value, (int, float)) and float(value).is_integer():
        variants.add(f"{int(value):,}")
    elif isinstance(value, float):
        variants.add(f"{value:,.{max(0, len(number.partition('.')[2]))}f}")
    for variant in variants:
        if re.search(rf"(?<![\w.]){re.escape(variant)}(?!\w|\.(?=\d))", searchable): return True
        if isinstance(value, float) and "." in variant:
            comma_variant = variant.replace(".", ",")
            if re.search(rf"(?<![\w.]){re.escape(comma_variant)}(?![\w.])", searchable): return True
    return False


def validate_output(path: str | Path, input_data: InputData, contract_dir: str | Path, expected_claims: int = 1000) -> list[str]:
    problems: list[str] = []
    p = Path(path)
    if not p.is_file(): return ["output CSV does not exist"]
    try:
        if p.stat().st_size > 16 * 1024 * 1024: return ["output CSV exceeds 16 MiB"]
    except OSError as exc:
        return [f"cannot inspect output CSV: {exc}"]
    try:
        with p.open("r", encoding="utf-8-sig", newline="") as handle:
            first_line = handle.readline()
            handle.seek(0)
            delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
            reader = csv.DictReader(handle, strict=True, delimiter=delimiter)
            fields = reader.fieldnames or []
            if len(fields) != len(OUTPUT_COLUMNS) or set(fields) != set(OUTPUT_COLUMNS):
                return problems + [f"output columns must be {OUTPUT_COLUMNS} in any order"]
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return problems + [f"invalid output CSV: {exc}"]
    seen_ids: set[str] = set()
    input_ids = {r.row_id for r in input_data.rows}
    blank_ids = {r.row_id for r in input_data.rows if r.label is None}
    input_texts = {" ".join(r.text.casefold().split()).rstrip(".!? ") for r in input_data.rows}
    claims: list[dict[str, str]] = []
    labels: dict[str, dict[str, str]] = {}
    for i, row in enumerate(rows, start=2):
        if None in row: problems.append(f"line {i}: extra CSV fields")
        if any(value is None for value in row.values()): problems.append(f"line {i}: missing CSV fields")
        rid = (row.get("id") or "").strip()
        if not CLAIM_ID.fullmatch(rid): problems.append(f"line {i}: invalid id")
        if rid in seen_ids: problems.append(f"line {i}: duplicate id {rid!r}")
        seen_ids.add(rid)
        kind = (row.get("type") or "").strip()
        if not kind:
            label = (row.get("label") or "").strip().lower()
            confidence = (row.get("confidence") or "").strip()
            if (row.get("text") or "").strip() or (row.get("form") or "").strip():
                problems.append(f"line {i}: label row must have empty text and form")
            if rid not in input_ids: problems.append(f"line {i}: label id is not in input")
            elif rid not in blank_ids: problems.append(f"line {i}: label id already has an input label")
            if label not in LABELS: problems.append(f"line {i}: invalid label")
            if label == "unsure":
                if confidence: problems.append(f"line {i}: unsure confidence must be empty")
            else:
                c = _parse_number(confidence, decimal_comma=(delimiter == ";"))
                if c is None: c = -1
                if not 0.5 <= c <= 1: problems.append(f"line {i}: confidence must be 0.5..1")
            labels[rid] = row
        else:
            claims.append(row)
    for r in input_data.rows:
        if r.label is None and r.row_id not in labels: problems.append(f"missing label row for {r.row_id!r}")
    if len(claims) != expected_claims: problems.append(f"expected {expected_claims} claims, found {len(claims)}")
    entry_validator = SchemaValidator(Path(contract_dir) / "entry.schema.json")
    if input_data.lexicon is None: problems.append("cannot validate claim names without a valid lexicon")
    seen_claim_texts: set[str] = set()
    seen_claim_keys: set[tuple[Any, ...]] = set()
    for i, row in enumerate(claims, start=2):
        try: form = json.loads(row.get("form") or "")
        except json.JSONDecodeError:
            problems.append(f"claim line {i}: form is not valid JSON")
            continue
        entry = {"id": row.get("id"), "type": row.get("type"), "text": row.get("text"), "form": form, "tag": (row.get("label") or "true").strip().lower(), "confidence": _parse_number(row.get("confidence"), decimal_comma=(delimiter == ";"))}
        if entry["confidence"] is None: problems.append(f"claim line {i}: invalid confidence")
        schema_errors = entry_validator.validate(entry)
        for error in schema_errors: problems.append(f"claim line {i}: schema {error}")
        if schema_errors: continue
        if not isinstance(form, dict):
            continue
        if "label" in row and (row.get("label") or "true").strip().lower() != "true": problems.append(f"claim line {i}: claims must be true")
        normalized_text = " ".join((row.get("text") or "").casefold().split()).rstrip(".!? ")
        if normalized_text in input_texts: problems.append(f"claim line {i}: duplicate of input text")
        if normalized_text in seen_claim_texts: problems.append(f"claim line {i}: duplicate claim text")
        seen_claim_texts.add(normalized_text)
        if input_data.lexicon:
            claim_key = _claim_semantic_key(row.get("type", ""), form, input_data.lexicon)
            if claim_key is not None and claim_key in seen_claim_keys:
                problems.append(f"claim line {i}: semantically duplicate claim")
            if claim_key is not None: seen_claim_keys.add(claim_key)
            _validate_form_names(row.get("type", ""), form, input_data.lexicon, i, problems)
            problems.extend(f"claim line {i}: {x}" for x in validate_claim_text(row.get("type", ""), row.get("text", ""), form, input_data.lexicon))
    return problems


def _parse_number(raw: str | None, decimal_comma: bool = False) -> float | None:
    try:
        if raw is None or not raw.strip(): return None
        number = raw.strip()
        if decimal_comma:
            if number.count(",") > 1 or "." in number: return None
            number = number.replace(",", ".")
        value = float(number)
        return value if value is not None and math.isfinite(value) else None
    except ValueError: return None


def _canonical_name_key(name: Any, lexicon: Lexicon) -> str:
    if not isinstance(name, str): return str(name)
    entity = lexicon.resolve(name)
    return entity.name.casefold() if entity else Lexicon.normalize_name(name)


def _canonical_value_key(value: Any, lexicon: Lexicon) -> tuple[Any, ...] | None:
    if not isinstance(value, Mapping): return None
    kind, raw = value.get("kind"), value.get("value")
    if kind == "quantity":
        unit = _quantity_unit(value.get("unit"))
        if unit:
            try:
                number = float(raw)
                if not math.isfinite(number): return None
                return kind, unit[0], round(number * unit[1], 9), value.get("op")
            except (TypeError, ValueError, OverflowError): return None
        return kind, raw, value.get("unit"), value.get("op")
    if kind == "duration":
        fixed = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "day": 86400, "week": 604800}
        calendar = {"month": 1, "year": 12}
        if value.get("unit") in fixed or value.get("unit") in calendar:
            try:
                number = float(raw)
                if not math.isfinite(number): return None
                if value.get("unit") in fixed: return kind, "fixed", round(number * fixed[value["unit"]], 9), value.get("op")
                return kind, "calendar_month", number * calendar[value["unit"]], value.get("op")
            except (TypeError, ValueError, OverflowError): return None
    if kind == "name": return kind, _canonical_name_key(raw, lexicon)
    if kind == "money": return kind, raw, value.get("currency"), value.get("per"), value.get("op")
    if kind in {"percent", "date", "version", "boolean"}: return kind, raw, value.get("op")
    return None


def _claim_semantic_key(kind: str, form: Mapping[str, Any], lexicon: Lexicon) -> tuple[Any, ...] | None:
    def ref(value: Any) -> tuple[str, str] | None:
        if not isinstance(value, Mapping): return None
        subject, attribute = value.get("subject"), value.get("attribute")
        if not isinstance(subject, str) or not isinstance(attribute, str): return None
        return _canonical_name_key(subject, lexicon), attribute

    def val(value: Any) -> tuple[Any, ...] | None:
        return _canonical_value_key(value, lexicon)

    if kind == "fact":
        r, v = ref(form), val(form.get("value"))
        return (kind, r, v) if r and v else None
    if kind == "change":
        r, before, after = ref(form), val(form.get("from")), val(form.get("to"))
        return (kind, r, before, after) if r and before and after else None
    if kind == "at_event":
        r, v, event = ref(form), val(form.get("value")), form.get("event")
        return (kind, r, Lexicon.normalize_name(event), v) if r and v and isinstance(event, str) else None
    if kind == "relation":
        subject = ref({"subject": form.get("subject"), "attribute": form.get("link")})
        target = ref({"subject": form.get("target"), "attribute": form.get("attribute")})
        v = val(form.get("value"))
        return (kind, subject, target, v) if subject and target and v else None
    if kind == "compare":
        left, right = ref(form.get("left")), ref(form.get("right"))
        op = form.get("op")
        if not left or not right or op not in {"gt", "lt", "eq"}: return None
        if op == "eq": return (kind, "eq", *sorted((left, right)))
        inverse = {"gt": "lt", "lt": "gt"}
        return (kind, op, left, right) if left <= right else (kind, inverse[op], right, left)
    return None


def _validate_form_names(kind: str, form: Mapping[str, Any], lexicon: Lexicon, line: int, errors: list[str]) -> None:
    def fact(subject: Any, attribute: Any) -> None:
        if not isinstance(subject, str) or lexicon.resolve(subject) is None: errors.append(f"claim line {line}: unknown/ambiguous subject {subject!r}")
        elif attribute not in lexicon.resolve(subject).attributes: errors.append(f"claim line {line}: invalid attribute {attribute!r} for {subject!r}")
    if kind in {"fact", "at_event"}: fact(form.get("subject"), form.get("attribute"))
    elif kind == "compare":
        sides = (form.get("left", {}), form.get("right", {}))
        refs: list[tuple[str, str]] = []
        for side in sides:
            if isinstance(side, Mapping): fact(side.get("subject"), side.get("attribute"))
            if isinstance(side, Mapping) and isinstance(side.get("subject"), str) and isinstance(side.get("attribute"), str):
                entity = lexicon.resolve(side["subject"])
                refs.append((entity.name if entity else side["subject"], side["attribute"]))
        if len(refs) == 2 and refs[0] == refs[1]: errors.append(f"claim line {line}: cannot compare a fact with itself")
    elif kind == "relation":
        fact(form.get("subject"), form.get("link"))
        fact(form.get("target"), form.get("attribute"))
    elif kind == "change":
        fact(form.get("subject"), form.get("attribute"))
        before, before_error = TypedValue.parse(form.get("from"))
        after, after_error = TypedValue.parse(form.get("to"))
        if not before_error and not after_error and before and after and _same_observed_value(before, after):
            errors.append(f"claim line {line}: change endpoints have the same value")
    if kind == "at_event" and form.get("event") not in lexicon.events:
        errors.append(f"claim line {line}: unknown event")
