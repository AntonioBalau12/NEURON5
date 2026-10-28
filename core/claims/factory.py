"""Reusable production adapter around the actual P3 rule and contract code."""
from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from foundation import _claim_semantic_key

from .best_k import BestKPool
from .p3.contract import ContractChecker
from .p3.rules import gen_at_event, gen_change, gen_compare, gen_fact, gen_relation
from .p3.observations import same_value
from .p3.store import Params, Store, load_novelty_texts
from .ranker import RankedClaim, reported_confidence, score_candidate
from .scheduler import AnytimeScheduler


SAFE_STRATEGIES = ("fact", "compare", "change")


class ClaimFactory:
    """Generate candidates only from TRUE-row form evidence in the P3 store.

    Runtime-universe parser candidates remain UNVERIFIED and cannot support a claim.
    Generation uses the original P3 A+B+C strategies with the approved P3 policies.
    """

    def __init__(self, universe_csv: str | Path, lexicon_json: str | Path,
                 practice_csv: str | Path, contract_dir: str | Path,
                 deadline: int = 0, clock=time.time, stop_event=None,
                 publication_seconds: float = 0.0):
        self.universe_csv = Path(universe_csv)
        self.lexicon_json = Path(lexicon_json)
        self.practice_csv = Path(practice_csv)
        self.contract_dir = Path(contract_dir)
        self.scheduler = AnytimeScheduler(deadline, clock, stop_event)
        self.scheduler.record_publication(publication_seconds)
        self.metrics: dict[str, Any] = {}

    @staticmethod
    def _event_has_date_conflict(store: Store, event: str) -> bool:
        values = []
        for obs in store.support((event, "date")):
            if obs.value.kind == "date" and not any(same_value(obs.value, known) for known in values):
                values.append(obs.value)
        # Any distinct verified dates can encode a rescheduling. Without an
        # explicit resolution policy they are quarantined, even if one is later.
        return len(values) > 1

    @staticmethod
    def _is_asof_grounded(store: Store, key: tuple[str, str]) -> bool:
        result = store.asof_fact(key)
        if not result.accepted or result.last is None:
            return False
        # P3's configured as-of policy already checks corroboration, blockers,
        # volatility and freshness. Under relax_definitive it also admits its
        # explicitly defined stable structural facts.
        return result.accepted

    @staticmethod
    def _eligible(candidate: Any, store: Store) -> tuple[bool, str | None]:
        if not candidate.verified or candidate.status == "rejected":
            return False, "not_verified_by_p3"
        if candidate.rule.startswith("change_rule=") and candidate.rule not in (
            "change_rule=engine", "change_rule=safe_transition"
        ):
            return False, "unsafe_change_strategy"
        if candidate.rule.startswith("relation_rule=") and candidate.rule != "relation_rule=engine":
            return False, "unsafe_relation_strategy"
        if "cross_attribute_compare" in candidate.flags:
            # cross_date is the original P3 date-only mode. Permit only its
            # immutable calendar-date comparisons; same_kind remains excluded.
            if not (store.params.compare_scope == "cross_date"
                    and candidate.evidence.get("scope") == "cross_attribute"
                    and candidate.evidence.get("value_kind") == "date"):
                return False, "cross_attribute_comparison"
        if candidate.type == "change":
            # Change uses its specific ordered-endpoint verifier: both values
            # were directly stated by clean, verified TRUE observations.
            proof = candidate.evidence.get("change_verification", {})
            if candidate.rule == "change_rule=safe_transition":
                # Original P3 proof: corroborated endpoint rows, no flapping,
                # strict chronology, and no later differing observation.
                evidence = candidate.evidence
                ids = evidence.get("evidence_ids", [])
                support = evidence.get("support", [])
                support_ids = {item.get("row_id") for item in support if isinstance(item, dict)}
                from_date, to_date = evidence.get("from_date", ""), evidence.get("to_date", "")
                if ("safe_transition" not in candidate.flags or evidence.get("flapping") is True
                        or not isinstance(ids, list) or len(set(ids)) < 2
                        or not set(ids).issubset(support_ids)
                        or not from_date or not to_date or from_date >= to_date):
                    return False, "change_safe_transition_proof_missing"
            elif (candidate.engine.get("status") != "VERIFIED_SUPPORT"
                    or proof.get("rule") != "ordered_true_endpoints"
                    or len(proof.get("evidence_ids", [])) < 2
                    or proof.get("from_date", "") >= proof.get("to_date", "")):
                return False, "change_ordered_true_endpoint_proof_missing"
        if candidate.type == "at_event":
            event = (candidate.form or {}).get("event")
            if isinstance(event, str) and ClaimFactory._event_has_date_conflict(store, event):
                return False, "event_date_conflict_or_reschedule"
        if candidate.type == "fact":
            key = (str((candidate.form or {}).get("subject", "")), str((candidate.form or {}).get("attribute", "")))
            if not ClaimFactory._is_asof_grounded(store, key):
                return False, "current_fact_not_directly_observed_asof"
        if candidate.type == "compare":
            form = candidate.form or {}
            for side in (form.get("left"), form.get("right")):
                if not isinstance(side, dict) or not ClaimFactory._is_asof_grounded(
                    store, (str(side.get("subject", "")), str(side.get("attribute", "")))
                ):
                    return False, "comparison_side_not_directly_observed_asof"
        if candidate.type == "relation":
            # The published relation form is historical. Its generator must
            # provide a verified same-day link/target pair with traceable rows.
            pairs = candidate.evidence.get("relation_pairs", [])
            if (candidate.engine.get("status") != "VERIFIED_SUPPORT" or not pairs
                    or any(not isinstance(pair, dict) or not pair.get("date")
                           or not isinstance(pair.get("link"), dict) or not isinstance(pair.get("target"), dict)
                           for pair in pairs)):
                return False, "relation_temporal_provenance_missing"
        _, _, evidence_ids = score_candidate(candidate)
        if not evidence_ids:
            return False, "missing_traceable_support_ids"
        return True, None

    def _strategies(self, store: Store, enabled: tuple[str, ...]) -> dict[str, Any]:
        return {
            "fact": lambda: gen_fact(store),
            "compare": lambda: gen_compare(store),
            "relation": lambda: gen_relation(store),
            "at_event": lambda: gen_at_event(store),
            "change": lambda: gen_change(store),
        }

    @staticmethod
    def _rank_candidates(store: Store, source: list[Any], novelty: set[str],
                         max_claims: int) -> tuple[BestKPool, Counter[str], int]:
        checker = ContractChecker(store, novelty)
        pool = BestKPool(max_claims)
        rejections: Counter[str] = Counter()
        prepared: list[tuple[float, Any, tuple[Any, ...], tuple[str, ...], tuple[str, ...]]] = []
        for candidate in deepcopy(source):
            accepted, reason = ClaimFactory._eligible(candidate, store)
            if not accepted:
                rejections[reason or "ineligible"] += 1
                continue
            score, flags, evidence_ids = score_candidate(candidate)
            key = _claim_semantic_key(candidate.type, candidate.form, store.lexicon)
            if key is None or candidate.form is None or candidate.text is None:
                rejections["missing_semantic_identity_or_render"] += 1
                continue
            prepared.append((score, candidate, key, flags, evidence_ids))
        # Strongest semantic representative reaches P3's stateful novelty and
        # duplicate checker first, so weaker renderings cannot block it.
        prepared.sort(key=lambda x: (-x[0], x[1].type, x[1].ckey, x[1].text or ""))
        for score, candidate, key, flags, evidence_ids in prepared:
            original_confidence = float(candidate.confidence)
            candidate.confidence = 0.5
            checked = checker.check(candidate)
            if checked.status != "accepted":
                why = checked.reasons[-1] if checked.reasons else "contract_rejected"
                rejections[why.split(":", 1)[0]] += 1
                continue
            digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:24]
            claim = {"id": "p3-" + digest, "type": checked.type, "text": checked.text,
                     "form": checked.form, "label": "true", "confidence": reported_confidence(checked)}
            temporal_assumptions = []
            for entry in checked.evidence.values():
                if isinstance(entry, dict):
                    if isinstance(entry.get("age_days"), int):
                        temporal_assumptions.append(f"max_observation_age_days={entry['age_days']}")
                    if entry.get("volatile") is True:
                        temporal_assumptions.append("historically_volatile_attribute")
                    if entry.get("immutable_event_date") is True:
                        temporal_assumptions.append("immutable_past_event_date")
            pool.add(RankedClaim(claim, key, evidence_ids, flags, score, checked.rule,
                                 checked.engine.get("status", ""), tuple(sorted(set(temporal_assumptions))),
                                 original_confidence))
        return pool, rejections, len(prepared)

    def generate(self, strategies: tuple[str, ...] = SAFE_STRATEGIES,
                 max_claims: int = 1500,
                 on_checkpoint: Callable[[list[dict[str, Any]]], float | None] | None = None
                 ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.monotonic()
        params = Params(min_support_rows=1, max_age_days=14, block_on_false_candidates=True,
                        allow_unlisted_names=False, change_rule="safe_transition", relation_rule="engine",
                        compare_scope="cross_date", staleness_rule="relax_definitive")
        store = Store(self.universe_csv, self.lexicon_json, params=params, reference_csv=self.practice_csv)
        store_seconds = time.monotonic() - started
        novelty = load_novelty_texts([self.universe_csv, self.practice_csv])
        rejections: Counter[str] = Counter()
        stage_times: dict[str, float] = {}
        all_candidates = []
        pool = BestKPool(max_claims)
        eligible_count = 0
        generators = self._strategies(store, strategies)
        for name in strategies:
            if name not in generators:
                rejections["unknown_strategy:" + name] += 1
                continue
            if not self.scheduler.can_start(name):
                rejections["deadline_skipped:" + name] += 1
                continue
            t0 = time.monotonic()
            candidates = generators[name]()
            all_candidates.extend(candidates)
            if on_checkpoint is not None:
                pool, rejections, eligible_count = self._rank_candidates(store, all_candidates, novelty, max_claims)
                elapsed_for_callback = on_checkpoint([entry.claim for entry in pool.selected(1000)])
                if isinstance(elapsed_for_callback, (int, float)):
                    self.scheduler.record_publication(float(elapsed_for_callback))
            elapsed = time.monotonic() - t0
            stage_times[name] = elapsed
            self.scheduler.record(name, elapsed)

        if on_checkpoint is None:
            pool, rejections, eligible_count = self._rank_candidates(store, all_candidates, novelty, max_claims)
        selected = pool.selected(1000)
        claims = [entry.claim for entry in selected]
        dependency_counts: Counter[str] = Counter(row for item in selected for row in item.evidence_ids)
        self.metrics = {
            "store_seconds": store_seconds,
            "generation_seconds_by_strategy": stage_times,
            "generated_candidates": len(all_candidates),
            "eligible_before_contract": eligible_count,
            "distinct_contract_accepted": len(pool),
            "selected_claims": len(claims),
            "deficit_to_1000": max(0, 1000 - len(claims)),
            "rejections": dict(sorted(rejections.items())),
            "ranking_score_is_calibrated_probability": False,
            "elapsed_seconds": time.monotonic() - started,
            "enabled_strategies": list(strategies),
            "universe_row_count": len(store.rows),
            "evidence_source": "TRUE-labelled practice forms; runtime text candidates are not support",
            "selected_shared_evidence_ids": {row: count for row, count in sorted(dependency_counts.items()) if count > 1},
            "selected_max_claims_per_evidence_id": max(dependency_counts.values(), default=0),
            "selected_claim_trace": [
                {"claim_id": item.claim["id"], "type": item.claim["type"], "evidence_ids": list(item.evidence_ids),
                 "generation_rule": item.generation_rule, "verification_status": item.verification_status,
                 "risk_flags": list(item.risk_flags), "risk_score": item.score,
                 "temporal_assumptions": list(item.temporal_assumptions),
                 "original_confidence": item.original_confidence, "reported_confidence": item.claim["confidence"]}
                for item in selected
            ],
        }
        return claims, self.metrics

