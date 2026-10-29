"""Deterministic risk ranking for contract-checked P3 candidates.

The score is an ordering heuristic, not a probability. Reported confidence is
kept separate and remains conservative until a held-out calibration exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RankedClaim:
    claim: dict[str, Any]
    semantic_key: tuple[Any, ...]
    evidence_ids: tuple[str, ...]
    risk_flags: tuple[str, ...]
    score: float
    generation_rule: str
    verification_status: str = ""
    temporal_assumptions: tuple[str, ...] = ()
    original_confidence: float = 0.5


RULE_RELIABILITY = {
    "asof_rule": 0.72,
    "asof_both_sides": 0.68,
    "fact_observed_on_event_day": 0.64,
}


def score_candidate(candidate: Any) -> tuple[float, tuple[str, ...], tuple[str, ...]]:
    evidence = candidate.evidence or {}
    ids = set()
    temporal = {"max_age_days": 0, "volatile": False, "blocker_count": 0}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            age = value.get("age_days")
            if isinstance(age, (int, float)) and not isinstance(age, bool):
                temporal["max_age_days"] = max(temporal["max_age_days"], age)
            temporal["volatile"] = temporal["volatile"] or value.get("volatile") is True
            blockers = value.get("blockers")
            if isinstance(blockers, list):
                temporal["blocker_count"] += len(blockers)
            if value.get("role", "").startswith(("support", "fact_on_event_day", "event_date", "link", "target_fact")):
                if isinstance(value.get("row_id"), str):
                    ids.add(value["row_id"])
            if isinstance(value.get("fact_rows"), list):
                ids.update(x for x in value["fact_rows"] if isinstance(x, str))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(evidence)
    flags = set(candidate.flags or ())
    rule = candidate.rule.split("=", 1)[-1]
    base = RULE_RELIABILITY.get(rule, 0.58)
    base += min(0.12, max(0, len(ids) - 1) * 0.025)
    base -= min(0.2, temporal["max_age_days"] * 0.004)
    if temporal["volatile"]:
        base -= 0.14
        flags.add("volatile_temporal_history")
    if temporal["blocker_count"]:
        base -= min(0.25, 0.1 + 0.03 * temporal["blocker_count"])
        flags.add("contradictory_observation_context")
    if candidate.engine.get("status") != "VERIFIED_SUPPORT":
        base -= 0.12
        flags.add("engine_not_verified_support")
    if "cross_attribute_compare" in flags:
        base -= 0.2
    if any("reschedul" in x.casefold() for x in flags):
        base -= 0.3
    for token in ("reconstructed", "relaxed", "safe_transition", "cross_attribute"):
        if any(token in x.casefold() for x in flags) or token in rule.casefold():
            base -= 0.18
    return max(0.0, min(1.0, base)), tuple(sorted(flags)), tuple(sorted(ids))


def reported_confidence(candidate: Any) -> float:
    """A conservative, non-calibrated output value; no heuristic is called certainty."""
    score, flags, ids = score_candidate(candidate)
    if not candidate.verified or candidate.status != "accepted":
        return 0.5
    if score >= 0.76 and len(ids) >= 2 and not flags:
        return 0.65
    if score >= 0.62 and len(ids) >= 1 and not flags:
        return 0.58
    return 0.5
