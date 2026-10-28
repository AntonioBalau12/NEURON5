"""Dataset creation, inspection, preview and confirmed mapping."""

from __future__ import annotations

import asyncio
import codecs
import copy
import csv
import datetime
import io
import json
import math
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from .errors import ApiError
from .sessions import require_session
from .stores import ApiState, DatasetRecord, SessionRecord
from .utils import (
    new_id,
    parse_pagination,
    read_csv_page,
    serialize_csv,
    utcnow,
)

router = APIRouter(tags=["datasets"])

DEFAULT_COLUMNS = ["id", "text", "date"]
PREVIEW_LIMIT = 5
TEXT_COLUMN_NAMES = ("text", "sentence", "proposition", "claim", "content")
DATE_COLUMN_NAMES = ("date", "timestamp", "day")
ID_COLUMN_NAMES = ("id",)
COUNT_BUDGET_BYTES = 2_000_000

#: Exact schema of the input files the team receives (data/practice.csv shape).
PRACTICE_COLUMNS = ("id", "text", "date", "label", "form")
PRACTICE_LABELS = {"", "true", "false", "unsure"}


def _is_practice_header(header: list[str]) -> bool:
    """True when the header is exactly id,text,date,label,form (same order)."""
    return [
        column.strip().casefold() for column in header
    ] == list(PRACTICE_COLUMNS)


def _practice_row_problem(record: list[str]) -> str | None:
    """Return a short reason when a practice-format row is malformed, else None."""
    if len(record) != len(PRACTICE_COLUMNS):
        return "field count"
    row_id, text, when, label, form = (value.strip() for value in record)
    if not row_id:
        return "empty id"
    if not text:
        return "empty text"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
        return "invalid date"
    try:
        datetime.date.fromisoformat(when)
    except ValueError:
        return "invalid date"
    if label.casefold() not in PRACTICE_LABELS:
        return "invalid label"
    if form:
        try:
            parsed = json.loads(form)
        except ValueError:
            return "invalid form JSON"
        if not isinstance(parsed, list) or not all(
            isinstance(item, dict)
            and isinstance(item.get("subject"), str)
            and isinstance(item.get("attribute"), str)
            and isinstance(item.get("value"), dict)
            for item in parsed
        ):
            return "invalid form shape"
    return None


def _practice_mapping(header: list[str]) -> dict[str, Any]:
    """Fixed schema, so the mapping is known and already confirmed."""
    return {
        "textColumn": header[1],
        "dateColumn": header[2],
        "idColumn": header[0],
        "resultColumn": header[3],
        "confirmed": True,
        "autoDetected": True,
    }


def get_state(request: Request) -> ApiState:
    return request.app.state.n5


def _warnings(*items: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _find_column(columns: list[str], names: tuple[str, ...]) -> str | None:
    folded = [(column, column.strip().casefold()) for column in columns]
    for name in names:
        for column, low in folded:
            if low == name:
                return column
    return None


def _autodetect_mapping(columns: list[str]) -> dict[str, Any] | None:
    text = _find_column(columns, TEXT_COLUMN_NAMES)
    if text is None:
        return None
    date_column = _find_column(columns, DATE_COLUMN_NAMES)
    id_column = _find_column(columns, ID_COLUMN_NAMES)
    result_column = "label"
    for column in columns:
        if column.strip().casefold() == "label":
            result_column = column
            break
    return {
        "textColumn": text,
        "dateColumn": date_column,
        "idColumn": id_column,
        "resultColumn": result_column,
        "confirmed": False,
        "autoDetected": True,
    }


def _dataset_payload(dataset: DatasetRecord) -> dict[str, Any]:
    return {
        "id": dataset.id,
        "mode": dataset.mode,
        "format": dataset.format,
        "createdAt": _iso(dataset),
        "byteSize": dataset.byte_size,
        "encoding": dataset.encoding,
        "delimiter": dataset.delimiter,
        "hasHeader": True,
        "columns": list(dataset.columns),
        "rowCount": dataset.row_count,
        "mapping": copy.deepcopy(dataset.mapping),
        "warnings": list(dataset.warnings),
        "preview": {
            "columns": list(dataset.columns),
            "rows": [list(row) for row in dataset.preview_rows],
            "offset": 0,
            "limit": PREVIEW_LIMIT,
            "total": dataset.preview_total
            if dataset.preview_total is not None
            else dataset.row_count,
        },
    }


def _iso(dataset: DatasetRecord) -> str:
    from .utils import iso_utc

    value = iso_utc(dataset.created_at)
    assert value is not None
    return value


def _owned_dataset(state: ApiState, session: SessionRecord, dataset_id: str) -> DatasetRecord:
    dataset = state.datasets.get(dataset_id)
    if dataset is None or dataset.session_id != session.id:
        raise ApiError(404, "NOT_FOUND", "Dataset not found.")
    return dataset


def _validate_columns(raw: Any) -> list[str]:
    if raw is None:
        return list(DEFAULT_COLUMNS)
    if not isinstance(raw, list) or not raw:
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "columns must be a non-empty array of names.",
        )
    columns: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise ApiError(
                400,
                "INVALID_REQUEST",
                "Column names must be non-empty strings.",
                {"index": index},
            )
        columns.append(value)
    if len(set(columns)) != len(columns):
        duplicates = sorted({name for name in columns if columns.count(name) > 1})
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "Column names must be unique.",
            {"duplicates": duplicates},
        )
    return columns


