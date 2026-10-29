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


SAFE_STRATEGIES = ("fact", "compare", "change", "at_event", "relation")


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
        # Current mutable facts need an observation on the claim's as-of date;
        # freshness within the 14-day window is not proof of persistence. P3
        # may separately admit only attributes it explicitly marks immutable.
        return result.immutable or result.last.on == store.params.as_of

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
    def _rank_candidates(store: Store, source: list[tuple[str, Any]], novelty: set[str],
                         max_claims: int,
                         validation_cache: dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, ...]]]
                         ) -> tuple[BestKPool, Counter[str], int, dict[str, Any]]:
        pass_started = time.perf_counter()
        checker = ContractChecker(store, novelty, validation_cache)
        pool = BestKPool(max_claims)
        rejections: Counter[str] = Counter()
        stages = Counter()
        prepared: list[tuple[float, Any, tuple[Any, ...], tuple[str, ...], tuple[str, ...], str]] = []
        for strategy, original in source:
            t0 = time.perf_counter()
            candidate = deepcopy(original)
            stages["deepcopy_seconds"] += time.perf_counter() - t0
            t0 = time.perf_counter()
            accepted, reason = ClaimFactory._eligible(candidate, store)
            stages["eligible_seconds"] += time.perf_counter() - t0
            if not accepted:
                rejections[reason or "ineligible"] += 1
                continue
            t0 = time.perf_counter()
            score, flags, evidence_ids = score_candidate(candidate)
            key = _claim_semantic_key(candidate.type, candidate.form, store.lexicon)
            stages["score_and_semantic_key_seconds"] += time.perf_counter() - t0
            if key is None or candidate.form is None or candidate.text is None:
                rejections["missing_semantic_identity_or_render"] += 1
                continue
            prepared.append((score, candidate, key, flags, evidence_ids, strategy))
        # Strongest semantic representative reaches P3's stateful novelty and
        # duplicate checker first, so weaker renderings cannot block it.
        t0 = time.perf_counter()
        prepared.sort(key=lambda x: (-x[0], x[1].type, x[1].ckey, x[1].text or ""))
        stages["sort_seconds"] += time.perf_counter() - t0
        for score, candidate, key, flags, evidence_ids, _strategy in prepared:
            original_confidence = float(candidate.confidence)
            candidate.confidence = 0.5
            t0 = time.perf_counter()
            checked = checker.check(candidate)
            stages["contract_checker_seconds"] += time.perf_counter() - t0
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
            t0 = time.perf_counter()
            pool.add(RankedClaim(claim, key, evidence_ids, flags, score, checked.rule,
                                 checked.engine.get("status", ""), tuple(sorted(set(temporal_assumptions))),
                                 original_confidence))
            stages["best_k_add_seconds"] += time.perf_counter() - t0
        stages.update(checker.timings)
        diagnostics = {
            "candidate_count": len(source), "eligible_count": len(prepared), "accepted_count": len(pool),
            "elapsed_seconds": round(time.perf_counter() - pass_started, 6),
            "timings": {key: round(float(value), 6) for key, value in stages.items()},
            "rejections": dict(sorted(rejections.items())), "contract_counts": dict(checker.counts),
        }
        return pool, rejections, len(prepared), diagnostics

    def generate(self, strategies: tuple[str, ...] = SAFE_STRATEGIES,
                 max_claims: int = 1500,
                 on_checkpoint: Callable[[list[dict[str, Any]]], float | None] | None = None
                 ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.perf_counter()
        params = Params(min_support_rows=1, max_age_days=14, block_on_false_candidates=True,
                        allow_unlisted_names=False, change_rule="safe_transition", relation_rule="engine",
                        compare_scope="cross_date", staleness_rule="relax_definitive")
        store = Store(self.universe_csv, self.lexicon_json, params=params, reference_csv=self.practice_csv)
        store_seconds = time.perf_counter() - started
        novelty_started = time.perf_counter()
        novelty = load_novelty_texts([self.universe_csv, self.practice_csv])
        novelty_load_seconds = time.perf_counter() - novelty_started
        rejections: Counter[str] = Counter()
        stage_times: dict[str, float] = {}
        strategy_phase_times: dict[str, float] = {}
        all_candidates: list[tuple[str, Any]] = []
        rank_passes: list[dict[str, Any]] = []
        validation_cache: dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, ...]]] = {}
        callback_wall_seconds = 0.0
        callback_reported_seconds = 0.0
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
            phase_started = time.perf_counter()
            t0 = time.perf_counter()
            candidates = generators[name]()
            stage_times[name] = time.perf_counter() - t0
            all_candidates.extend((name, candidate) for candidate in candidates)
            if on_checkpoint is not None:
                pool, rejections, eligible_count, pass_metrics = self._rank_candidates(
                    store, all_candidates, novelty, max_claims, validation_cache)
                pass_metrics["trigger_strategy"] = name
                rank_passes.append(pass_metrics)
                callback_started = time.perf_counter()
                elapsed_for_callback = on_checkpoint([entry.claim for entry in pool.selected(1000)])
                callback_wall_seconds += time.perf_counter() - callback_started
                if isinstance(elapsed_for_callback, (int, float)):
                    callback_reported_seconds += float(elapsed_for_callback)
                    self.scheduler.record_publication(float(elapsed_for_callback))
            phase_elapsed = time.perf_counter() - phase_started
            strategy_phase_times[name] = phase_elapsed
            self.scheduler.record(name, phase_elapsed)

        if on_checkpoint is None:
            pool, rejections, eligible_count, pass_metrics = self._rank_candidates(
                store, all_candidates, novelty, max_claims, validation_cache)
            pass_metrics["trigger_strategy"] = "final"
            rank_passes.append(pass_metrics)
        selection_started = time.perf_counter()
        ordered_pool = pool.selected()
        selected = pool.selected(1000)
        selection_seconds = time.perf_counter() - selection_started
        claims = [entry.claim for entry in selected]
        reserve = ordered_pool[len(selected):]
        dependency_counts: Counter[str] = Counter(row for item in selected for row in item.evidence_ids)
        candidate_audit: dict[str, dict[str, Counter[str]]] = {
            "by_strategy": {}, "by_type": {}, "by_status": {}, "by_stage": {},
            "by_rule": {}, "by_reason": {}, "by_primary_reason": {},
            "by_strategy_reason": {}, "by_strategy_primary_reason": {}, "by_flag": {},
        }
        for strategy, candidate in all_candidates:
            dimensions = {"by_strategy": strategy, "by_type": candidate.type, "by_status": candidate.status,
                          "by_stage": candidate.stage, "by_rule": candidate.rule or "(none)"}
            for bucket, value in dimensions.items():
                candidate_audit[bucket].setdefault(value, Counter())["count"] += 1
            for reason in candidate.reasons:
                candidate_audit["by_reason"].setdefault(reason, Counter())["count"] += 1
                candidate_audit["by_strategy_reason"].setdefault(
                    f"{strategy}|{candidate.type}|{reason}", Counter())["count"] += 1
            primary_reason = candidate.reasons[0] if candidate.reasons else f"{candidate.stage}:{candidate.status}"
            candidate_audit["by_primary_reason"].setdefault(primary_reason, Counter())["count"] += 1
            candidate_audit["by_strategy_primary_reason"].setdefault(
                f"{strategy}|{candidate.type}|{primary_reason}", Counter())["count"] += 1
            for flag in candidate.flags:
                candidate_audit["by_flag"].setdefault(flag, Counter())["count"] += 1
        reserve_by_type = Counter(item.claim["type"] for item in reserve)
        self.metrics = {
            "store_seconds": round(store_seconds, 6),
            "novelty_load_seconds": round(novelty_load_seconds, 6),
            "generation_seconds_by_strategy": {key: round(value, 6) for key, value in stage_times.items()},
            "strategy_phase_wall_seconds": {key: round(value, 6) for key, value in strategy_phase_times.items()},
            "generated_candidates": len(all_candidates),
            "eligible_before_contract": eligible_count,
            "distinct_contract_accepted": len(pool),
            "selected_claims": len(claims),
            "deficit_to_1000": max(0, 1000 - len(claims)),
            "rejections": dict(sorted(rejections.items())),
            "ranking_score_is_calibrated_probability": False,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "timing_profile": {
                "rank_passes": rank_passes,
                "ranked_candidate_evaluations": sum(item["candidate_count"] for item in rank_passes),
                "repeated_candidate_evaluations": max(0, sum(item["candidate_count"] for item in rank_passes) - len(all_candidates)),
                "selection_seconds": round(selection_seconds, 6),
                "checkpoint_callback_wall_seconds": round(callback_wall_seconds, 6),
                "checkpoint_reported_seconds": round(callback_reported_seconds, 6),
            },
            "candidate_audit": {name: {key: value["count"] for key, value in sorted(counts.items())}
                                for name, counts in candidate_audit.items()},
            "reserve": {
                "count": len(reserve), "by_type": dict(sorted(reserve_by_type.items())),
                "claims": [{"position": index + len(selected) + 1, "id": item.claim["id"],
                            "type": item.claim["type"], "text": item.claim["text"], "rank_score": item.score,
                            "evidence_ids": list(item.evidence_ids), "temporal_assumptions": list(item.temporal_assumptions),
                            "risk_flags": list(item.risk_flags),
                            "selection_note": "below top 1000 after deterministic dependency-penalized BestKPool selection"}
                           for index, item in enumerate(reserve)],
            },
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

