"""Whole-dataset classification via the teammates' HTTP service.

The team owns classification. This backend never classifies rows itself: it
POSTs the dataset to one or more configured HTTP endpoints and waits for the
answer, which is expected to be the labelled data or a CSV file directly.

Configure with environment variables (see app/config.py):

  NEURON_CLASSIFIER_URLS        comma-separated POST endpoints, tried in order
                                (NEURON_CLASSIFIER_URL also works)
  NEURON_CLASSIFIER_MODE        "csv" (default): multipart upload, file field
                                "rows": JSON {"asOf","mapping","columns","rows"}
  NEURON_CLASSIFIER_FIELD_NAME  multipart file field name, default "file"
  NEURON_CLASSIFIER_TIMEOUT_SECONDS  request timeout, default 1800
  NEURON_CLASSIFIER_TOKEN       optional Authorization: Bearer value

The response may be:
  - CSV bytes (Content-Type text/csv or the body is not JSON),
  - JSON {"csv": "..."} (the CSV as a string),
  - JSON {"columns": [...], "rows": [[...], ...]},
  - JSON {"rows": [{"<original column>": ..., "label": "..."}]} (full rows),
  - JSON {"results": [{"id": "...", "label": "...", "confidence": 0.9}]}
    (narrow labels, merged into the input snapshot by id/mapping),
  - a JSON list of any of the above row objects,
  - a JSON object keyed by row id with label objects.

The returned table is authoritative: the processor stores it as the job output.
When the service returns narrow labels, the original snapshot columns and row
order are preserved and the result column is filled/appended.
"""

from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import httpx

from .api import MappingSpec, RowDecision, RowInput, emit_event

LABEL_ALIASES = {
    "true": "true",
    "t": "true",
    "yes": "true",
    "false": "false",
    "f": "false",
    "no": "false",
    "unsure": "unsure",
    "unknown": "unsure",
    "uncertain": "unsure",
}
LABEL_KEYS = ("label", "verdict", "result", "prediction", "classification", "tag")
CONFIDENCE_KEYS = ("confidence", "score", "probability", "certainty")
FULL_ROW_LIST_KEYS = ("results", "rows", "data", "items", "classifications", "predictions", "output")
CSV_STRING_KEYS = ("csv", "output_csv", "csv_content")
MAX_RESPONSE_BYTES = 64 * 1024 * 1024


class ClassifierUnavailable(RuntimeError):
    """The teammates' classification service could not be reached or rejected the payload."""


class ClassifierResponseError(ClassifierUnavailable):
    """The service answered, but the payload could not be understood as data/CSV."""


class ClassifierTimeout(ClassifierUnavailable):
    """The job deadline or the request timeout expired while waiting for the service."""


@dataclass
class RemoteResult:
    content: bytes            # final CSV table (UTF-8)
    columns: list[str]
    total_rows: int
    counts: dict[str, int] | None = None   # true/false/unsure/fallback when derivable
    errors: list[dict] = field(default_factory=list)
    source: str = "csv"       # "csv" | "json" | "merged"
    notes: list[str] = field(default_factory=list)


