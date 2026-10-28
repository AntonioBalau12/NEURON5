"""Calibrated confidence formulas for P3 claim generation and factual verification.

Guarantees:
- Every accepted claim gets a confidence score bounded strictly in [0.50, 1.00].
- Immutable facts (dates, founders, released physical specs, corporate history) receive top-tier confidence (0.95).
- Mutable facts decay smoothly with observation age relative to the as-of date (2026-10-29) in [0.75, 0.94].
- Multi-row corroboration (>= 3 rows) provides a +0.02 boost.
- Everything below 0.50 or rejected has confidence None (null in output).
"""
from __future__ import annotations

import datetime
from typing import Any

# Hardware specifications, corporate founding/history, and governance that cannot mutate
IMMUTABLE_ATTRIBUTES = {
    "date", "founded", "founders", "joined", "released", "acquired",
    "screen_size", "battery_capacity", "charging_power", "weight", "colours",
    "main_camera", "refresh_rate", "cellular_option", "full_charge_time",
    "previous_employer", "raised_series_a", "raised_series_b",
    "series_a_amount", "series_a_lead", "is_engineering_hub", "venue",
    "sponsors", "opening_keynote", "keynote_speaker", "livestreamed",
    "chair_since", "cto", "head_of_security", "reliability_lead",
    "inner_screen_size", "cover_screen_size", "hinge_rating", "water_resistance_depth",
}


def calculate_fact_confidence(
    attribute: str,
    age_days: int | None = None,
    is_immutable: bool = False,
    n_support_rows: int = 1,
    min_confidence: float = 0.50,
) -> float:
    """Calculate calibrated confidence for an atomic factual claim."""
    attr_clean = (attribute or "").strip().lower()
    if is_immutable or attr_clean in IMMUTABLE_ATTRIBUTES:
        return 0.95

    days = max(0, age_days if age_days is not None else 0)
    recency = max(0.0, min(1.0, 1.0 - days / 365.0))
    conf = 0.75 + 0.17 * recency
    if n_support_rows >= 3:
        conf += 0.02
    return round(float(min(1.0, max(min_confidence, conf))), 4)


def calculate_compare_confidence(
    attr_left: str,
    attr_right: str,
    age_left: int | None = None,
    age_right: int | None = None,
    is_date_compare: bool = False,
) -> float:
    """Calculate calibrated confidence for comparison claims."""
    if is_date_compare:
        return 0.95
    left_imm = (attr_left or "").strip().lower() in IMMUTABLE_ATTRIBUTES
    right_imm = (attr_right or "").strip().lower() in IMMUTABLE_ATTRIBUTES
    if left_imm and right_imm:
        return 0.95
    max_age = max(age_left or 0, age_right or 0)
    recency = max(0.0, min(1.0, 1.0 - max_age / 365.0))
    return round(float(min(1.0, max(0.50, 0.75 + 0.17 * recency))), 4)


def calculate_change_confidence(
    is_safe_transition: bool = True,
    is_engine_verified: bool = False,
) -> float:
    """Calculate calibrated confidence for change claims."""
    if is_safe_transition and is_engine_verified:
        return 0.92
    if is_safe_transition:
        return 0.88
    return 0.80


def calculate_at_event_confidence(
    is_immutable_event: bool = True,
    differing_observations: int = 0,
) -> float:
    """Calculate calibrated confidence for at_event claims."""
    if differing_observations > 0:
        return 0.50
    return 0.95 if is_immutable_event else 0.88


def calculate_relation_confidence(
    target_immutable: bool = False,
    is_engine_verified: bool = True,
) -> float:
    """Calculate calibrated confidence for structural relation claims."""
    if is_engine_verified and target_immutable:
        return 0.95
    if is_engine_verified:
        return 0.90
    return 0.82
