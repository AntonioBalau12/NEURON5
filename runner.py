"""Minimal offline contract runner. No unsupported claims are synthesized."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import tempfile
import time
import threading
from pathlib import Path
from typing import Any, Callable

from foundation import OUTPUT_COLUMNS, InputData, evidence_audit, load_inputs, validate_output
from core.claims.checkpoint import CheckpointManager
from core.claims.factory import ClaimFactory


def default_path(runtime: str, local: str) -> str:
    return runtime if Path(runtime).exists() else str(Path(__file__).resolve().parent / local)


def atomic_write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    """Write in the destination directory then atomically replace output.csv."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_candidates(path: str | Path) -> list[dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list) or not all(isinstance(x, dict) for x in raw):
        raise ValueError("candidate file must be a JSON array of claim objects")
    return raw


def predict_unlabeled(data: InputData, model_path: str, practice_path: str, *, deadline: int = 0,
                      progress: Callable[[dict[str, tuple[str, float | None]]], None] | None = None,
                      stop_event: threading.Event | None = None, chunk_size: int = 256,
                      checkpoint_every: int = 1000) -> dict[str, tuple[str, float | None]]:
    """Run serialized M2 inference incrementally; never use runtime forms."""
    from ml.classical.runtime import M2Runtime

    model = M2Runtime(model_path, practice_path)
    pending = [row for row in data.rows if row.label is None]
    result: dict[str, tuple[str, float | None]] = {}
    for row in pending:
        if not row.text.strip() or row.date is None:
            result[row.row_id] = ("unsure", None)
    usable = [row for row in pending if row.text.strip() and row.date is not None]
    processed = 0
    for offset in range(0, len(usable), max(1, chunk_size)):
        if (deadline and time.time() >= deadline) or (stop_event is not None and stop_event.is_set()):
            break
        chunk = usable[offset:offset + max(1, chunk_size)]
        model_rows = [{"id": row.row_id, "text": row.text, "date": row.date.isoformat()} for row in chunk]
        for row, prediction in zip(chunk, model.predict(model_rows), strict=True):
            result[row.row_id] = (prediction["label"], prediction["confidence"])
        processed += len(chunk)
        if progress is not None and processed % max(1, checkpoint_every) < len(chunk):
            progress(result.copy())
    if progress is not None and result:
        progress(result.copy())
    return result


