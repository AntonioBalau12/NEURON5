"""Stream local model predictions into an atomically published CSV table.

The mapped label is overwritten or appended. Other cells, row order, frontend
progress events and per-row error containment retain their existing contract.
"""

from __future__ import annotations

import csv
import os
import tempfile
import time
from pathlib import Path

from .api import Engine, EventEmitter, MappingSpec, ProcessOutcome, RowDecision, RowInput, emit_event

MAX_ERRORS = 2000


class ProcessingError(RuntimeError):
    """Infrastructure error: the job cannot produce a valid output."""


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


def _safe_id(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value or fallback


def process_csv(
    input_path: str | Path,
    output_path: str | Path,
    mapping: MappingSpec,
    engine: Engine,
    *,
    deadline_epoch: float | None = None,
    emit: EventEmitter | None = None,
    progress_every: int = 50,
    as_of: str | None = None,
) -> ProcessOutcome:
    input_path = Path(input_path)
    output_path = Path(output_path)
    started = time.time()
    engine.prepare()
    parse_started = time.perf_counter()
    emit_event(
        emit,
        "step.started",
        step="parse",
        component="processor",
        message="Reading dataset snapshot.",
        details={
            "inputBytes": input_path.stat().st_size,
            "textColumn": mapping.text_column,
            "dateColumn": mapping.date_column,
            "idColumn": mapping.id_column,
            "resultColumn": mapping.result_column,
        },
    )
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
                emit_event(
                    emit,
                    "step.completed",
                    step="parse",
                    component="processor",
                    message=f"Read {len(columns)} input columns.",
                    durationMs=round((time.perf_counter() - parse_started) * 1000),
                    details={
                        "columnCount": len(columns),
                        "columns": columns,
                        "resultColumnExisted": result_index is not None,
                    },
                )
                classify_started = time.perf_counter()
                emit_event(
                    emit,
                    "step.started",
                    step="classify",
                    component="classifier",
                    message="Classifying rows.",
                    details={"progressEveryRows": progress_every},
                )
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
                        decision = RowDecision(id=row_id, label="unsure", confidence=None, fallback=True, error="EMPTY_TEXT", reason="empty text")
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
                            error_column = mapping.date_column if decision.error in ("MISSING_DATE", "INVALID_DATE") else mapping.text_column
                            errors.append(_error_entry(row_id, line_number, error_column, decision.error, decision.reason or decision.error))
                            emit_event(emit, "row.failed", rowId=row_id, lineNumber=line_number, column=error_column,
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
                        elapsed = max(time.perf_counter() - classify_started, 0.001)
                        emit_event(
                            emit,
                            "progress.updated",
                            processedRows=processed,
                            totalRows=None,
                            counts=dict(counts),
                            message=f"Processed {processed} rows.",
                            details={"rowsPerSecond": round(processed / elapsed, 2)},
                        )
                if timed_out:
                    emit_event(
                        emit,
                        "log.recorded",
                        level="WARN",
                        component="processor",
                        step="classify",
                        message="Job deadline reached; remaining rows were written with the fallback label.",
                        details={"processedRows": processed, "fallbackRows": counts["fallback"]},
                    )
                out_handle.flush()
                os.fsync(out_handle.fileno())
                classify_duration = time.perf_counter() - classify_started
                emit_event(
                    emit,
                    "step.completed",
                    step="classify",
                    component="classifier",
                    message=f"Classified {total_rows} rows.",
                    durationMs=round(classify_duration * 1000),
                    details={
                        "processedRows": total_rows,
                        "counts": dict(counts),
                        "errorRows": len(errors),
                        "timedOut": timed_out,
                        "rowsPerSecond": round(total_rows / max(classify_duration, 0.001), 2),
                    },
                )
            validate_started = time.perf_counter()
            emit_event(
                emit,
                "step.started",
                step="validate",
                component="processor",
                message="Validating output table.",
                details={"outputBytes": temp.stat().st_size, "expectedRows": total_rows},
            )
            out_columns_check, rows_check = _validate_table(temp)
            if rows_check != total_rows:
                raise ProcessingError(f"output row count mismatch ({rows_check} != {total_rows})")
            _publish(temp, output_path)
            emit_event(
                emit,
                "step.completed",
                step="validate",
                component="processor",
                message=f"Output validated: {rows_check} rows.",
                durationMs=round((time.perf_counter() - validate_started) * 1000),
                details={
                    "rowCount": rows_check,
                    "columnCount": len(out_columns_check),
                    "columns": out_columns_check,
                    "outputBytes": output_path.stat().st_size,
                },
            )
        except BaseException:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    emit_event(emit, "progress.updated", processedRows=total_rows, totalRows=total_rows, counts=counts,
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