def _cell(value: Any, row_index: int, column: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ApiError(
                400,
                "INVALID_REQUEST",
                "Cell values must be finite numbers.",
                {"row": row_index, "column": column},
            )
        return str(value)
    raise ApiError(
        400,
        "INVALID_REQUEST",
        "Cell values must be strings, numbers, booleans or null.",
        {"row": row_index, "column": column},
    )


def _prepare_rows(columns: list[str], raw_rows: list[Any]) -> list[list[str]]:
    prepared: list[list[str]] = []
    for row_index, item in enumerate(raw_rows):
        if isinstance(item, dict):
            unknown = [key for key in item if key not in columns]
            if unknown:
                raise ApiError(
                    400,
                    "INVALID_REQUEST",
                    "Row objects may only contain declared columns.",
                    {"row": row_index, "unknownColumns": unknown},
                )
            prepared.append(
                [_cell(item.get(column, ""), row_index, column) for column in columns]
            )
        elif isinstance(item, list):
            if len(item) > len(columns):
                raise ApiError(
                    400,
                    "INVALID_REQUEST",
                    "A row has more values than the declared columns.",
                    {"row": row_index, "values": len(item), "columns": len(columns)},
                )
            values = [
                _cell(value, row_index, columns[index])
                for index, value in enumerate(item)
            ]
            values.extend([""] * (len(columns) - len(values)))
            prepared.append(values)
        else:
            raise ApiError(
                400,
                "INVALID_REQUEST",
                "Each row must be an array or an object keyed by column name.",
                {"row": row_index},
            )
    return prepared


def _detect_delimiter(text: str) -> tuple[str, bool]:
    first = ""
    for line in text.splitlines():
        if line.strip():
            first = line
            break
    if not first:
        return ",", False
    counts = {",": first.count(","), ";": first.count(";"), "\t": first.count("\t")}
    best = max(counts.values())
    if best == 0:
        return ",", False
    winners = [delimiter for delimiter, count in counts.items() if count == best]
    if len(winners) > 1:
        return ",", True
    return winners[0], False


def _normalize_delimiter(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ApiError(400, "INVALID_REQUEST", "delimiter must be a string.")
    if raw in (",", ";", "\t"):
        return raw
    if raw == "\\t":
        return "\t"
    raise ApiError(
        400,
        "INVALID_REQUEST",
        "delimiter must be one of comma, semicolon or tab.",
        {"delimiter": raw},
    )


def _parse_bulk(data: bytes, explicit_delimiter: str | None) -> dict[str, Any]:
    has_bom = data.startswith(codecs.BOM_UTF8)
    encoding = "utf-8-sig" if has_bom else "utf-8"
    try:
        text = data.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ApiError(
            400,
            "UNSUPPORTED_ENCODING",
            "The CSV file must be UTF-8 encoded.",
        ) from exc
    if not text.strip():
        raise ApiError(400, "INVALID_CSV", "The CSV file is empty.")
    warnings: list[str] = []
    if has_bom:
        warnings.append("BOM_PRESENT")
    if explicit_delimiter is None:
        delimiter, ambiguous = _detect_delimiter(text)
        if ambiguous:
            warnings.append("AMBIGUOUS_DELIMITER")
    else:
        delimiter = explicit_delimiter
    stream = io.StringIO(text, newline="")
    reader = csv.reader(stream, delimiter=delimiter, strict=True)
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ApiError(400, "INVALID_CSV", "The CSV file has no header row.") from exc
    except csv.Error as exc:
        raise ApiError(
            400,
            "INVALID_CSV",
            "The CSV file could not be parsed.",
            {"line": getattr(reader, "line_num", 1)},
        ) from exc
    if not header or not any(name.strip() for name in header):
        raise ApiError(400, "INVALID_CSV", "The CSV header row is empty.")
    # The input files the team receives have exactly id,text,date,label,form.
    # That schema is first-class: it is validated row by row, the mapping is
    # known (text/date/id/label) and already confirmed, so a job can start
    # immediately after the upload; "form" is preserved untouched.
    practice = _is_practice_header(header)
    preview: list[list[str]] = []
    row_count = 0
    practice_issues = 0
    try:
        for record in reader:
            row_count += 1
            if practice and _practice_row_problem(record) is not None:
                practice_issues += 1
            if len(preview) < PREVIEW_LIMIT:
                preview.append(record)
    except csv.Error as exc:
        raise ApiError(
            400,
            "INVALID_CSV",
            "The CSV file could not be parsed.",
            {"line": getattr(reader, "line_num", row_count + 2)},
        ) from exc
    if row_count == 0:
        warnings.append("EMPTY_FILE")
    if practice:
        dataset_format = "practice"
        mapping = _practice_mapping(header)
        if practice_issues:
            warnings.append("PRACTICE_ROW_ERRORS")
    else:
        dataset_format = "generic"
        mapping = _autodetect_mapping(header)
        if mapping is None:
            warnings.append("HEADER_WITHOUT_TEXT_COLUMN")
    return {
        "encoding": encoding,
        "delimiter": delimiter,
        "format": dataset_format,
        "columns": list(header),
        "row_count": row_count if len(data) <= COUNT_BUDGET_BYTES else None,
        "total_rows": row_count,
        "preview_rows": preview,
        "warnings": _warnings(*warnings),
        "mapping": mapping,
    }


def _write_comma_snapshot(data: bytes, encoding: str, delimiter: str, path: Path, expected_rows: int | None) -> int:
    """Store an immutable comma-delimited UTF-8 snapshot of the uploaded CSV.

    The engine clients only speak comma CSV; metadata keeps the detected
    delimiter/encoding for display. Parsing was already validated by _parse_bulk.
    """
    text = data.decode(encoding)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            records = 0
            for record in reader:
                writer.writerow(record)
                records += 1
    except (csv.Error, OSError) as exc:
        raise ApiError(400, "INVALID_CSV", "The CSV file could not be normalised.") from exc
    row_count = max(0, records - 1)
    if expected_rows is not None and row_count != expected_rows:
        raise ApiError(400, "INVALID_CSV", "The CSV file changed while being normalised.")
    return path.stat().st_size


@router.post("/datasets/manual", status_code=201)
async def create_manual_dataset(
    request: Request,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "INVALID_REQUEST", "Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_REQUEST", "Request body must be a JSON object.")
    columns = _validate_columns(body.get("columns"))
    raw_rows = body.get("rows", [])
    if raw_rows is None:
        raw_rows = []
    if not isinstance(raw_rows, list):
        raise ApiError(400, "INVALID_REQUEST", "rows must be an array.")
    rows = _prepare_rows(columns, raw_rows)
    payload = serialize_csv(columns, rows)
    if len(payload) > state.settings.manual_max_bytes:
        raise ApiError(
            413,
            "DATASET_TOO_LARGE",
            "The serialized dataset exceeds the manual-size limit.",
            {"maxBytes": int(state.settings.manual_max_bytes)},
        )
    dataset_id = new_id("ds")
    state.ensure_dirs()
    path = state.dataset_path(dataset_id)
    await asyncio.to_thread(path.write_bytes, payload)
    warnings: list[str] = []
    if not rows:
        warnings.append("EMPTY_FILE")
    mapping = _autodetect_mapping(columns)
    if mapping is None:
        warnings.append("HEADER_WITHOUT_TEXT_COLUMN")
    dataset = DatasetRecord(
        id=dataset_id,
        mode="manual",
        format="manual",
        session_id=session.id,
        path=path,
        created_at=utcnow(),
        byte_size=len(payload),
        encoding="utf-8",
        delimiter=",",
        columns=list(columns),
        row_count=len(rows),
        mapping=mapping,
        warnings=_warnings(*warnings),
        preview_rows=rows[:PREVIEW_LIMIT],
        preview_total=len(rows),
    )
    state.datasets[dataset.id] = dataset
    return _dataset_payload(dataset)


@router.post("/datasets/bulk", status_code=201)
async def create_bulk_dataset(
    request: Request,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise ApiError(
            415,
            "UNSUPPORTED_MEDIA_TYPE",
            "Bulk upload requires multipart/form-data with a file field.",
        )
    try:
        form = await request.form()
    except Exception as exc:
        raise ApiError(400, "INVALID_REQUEST", "Malformed multipart body.") from exc
    try:
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise ApiError(
                400,
                "INVALID_REQUEST",
                "The multipart field 'file' is required.",
            )
        delimiter = _normalize_delimiter(form.get("delimiter"))
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > state.settings.bulk_max_bytes:
                raise ApiError(
                    413,
                    "DATASET_TOO_LARGE",
                    "The uploaded CSV exceeds the bulk-size limit.",
                    {"maxBytes": int(state.settings.bulk_max_bytes)},
                )
            chunks.append(chunk)
    finally:
        close = getattr(form, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # pragma: no cover - defensive
                pass
    data = b"".join(chunks)
    if not data:
        raise ApiError(400, "INVALID_CSV", "The CSV file is empty.")
    parsed = await asyncio.to_thread(_parse_bulk, data, delimiter)
    dataset_id = new_id("ds")
    state.ensure_dirs()
    path = state.dataset_path(dataset_id)
    snapshot_bytes = await asyncio.to_thread(
        _write_comma_snapshot, data, parsed["encoding"], parsed["delimiter"], path, parsed["row_count"]
    )
    dataset = DatasetRecord(
        id=dataset_id,
        mode="bulk",
        format=parsed["format"],
        session_id=session.id,
        path=path,
        created_at=utcnow(),
        byte_size=snapshot_bytes,
        encoding=parsed["encoding"],
        delimiter=parsed["delimiter"],
        columns=parsed["columns"],
        row_count=parsed["row_count"],
        mapping=parsed["mapping"],
        warnings=parsed["warnings"],
        preview_rows=parsed["preview_rows"],
        preview_total=parsed["total_rows"],
    )
    state.datasets[dataset.id] = dataset
    return _dataset_payload(dataset)


@router.get("/datasets/{dataset_id}")
async def get_dataset(
    request: Request,
    dataset_id: str,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    dataset = _owned_dataset(state, session, dataset_id)
    return _dataset_payload(dataset)


@router.get("/datasets/{dataset_id}/preview")
async def get_dataset_preview(
    request: Request,
    dataset_id: str,
    offset: int = 0,
    limit: int | None = None,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    dataset = _owned_dataset(state, session, dataset_id)
    resolved_offset, resolved_limit = parse_pagination(offset, limit, state.settings)
    # Bulk snapshots are normalised to comma on save; the delimiter field keeps
    # the delimiter detected in the upload for display only.
    columns, rows, total = await asyncio.to_thread(
        read_csv_page,
        dataset.path,
        ",",
        resolved_offset,
        resolved_limit,
        dataset.row_count,
    )
    if dataset.row_count is None:
        dataset.row_count = total
    dataset.preview_total = total
    return {
        "columns": columns,
        "rows": rows,
        "offset": resolved_offset,
        "limit": resolved_limit,
        "total": total,
    }


@router.put("/datasets/{dataset_id}/mapping")
async def update_mapping(
    request: Request,
    dataset_id: str,
    session: SessionRecord = Depends(require_session),
) -> dict[str, Any]:
    state = get_state(request)
    dataset = _owned_dataset(state, session, dataset_id)
    if dataset.mapping_frozen:
        raise ApiError(
            409,
            "INVALID_REQUEST",
            "The mapping is frozen because a job already used this dataset.",
        )
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(400, "INVALID_MAPPING", "Mapping body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_MAPPING", "Mapping body must be a JSON object.")
    issues: dict[str, Any] = {}
    text_column = body.get("textColumn")
    if not isinstance(text_column, str) or text_column not in dataset.columns:
        issues["textColumn"] = text_column
    date_column = body.get("dateColumn")
    if date_column is not None and (
        not isinstance(date_column, str) or date_column not in dataset.columns
    ):
        issues["dateColumn"] = date_column
    id_column = body.get("idColumn")
    if id_column is not None and (
        not isinstance(id_column, str) or id_column not in dataset.columns
    ):
        issues["idColumn"] = id_column
    if "resultColumn" in body:
        result_column = body.get("resultColumn")
    else:
        result_column = "label"
    if (
        not isinstance(result_column, str)
        or not result_column.strip()
        or len(result_column) > 64
    ):
        issues["resultColumn"] = result_column
    if issues:
        raise ApiError(
            400,
            "INVALID_MAPPING",
            "The mapping refers to invalid column names.",
            {"issues": issues, "columns": list(dataset.columns)},
        )
    dataset.mapping = {
        "textColumn": text_column,
        "dateColumn": date_column,
        "idColumn": id_column,
        "resultColumn": result_column,
        "confirmed": True,
        "autoDetected": False,
    }
    return _dataset_payload(dataset)