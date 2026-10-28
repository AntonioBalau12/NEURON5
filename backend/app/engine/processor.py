"""CSV processor: dataset snapshot -> labelled result table.

Two modes, same ProcessOutcome contract:

1. Remote mode (the real one): the classifier engine is backed by the teammates'
   HTTP service. The whole snapshot is sent in one request (RemoteClassifierEngine
   .submit_dataset) and the returned data/CSV becomes the job output. No local
   classification happens here.
2. Row mode (test/diagnostic engines implementing the Engine protocol): rows are
   classified one by one with per-row error containment. Kept so the API tests can
   inject a fake engine without any network.

Both modes preserve row order, write incrementally/atomically and validate the
CSV before publishing it. See docs/API_CONTRACT.md section 7.
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable

from .api import EventEmitter, MappingSpec, ProcessOutcome, RowDecision, RowInput

MAX_ERRORS = 2000


class ProcessingError(RuntimeError):
    """Infrastructure error: the job cannot produce a valid output."""


def _emit(emit: EventEmitter | None, event_type: str, **payload: Any) -> None:
    if emit is None:
        return
    try:
        emit(event_type, payload)
    except Exception:  # pragma: no cover - logging must never break processing
        pass


def _error_entry(row_id: str, line_number: int | None, column: str | None, code: str, message: str) -> dict:
    return {
        "rowId": row_id,
        "lineNumber": line_number,
        "column": column,
        "code": code,
        "message": message[:500],
    }


def _temp_path(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=output_path.name + ".", suffix=".tmp", dir=output_path.parent)
    os.close(fd)
    return Path(name)


def _publish(temp_path: Path, output_path: Path) -> None:
    os.replace(temp_path, output_path)


def _validate_table(path: Path) -> tuple[list[str], int]:
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                columns = next(reader)
            except StopIteration as exc:
                raise ProcessingError("output table is empty") from exc
            if not columns:
                raise ProcessingError("output table has an empty header")
            rows = sum(1 for row in reader if row)
    except UnicodeDecodeError as exc:
        raise ProcessingError(f"output table is not valid UTF-8: {exc}") from exc
    return columns, rows


def _counts_from_output(path: Path, result_column: str) -> dict[str, int]:
    counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            columns = next(reader, [])
            index = None
            for i, name in enumerate(columns):
                if name.strip().lower() in (result_column.strip().lower(), "label"):
                    index = i
                    break
            if index is None:
                return counts
            for row in reader:
                if not row:
                    continue
                value = (row[index] if index < len(row) else "").strip().lower()
                counts[value if value in ("true", "false", "unsure") else "fallback"] += 1
    except (OSError, UnicodeDecodeError):
        return counts
    return counts


def _safe_id(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value or fallback


def process_csv(
    input_path: str | Path,
    output_path: str | Path,
    mapping: MappingSpec,
    engine: Any,
    *,
    deadline_epoch: float | None = None,
    emit: EventEmitter | None = None,
    progress_every: int = 50,
    as_of: str | None = None,
) -> ProcessOutcome:
    input_path = Path(input_path)
    output_path = Path(output_path)
    started = time.time()
    if hasattr(engine, "submit_dataset"):
        return _process_remote(input_path, output_path, mapping, engine, deadline_epoch, emit, as_of, started)
    return _process_rows(input_path, output_path, mapping, engine, deadline_epoch, emit, progress_every, started)


# --------------------------------------------------------------------------- #
# Remote mode: one request to the teammates' service, its table is the output.
# --------------------------------------------------------------------------- #
def _process_remote(
    input_path: Path,
    output_path: Path,
    mapping: MappingSpec,
    engine: Any,
    deadline_epoch: float | None,
    emit: EventEmitter | None,
    as_of: str | None,
    started: float,
) -> ProcessOutcome:
    _emit(emit, "progress.updated", processedRows=0, totalRows=None, counts={"true": 0, "false": 0, "unsure": 0, "fallback": 0},
          message="Waiting for the classification service")
    result = engine.submit_dataset(
        input_path,
        mapping,
        as_of=as_of,
        deadline_epoch=deadline_epoch,
        emit=emit,
    )

    temp = _temp_path(output_path)
    try:
        with open(temp, "wb") as handle:
            handle.write(result.content)
            handle.flush()
            os.fsync(handle.fileno())
        _emit(emit, "step.started", step="validate", component="processor", message="Validating the returned table")
        columns, rows = _validate_table(temp)
        if rows != result.total_rows:
            raise ProcessingError(f"remote table changed while being stored ({result.total_rows} -> {rows} rows)")
        _publish(temp, output_path)
        _emit(emit, "step.completed", step="validate", component="processor", message=f"Output valid: {rows} rows, {len(columns)} columns")
    except BaseException:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    counts = result.counts or _counts_from_output(output_path, mapping.result_column)
    errors = list(result.errors)[:MAX_ERRORS]
    duration = time.time() - started
    _emit(emit, "progress.updated", processedRows=rows, totalRows=rows, counts=counts,
          message=f"Received {rows} rows from the classification service")
    return ProcessOutcome(
        output_path=output_path,
        total_rows=rows,
        processed_rows=rows,
        counts=counts,
        errors=errors,
        duration_seconds=duration,
        timed_out=False,
        valid=True,
    )


# --------------------------------------------------------------------------- #
# Row mode: per-row Engine.classify, used by tests and diagnostic engines.
# --------------------------------------------------------------------------- #
def _read_header(handle: Any) -> list[str]:
    reader = csv.reader(handle)
    try:
        return next(reader)
    except StopIteration:
        return []


def _process_rows(
    input_path: Path,
    output_path: Path,
    mapping: MappingSpec,
    engine: Any,
    deadline_epoch: float | None,
    emit: EventEmitter | None,
    progress_every: int,
    started: float,
) -> ProcessOutcome:
    _emit(emit, "step.started", step="parse", component="processor", message="Reading dataset snapshot")
    with open(input_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            columns = next(reader)
        except StopIteration:
            raise ProcessingError("input dataset is empty")
        if not columns:
            raise ProcessingError("input dataset has an empty header")
        if mapping.text_column not in columns:
            raise ProcessingError(f"text column {mapping.text_column!r} is not in the dataset")
        column_index = {name: index for index, name in enumerate(columns)}
        text_index = column_index[mapping.text_column]
        date_index = column_index.get(mapping.date_column) if mapping.date_column else None
        id_index = column_index.get(mapping.id_column) if mapping.id_column else None
        result_index = column_index.get(mapping.result_column)
        out_columns = list(columns) if result_index is not None else columns + [mapping.result_column]

        temp = _temp_path(output_path)
        counts = {"true": 0, "false": 0, "unsure": 0, "fallback": 0}
        errors: list[dict] = []
        total_rows = 0
        processed = 0
        timed_out = False
        try:
            with open(temp, "w", encoding="utf-8", newline="") as out_handle:
                writer = csv.writer(out_handle, lineterminator="\n")
                writer.writerow(out_columns)
                _emit(emit, "step.completed", step="parse", component="processor", message=f"Parsed {len(columns)} columns")
                _emit(emit, "step.started", step="classify", component="classifier", message="Classifying rows")
                for row in reader:
                    if not row:
                        continue
                    if len(row) < len(columns):
                        row = row + [""] * (len(columns) - len(row))
                    elif len(row) > len(columns):
                        row = row[: len(columns)]
                    line_number = processed + 2
                    row_id = _safe_id(row[id_index], f"r-{processed + 1}") if id_index is not None else f"r-{processed + 1}"
                    text = row[text_index]
                    row_date = row[date_index].strip() if date_index is not None else None

                    decision: RowDecision | None = None
                    if deadline_epoch is not None and time.time() >= deadline_epoch:
                        timed_out = True
                        decision = RowDecision(id=row_id, label="unsure", confidence=None, fallback=True,
                                               error="DEADLINE_EXCEEDED", reason="job deadline reached")
                    elif not text.strip():
                        errors.append(_error_entry(row_id, line_number, mapping.text_column, "EMPTY_TEXT", "row has no sentence"))
                        decision = RowDecision(id=row_id, label="unsure", confidence=None, fallback=True, error="EMPTY_TEXT", reason="empty text")
                    elif row_date and not _is_iso_date(row_date):
                        errors.append(_error_entry(row_id, line_number, mapping.date_column or "date", "INVALID_DATE", f"date {row_date!r} is not yyyy-mm-dd"))
                        if len(errors) <= MAX_ERRORS:
                            _emit(emit, "row.failed", rowId=row_id, lineNumber=line_number, column=mapping.date_column, code="INVALID_DATE",
                                  message=f"date {row_date!r} is not yyyy-mm-dd", level="WARN", component="processor", step="classify")
                        row_date = None
                    if decision is None:
                        try:
                            decision = engine.classify(RowInput(id=row_id, text=text, row_date=row_date))
                        except Exception as exc:  # per-row containment
                            decision = RowDecision(
                                id=row_id,
                                label="unsure",
                                confidence=None,
                                fallback=True,
                                error="ROW_ERROR",
                                reason=f"{type(exc).__name__}: {exc}"[:300],
                            )
                    if decision.fallback:
                        counts["fallback"] += 1
                        if decision.error and len(errors) < MAX_ERRORS:
                            errors.append(_error_entry(row_id, line_number, mapping.text_column, decision.error, decision.reason or decision.error))
                            _emit(emit, "row.failed", rowId=row_id, lineNumber=line_number, column=mapping.text_column,
                                  code=decision.error, message=decision.reason or decision.error, level="WARN",
                                  component="classifier", step="classify")
                    else:
                        counts[decision.label if decision.label in ("true", "false", "unsure") else "fallback"] += 1
                    output_row = list(row)
                    label = decision.label if decision.label in ("true", "false", "unsure") else "unsure"
                    if result_index is None:
                        output_row.append(label)
                    else:
                        output_row[result_index] = label
                    writer.writerow(output_row)
                    total_rows += 1
                    processed += 1
                    if progress_every and processed % progress_every == 0:
                        out_handle.flush()
                        _emit(emit, "progress.updated", processedRows=processed, totalRows=None, counts=dict(counts),
                              message=f"Processed {processed} rows")
                if timed_out:
                    _emit(emit, "log.recorded", level="WARN", component="processor", step="classify",
                          message="Job deadline reached; remaining rows were written with the fallback label")
                out_handle.flush()
                os.fsync(out_handle.fileno())
                _emit(emit, "step.completed", step="classify", component="classifier", message=f"Classified {total_rows} rows")
            _emit(emit, "step.started", step="validate", component="processor", message="Validating output table")
            out_columns_check, rows_check = _validate_table(temp)
            if rows_check != total_rows:
                raise ProcessingError(f"output row count mismatch ({rows_check} != {total_rows})")
            _publish(temp, output_path)
            _emit(emit, "step.completed", step="validate", component="processor", message=f"Output valid: {rows_check} rows")
        except BaseException:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    _emit(emit, "progress.updated", processedRows=total_rows, totalRows=total_rows, counts=counts,
          message=f"Processed {total_rows} rows")
    return ProcessOutcome(
        output_path=output_path,
        total_rows=total_rows,
        processed_rows=total_rows,
        counts=counts,
        errors=errors[:MAX_ERRORS],
        duration_seconds=time.time() - started,
        timed_out=timed_out,
        valid=True,
    )


def _is_iso_date(value: str) -> bool:
    import datetime

    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True