"""Shared constants and path setup for the claim-factory experiment (read-only reuse of repo code)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SHARED = ROOT / "experiments" / "shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

PRACTICE_CSV = ROOT / "data" / "practice.csv"
LEXICON_JSON = ROOT / "data" / "lexicon.json"
CONTRACT_DIR = ROOT / "contracts"
AS_OF = date(2026, 10, 29)
CLAIM_TYPES = ("fact", "compare", "change", "at_event", "relation")
