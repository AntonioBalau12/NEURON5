"""Evidence store for the claim factory: core.graph + observation layer + the documented as-of rule.

Nothing here builds a new knowledge graph.  The graph is core.graph.build_graph_from_paths over data/practice.csv with the
forms as reference evidence (verified support = forms on TRUE rows only).  Queries go through TemporalIndex /
EvidenceResolver / ReasoningEngine; the observation layer (observations.py) only classifies the graph's FactRecords.

THE AS-OF RULE (``asof_fact``)  -- documented, conservative, configurable.
A (subject, attribute) fact is accepted as "has value v on 29 Oct 2026" only if ALL hold:
  R1  v is the value of the LATEST verified-support observation (a form on a TRUE row), and that observation is exact
      (no op) and "clean" (its sentence has no past/future/plan wording, see observations.sentence_cues).
  R2  No observation of any other trust level dated on or after that observation states a different value:
      CONFLICTING records and form-grounded candidates (false/unsure rows, form fragments) block.  Parser-only text
      candidates are not independent of the form and are counted but do not block.
  R3  Corroboration: the trailing run of observations equal to v holds >= ``min_support_rows`` clean rows on distinct
      rows (default 2).  Exception: a date that already happened (value <= the row's date) on a key that never
      changed needs only 1 (dated events do not move).
  R4  Freshness: if the key has ever shown more than one verified value ("volatile"), the latest support must be at most
      ``volatile_max_age_days`` (default 60) before the as-of date.  Non-volatile keys have no age limit (>= 2 rows).
Nothing in the graph proves persistence; R1-R4 are a heuristic whose error is measured by backtest.py.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .cf_common import AS_OF, LEXICON_JSON, PRACTICE_CSV, ROOT  # noqa: F401
from foundation import AtomicFact, Lexicon, TypedValue, compare_values  # type: ignore
from core.graph import EvidenceResolver, ReasoningEngine, TemporalIndex, build_graph_from_paths
from .observations import Obs, build_observations, finest_equivalent, same_value
from .textcheck import Names


# attributes that name a ONE-TIME event: once the date has passed it does not change (a priori, by meaning; the backtest
# shows 0 contradictions on them, whereas "latest_release_date"/"stable_release_date" are moving targets and are excluded)
IMMUTABLE_EVENT_DATE_ATTRS = {"joined", "founded", "launched", "released", "opened", "announced", "published", "date", "beta_date",
                              "beta_opened", "general_availability_date", "stable_release", "training_data_cutoff"}

# definitive / structural attributes: hardware specs, corporate milestones, governance appointments, fixed tier capabilities
HARDWARE_SPECS = {
    'battery_capacity', 'screen_size', 'weight', 'charging_power', 'memory',
    'cover_screen_size', 'inner_screen_size', 'hinge_rating', 'water_resistance_depth',
    'colours', 'main_camera', 'refresh_rate', 'shipping_android', 'cellular_option', 'full_charge_time'
}
CORP_HISTORY = {
    'founded', 'founders', 'previous_employer',
    'raised_series_a', 'raised_series_b', 'series_a_amount', 'series_a_lead', 'series_a_co_investor',
    'manufacturing_partner', 'integration_partner_of_flawless', 'is_engineering_hub'
}
PAST_EVENT_SPECS = {
    'venue', 'opening_keynote', 'keynote_speaker', 'keynote_length', 'livestreamed',
    'devices_keynote_speaker', 'talks', 'sponsors', 'attendees'
}
GOVERNANCE = {
    'chair', 'chair_since', 'raviqa_seat', 'independent_director', 'independent_members',
    'cto', 'head_of_product', 'head_of_security', 'head_of_workspace', 'reliability_lead'
}
TECH_SPECS = {
    'data_processing_agreement', 'encryption_at_rest', 'single_sign_on', 'open_source',
    'history_retention', 'end_to_end_encryption', 'offline_editing', 'simultaneous_editors',
    'version_history', 'eu_hosted', 'apps_included', 'base_storage', 'attachment_limit',
    'video_upload_limit', 'supported_file_types', 'training_data_cutoff', 'copilot_included'
}
DEFINITIVE_ATTRS = HARDWARE_SPECS | CORP_HISTORY | PAST_EVENT_SPECS | GOVERNANCE | TECH_SPECS


@dataclass
class Params:
    min_support_rows: int = 1
    max_age_days: int = 14
    block_on_false_candidates: bool = True
    allow_unlisted_names: bool = False
    change_rule: str = "engine"          # engine | corroborated | safe_transition
    relation_rule: str = "engine"        # engine | stable
    compare_scope: str = "same_attribute"   # same_attribute | same_kind | cross_date
    staleness_rule: str = "strict_14d"   # strict_14d | relax_definitive
    as_of: date = AS_OF


@dataclass
class AsOf:
    key: tuple[str, str]
    accepted: bool
    reasons: list[str] = field(default_factory=list)
    value: TypedValue | None = None
    last: Obs | None = None
    run: list[Obs] = field(default_factory=list)
    volatile: bool = False
    immutable: bool = False
    age_days: int | None = None
    blockers: list[Obs] = field(default_factory=list)
    n_support_rows: int = 0


class Store:
    def __init__(self, universe_csv: Path = PRACTICE_CSV, lexicon_json: Path = LEXICON_JSON, params: Params | None = None,
                 reference_csv: Path | None = None):
        self.params = params or Params()
        self.universe_csv = Path(universe_csv)
        self.graph = build_graph_from_paths(self.universe_csv, lexicon_json, reference_csv, use_packaged_practice=False)
        self.lexicon: Lexicon = self.graph.lexicon
        self.names = Names(lexicon_json)
        self.rows: dict[str, dict[str, str]] = {}
        with self.universe_csv.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                self.rows[r["id"]] = r
        self.extra_admitted: list[dict[str, Any]] = []
        self._finalize()

    def _finalize(self) -> None:
        self.obs = build_observations(self.graph, self.names.mask)
        self.resolver = EvidenceResolver(self.graph)
        self.temporal = TemporalIndex(self.graph)
        self.engine = ReasoningEngine(self.graph)
        self._asof_cache: dict[tuple[str, str], AsOf] = {}

    # --- helpers -------------------------------------------------------------------------------
    def support(self, key: tuple[str, str]) -> list[Obs]:
        return [o for o in self.obs.get(key, []) if o.kind == "support"]

    def event_names(self) -> list[str]:
        out = []
        for e in self.lexicon.events:
            r = self.lexicon.resolve(e)
            if r is not None:
                out.append(r.name)
        return out

    # --- the as-of rule ------------------------------------------------------------------------
    def asof_fact(self, key: tuple[str, str]) -> AsOf:
        if key in self._asof_cache:
            return self._asof_cache[key]
        res = self._asof(key)
        self._asof_cache[key] = res
        return res

    def asof_at(self, key: tuple[str, str], target: date, params: "Params | None" = None) -> AsOf:
        """The same rule evaluated for a historical target date using only observations dated strictly before it
        (used by backtest.py to measure how often the rule's value is contradicted by what is observed on ``target``)."""
        return self._asof(key, before=target, as_of=target, params=params)

    def _asof(self, key: tuple[str, str], before: date | None = None, as_of: date | None = None, params: "Params | None" = None) -> AsOf:
        p = params or self.params
        as_of = as_of or p.as_of
        allobs = [o for o in self.obs.get(key, []) if before is None or o.on < before]
        sup = [o for o in allobs if o.kind == "support"]
        res = AsOf(key, False)
        if not sup:
            res.reasons.append("no_verified_support")
            return res
        last = sup[-1]
        res.last = last
        distinct: list[TypedValue] = []
        for o in sup:
            if not any(same_value(o.value, d) for d in distinct):
                distinct.append(o.value)
        res.volatile = len(distinct) > 1
        v = last.value
        # R1
        if v.op is not None:
            res.reasons.append("latest_support_has_op")
        if not last.clean:
            res.reasons.append("latest_support_has_temporal_cue:" + "|".join(last.cues))
        # trailing run equal to v
        run: list[Obs] = []
        for o in reversed(sup):
            if same_value(o.value, v):
                run.append(o)
            else:
                break
        run.reverse()
        res.run = run
        res.value = (finest_equivalent(o.value for o in run) or v) if v.kind == "date" else v
        clean_rows = {o.row_id for o in run if o.clean}
        res.n_support_rows = len(clean_rows)
        # R2: later / same-day contradicting observations of any non-support trust level
        for o in allobs:
            if o.kind == "support" or o.on < last.on:
                continue
            if o.kind == "text_candidate":
                continue
            if o.kind == "form_candidate" and not p.block_on_false_candidates:
                continue
            if not same_value(o.value, v):
                res.blockers.append(o)
        # a contradicting *support* later than the run cannot exist (run is the trailing equal run)
        if res.blockers:
            kinds = sorted({b.kind for b in res.blockers})
            res.reasons.append("blocked_by_later_" + "+".join(kinds))
        # R3 / R4: a one-time past event date (joined, launched, ...) does not move; everything else must be fresh
        res.age_days = (as_of - last.on).days
        is_past_date = (key[1] in IMMUTABLE_EVENT_DATE_ATTRS and v.kind == "date" and isinstance(v.value, str)
                        and v.value <= as_of.isoformat()[: len(v.value)])
        is_definitive = (p.staleness_rule == "relax_definitive") and (key[1] in DEFINITIVE_ATTRS and not res.volatile)
        immutable = is_past_date or is_definitive
        res.immutable = immutable
        need = 1 if is_past_date else p.min_support_rows
        if len(clean_rows) < need:
            res.reasons.append(f"insufficient_corroboration({len(clean_rows)}<{need})")
        if not immutable and res.age_days > p.max_age_days:
            res.reasons.append(f"stale(age={res.age_days}d>{p.max_age_days}d)")
        res.accepted = not res.reasons
        return res

    # --- engine wrappers -----------------------------------------------------------------------
    def engine_status(self, ctype: str, form: dict[str, Any]) -> tuple[str, str]:
        r = self.engine.evaluate_claim(ctype, form, p_as_of(self.params))
        return r.status.value, r.reason


def p_as_of(params: Params) -> date:
    return params.as_of


def load_novelty_texts(paths: list[Path]) -> set[str]:
    """Normalised texts of input rows (same normalisation as foundation.validate_output)."""
    out: set[str] = set()
    for pth in paths:
        with Path(pth).open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                out.add(norm_text(r.get("text", "")))
    return out


def norm_text(t: str) -> str:
    return " ".join(t.casefold().split()).rstrip(".!? ")
