"""Standalone processor entry point (no HTTP API, no browser).

Sends the CSV to the teammates' HTTP classification service and writes the
returned table. Useful for etapa B validation and for debugging the remote
integration without starting FastAPI.

  python -m app.engine.cli --input ../data/practice.csv --output /tmp/out.csv \
      --text-column text --date-column date --id-column id --result-column label \
      --classifier-url http://127.0.0.1:8010/classify
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .api import MappingSpec, process_csv
from .remote_engine import ClassifierUnavailable, RemoteClassifierEngine


def emit(event_type: str, payload: dict) -> None:
    message = payload.get("message") or payload.get("code") or ""
    level = payload.get("level", "INFO")
    print(json.dumps({"event": event_type, "level": level, "message": message}, ensure_ascii=False), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CSV -> classification service -> labelled CSV")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--text-column", default="text")
    parser.add_argument("--date-column", default="date")
    parser.add_argument("--id-column", default="id")
    parser.add_argument("--result-column", default="label")
    parser.add_argument("--classifier-url", action="append", default=[], help="repeatable; overrides env")
    parser.add_argument("--classifier-mode", default=os.environ.get("NEURON_CLASSIFIER_MODE", "csv"), choices=["csv", "rows"])
    parser.add_argument("--as-of", default=os.environ.get("NEURON_AS_OF", "2026-10-29"))
    parser.add_argument("--deadline-seconds", type=int, default=0, help="0 = no local deadline")
    args = parser.parse_args(argv)

    urls = tuple(args.classifier_url) or tuple(
        u.strip() for u in (os.environ.get("NEURON_CLASSIFIER_URLS") or os.environ.get("NEURON_CLASSIFIER_URL") or "").split(",") if u.strip()
    )
    if not urls:
        print("no classifier URL: pass --classifier-url or set NEURON_CLASSIFIER_URLS", file=sys.stderr)
        return 2

    engine = RemoteClassifierEngine(urls, mode=args.classifier_mode, as_of=args.as_of)
    mapping = MappingSpec(
        text_column=args.text_column,
        date_column=args.date_column or None,
        id_column=args.id_column or None,
        result_column=args.result_column,
    )
    deadline = time.time() + args.deadline_seconds if args.deadline_seconds else None
    try:
        outcome = process_csv(args.input, args.output, mapping, engine, deadline_epoch=deadline, emit=emit, as_of=args.as_of)
    except ClassifierUnavailable as exc:
        print(json.dumps({"ok": False, "error": "CLASSIFIER_UNAVAILABLE", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    finally:
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
