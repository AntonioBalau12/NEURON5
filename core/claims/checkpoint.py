"""Validated, atomic output publication for complete or partial claim pools."""
from __future__ import annotations

import csv
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from foundation import OUTPUT_COLUMNS, validate_output


class CheckpointManager:
    def __init__(self, output: str | Path, input_data: Any, contract_dir: str | Path):
        self.output = Path(output)
        self.input_data = input_data
        self.contract_dir = contract_dir
        self.last_validation: list[str] = []
        self.last_elapsed = 0.0
        self.preserved_complete = False

    def publish(self, labels: dict[str, tuple[str, float | None]], claims: list[dict[str, Any]], *, exact: bool = False) -> bool:
        start = time.monotonic()
        # A previously complete, officially valid output is more valuable than
        # any partial checkpoint. Preserve it unless a newly validated exact
        # 1,000-claim result is ready to atomically replace it.
        if not exact and self.output.is_file():
            existing_issues = validate_output(self.output, self.input_data, self.contract_dir, expected_claims=1000)
            if not existing_issues:
                self.last_validation = []
                self.last_elapsed = time.monotonic() - start
                self.preserved_complete = True
                return True
        rows: list[dict[str, Any]] = []
        for row in self.input_data.rows:
            if row.label is None:
                label, confidence = labels.get(row.row_id, ("unsure", None))
                rows.append({"id": row.row_id, "type": "", "text": "", "form": "", "label": label,
                             "confidence": "" if confidence is None else confidence})
        for claim in claims:
            rows.append({"id": claim["id"], "type": claim["type"], "text": claim["text"],
                         "form": json.dumps(claim["form"], ensure_ascii=False, separators=(",", ":")),
                         "label": "true", "confidence": claim["confidence"]})
        self.output.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.output.name + ".", suffix=".tmp", dir=self.output.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            self.last_validation = validate_output(temp_name, self.input_data, self.contract_dir,
                                                   expected_claims=1000 if exact else len(claims))
            if self.last_validation:
                return False
            os.replace(temp_name, self.output)
            self.preserved_complete = False
            return True
        finally:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            self.last_elapsed = time.monotonic() - start