def normalise_label(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    return LABEL_ALIASES.get(raw.strip().lower())


def _item_label(item: Mapping[str, Any]) -> str | None:
    for key in LABEL_KEYS:
        if key in item:
            label = normalise_label(item[key])
            if label:
                return label
    return None


def _mapping_dict(mapping: MappingSpec) -> dict[str, Any]:
    return {
        "textColumn": mapping.text_column,
        "dateColumn": mapping.date_column,
        "idColumn": mapping.id_column,
        "resultColumn": mapping.result_column,
    }


def _read_snapshot(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            columns = next(reader)
        except StopIteration:
            return [], []
        rows: list[list[str]] = []
        for row in reader:
            if not row:
                continue
            if len(row) < len(columns):
                row = row + [""] * (len(columns) - len(row))
            elif len(row) > len(columns):
                row = row[: len(columns)]
            rows.append(row)
    return columns, rows


def _csv_bytes(columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> tuple[bytes, int]:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(list(columns))
    count = 0
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
        count += 1
    return buffer.getvalue().encode("utf-8"), count


def _validate_csv(content: bytes) -> tuple[list[str], int]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ClassifierResponseError(f"remote response is not valid UTF-8: {exc}") from exc
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        columns = next(reader)
    except StopIteration as exc:
        raise ClassifierResponseError("remote response is empty") from exc
    if not columns:
        raise ClassifierResponseError("remote response has an empty header")
    rows = 0
    for row in reader:
        if row:
            rows += 1
    return columns, rows


def _counts_from_table(content: bytes, result_column: str) -> dict[str, int] | None:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        columns = next(reader)
    except StopIteration:
        return None
    index = None
    for i, name in enumerate(columns):
        if name.strip().lower() == result_column.strip().lower() or name.strip().lower() == "label":
            index = i
            break
    if index is None:
        return None
    counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
    for row in reader:
        if not row:
            continue
        value = (row[index] if index < len(row) else "").strip().lower()
        if value in ("true", "false", "unsure"):
            counts[value] += 1
        else:
            counts["fallback"] += 1
    return counts


class RemoteClassifierEngine:
    """Engine-protocol object whose real work is one HTTP request per dataset."""

    def __init__(
        self,
        urls: Sequence[str],
        *,
        mode: str = "csv",
        field_name: str = "file",
        timeout: float = 30 * 60,
        retries: int = 0,
        token: str | None = None,
        as_of: str = "2026-10-29",
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        urls = tuple(url.strip() for url in urls if url and url.strip())
        if not urls:
            raise ClassifierUnavailable(
                "no classifier endpoint configured; set NEURON_CLASSIFIER_URLS to the team's HTTP service"
            )
        if mode not in ("csv", "rows"):
            raise ValueError("classifier mode must be 'csv' or 'rows'")
        self.urls = urls
        self.mode = mode
        self.field_name = field_name
        self.timeout = timeout
        self.retries = max(0, retries)
        self.token = token
        self.as_of = as_of
        self._last_good = 0
        headers = {"Accept": "text/csv, application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = client or httpx.Client(timeout=None, headers=headers, transport=transport, follow_redirects=True)

    # -- Engine protocol (whole-dataset engine) ----------------------------
    def prepare(self, context_rows: Iterable[RowInput] = ()) -> None:  # noqa: ARG002
        """Nothing to prepare: the remote service owns the classification context."""

    def classify(self, row: RowInput) -> RowDecision:  # pragma: no cover - defensive
        raise ClassifierUnavailable(
            "the remote classifier handles whole datasets; call submit_dataset instead of classify()"
        )

    def close(self) -> None:
        self._client.close()

    # -- main entry point ---------------------------------------------------
    def submit_dataset(
        self,
        input_path: str | Path,
        mapping: MappingSpec,
        *,
        as_of: str | None = None,
        deadline_epoch: float | None = None,
        emit=None,
    ) -> RemoteResult:
        input_path = Path(input_path)
        timeout = self._timeout(deadline_epoch)
        started = time.time()
        emit_event(emit, "step.started", step="remote", component="classifier", message="Sending dataset to the classification service")
        try:
            content, content_type = self._post(input_path, mapping, as_of or self.as_of, timeout, deadline_epoch)
        except ClassifierUnavailable:
            raise
        except httpx.TimeoutException as exc:
            raise ClassifierTimeout(f"classification request timed out after {timeout:.0f}s") from exc
        except httpx.HTTPError as exc:
            raise ClassifierUnavailable(f"classification request failed: {exc.__class__.__name__}: {exc}") from exc

        result = self._decode(content, content_type, input_path, mapping)
        emit_event(
            emit,
            "step.completed",
            step="remote",
            component="classifier",
            durationMs=int((time.time() - started) * 1000),
            message=f"Classification service returned {result.total_rows} rows ({result.source})",
        )
        return result

    # -- request building ----------------------------------------------------
    def _timeout(self, deadline_epoch: float | None) -> float:
        if deadline_epoch is None:
            return self.timeout
        remaining = deadline_epoch - time.time()
        if remaining <= 0:
            raise ClassifierTimeout("job deadline passed before the classification request")
        return max(1.0, min(self.timeout, remaining))

    def _post(self, input_path: Path, mapping: MappingSpec, as_of: str, timeout: float, deadline_epoch: float | None) -> tuple[bytes, str]:
        errors: list[str] = []
        order = list(range(len(self.urls)))
        order.remove(self._last_good) if self._last_good in order else None
        order.insert(0, self._last_good)
        for index in order:
            url = self.urls[index]
            for attempt in range(self.retries + 1):
                if deadline_epoch is not None and time.time() >= deadline_epoch:
                    raise ClassifierTimeout("job deadline passed while waiting for the classification service")
                try:
                    response = self._one_request(url, input_path, mapping, as_of, timeout)
                except httpx.HTTPError as exc:
                    errors.append(f"{url}: {exc.__class__.__name__}: {exc}")
                else:
                    if response.status_code < 300:
                        self._last_good = index
                        return response.content, response.headers.get("content-type", "")
                    body = response.text[:400].replace("\n", " ")
                    errors.append(f"{url}: HTTP {response.status_code}: {body}")
                    if 400 <= response.status_code < 500:
                        break  # bad payload: another endpoint will not help
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
        raise ClassifierUnavailable("; ".join(errors) or "classification request failed")

    def _one_request(self, url: str, input_path: Path, mapping: MappingSpec, as_of: str, timeout: float) -> httpx.Response:
        if self.mode == "csv":
            data = input_path.read_bytes()
            files = {self.field_name: (input_path.name, data, "text/csv")}
            form = {"asOf": as_of, "mapping": json.dumps(_mapping_dict(mapping))}
            return self._client.post(url, files=files, data=form, timeout=timeout)
        columns, rows = _read_snapshot(input_path)
        items = [dict(zip(columns, row)) for row in rows]
        payload = {"asOf": as_of, "mapping": _mapping_dict(mapping), "columns": columns, "rows": items}
        return self._client.post(url, json=payload, timeout=timeout)

    # -- response decoding ---------------------------------------------------
    def _decode(self, content: bytes, content_type: str, input_path: Path, mapping: MappingSpec) -> RemoteResult:
        if len(content) > MAX_RESPONSE_BYTES:
            raise ClassifierResponseError(f"remote response is too large ({len(content)} bytes)")
        stripped = content.lstrip()
        looks_json = stripped[:1] in (b"{", b"[")
        is_csv_type = "csv" in content_type.lower() or "text/plain" in content_type.lower()
        if looks_json:
            try:
                body = json.loads(content.decode("utf-8-sig"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ClassifierResponseError(f"remote response is not valid JSON: {exc}") from exc
            return self._as_json(body, input_path, mapping)
        if is_csv_type:
            return self._as_csv(content, mapping)
        raise ClassifierResponseError(f"unrecognised response content type: {content_type or 'unknown'!r}")

    def _as_csv(self, content: bytes, mapping: MappingSpec) -> RemoteResult:
        columns, rows = _validate_csv(content)
        counts = _counts_from_table(content, mapping.result_column)
        return RemoteResult(
            content=content,
            columns=columns,
            total_rows=rows,
            counts=counts,
            errors=[],
            source="csv",
        )

    def _as_json(self, body: Any, input_path: Path, mapping: MappingSpec) -> RemoteResult:
        if isinstance(body, Mapping):
            for key in CSV_STRING_KEYS:
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    result = self._as_csv(value.encode("utf-8"), mapping)
                    result.source = f"json.{key}"
                    return result
            if isinstance(body.get("columns"), list) and isinstance(body.get("rows"), list):
                return self._as_columns_rows(body["columns"], body["rows"], mapping)
            for key in FULL_ROW_LIST_KEYS:
                value = body.get(key)
                if isinstance(value, list):
                    return self._as_items(value, input_path, mapping)
            if self._looks_like_label_object(body):
                return self._merge_items({}, [body], input_path, mapping)
            if all(isinstance(value, Mapping) for value in body.values()):
                return self._merge_items({str(k): v for k, v in body.items()}, None, input_path, mapping)
        if isinstance(body, list):
            return self._as_items(body, input_path, mapping)
        raise ClassifierResponseError(f"unrecognised JSON response: {type(body).__name__}")

    def _as_columns_rows(self, columns: Sequence[Any], rows: Sequence[Any], mapping: MappingSpec) -> RemoteResult:
        columns = [str(column) for column in columns]
        normalised: list[list[Any]] = []
        for row in rows:
            if isinstance(row, Mapping):
                normalised.append([row.get(column, "") for column in columns])
            elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
                normalised.append(list(row))
            else:
                raise ClassifierResponseError("rows must be arrays or objects")
        content, count = _csv_bytes(columns, normalised)
        return RemoteResult(content=content, columns=columns, total_rows=count, counts=_counts_from_table(content, mapping.result_column), source="json.columnsRows")

    def _as_items(self, items: Sequence[Any], input_path: Path, mapping: MappingSpec) -> RemoteResult:
        mappings = [item for item in items if isinstance(item, Mapping)]
        if not mappings:
            raise ClassifierResponseError("row list does not contain objects")
        by_id: dict[str, Any] = {}
        for item in mappings:
            if "id" in item:
                by_id[str(item["id"])] = item
        if all(self._looks_like_label_object(item) and set(item).issubset({"id", *LABEL_KEYS, *CONFIDENCE_KEYS}) for item in mappings):
            return self._merge_items(by_id, mappings, input_path, mapping)
        # Full rows returned: authoritative table.
        columns: list[str] = []
        for item in mappings:
            for key in item:
                if key not in columns:
                    columns.append(key)
        content, count = _csv_bytes(columns, ([item.get(column, "") for column in columns] for item in mappings))
        return RemoteResult(content=content, columns=columns, total_rows=count, counts=_counts_from_table(content, mapping.result_column), source="json.rows")

    def _looks_like_label_object(self, item: Mapping[str, Any]) -> bool:
        return any(key in item for key in LABEL_KEYS)

    def _merge_items(self, by_id: Mapping[str, Any], ordered: Sequence[Mapping[str, Any]] | None, input_path: Path, mapping: MappingSpec) -> RemoteResult:
        columns, rows = _read_snapshot(input_path)
        result_column = mapping.result_column or "label"
        out_columns = list(columns)
        if result_column not in out_columns:
            out_columns.append(result_column)
        index = columns.index(result_column) if result_column in columns else None
        id_index = columns.index(mapping.id_column) if mapping.id_column in columns else None

        errors: list[dict] = []
        counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
        out_rows: list[list[str]] = []
        for position, row in enumerate(rows, start=1):
            row_id = row[id_index] if id_index is not None else f"r-{position}"
            item = by_id.get(str(row_id)) if by_id else None
            if item is None and ordered is not None and position - 1 < len(ordered):
                candidate = ordered[position - 1]
                if "id" not in candidate or str(candidate.get("id")) == str(row_id):
                    item = candidate
            if item is None:
                errors.append({"rowId": row_id, "lineNumber": position + 1, "column": result_column, "code": "REMOTE_MISSING_RESULT", "message": "classifier returned no result for this row"})
                label = "unsure"
                counts["fallback"] += 1
            else:
                label = _item_label(item)
                if label is None:
                    errors.append({"rowId": row_id, "lineNumber": position + 1, "column": result_column, "code": "REMOTE_INVALID_LABEL", "message": f"unreadable label: {item!r}"[:300]})
                    label = "unsure"
                    counts["fallback"] += 1
                else:
                    counts[label] += 1
            output_row = list(row)
            if index is None:
                output_row.append(label)
            else:
                output_row[index] = label
            out_rows.append(output_row)

        # rows the service returned but the snapshot does not hold are ignored (contract)
        content, count = _csv_bytes(out_columns, out_rows)
        return RemoteResult(
            content=content,
            columns=out_columns,
            total_rows=count,
            counts=counts,
            errors=errors,
            source="merged",
        )
