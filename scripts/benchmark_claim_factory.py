"""Reproduce P3 ClaimFactory profiling and compare conservative/all-safe strategies."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.claims.checkpoint import CheckpointManager
from core.claims.factory import SAFE_STRATEGIES, ClaimFactory
from foundation import load_inputs


BASELINE_STRATEGIES = ("fact", "compare", "change")


def _run_case(name: str, strategies: tuple[str, ...], universe: Path, lexicon: Path,
              practice: Path, contracts: Path, max_claims: int, checkpoint_mode: str,
              validate_final: bool) -> dict[str, Any]:
    data = load_inputs(universe, lexicon)
    if data.lexicon is None or data.issues:
        raise RuntimeError(f"benchmark input failed validation: {data.issues}")
    predictions = {row.row_id: ("unsure", None) for row in data.rows if row.label is None}
    with tempfile.TemporaryDirectory(prefix=".p3-claim-benchmark-", dir=ROOT) as temp:
        manager = CheckpointManager(Path(temp) / "output.csv", data, contracts)

        def publish(claims: list[dict[str, Any]]) -> float:
            exact = len(claims) == 1000
            if not manager.publish(predictions, claims, exact=exact):
                raise RuntimeError("checkpoint output validation failed: " + "; ".join(manager.last_validation[:8]))
            return manager.last_elapsed

        factory = ClaimFactory(universe, lexicon, practice, contracts)
        wall_started = time.perf_counter()
        if checkpoint_mode == "real":
            claims, metrics = factory.generate(strategies=strategies, max_claims=max_claims,
                                               on_checkpoint=publish)
        elif checkpoint_mode == "simulated":
            claims, metrics = factory.generate(strategies=strategies, max_claims=max_claims,
                                               on_checkpoint=lambda _claims: 0.0)
        else:
            claims, metrics = factory.generate(strategies=strategies, max_claims=max_claims)
        wall_seconds = time.perf_counter() - wall_started
        if len(claims) != 1000:
            raise RuntimeError(f"expected production fallback of 1,000 claims, got {len(claims)}")
        if validate_final and checkpoint_mode != "real":
            publish(claims)
            if manager.last_validation:
                raise RuntimeError("final output failed official local validation: " + "; ".join(manager.last_validation[:8]))
        return {
            "name": name,
            "strategies": list(strategies),
            "wall_seconds": round(wall_seconds, 6),
            "official_local_checker": "passed" if validate_final or checkpoint_mode == "real" else "not run",
            "claims_selected": len(claims),
            "checkpoint_last_elapsed_seconds": round(manager.last_elapsed, 6),
            "checkpoint_mode": checkpoint_mode,
            "metrics": metrics,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", type=Path, default=ROOT / "data" / "practice.csv")
    parser.add_argument("--lexicon", type=Path, default=ROOT / "data" / "lexicon.json")
    parser.add_argument("--practice", type=Path, default=ROOT / "data" / "practice.csv")
    parser.add_argument("--contracts", type=Path, default=ROOT / "contracts")
    parser.add_argument("--max-claims", type=int, default=1500)
    parser.add_argument("--checkpoint-mode", choices=("none", "simulated", "real"), default="simulated",
                        help="none ranks once; simulated checkpoints without I/O; real publishes after every phase")
    parser.add_argument("--validate-final", action="store_true",
                        help="run atomic serialization and official local validation once on final claims")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments" / "p3_claim_pool_1500" / "profile.json")
    args = parser.parse_args()
    reports = [
        _run_case("three_strategy_baseline", BASELINE_STRATEGIES, args.universe, args.lexicon,
                  args.practice, args.contracts, args.max_claims, args.checkpoint_mode, args.validate_final),
        _run_case("production_all_verified_strategies", SAFE_STRATEGIES, args.universe, args.lexicon,
                  args.practice, args.contracts, args.max_claims, args.checkpoint_mode, args.validate_final),
    ]
    report = {"dataset": str(args.universe), "rows": len(load_inputs(args.universe, args.lexicon).rows),
              "target_distinct_accepted": 1500, "production_output_claims": 1000, "cases": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for case in reports:
        metrics = case["metrics"]
        print(json.dumps({"case": case["name"], "wall_seconds": case["wall_seconds"],
                          "generated": metrics["generated_candidates"],
                          "accepted": metrics["distinct_contract_accepted"],
                          "selected": case["claims_selected"], "reserve": metrics["reserve"]["count"],
                          "profile": metrics["timing_profile"]}, ensure_ascii=False, sort_keys=True))
    print(f"report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
