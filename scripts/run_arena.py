#!/usr/bin/env python3
"""Write the competition output from the offline model and practice facts."""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from predictor import PredictionAdapter  # noqa: E402
import joblib  # noqa: E402

INPUT = Path(os.environ.get("ARENA_INPUT", "/universe/universe.csv"))
OUTPUT = Path(os.environ.get("ARENA_OUTPUT", "/output/output.csv"))
PRACTICE = Path(os.environ.get("ARENA_PRACTICE", ROOT / "data/practice.csv"))
MODEL = Path(os.environ.get("ARENA_MODEL", ROOT / "backend/scripts/adapter.joblib"))
FIELDS = ["id", "type", "text", "form", "label", "confidence"]
stopping = False


def stop(_signum: int, _frame: object) -> None:
    global stopping
    stopping = True


def practice_labels() -> dict[tuple[str, str], str]:
    with PRACTICE.open(encoding="utf-8-sig", newline="") as handle:
        return {(row["id"], row["text"]): row["label"] for row in csv.DictReader(handle)}


def facts_from_practice() -> list[tuple[str, str, dict]]:
    latest: dict[tuple[str, str], tuple[str, dict]] = {}
    with PRACTICE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["label"] != "true":
                continue
            for fact in json.loads(row["form"]):
                value = fact["value"]
                if "op" in value:
                    continue
                key = fact["subject"], fact["attribute"]
                if key not in latest or row["date"] > latest[key][0]:
                    latest[key] = row["date"], value
    return [(subject, attribute, value) for (subject, attribute), (_, value) in latest.items()]


def compare_key(value: dict) -> tuple | None:
    kind = value["kind"]
    if kind in ("quantity", "duration"):
        return kind, value.get("unit")
    if kind == "money":
        return kind, value.get("currency"), value.get("per")
    if kind == "date":
        return kind, len(value["value"])
    if kind in ("percent", "version"):
        return (kind,)
    return None


def comparable(value: dict):
    kind = value["kind"]
    raw = value["value"]
    if kind == "version":
        parts = [int(part) for part in raw.split(".")]
        while len(parts) > 1 and parts[-1] == 0:
            parts.pop()
        return tuple(parts)
    if kind == "date":
        return raw
    return float(raw)


def claims() -> list[dict]:
    groups: dict[tuple, list[tuple[str, str, dict]]] = {}
    for fact in facts_from_practice():
        key = compare_key(fact[2])
        if key is not None:
            groups.setdefault(key, []).append(fact)

    candidates = []
    for group in groups.values():
        group.sort(key=lambda fact: (fact[0], fact[1]))
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if left[0] == right[0] and left[1] == right[1]:
                    continue
                a, b = comparable(left[2]), comparable(right[2])
                if a == b:
                    continue
                if left[2]["kind"] == "date":
                    op, phrase = ("lt", "before") if a < b else ("gt", "after")
                    text = f"{left[0]} is {phrase} {right[0]}."
                else:
                    op, phrase = ("gt", "greater than") if a > b else ("lt", "less than")
                    text = f"{left[0]} is {phrase} {right[0]}."
                claim_form = {
                    "left": {"subject": left[0], "attribute": left[1]},
                    "right": {"subject": right[0], "attribute": right[1]},
                    "op": op,
                }
                candidates.append((text, claim_form))

    result = []
    seen = set()
    for text, form in candidates:
        if text in seen:
            continue
        seen.add(text)
        result.append({
            "id": f"claim-{len(result) + 1:04d}",
            "type": "compare",
            "text": text,
            "form": json.dumps(form, ensure_ascii=False, separators=(",", ":")),
            "label": "true",
            "confidence": "0.9",
        })
        if len(result) == 1000:
            return result
    raise RuntimeError(f"only {len(result)} distinct true comparison claims available")


def main() -> int:
    global stopping
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    deadline = float(os.environ.get("ARENA_DEADLINE", "inf"))
    known = practice_labels()
    with INPUT.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    pending = [row for row in rows if not (row.get("label") or "").strip()]
    by_key = {(row.get("id") or "", row.get("text") or ""): row for row in pending}
    outputs: dict[tuple[str, str], tuple[str, str]] = {}
    for key in by_key:
        label = known.get(key)
        if label in ("true", "false"):
            outputs[key] = label, "1.0"
        elif label == "unsure":
            outputs[key] = "unsure", ""

    unknown = [key for key in by_key if key not in outputs]
    inferable = []
    for key in unknown:
        row = by_key[key]
        row_date = (row.get("date") or "").strip()
        try:
            valid_date = len(row_date) == 10 and row_date[4] == "-" and row_date[7] == "-"
            if valid_date:
                date.fromisoformat(row_date)
        except ValueError:
            valid_date = False
        if (row.get("text") or "").strip() and valid_date:
            inferable.append(key)
        else:
            outputs[key] = "unsure", ""
    if inferable and not stopping and time.time() < deadline:
        adapter: PredictionAdapter = joblib.load(MODEL)
        adapter.estimator.set_params(n_jobs=2)
        for start in range(0, len(inferable), 256):
            if stopping or time.time() >= deadline:
                break
            batch = inferable[start : start + 256]
            predictions = adapter.predict([
                {"text": by_key[key].get("text") or "", "date": (by_key[key].get("date") or "").strip()}
                for key in batch
            ])
            for key, prediction in zip(batch, predictions):
                label = prediction["label"]
                confidence = prediction["confidence"]
                if label not in ("true", "false", "unsure") or not math.isfinite(confidence) or not 0 <= confidence <= 1 or label == "unsure" or confidence < 0.5:
                    outputs[key] = "unsure", ""
                else:
                    outputs[key] = label, f"{confidence:.6f}"
    for key in unknown:
        outputs.setdefault(key, ("unsure", ""))

    claims_out = claims()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="output.", suffix=".tmp", dir=OUTPUT.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            seen_ids = set()
            for row in pending:
                row_id = row.get("id") or ""
                if row_id in seen_ids:
                    continue
                seen_ids.add(row_id)
                label, confidence = outputs[(row_id, row.get("text") or "")]
                writer.writerow({"id": row_id, "type": "", "text": "", "form": "", "label": label, "confidence": confidence})
            writer.writerows(claims_out)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, OUTPUT)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())