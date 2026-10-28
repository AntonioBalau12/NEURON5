"""Minimal offline contract runner. No unsupported claims are synthesized."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from foundation import OUTPUT_COLUMNS, InputData, evidence_audit, load_inputs, validate_output


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


def run(universe: str, lexicon: str, output: str, contract_dir: str, candidates_path: str | None = None) -> int:
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
    # The P0 runner has no claim-generation model. It accepts externally
    # produced candidates only after the official schema and local checks pass.
    if not candidates_path:
        print("cannot meet exactly 1,000 claims: no verified candidate source is available", file=sys.stderr)
        print("no output written; unsupported claims will not be fabricated", file=sys.stderr)
        return 2
    try:
        claims = read_candidates(candidates_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"cannot load claim candidates: {exc}", file=sys.stderr)
        return 2
    if len(claims) != 1000:
        print(f"candidate count is {len(claims)}, not 1,000; no output written", file=sys.stderr)
        return 2
    rows: list[dict[str, Any]] = []
    for row in data.rows:
        if row.label is None:
            rows.append({"id": row.row_id, "type": "", "text": "", "form": "", "label": "unsure", "confidence": ""})
    for claim in claims:
        rows.append({
            "id": claim.get("id", ""), "type": claim.get("type", ""), "text": claim.get("text", ""),
            "form": json.dumps(claim.get("form", {}), ensure_ascii=False, separators=(",", ":")),
            "label": claim.get("label", "true"), "confidence": claim.get("confidence", 0.5),
        })
    # Validate a temporary candidate before replacing any previously complete output.
    dest = Path(output)
    staged = dest.with_name(dest.name + ".validate.tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(staged, rows)
        problems = validate_output(staged, data, contract_dir)
        if problems:
            print("output validation failed:", *problems[:40], sep="\n- ", file=sys.stderr)
            staged.unlink(missing_ok=True)
            return 2
        if deadline and time.time() >= deadline:
            print("deadline passed before output commit", file=sys.stderr)
            staged.unlink(missing_ok=True)
            return 2
        os.replace(staged, dest)
    except OSError as exc:
        print(f"cannot publish output: {exc}", file=sys.stderr)
        return 2
    finally:
        try:
            staged.unlink(missing_ok=True)
        except OSError:
            pass
    print(f"wrote {dest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default=default_path("/universe/universe.csv", "data/practice.csv"))
    parser.add_argument("--lexicon", default=default_path("/universe/lexicon.json", "data/lexicon.json"))
    parser.add_argument("--output", default=default_path("/output/output.csv", "output/output.csv"))
    parser.add_argument("--contract-dir", default=str(Path(__file__).resolve().parent / "contracts"))
    parser.add_argument("--candidates-json", help="JSON array of 1,000 precomputed verified claim candidates")
    args = parser.parse_args()
    return run(args.universe, args.lexicon, args.output, args.contract_dir, args.candidates_json)


if __name__ == "__main__":
    raise SystemExit(main())
