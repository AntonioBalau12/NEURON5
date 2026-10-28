"""Small shared helpers: ids, UTC timestamps, pagination and CSV IO."""

from __future__ import annotations

import csv
import io
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .errors import ApiError

LABEL_KEYS = ("true", "false", "unsure", "fallback")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(16)}"


def parse_pagination(offset: int | None, limit: int | None, settings) -> tuple[int, int]:
    if offset is None:
        offset = 0
    if offset < 0:
        raise ApiError(
            400,
            "INVALID_REQUEST",
            "offset must be greater than or equal to 0.",
            {"offset": offset},
        )
    if limit is None:
        limit = int(settings.preview_default_rows)
    if limit < 1 or limit > int(settings.page_max_rows):
        raise ApiError(
            400,
            "INVALID_REQUEST",
            f"limit must be between 1 and {settings.page_max_rows}.",
            {"limit": limit, "max": int(settings.page_max_rows)},
        )
    return int(offset), int(limit)


def normalize_counts(raw: Any, errors: int = 0) -> dict[str, int]:
    counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0, "errors": 0}
    if isinstance(raw, dict):
        for key in LABEL_KEYS:
            try:
                value = int(raw.get(key, 0) or 0)
            except (TypeError, ValueError):
                value = 0
            counts[key] = max(0, value)
    try:
        counts["errors"] = max(0, int(errors))
    except (TypeError, ValueError):
        counts["errors"] = 0
    return counts


def serialize_csv(columns: Sequence[str], rows: Iterable[Sequence[str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(columns))
    for row in rows:
        writer.writerow(list(row))
    return buffer.getvalue().encode("utf-8")


def read_csv_page(
    path: str | Path,
    delimiter: str = ",",
    offset: int = 0,
    limit: int = 50,
    total_hint: int | None = None,
) -> tuple[list[str], list[list[str]], int]:
    """Read one page of a stored CSV without materialising the whole file.

    When total_hint is supplied (the dataset/job already knows its row
    count) scanning stops as soon as the requested page is complete.  When
    it is None the file is streamed once to count the total.
    """

    offset = max(0, int(offset))
    limit = max(1, int(limit))
    columns: list[str] = []
    rows: list[list[str]] = []
    total = 0
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter, strict=True)
            try:
                columns = next(reader)
            except StopIteration:
                return [], [], 0
            for record in reader:
                if total >= offset and len(rows) < limit:
                    rows.append(record)
                total += 1
                if total_hint is not None and total >= offset + limit:
                    break
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ApiError(
            500,
            "INTERNAL_ERROR",
            "The stored CSV could not be read.",
        ) from exc
    if total_hint is not None:
        total = max(0, int(total_hint))
    return list(columns), rows, total


def iter_file_chunks(path: str | Path, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            yield chunk


def coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
