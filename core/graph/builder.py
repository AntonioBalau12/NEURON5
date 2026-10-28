"""Dynamic graph construction from runtime rows and optional form evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from foundation import AtomicFact, EvidenceRecord, InputData, Lexicon, TypedValue, _canonical_value_key, _quantity_unit, load_inputs, normalize_date
from .models import (
    EvidenceState,
    FactRecord,
    GraphEvidence,
    ParseStatus,
    TemporalKnowledgeGraph,
    entity_nodes,
)
from .parsing import TextFactParser


def _canonical_fact(fact: AtomicFact, lexicon: Lexicon) -> AtomicFact | None:
    entity = lexicon.resolve(fact.subject)
    if entity is None or fact.attribute not in entity.attributes:
        return None
    value = fact.value
    if value.kind == "name" and isinstance(value.value, str):
        target = lexicon.resolve(value.value)
        if target is not None:
            value = replace(value, value=target.name)
    return replace(fact, subject=entity.name, value=value,
                   subject_spelling=fact.subject_spelling or fact.subject)


def _from_rows(rows: Iterable[Mapping[str, Any]], lexicon: Lexicon) -> tuple[list[EvidenceRecord], list[str]]:
    records: list[EvidenceRecord] = []
    issues: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        row_id = str(row.get("id", "")).strip()
        if not row_id:
            issues.append(f"row {index}: missing id")
            continue
        if row_id in seen:
            issues.append(f"duplicate row id {row_id!r}; later duplicate ignored")
            continue
        seen.add(row_id)
        text = row.get("text") if isinstance(row.get("text"), str) else ""
        when, date_issue = normalize_date(row.get("date"))
        label_raw = row.get("label")
        label = str(label_raw).strip().lower() if label_raw is not None and str(label_raw).strip() else None
        row_issues = [date_issue] if date_issue else []
        if not text.strip():
            row_issues.append("missing text")
        if label not in {None, "true", "false", "unsure"}:
            row_issues.append(f"invalid label {label!r}")
            label = None
        facts: tuple[AtomicFact, ...] = ()
        if row.get("form") not in (None, ""):
            # Reuse P0's input validation and form parsing for canonical evidence.
            loaded = load_inputs_from_single_row(row, lexicon)
            facts = loaded[0]
            row_issues.extend(loaded[1])
        status = "malformed" if row_issues else "ok"
        records.append(EvidenceRecord(row_id, label, when, facts, text, status, tuple(row_issues)))
        issues.extend(f"row {row_id}: {item}" for item in row_issues)
    return records, issues


def load_inputs_from_single_row(row: Mapping[str, Any], lexicon: Lexicon) -> tuple[tuple[AtomicFact, ...], list[str]]:
    """Validate an in-memory practice form using the same value schema as P0."""
    from foundation import SchemaValidator, parse_evidence_form

    validator = _value_validator()
    facts, issues = parse_evidence_form(str(row.get("form", "")), validator)
    normalized: list[AtomicFact] = []
    for fact in facts:
        canonical = _canonical_fact(fact, lexicon)
        if canonical is None:
            issues.append(f"unknown subject/attribute {fact.subject!r}.{fact.attribute}")
        else:
            normalized.append(canonical)
    return tuple(normalized), issues


@lru_cache(maxsize=1)
def _value_validator():
    from foundation import SchemaValidator

    schema_path = Path(__file__).resolve().parents[2] / "contracts" / "claimed_value.schema.json"
    return SchemaValidator(schema_path) if schema_path.is_file() else None


def _unwrap_rows(value: InputData | Iterable[EvidenceRecord] | Iterable[Mapping[str, Any]], lexicon: Lexicon) -> tuple[list[EvidenceRecord], list[str]]:
    if isinstance(value, InputData):
        if value.lexicon is not None:
            lexicon = value.lexicon
        items = list(value.rows)
        inherited_issues = list(value.issues)
    else:
        items = list(value)
        inherited_issues = []
    if not items:
        return [], inherited_issues
    if isinstance(items[0], EvidenceRecord):
        records: list[EvidenceRecord] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, EvidenceRecord):
                continue
            if item.row_id in seen:
                inherited_issues.append(f"duplicate evidence ID {item.row_id!r}; later duplicate ignored")
                continue
            seen.add(item.row_id)
            records.append(item)
        return records, inherited_issues
    records, issues = _from_rows((item for item in items if isinstance(item, Mapping)), lexicon)
    return records, inherited_issues + issues


def _as_lexicon(value: Lexicon | Mapping[str, Any] | str | Path) -> tuple[Lexicon, list[str]]:
    if isinstance(value, Lexicon):
        return value, []
    if isinstance(value, (str, Path)):
        import json

        with open(value, "r", encoding="utf-8-sig") as handle:
            value = json.load(handle)
    lexicon, issues = Lexicon.parse(value)
    if lexicon is None:
        raise ValueError("invalid lexicon: " + "; ".join(issues))
    return lexicon, issues


def _exact_fact_key(fact: AtomicFact) -> tuple[Any, ...]:
    return (fact.subject.casefold(), fact.attribute, fact.value.key())


def build_graph(
    universe_rows: InputData | Iterable[EvidenceRecord] | Iterable[Mapping[str, Any]],
    lexicon: Lexicon | Mapping[str, Any] | str | Path | None = None,
    reference_evidence: InputData | Iterable[EvidenceRecord] | Iterable[Mapping[str, Any]] | None = None,
) -> TemporalKnowledgeGraph:
    """Build indexed graph; text extraction always creates candidates, never truth."""
    issues: list[str] = []
    if isinstance(universe_rows, InputData) and universe_rows.lexicon is not None:
        resolved_lexicon = universe_rows.lexicon
        if lexicon is not None:
            supplied, lex_issues = _as_lexicon(lexicon)
            if supplied != resolved_lexicon:
                issues.append("explicit lexicon differs from InputData lexicon; InputData lexicon used")
            issues.extend(lex_issues)
    else:
        if lexicon is None:
            raise ValueError("lexicon is required when universe_rows is not InputData")
        resolved_lexicon, lex_issues = _as_lexicon(lexicon)
        issues.extend(lex_issues)
    universe, row_issues = _unwrap_rows(universe_rows, resolved_lexicon)
    issues.extend(row_issues)
    refs: list[EvidenceRecord] = []
    if reference_evidence is not None:
        refs, ref_issues = _unwrap_rows(reference_evidence, resolved_lexicon)
        issues.extend(f"reference: {item}" for item in ref_issues)

    # Runtime copies of practice rows have no forms. Match packaged reference
    # forms only when identity, text, date, and label agree; do not duplicate IDs.
    universe_by_id = {row.row_id: row for row in universe}
    reference_by_id = {row.row_id: row for row in refs}
    merged: list[EvidenceRecord] = []
    used_refs: set[str] = set()
    for row in universe:
        ref = reference_by_id.get(row.row_id)
        if ref and ref.text == row.text and ref.date == row.date and ref.label == row.label and ref.facts and not row.facts:
            merged.append(replace(row, facts=ref.facts, parse_status=ref.parse_status, issues=tuple(dict.fromkeys((*row.issues, *ref.issues)))))
            used_refs.add(row.row_id)
        else:
            if ref and (ref.text != row.text or ref.date != row.date or ref.label != row.label):
                issues.append(f"reference evidence for {row.row_id} did not match runtime row and was not merged")
            merged.append(row)
    for ref in refs:
        if ref.row_id not in universe_by_id and ref.row_id not in used_refs:
            merged.append(ref)

    attribute_kinds: dict[str, str] = {}
    known_units: set[str] = set()
    for row in merged:
        for fact in row.facts:
            attribute_kinds.setdefault(fact.attribute, fact.value.kind)
            if fact.value.kind in {"quantity", "duration"} and fact.value.unit:
                known_units.add(fact.value.unit)
    parser = TextFactParser(resolved_lexicon, attribute_kinds, known_units)
    graph = TemporalKnowledgeGraph(resolved_lexicon, entity_nodes(resolved_lexicon), issues=issues)
    for row in merged:
        extracted = parser.parse(row.text)
        form_facts = tuple(f for fact in row.facts if (f := _canonical_fact(fact, resolved_lexicon)) is not None)
        has_valid_form = bool(row.facts) and row.parse_status == "ok"
        if has_valid_form:
            primary_facts = form_facts
            parse_status = ParseStatus.FORM_GROUNDED
            coverage = 1.0
            provenance = "practice.form" if row.label is not None else "provided.form"
        else:
            primary_facts = extracted.facts
            parse_status = extracted.status
            coverage = extracted.confidence
            provenance = "deterministic_text_extraction"
        extracted_facts = tuple(f for fact in extracted.facts if (f := _canonical_fact(fact, resolved_lexicon)) is not None)
        form_keys = {_exact_fact_key(fact) for fact in form_facts}
        all_evidence_facts = tuple({
            _exact_fact_key(fact): fact for fact in (*form_facts, *extracted_facts)
        }.values())
        if has_valid_form and any(_exact_fact_key(fact) not in form_keys for fact in extracted_facts):
            provenance = "practice.form+deterministic_text_extraction"
        graph.evidence_by_id[row.row_id] = GraphEvidence(
            row.row_id, row.text, row.label, row.date, all_evidence_facts,
            parse_status, coverage, provenance, tuple((*row.issues, *extracted.issues)),
            (row.row_id,) if row.label == "true" and has_valid_form else (),
        )
        true_form = row.label == "true" and has_valid_form
        record_state = EvidenceState.VERIFIED_SUPPORT if true_form else EvidenceState.UNVERIFIED_CANDIDATE
        primary_keys: set[tuple[Any, ...]] = set()
        for fact in primary_facts:
            canonical = _canonical_fact(fact, resolved_lexicon)
            if canonical is None:
                continue
            primary_keys.add(_exact_fact_key(canonical))
            fact_record = FactRecord(
                fact=canonical,
                observed_on=row.date,
                valid_from=None,
                valid_to=None,
                source_row_id=row.row_id,
                evidence_status=record_state,
                parse_status=parse_status,
                provenance=provenance,
                confidence=1.0 if true_form else coverage,
            # The source row itself is provenance, not independent supporting evidence.
            supporting_evidence=(),
            )
            graph.add_fact(fact_record)
        # Preserve form fragments and text-only atoms as candidates unless the
        # same source row already supplied them as its primary observation.
        for fact in (*form_facts, *extracted_facts):
            canonical = _canonical_fact(fact, resolved_lexicon)
            if canonical is None or _exact_fact_key(canonical) in primary_keys:
                continue
            primary_keys.add(_exact_fact_key(canonical))
            graph.add_fact(FactRecord(
                canonical, row.date, None, None, row.row_id,
                EvidenceState.UNVERIFIED_CANDIDATE,
                ParseStatus.FORM_GROUNDED if fact in form_facts else extracted.status,
                "provided.form_fragment" if fact in form_facts else "deterministic_text_extraction",
                0.5 if fact in form_facts else extracted.confidence,
            ))
    _mark_same_day_conflicts(graph)
    _attach_evidence_references(graph)
    graph.sort_indexes()
    return graph


def build_graph_from_paths(
    universe_csv: str | Path = "/universe/universe.csv",
    lexicon_json: str | Path = "/universe/lexicon.json",
    reference_csv: str | Path | None = None,
    *,
    use_packaged_practice: bool = True,
) -> TemporalKnowledgeGraph:
    """Convenience loader for the official runtime paths and local development."""
    universe = load_inputs(universe_csv, lexicon_json)
    if universe.lexicon is None:
        raise ValueError("runtime inputs could not be loaded: " + "; ".join(universe.issues))
    if reference_csv is None and use_packaged_practice:
        packaged = Path(__file__).resolve().parents[2] / "data" / "practice.csv"
        if packaged.is_file():
            reference_csv = packaged
    references = load_inputs(reference_csv, lexicon_json) if reference_csv else None
    return build_graph(universe, universe.lexicon, references)


def _mark_same_day_conflicts(graph: TemporalKnowledgeGraph) -> None:
    from .models import EvidenceState

    grouped: dict[tuple[str, str, date, tuple[Any, ...]], dict[tuple[Any, ...], list[FactRecord]]] = {}
    for record in (record for values in graph.facts_by_subject_attribute.values() for record in values):
        if record.evidence_status != EvidenceState.VERIFIED_SUPPORT or record.observed_on is None or record.fact.value.op is not None:
            continue
        key = (record.fact.subject.casefold(), record.fact.attribute, record.observed_on,
               _value_comparison_group(record.fact.value))
        canonical = _canonical_value_key(_typed_value_mapping(record.fact.value), graph.lexicon)
        if canonical is None:
            continue
        grouped.setdefault(key, {}).setdefault(canonical, []).append(record)
    replacements: dict[tuple[str, str, date, tuple[Any, ...], str], FactRecord] = {}
    for (subject, attribute, day, _), value_groups in grouped.items():
        if len(value_groups) > 1:
            records = [record for value_records in value_groups.values() for record in value_records]
            conflict_ids = {record.source_row_id for record in records}
            graph.issues.append(f"same-day evidence conflict for {subject}.{attribute} on {day.isoformat()}")
            for record in records:
                if record.source_row_id in conflict_ids:
                    replacements[(subject, attribute, day, record.fact.value.key(), record.source_row_id)] = replace(record, evidence_status=EvidenceState.CONFLICTING)
            for row_id in conflict_ids:
                evidence = graph.evidence_by_id.get(row_id)
                if evidence is not None:
                    other_ids = tuple(sorted(conflict_ids - {row_id}))
                    graph.evidence_by_id[row_id] = replace(evidence, contradicting_evidence_ids=other_ids)
    if not replacements:
        return
    def update(record: FactRecord) -> FactRecord:
        return replacements.get((record.fact.subject.casefold(), record.fact.attribute, record.observed_on, record.fact.value.key(), record.source_row_id), record) if record.observed_on else record
    graph.facts_by_subject_attribute = {key: [update(record) for record in values] for key, values in graph.facts_by_subject_attribute.items()}
    graph.facts_by_date = {key: [update(record) for record in values] for key, values in graph.facts_by_date.items()}
    graph.facts_by_key = {key: [update(record) for record in values] for key, values in graph.facts_by_key.items()}
    graph.candidate_facts_by_key = {key: [update(record) for record in values] for key, values in graph.candidate_facts_by_key.items()}
    graph.relations_by_entity = {key: [update(record) for record in values] for key, values in graph.relations_by_entity.items()}


def _typed_value_mapping(value: TypedValue) -> dict[str, Any]:
    result = {"kind": value.kind, "value": value.value}
    for key in ("unit", "currency", "per", "op"):
        item = getattr(value, key)
        if item is not None:
            result[key] = item
    return result


def _value_comparison_group(value: TypedValue) -> tuple[Any, ...]:
    if value.kind == "quantity":
        normalized = _quantity_unit(value.unit)
        return (value.kind, normalized[0] if normalized else value.unit)
    if value.kind == "money":
        return value.kind, value.currency, value.per
    if value.kind == "duration":
        if value.unit in {"ms", "s", "min", "h", "day", "week"}:
            return value.kind, "fixed"
        if value.unit in {"month", "year"}:
            return value.kind, "calendar"
    if value.kind == "date":
        return value.kind, len(str(value.value))
    if value.kind == "name":
        return value.kind, "name"
    return value.kind, value.unit, value.currency, value.per


def _attach_evidence_references(graph: TemporalKnowledgeGraph) -> None:
    for row_id, evidence in tuple(graph.evidence_by_id.items()):
        supporting: set[str] = set()
        for fact in evidence.facts:
            records = graph.facts_by_key.get(_exact_fact_key(fact), ())
            supporting.update(record.source_row_id for record in records
                              if record.source_row_id != row_id and record.evidence_status == EvidenceState.VERIFIED_SUPPORT)
        graph.evidence_by_id[row_id] = replace(
            evidence,
            supporting_evidence_ids=tuple(sorted(supporting)),
        )
