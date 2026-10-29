"""Compatibility entry point for the final calibrated M2 + P3 anytime runner."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runner import main

if __name__ == "__main__":
    raise SystemExit(main())
