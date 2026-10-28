"""Candidate generation for the five claim types.  Every candidate carries its evidence and, if it is refused,
a stable reason code.  Nothing is invented: a candidate exists only because the evidence store holds the facts it needs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from foundation import TypedValue, compare_values  # type: ignore
from core.graph import EvidenceState

import render
from observations import Obs, same_value
from store import AsOf, Store
from confidence import (
    calculate_fact_confidence,
    calculate_compare_confidence,
    calculate_change_confidence,
    calculate_at_event_confidence,
    calculate_relation_confidence,
)


@dataclass
class Cand:
    type: str
    ckey: str                       # stable candidate key (also the base of the claim id)
    form: dict[str, Any] | None = None
    text: str | None = None
    status: str = "pending"         # pending | rejected | accepted
    stage: str = "generated"
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    engine: dict[str, str] = field(default_factory=dict)
    rule: str = ""
    verified: bool = False
    confidence: float = 0.8
    cid: str = ""

    def reject(self, stage: str, reason: str) -> "Cand":
        self.status = "rejected"
        self.stage = stage
        self.reasons.append(f"{stage}:{reason}")
        return self


def vdict(v: TypedValue) -> dict[str, Any]:
    d: dict[str, Any] = {"kind": v.kind, "value": v.value}
    for k in ("unit", "currency", "per"):
        x = getattr(v, k)
        if x is not None:
            d[k] = x
    if isinstance(d["value"], float) and d["value"].is_integer():
        d["value"] = int(d["value"])
    return d


def _src(o: Obs, role: str) -> dict[str, Any]:
    return {"row_id": o.row_id, "date": o.on.isoformat(), "role": role, "subject": o.subject, "attribute": o.attribute,
            "value": vdict(o.value), "label": o.label, "provenance": o.provenance, "text": o.text[:200]}


def _h(*parts: str) -> int:
    return int(hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest(), 16)


# ------------------------------------------------------------------------------------------------
# fact
# ------------------------------------------------------------------------------------------------
def gen_fact(store: Store) -> list[Cand]:
    out: list[Cand] = []
    for key in sorted(store.obs):
        subject, attr = key
        c = Cand("fact", f"fact|{subject}|{attr}", rule="asof_rule")
        res = store.asof_fact(key)
        c.evidence = {"key": [subject, attr], "n_support_rows": res.n_support_rows, "volatile": res.volatile, "immutable_event_date": res.immutable, "age_days": res.age_days,
                      "support": [_src(o, "support") for o in res.run[-6:]],
                      "blockers": [_src(o, "blocker:" + o.kind) for o in res.blockers[:4]]}
        if not res.accepted or res.value is None:
            for r in res.reasons or ["unknown"]:
                c.reasons.append("evidence:" + r)
            c.status, c.stage = "rejected", "evidence"
            out.append(c)
            continue
        c.form = {"subject": subject, "attribute": attr, "value": vdict(res.value)}
        status, why = store.engine_status("fact", c.form)
        c.engine = {"status": status, "reason": why}
        c.verified = True
        c.confidence = calculate_fact_confidence(
            attr,
            age_days=res.age_days,
            is_immutable=getattr(res, "immutable", False),
            n_support_rows=res.n_support_rows,
        )
        text, err = render.build_sentence("fact", subject, attr, c.form["value"], store.names, store.params.allow_unlisted_names, store.params.as_of)
        if err:
            c.reject("render", err)
        else:
            c.text = text
        out.append(c)
    return out


# ------------------------------------------------------------------------------------------------
# compare
# ------------------------------------------------------------------------------------------------
COMPARABLE_KINDS = {"quantity", "money", "percent", "duration", "date"}


def gen_compare(store: Store) -> list[Cand]:
    by_attr: dict[str, list[tuple[str, str]]] = {}
    for key in sorted(store.obs):
        if store.support(key):
            by_attr.setdefault(key[1], []).append(key)
    out: list[Cand] = []
    for attr in sorted(by_attr):
        keys = by_attr[attr]
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                ka, kb = keys[i], keys[j]
                c = Cand("compare", f"compare|{attr}|{ka[0]}|{kb[0]}", rule="asof_both_sides")
                ra, rb = store.asof_fact(ka), store.asof_fact(kb)
                c.evidence = {"attribute": attr, "left_candidate": ka[0], "right_candidate": kb[0],
                              "sides": [{"key": list(k), "accepted": r.accepted, "support": [_src(o, "support") for o in r.run[-3:]]}
                                        for k, r in ((ka, ra), (kb, rb))]}
                if not (ra.accepted and rb.accepted):
                    for tag, r in (("a", ra), ("b", rb)):
                        if not r.accepted:
                            c.reasons.append("evidence:side_not_verified(" + ",".join(x.split("(")[0] for x in r.reasons) + ")")
                    c.status, c.stage = "rejected", "evidence"
                    out.append(c)
                    continue
                va, vb = ra.value, rb.value
                assert va is not None and vb is not None
                if va.kind not in COMPARABLE_KINDS:
                    c.reject("evidence", f"kind_not_comparable:{va.kind}")
                    out.append(c)
                    continue
                if compare_values(va, vb, "eq") is None:
                    c.reject("evidence", "values_incomparable(units/period/precision)")
                    out.append(c)
                    continue
                if va.kind == "date" and not (len(str(va.value)) == 10 and len(str(vb.value)) == 10):
                    c.reject("evidence", "date_precision_below_day")
                    out.append(c)
                    continue
                if compare_values(va, vb, "eq") is True:
                    left, right, op = ka, kb, "eq"
                else:
                    a_gt = compare_values(va, vb, "gt") is True
                    big, small = (ka, kb) if a_gt else (kb, ka)
                    # orientation alternates deterministically between 'gt' (larger first) and 'lt' (smaller first)
                    if _h(ka[0], kb[0], attr) % 2 == 0:
                        left, right, op = big, small, "gt"
                    else:
                        left, right, op = small, big, "lt"
                lv = va if left == ka else vb
                c.evidence["value_kind"] = lv.kind
                c.form = {"left": {"subject": left[0], "attribute": attr}, "right": {"subject": right[0], "attribute": attr}, "op": op}
                status, why = store.engine_status("compare", c.form)
                c.engine = {"status": status, "reason": why}
                c.verified = True
                c.confidence = calculate_compare_confidence(
                    attr, attr,
                    age_left=ra.age_days,
                    age_right=rb.age_days,
                    is_date_compare=(lv.kind == "date"),
                )
                text, err = render.compare_text(left[0], right[0], attr, op, lv.kind, lv.unit)
                if err:
                    c.reject("render", err)
                else:
                    c.text = text
                out.append(c)
    if store.params.compare_scope in ("same_kind", "cross_date"):
        out.extend(_gen_compare_cross_attribute(store, date_only=(store.params.compare_scope == "cross_date")))
    return out


def _gen_compare_cross_attribute(store: Store, date_only: bool = False) -> list[Cand]:
    """OPTIONAL (--compare-scope same_kind or cross_date): compare two verified facts of DIFFERENT attributes that compare by the contract.
    When date_only is True (cross_date), exclusively compares immutable calendar dates using render.DATE_VERB and render.DATE_PHRASE."""
    ok: list[tuple[tuple[str, str], AsOf]] = []
    allowed_kinds = ("date",) if date_only else ("date", "quantity", "duration", "money")
    for key in sorted(store.obs):
        if store.support(key):
            r = store.asof_fact(key)
            if r.accepted and r.value is not None and r.value.kind in allowed_kinds:
                if r.value.kind == "date" and len(str(r.value.value)) != 10:
                    continue
                ok.append((key, r))
    out: list[Cand] = []
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            (ka, ra), (kb, rb) = ok[i], ok[j]
            if ka[1] == kb[1]:
                continue                              # same attribute pairs are in the main loop
            va, vb = ra.value, rb.value
            if va.kind != vb.kind or compare_values(va, vb, "eq") is None:
                continue
            c = Cand("compare", f"compare_x|{ka[0]}|{ka[1]}|{kb[0]}|{kb[1]}", rule="asof_both_sides(cross_attribute)")
            c.evidence = {"scope": "cross_attribute", "sides": [{"key": list(k), "accepted": True, "support": [_src(o, "support") for o in r.run[-2:]]}
                                                              for k, r in ((ka, ra), (kb, rb))], "value_kind": va.kind}
            if ka[0] == kb[0]:
                c.reject("evidence", "same_subject_on_both_sides")
                out.append(c)
                continue
            a_vs_b = "eq" if compare_values(va, vb, "eq") is True else ("gt" if compare_values(va, vb, "gt") is True else "lt")
            if a_vs_b == "eq":
                left, right, op = ka, kb, "eq"
            elif _h(ka[0], ka[1], kb[0], kb[1]) % 2 == 0:
                left, right, op = ((ka, kb) if a_vs_b == "gt" else (kb, ka)) + ("gt",)
            else:
                left, right, op = ((kb, ka) if a_vs_b == "gt" else (ka, kb)) + ("lt",)
            lv = va if left == ka else vb
            c.form = {"left": {"subject": left[0], "attribute": left[1]}, "right": {"subject": right[0], "attribute": right[1]}, "op": op}
            status, why = store.engine_status("compare", c.form)
            c.engine = {"status": status, "reason": why}
            c.verified = True
            c.confidence = calculate_compare_confidence(
                ka[1], kb[1],
                age_left=ra.age_days,
                age_right=rb.age_days,
                is_date_compare=(lv.kind == "date"),
            )
            c.flags.append("cross_attribute_compare")
            if lv.kind == "date":
                vl, vr = render.DATE_VERB.get(left[1]), render.DATE_VERB.get(right[1])
                if vl is None or vr is None:
                    c.reject("render", "no_verb_for_date_attribute")
                else:
                    c.text = f"{left[0]} {vl} {render.DATE_PHRASE[op]} {right[0]} {vr}."
            else:
                text, err = render.compare_text(left[0], right[0], left[1], op, lv.kind, lv.unit)
                if err:
                    c.reject("render", err)
                else:
                    c.text = text
            out.append(c)
    return out


# ------------------------------------------------------------------------------------------------
# change
# ------------------------------------------------------------------------------------------------
def _clean_rows(sup: list[Obs], value: TypedValue) -> set[str]:
    return {o.row_id for o in sup if o.clean and same_value(o.value, value)}


def gen_change(store: Store) -> list[Cand]:
    out: list[Cand] = []
    p = store.params
    for key in sorted(store.obs):
        sup = store.support(key)
        if not sup:
            continue
        subject, attr = key
        changes = store.temporal.get_temporal_changes(subject, attr)
        # flapping: a value that comes back after having been replaced is treated as noise
        seq: list[TypedValue] = []
        for o in sup:
            if not seq or not same_value(o.value, seq[-1]):
                seq.append(o.value)
        flapping = any(same_value(seq[i], seq[j]) for i in range(len(seq)) for j in range(i + 2, len(seq)))
        for ch in changes:
            c = Cand("change", f"change|{subject}|{attr}|{ch.from_date}|{ch.to_date}", rule=f"change_rule={p.change_rule}")
            fv, tv = ch.from_value, ch.to_value
            c.form = {"subject": subject, "attribute": attr, "from": vdict(fv), "to": vdict(tv)}
            c.evidence = {"key": [subject, attr], "from_date": ch.from_date.isoformat(), "to_date": ch.to_date.isoformat(),
                          "evidence_ids": list(ch.evidence_ids), "flapping": flapping,
                          "support": [_src(o, "support") for o in sup if o.row_id in ch.evidence_ids]}
            status, why = store.engine_status("change", c.form)
            c.engine = {"status": status, "reason": why}
            if same_value(fv, tv):
                c.reject("evidence", "endpoints_equivalent")
                out.append(c)
                continue
            if fv.kind == "boolean" or tv.kind == "boolean":
                c.reject("evidence", "boolean_change_not_generated")
                out.append(c)
                continue
            if status == EvidenceState.VERIFIED_SUPPORT.value:
                c.verified = True
            elif p.change_rule in ("corroborated", "safe_transition"):
                reasons = []
                if flapping:
                    reasons.append("flapping_value_sequence")
                def need(v: TypedValue) -> int:
                    return 1 if (v.kind == "date" and isinstance(v.value, str) and len(v.value) == 10) else 2
                nf, nt = len(_clean_rows(sup, fv)), len(_clean_rows(sup, tv))
                if nf < need(fv):
                    reasons.append(f"from_endpoint_uncorroborated({nf}<{need(fv)})")
                if nt < need(tv):
                    reasons.append(f"to_endpoint_uncorroborated({nt}<{need(tv)})")
                if p.change_rule == "safe_transition":
                    fr = [o for o in sup if same_value(o.value, fv)]
                    to = [o for o in sup if same_value(o.value, tv)]
                    if fr and to and not (min(o.on for o in fr) < max(o.on for o in to)):
                        reasons.append("from_not_strictly_before_to")
                    max_to_date = max(o.on for o in to) if to else None
                    if max_to_date is not None:
                        later = [o for o in store.obs.get(key, []) if o.on >= max_to_date and not same_value(o.value, tv)]
                        if later:
                            reasons.append("later_differing_observation")
                if reasons:
                    for r in reasons:
                        c.reasons.append("evidence:" + r)
                    c.status, c.stage = "rejected", "evidence"
                    out.append(c)
                    continue
                c.verified = True
                c.flags.append("safe_transition" if p.change_rule == "safe_transition" else "not_engine_verified:change_by_corroborated_pair")
            else:
                c.reject("evidence", "engine_change_candidate_only(observation dates do not establish a transition)")
                out.append(c)
                continue
            c.confidence = calculate_change_confidence(
                is_safe_transition=(p.change_rule == "safe_transition"),
                is_engine_verified=(c.engine.get("status") == EvidenceState.VERIFIED_SUPPORT.value),
            )
            f, ferr = render.render_value(c.form["from"], store.names, p.allow_unlisted_names, attr)
            t, terr = render.render_value(c.form["to"], store.names, p.allow_unlisted_names, attr)
            if ferr or terr or f is None or t is None:
                c.reject("render", ferr or terr or "value")
            else:
                if fv.kind == "date":
                    # change sides state a date as a bare date, no preposition
                    pass
                if render.attr_has_unsafe_words(attr):
                    c.reject("render", "attribute_words_unsafe:" + str(render.attr_has_unsafe_words(attr)))
                else:
                    c.text = render.change_text(subject, attr, f, t)
            out.append(c)
    return out


# ------------------------------------------------------------------------------------------------
# at_event
# ------------------------------------------------------------------------------------------------
def _event_date_state(store: Store, event: str) -> tuple[str | None, list[Obs], list[str]]:
    """Day of an event, from its verified date facts, or the reason it is not usable.

    Rule: the event's date is the day-precision value of the TRAILING run of verified date observations (a plan may have
    been corrected earlier: earlier different values must be dated before the run starts).  Coarser equal values
    ('2026' for 2026-06-09) belong to the run.  It must be confirmed: a clean row dated on/after that day, or >= 2 clean
    rows.  A later conflicting / false-row differing date blocks it.  The page date of a row is never an event date."""
    sup = store.support((event, "date"))
    if not sup:
        return None, [], ["event_has_no_verified_date_fact"]
    last_day = next((o for o in reversed(sup) if o.value.kind == "date" and len(str(o.value.value)) == 10), None)
    if last_day is None:
        return None, sup, ["event_date_not_day_precision"]
    day = str(last_day.value.value)
    run: list[Obs] = []
    for o in reversed(sup):
        v = str(o.value.value)
        if o.value.kind == "date" and (v == day or day.startswith(v)):
            run.append(o)
        else:
            break
    run.reverse()
    if sup[-1] not in run:
        return None, sup, ["event_date_latest_observation_differs"]
    start = run[0].on
    later_diff = [o for o in store.obs.get((event, "date"), []) if o.kind in ("conflict", "form_candidate") and o.on >= start
                  and not (str(o.value.value) == day or day.startswith(str(o.value.value)))]
    if later_diff:
        return None, run, ["event_date_contradicted_by_" + "+".join(sorted({o.kind for o in later_diff}))]
    clean = [o for o in run if o.clean]
    confirmed = any(o.on >= date.fromisoformat(day) for o in clean) or len({o.row_id for o in clean}) >= 2
    if not confirmed:
        return None, run, ["event_date_not_confirmed(needs a clean row on/after the day or >=2 clean rows)"]
    return day, run, []


def gen_at_event(store: Store) -> list[Cand]:
    out: list[Cand] = []
    seen: set[str] = set()
    for event in store.event_names():
        day, date_obs, ereasons = _event_date_state(store, event)
        evs = store.temporal.get_event_facts(event)
        n_all_joins = len(evs)
        if day is not None:   # the graph joins facts on EVERY dated value of the event (also superseded plan dates); keep the final day
            evs = tuple(e for e in evs if e.event_date.isoformat() == day)
        else:
            evs = tuple(evs)
        # event facts the graph can join (verified support observed exactly on the event day)
        joined = {(e.fact.fact.subject, e.fact.fact.attribute): [] for e in evs}
        for e in evs:
            joined[(e.fact.fact.subject, e.fact.fact.attribute)].append(e)
        for (subject, attr), lst in sorted(joined.items()):
            ev0 = lst[0]
            c = Cand("at_event", f"at_event|{event}|{subject}|{attr}", rule="fact_observed_on_event_day")
            fv = ev0.fact.fact.value
            c.form = {"subject": subject, "attribute": attr, "event": event, "value": vdict(fv)}
            c.evidence = {"event": event, "event_date": ev0.event_date.isoformat(),
                          "event_date_rows": [_src(o, "event_date") for o in date_obs[:4]],
                          "fact_rows": [e.fact.source_row_id for e in lst]}
            status, why = store.engine_status("at_event", c.form)
            c.engine = {"status": status, "reason": why}
            if ckey_seen(seen, c.ckey):
                c.reject("dedup", "duplicate_candidate")
                out.append(c)
                continue
            if ereasons or day is None:
                for r in ereasons:
                    c.reasons.append("evidence:" + r)
                c.status, c.stage = "rejected", "evidence"
                out.append(c)
                continue
            if status != EvidenceState.VERIFIED_SUPPORT.value:
                c.reject("evidence", "engine_not_verified:" + status)
                out.append(c)
                continue
            if subject == event:
                c.reject("evidence", "subject_is_the_event")
                out.append(c)
                continue
            if attr == "date" or fv.kind == "date":
                c.reject("evidence", "date_valued_event_fact_excluded")
                out.append(c)
                continue
            # the day's observations of this fact: clean, exact, no differing support on that day
            day_obs = [o for o in store.obs.get((subject, attr), []) if o.on == ev0.event_date and o.kind in ("support", "conflict")]
            good = [o for o in day_obs if o.kind == "support" and o.clean and same_value(o.value, fv)]
            c.evidence["fact_rows_detail"] = [_src(o, "fact_on_event_day") for o in good[:4]]
            if not good:
                c.reject("evidence", "fact_observation_on_event_day_unclean")
                out.append(c)
                continue
            if any(not same_value(o.value, fv) for o in day_obs):
                c.reject("evidence", "differing_observation_on_event_day")
                out.append(c)
                continue
            c.verified = True
            c.confidence = calculate_at_event_confidence(
                is_immutable_event=True,
                differing_observations=0,
            )
            text, err = render.build_sentence("at_event", subject, attr, c.form["value"], store.names, store.params.allow_unlisted_names,
                                              store.params.as_of, event=event)
            if err:
                c.reject("render", err)
            else:
                c.text = text
            out.append(c)
    return out


def ckey_seen(seen: set[str], k: str) -> bool:
    if k in seen:
        return True
    seen.add(k)
    return False


# ------------------------------------------------------------------------------------------------
# relation
# ------------------------------------------------------------------------------------------------
UNGRAMMATICAL_LINKS = {"chairs", "run_by"}   # verb-like link words do not read in 'The <link> of <subject> ...'


def gen_relation(store: Store) -> list[Cand]:
    out: list[Cand] = []
    seen: set[str] = set()
    p = store.params
    # links = verified name-valued observations whose value resolves to a lexicon entity
    link_obs: list[Obs] = []
    for key, lst in store.obs.items():
        for o in lst:
            if o.kind == "support" and o.value.kind == "name" and store.lexicon.resolve(str(o.value.value)) is not None:
                link_obs.append(o)
    for lo in sorted(link_obs, key=lambda o: (o.subject, o.attribute, o.on, o.row_id)):
        target = store.lexicon.resolve(str(lo.value.value))
        assert target is not None
        tgt_name = target.name
        for (ts, ta), tlist in sorted(store.obs.items()):
            if ts != tgt_name or ta == lo.attribute and ts == lo.subject:
                continue
            tsup = [o for o in tlist if o.kind == "support"]
            if not tsup:
                continue
            for value_obs_group in _distinct_values(tsup):
                tv = value_obs_group[0].value
                ck = f"relation|{lo.subject}|{lo.attribute}|{tgt_name}|{ta}|{tv.kind}:{tv.value}"
                if ck in seen:
                    continue
                seen.add(ck)
                c = Cand("relation", ck, rule=f"relation_rule={p.relation_rule}")
                c.form = {"subject": lo.subject, "link": lo.attribute, "target": tgt_name, "attribute": ta, "value": vdict(tv)}
                status, why = store.engine_status("relation", c.form)
                c.engine = {"status": status, "reason": why}
                link_rows = [o for o in store.support((lo.subject, lo.attribute)) if same_value(o.value, lo.value)]
                c.evidence = {"link_rows": [_src(o, "link") for o in link_rows[:4]], "target_rows": [_src(o, "target_fact") for o in value_obs_group[:4]]}
                if tv.kind in ("name",):
                    c.reject("evidence", "name_valued_target_fact_excluded(another entity of the same type in the sentence)")
                    out.append(c)
                    continue
                if status == EvidenceState.VERIFIED_SUPPORT.value:
                    # engine joined link and target on the same day; also require clean rows for the joining pair
                    link_days = {o.on for o in link_rows if o.clean}
                    tgt_days = {o.on for o in value_obs_group if o.clean}
                    if not (link_days & tgt_days):
                        c.reject("evidence", "same_day_pair_rows_unclean")
                        out.append(c)
                        continue
                    c.verified = True
                    c.confidence = calculate_relation_confidence(
                        target_immutable=(tv.kind == "date"),
                        is_engine_verified=True,
                    )
                elif p.relation_rule == "stable":
                    asof = store.asof_fact((tgt_name, ta))
                    link_ok = any(o.clean for o in link_rows)
                    immutable = (tv.kind == "date" and isinstance(tv.value, str) and len(tv.value) == 10
                                 and not asof.volatile and any(tv.value <= o.on.isoformat() for o in value_obs_group))
                    if asof.accepted and link_ok and (immutable or not asof.volatile) and same_value(asof.value, tv):
                        c.verified = True
                        c.flags.append("not_engine_verified:relation_by_stable_target_fact")
                        c.confidence = calculate_relation_confidence(
                            target_immutable=immutable,
                            is_engine_verified=False,
                        )
                    else:
                        c.reject("evidence", "stable_rule_not_met(target_fact_not_stable_or_link_unclean)")
                        out.append(c)
                        continue
                else:
                    c.reject("evidence", "engine_no_same_day_link_and_target_observation")
                    out.append(c)
                    continue
                text, err = render.build_sentence("relation", lo.subject, ta, c.form["value"], store.names, p.allow_unlisted_names, p.as_of,
                                                  link=lo.attribute)
                if err:
                    c.reject("render", err)
                elif render.attr_has_unsafe_words(lo.attribute):
                    c.reject("render", "link_words_unsafe:" + str(render.attr_has_unsafe_words(lo.attribute)))
                elif lo.attribute in UNGRAMMATICAL_LINKS:
                    c.reject("render", "link_words_ungrammatical_in_the_relation_frame")
                else:
                    c.text = text
                out.append(c)
    return out


def _distinct_values(sup: list[Obs]) -> list[list[Obs]]:
    groups: list[list[Obs]] = []
    for o in sup:
        for g in groups:
            if same_value(g[0].value, o.value):
                g.append(o)
                break
        else:
            groups.append([o])
    return groups

