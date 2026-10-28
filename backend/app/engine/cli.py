"""Run the local model over a CSV without starting FastAPI."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time

from ..config import get_settings
from .api import ClassifierUnavailable, MappingSpec, create_engine, process_csv
from .processor import ProcessingError


def emit(event_type: str, payload: dict) -> None:
    message = payload.get("message") or payload.get("code") or ""
    level = payload.get("level", "INFO")
    print(json.dumps({"event": event_type, "level": level, "message": message}, ensure_ascii=False), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV -> local LightGBM model -> labelled CSV")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", type=Path, help="override NEURON_MODEL_PATH")
    parser.add_argument("--text-column", default="text")
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--result-column", default="label")
    parser.add_argument("--deadline-seconds", type=int, default=0, help="0 = no local deadline")
    args = parser.parse_args(argv)
    if args.deadline_seconds < 0:
        parser.error("--deadline-seconds must be non-negative")
    deadlines = [time.time() + args.deadline_seconds] if args.deadline_seconds else []
    if os.environ.get("ARENA_DEADLINE"):
        try:
            deadlines.append(float(os.environ["ARENA_DEADLINE"]))
        except ValueError:
            parser.error("ARENA_DEADLINE must be Unix seconds")
    deadline = min(deadlines) if deadlines else None
    settings = get_settings()
    if args.model is not None:
        settings = replace(settings, model_path=args.model)
    mapping = MappingSpec(
        text_column=args.text_column,
        date_column=args.date_column or None,
        id_column=args.id_column or None,
        result_column=args.result_column,
    )
    engine = None
    try:
        engine = create_engine(settings=settings)
        outcome = process_csv(args.input, args.output, mapping, engine, deadline_epoch=deadline, emit=emit)
    except (ClassifierUnavailable, ProcessingError, OSError) as exc:
        code = "CLASSIFIER_UNAVAILABLE" if isinstance(exc, ClassifierUnavailable) else "PROCESSOR_ERROR"
        print(json.dumps({"ok": False, "error": code, "message": str(exc)}, ensure_ascii=False))
        return 1
    finally:
        if engine is not None:
            engine.close()
    print(json.dumps({
        "ok": outcome.valid,
        "output": str(outcome.output_path),
        "totalRows": outcome.total_rows,
        "counts": outcome.counts,
        "errors": len(outcome.errors),
        "durationSeconds": round(outcome.duration_seconds, 2),
        "timedOut": outcome.timed_out,
    }, ensure_ascii=False, indent=2))
    return 0 if outcome.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