def run(
    universe: str,
    lexicon: str,
    output: str,
    contract_dir: str,
    candidates_path: str | None = None,
    model_path: str | None = None,
    practice_path: str | None = None,
) -> int:
    os.environ.setdefault("HOME", "/tmp")
    os.environ.setdefault("XDG_CACHE_HOME", "/tmp/.cache")
    os.environ.setdefault("HF_HOME", "/tmp/huggingface")
    try:
        deadline = int(os.environ.get("ARENA_DEADLINE", "0"))
    except ValueError:
        print("ARENA_DEADLINE must be Unix seconds", file=sys.stderr)
        return 2
    if deadline and time.time() >= deadline:
        print("ARENA_DEADLINE has passed; stopping without writing output", file=sys.stderr)
        return 2
    data = load_inputs(universe, lexicon)
    if data.lexicon is None or any(x.startswith("lexicon:") for x in data.issues):
        print("input/lexicon validation failed:", *data.issues, sep="\n- ", file=sys.stderr)
        return 2
    if any(not row.row_id for row in data.rows) or len({row.row_id for row in data.rows}) != len(data.rows):
        print("input has missing or duplicate row IDs; cannot produce unambiguous label rows", file=sys.stderr)
        return 2
    audit = evidence_audit(data)
    print("evidence audit:", json.dumps(audit, sort_keys=True))
    packaged_practice = practice_path or str(Path(__file__).resolve().parent / "data" / "practice.csv")
    packaged_model = model_path or os.environ.get(
        "NEURON_M2_MODEL",
        str(Path(__file__).resolve().parent / "ml" / "classical" / "results_m2_v2" / "model.joblib"),
    )
    fallback_predictions = {row.row_id: ("unsure", None) for row in data.rows if row.label is None}
    predictions = fallback_predictions
    manager = CheckpointManager(output, data, contract_dir)
    try:
        if not manager.publish(predictions, []):
            print("initial UNSURE checkpoint validation failed:", *manager.last_validation[:30], sep="\n- ", file=sys.stderr)
            return 2
    except OSError as exc:
        print(f"cannot publish initial UNSURE checkpoint: {exc}", file=sys.stderr)
        return 2
    stop_event = threading.Event()
    previous_handler = None
    if hasattr(signal, "SIGTERM"):
        try:
            previous_handler = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGTERM, lambda _signum, _frame: stop_event.set())
        except (ValueError, OSError):  # signal handlers can only be installed on the main thread
            previous_handler = None
    inference_predictions = fallback_predictions.copy()

    def checkpoint_inference(partial: dict[str, tuple[str, float | None]]) -> None:
        inference_predictions.update(partial)
        try:
            if not manager.publish(inference_predictions, []):
                print("inference checkpoint rejected; previous checkpoint preserved:",
                      *manager.last_validation[:10], sep="\n- ", file=sys.stderr)
        except OSError as exc:
            print(f"inference checkpoint write failed; previous checkpoint preserved: {exc}", file=sys.stderr)

    try:
        inferred = predict_unlabeled(data, packaged_model, packaged_practice, deadline=deadline,
                                      progress=checkpoint_inference, stop_event=stop_event)
        inference_predictions.update(inferred)
    except Exception as exc:
        print(f"M2 inference unavailable; using UNSURE for unprocessed rows: {exc}", file=sys.stderr)
        predictions = inference_predictions
    else:
        try:
            if manager.publish(inference_predictions, []):
                predictions = inference_predictions
                print(f"M2 inference completed: {len(inferred)} unlabeled rows")
            else:
                print("classification checkpoint validation failed; keeping all-UNSURE checkpoint:",
                      *manager.last_validation[:30], sep="\n- ", file=sys.stderr)
        except OSError as exc:
            print(f"cannot update classification checkpoint; keeping all-UNSURE checkpoint: {exc}", file=sys.stderr)
    claims: list[dict[str, Any]] = []
    # Publish a validated classification checkpoint before claim generation.
    # Generation failure or SIGTERM therefore leaves a complete label file.
    factory = ClaimFactory(universe, lexicon, packaged_practice, contract_dir, deadline, stop_event=stop_event,
                           publication_seconds=manager.last_elapsed)

    def checkpoint_claims(partial_claims: list[dict[str, Any]]) -> float:
        try:
            exact_partial = len(partial_claims) == 1000
            if not manager.publish(predictions, partial_claims, exact=exact_partial):
                print("claim checkpoint rejected; previous valid output preserved:",
                      *manager.last_validation[:10], sep="\n- ", file=sys.stderr)
        except OSError as exc:
            print(f"claim checkpoint write failed; previous valid output preserved: {exc}", file=sys.stderr)
        return manager.last_elapsed

    try:
        if not stop_event.is_set() and (not deadline or time.time() < deadline):
            if candidates_path:
                print("--candidates-json is not accepted for publication; candidates require P3 evidence provenance", file=sys.stderr)
            claims, metrics = factory.generate(on_checkpoint=checkpoint_claims)
            summary = {key: value for key, value in metrics.items()
                       if key not in {"selected_claim_trace", "selected_shared_evidence_ids"}}
            print("claim factory:", json.dumps(summary, sort_keys=True))
    except Exception as exc:
        print(f"claim generation failed; preserving the validated classification checkpoint: {exc}", file=sys.stderr)
        claims = []
    finally:
        if previous_handler is not None:
            try:
                signal.signal(signal.SIGTERM, previous_handler)
            except (ValueError, OSError):
                pass

    claims = claims[:1000]
    exact = len(claims) == 1000
    try:
        if not manager.publish(predictions, claims, exact=exact):
            print("final output validation failed; previous valid checkpoint preserved:",
                  *manager.last_validation[:30], sep="\n- ", file=sys.stderr)
            return 2
    except OSError as exc:
        print(f"cannot publish final output: {exc}; previous checkpoint preserved", file=sys.stderr)
        return 2
    if manager.preserved_complete:
        print("kept the previously validated complete 1,000-claim output")
    elif not exact:
        print(f"published best available output with {len(claims)} claims; deficit={1000-len(claims)}. "
              "This is not 1,000-claim compliance.", file=sys.stderr)
    else:
        print(f"wrote {output}; claims={len(claims)}; checkpoint_write_seconds={manager.last_elapsed:.3f}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=default_path("/universe/universe.csv", "data/practice.csv"))
    parser.add_argument("--lexicon", default=default_path("/universe/lexicon.json", "data/lexicon.json"))
    parser.add_argument("--output", default=default_path("/output/output.csv", "output/output.csv"))
    parser.add_argument("--contract-dir", default=str(Path(__file__).resolve().parent / "contracts"))
    parser.add_argument("--candidates-json", help="Deprecated; external claims are rejected without evidence provenance")
    parser.add_argument("--model", default=None, help="Path to the serialized M2 model")
    parser.add_argument("--practice", default=None, help="Path to packaged practice evidence with forms")
    args = parser.parse_args()
    return run(args.universe, args.lexicon, args.output, args.contract_dir, args.candidates_json, args.model, args.practice)


if __name__ == "__main__":
    raise SystemExit(main())
