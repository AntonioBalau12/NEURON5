"""Candidate generation, scoring, selection and fact building on top of engine.py."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from engine import (Ent, GroupLogit, Profile, SentInfo, VM, analyse_row, attr_name_tokens, candidate_features,
                    clause_of, clause_spans, invisible_near, pick_reading, stem, sub_key, tokens, value_with_op, STOP)
from values import NEGATION_WORDS, COMPARISON_NEG

BOOL_MIN_SHARE = 0.5
NEEDS_CUE = {"date", "name", "money"}
UNKNOWN_NAME_EXTRA = 0.15


@dataclass
class Cand:
    vm: VM
    ent: Ent
    attr: str
    reading: dict
    features: dict
    p: float = 0.0
    si: SentInfo | None = None
    value: dict | None = None
    negated: bool = False
    end: int = 0
    notes: list = field(default_factory=list)
    label: int = 0
    runner_gap: float = 1.0
    runner: object = None


# ----------------------------------------------------------------------------------------
def norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def sentence_negation(sent: str):
    s = COMPARISON_NEG.sub(" ", sent)
    return bool(NEGATION_WORDS.search(s))


def bool_vms(si: SentInfo, text: str):
    """One pseudo mention per distinct entity: the clause holding its first mention is the cue window."""
    out = []
    seen = set()
    for e in si.ents:
        clause = None
        for a, b in si.clauses:
            if a <= e.start and e.end <= b:
                clause = (a, b)
                break
        if clause is None:
            clause = (si.start, si.end)
        if (e.canon, clause) in seen:
            continue
        seen.add((e.canon, clause))
        near = frozenset(t[0] for t in si.tok_all if clause[0] <= t[1] and t[2] <= clause[1])
        far = frozenset(t[0] for t in si.tok_all) - near
        vm = VM("boolean", [{"kind": "boolean", "value": True}], e.start, e.end, "bool_clause", near=near, far=far,
                clause=clause, sent=(si.start, si.end))
        neg_c = sentence_negation(text[clause[0]:clause[1]])
        neg_s = sentence_negation(si.text)
        if neg_c != neg_s:
            vm.suppressed = "negation_scope_mismatch"
        if invisible_near(text[clause[0]:clause[1]], 0, clause[1] - clause[0]):
            vm.suppressed = "invisible_character"
        vm.temporal = {"negated": neg_c}
        out.append((e, vm))
    return out


# ----------------------------------------------------------------------------------------
def _tok_gap(e: Ent, vm: VM, si: SentInfo):
    """(number of word tokens between entity mention and value, 0 if the entity comes first else 1)."""
    if e.end <= vm.start:
        lo, hi, before = e.end, vm.start, 0
    elif vm.end <= e.start:
        lo, hi, before = vm.end, e.start, 1
    else:
        return (0, 0)
    return (sum(1 for t in si.tok_all if lo <= t[1] < hi), before)


def score_groups(cands, lr):
    groups: dict = {}
    for c in cands:
        groups.setdefault(id(c.vm), []).append(c)
    for g in groups.values():
        ps = lr.group_probs([c.features for c in g], g[0].vm.kind)
        for c, p in zip(g, ps):
            c.p = p


def training_groups(cands):
    """(kind, feature dicts, target probabilities) per value mention; no positive candidate => target is 'none'."""
    groups: dict = {}
    for c in cands:
        groups.setdefault(id(c.vm), []).append(c)
    out = []
    for g in groups.values():
        npos = sum(c.label for c in g)
        tgt = [(c.label / npos) if npos else 0.0 for c in g]
        out.append((g[0].vm.kind, [c.features for c in g], tgt))
    return out


def generate(text: str, infos: list[SentInfo], lex, profile: Profile, allow_cold=True):
    cands: list[Cand] = []
    for si in infos:
        if not si.ents:
            continue
        canon = sorted({e.canon for e in si.ents})
        nent = len(canon)
        for vm in si.vms:
            if vm.suppressed:
                continue
            gaps = {}
            for c in canon:
                gaps[c] = min(_tok_gap(e, vm, si) for e in si.ents if e.canon == c)
            for c in canon:
                ent = next(e for e in si.ents if e.canon == c)
                if vm.kind == "name" and (vm.ent_canon == c):
                    continue
                if vm.kind == "name" and any(e.canon == c and e.start == vm.start and e.end == vm.end for e in si.ents):
                    continue
                if any(e.canon == c and e.start < vm.end and vm.start < e.end for e in si.ents):
                    continue
                for attr in lex.subjects[c].attributes:
                    n_a = profile.n.get(attr, 0)
                    name_toks = attr_name_tokens(attr)
                    if n_a > 0:
                        if profile.kind[attr].get(vm.kind, 0) <= 0:
                            continue
                    else:
                        if not allow_cold or vm.kind == "boolean":
                            continue
                        if not (set(name_toks) & (vm.near | vm.far)):
                            continue
                    rd, _ = pick_reading(vm, profile, attr, name_toks)
                    if rd is None:
                        continue
                    if n_a > 0 and vm.kind in ("quantity", "money", "date", "name"):
                        nk = profile.kind[attr].get(vm.kind, 0)
                        sk = sub_key(vm.kind, rd, vm)
                        unit_named = vm.kind == "quantity" and (stem(rd["unit"]) in name_toks or rd["unit"] in name_toks)
                        if (nk >= 3 or (vm.kind == "quantity" and nk >= 1)) \
                                and profile.sub[attr].get(vm.kind + "|" + sk, 0) == 0 and not unit_named:
                            continue          # this form (unit class / billing period / date precision / name type) never seen
                    f = candidate_features(vm, ent, attr, profile, si, si.ents, nent, rd)
                    g = gaps[c]
                    f["ent_rank0"] = 1.0 if all(g <= gaps[o] for o in canon) else 0.0
                    f["closer_same_attr"] = 1.0 if any(
                        gaps[o] < g and attr in lex.subjects[o].attributes for o in canon if o != c) else 0.0
                    f["gap_log"] = math.log1p(g[0])
                    f["first_ent"] = 1.0 if si.ents[0].canon == c else 0.0
                    if f["no_cue"] and vm.kind in NEEDS_CUE:
                        continue            # a date / name / price with no cue word for this attribute at all
                    cd = Cand(vm, ent, attr, rd, f, si=si)
                    cd.value = value_with_op(rd, vm.op)
                    cd.end = vm.end
                    if vm.extra_ends:
                        idx = vm.readings.index(rd)
                        cd.end = vm.extra_ends[idx]
                    cands.append(cd)
        # booleans
        for ent, vm in bool_vms(si, text):
            if vm.suppressed:
                continue
            for attr in lex.subjects[ent.canon].attributes:
                n_a = profile.n.get(attr, 0)
                if n_a <= 0:
                    continue
                if profile.kind[attr].get("boolean", 0) / n_a < BOOL_MIN_SHARE:
                    continue
                f = candidate_features(vm, ent, attr, profile, si, si.ents, len({e.canon for e in si.ents}),
                                       vm.readings[0])
                # a boolean needs its attribute words: no overlap and no learned cue means nothing to hold on to
                if f["cue_near"] + f["cue_far"] + f["name_near"] + f["name_far"] <= 0:
                    continue
                f["ent_rank0"] = 1.0
                f["first_ent"] = 1.0 if si.ents[0].canon == ent.canon else 0.0
                cd = Cand(vm, ent, attr, vm.readings[0], f, si=si)
                neg = vm.temporal["negated"]
                cd.negated = neg
                cd.value = {"kind": "boolean", "value": not neg}
                cd.end = vm.end
                cands.append(cd)
    return cands


# ----------------------------------------------------------------------------------------
def gold_key(g):
    return (g["subject"], g["attribute"], tuple(sorted((k, str(v)) for k, v in g["value"].items())))


def cand_key(c: Cand):
    return (c.ent.canon, c.attr, tuple(sorted((k, str(v)) for k, v in c.value.items())))


def row_examples(infos: list[SentInfo], text: str, gold: list, lex):
    """Profile examples for one dev row: (attr, kind, sub, near, far, op) from gold facts matched to mentions."""
    exs = []
    for g in gold:
        v = g["value"]
        kind = v["kind"]
        attr = g["attribute"]
        hit = None
        if kind == "boolean":
            subj_ent = None
            for si in infos:
                for e in si.ents:
                    if e.canon == g["subject"]:
                        subj_ent = (si, e)
                        break
                if subj_ent:
                    break
            if subj_ent:
                si, e = subj_ent
                for ent, vm in bool_vms(si, text):
                    if ent.canon == g["subject"] and not vm.suppressed and vm.temporal["negated"] == (not v["value"]):
                        hit = vm
                        break
            if hit is not None:
                exs.append({"attr": attr, "kind": kind, "sub": "", "near": set(hit.near), "far": set(hit.far), "op": None})
            continue
        for si in infos:
            for vm in si.vms:
                if vm.kind != kind or vm.suppressed:
                    continue
                if kind == "name":
                    gv = norm_name(v["value"])
                    if norm_name(vm.readings[0]["value"]) == gv or (vm.ent_canon and norm_name(vm.ent_canon) == gv):
                        hit = vm
                        break
                else:
                    for rd in vm.readings:
                        if value_with_op(rd, vm.op) == v:
                            hit = vm
                            break
                    if hit:
                        rd_hit = next(rd for rd in hit.readings if value_with_op(rd, hit.op) == v)
                        break
            if hit:
                break
        if hit is None:
            continue
        sub = sub_key(kind, rd_hit, hit) if kind != "name" else sub_key("name", None, hit)
        exs.append({"attr": attr, "kind": kind, "sub": sub, "near": set(hit.near), "far": set(hit.far),
                    "op": hit.op})
    return exs


def label_candidates(cands: list[Cand], gold: list):
    gk = {}
    for g in gold:
        gk[gold_key(g)] = g
    for c in cands:
        if c.vm.kind == "name":
            ok = False
            for g in gold:
                if g["subject"] == c.ent.canon and g["attribute"] == c.attr and g["value"]["kind"] == "name":
                    gv = norm_name(g["value"]["value"])
                    if norm_name(c.vm.readings[0]["value"]) == gv or (c.vm.ent_canon and norm_name(c.vm.ent_canon) == gv):
                        ok = True
            c.label = int(ok)
        else:
            c.label = int(cand_key(c) in gk)


# ----------------------------------------------------------------------------------------
def select(cands: list[Cand], thr: dict, margin=0.3):
    """Best candidate per value mention (one atomic fact per mention); booleans best per entity/attribute."""
    by_vm: dict = {}
    for c in cands:
        by_vm.setdefault(id(c.vm), []).append(c)
    chosen = []
    for key, group in by_vm.items():
        group.sort(key=lambda c: -c.p)
        best = group[0]
        need = thr.get(best.vm.kind, thr["default"])
        if best.vm.kind == "name" and best.vm.name_src == "unknown":
            need += UNKNOWN_NAME_EXTRA
        if best.p < need:
            continue
        runner = next((c for c in group[1:] if (c.ent.canon, c.attr) != (best.ent.canon, best.attr)), None)
        best.notes.append("margin=%.2f" % (best.p - (runner.p if runner else 0.0)))
        best.runner_gap = best.p - (runner.p if runner else 0.0)
        best.runner = (runner.ent.canon, runner.attr) if runner and best.p - runner.p < margin else None
        chosen.append(best)
    # booleans: for one entity keep attributes by threshold; each boolean mention produced (ent, attr) groups
    return chosen


def select_bool(cands, thr, margin=0.12):
    """Booleans: group is (entity); the same clause cannot support two different attributes unless both clear thr."""
    groups: dict = {}
    for c in cands:
        groups.setdefault((c.ent.canon, c.vm.start), []).append(c)
    out = []
    for key, g in groups.items():
        g.sort(key=lambda c: -c.p)
        for i, c in enumerate(g):
            if c.p < thr.get("boolean", thr["default"]):
                break
            c.runner_gap = c.p - (g[i + 1].p if i + 1 < len(g) else 0.0)
            c.runner = None
            out.append(c)
    return out


def run_selection(cands, thr):
    chosen = select(cands, thr)
    # one value per (subject, attribute, form) inside a sentence: the more probable mention wins
    chosen.sort(key=lambda c: -c.p)
    keep, used = [], {}
    for c in chosen:
        k = (c.si.start, c.ent.canon, c.attr, sub_key(c.vm.kind, c.reading) if c.vm.kind != "boolean" else "")
        if c.vm.kind != "name" and k in used and used[k] != c.value:
            continue                               # competing value for the same slot: keep the stronger one only
        used.setdefault(k, c.value)
        keep.append(c)
    return keep


# ----------------------------------------------------------------------------------------
# temporal handling
# ----------------------------------------------------------------------------------------
TQ = re.compile(r"\b(from today|from now on|as of|since|still|now|currently|today|for now|right now|so far|"
                r"at the moment|for the moment|already|before|until|yet)\b", re.I)
LEAD_TQ = re.compile(r"^\s*(from today|from now on|today|now|as of [^,]{0,30}|for now|currently|right now)\s*,", re.I)


def temporal_for(c: Cand, text: str, date_vms: list[VM]):
    """Return (qualifier, observation_date, valid_from, valid_to, notes)."""
    si = c.si
    a, b = c.vm.clause
    seg = text[a:b]
    quals = []
    for m in TQ.finditer(seg):
        w = m.group(1)
        pos = a + m.start()
        wl = w.lower()
        # a comparison word right before a date or number value belongs to the value, not to the qualifier
        if wl in ("before", "until") and c.vm.start >= a and 0 <= c.vm.start - (a + m.end()) <= 2:
            continue
        # 'yet' and 'already' are weak
        if wl in ("yet",) and False:
            continue
        quals.append(w.lower() if wl != w else w)
    lead = LEAD_TQ.match(text[si.start:si.end])
    if lead and not quals and c.vm.clause[0] > si.start:
        quals.append(lead.group(1).strip())
    obs = vf = vt = None
    notes = []
    for dv in date_vms:
        if dv is c.vm or dv.suppressed and dv.suppressed != "x":
            pass
        if dv is c.vm:
            continue
        if not (si.start <= dv.start < si.end):
            continue
        before = text[max(si.start, dv.start - 12):dv.start]
        val = dv.readings[0]["value"]
        full = len(val) == 10
        if re.search(r"\bas of\s*$", before, re.I):
            if full:
                obs = val
            else:
                notes.append("as_of_partial_date:" + val)
            if "as of" not in [q.lower() for q in quals]:
                quals.append("as of")
        elif re.search(r"\b(?:until|till|through)\s*$", before, re.I):
            if full:
                vt = val
            else:
                notes.append("until_partial_date:" + val)
        elif c.vm.kind != "date" and re.search(r"\b(?:since|from)\s*$", before, re.I):
            if full:
                vf = val
            else:
                notes.append("since_partial_date:" + val)
    q = "; ".join(dict.fromkeys(quals)) if quals else None
    return q, obs, vf, vt, notes


# ----------------------------------------------------------------------------------------
TEMPORAL_WORDS = {"far", "still", "now", "today", "yet", "already", "currently", "since", "before", "until", "moment"}


def cue_words(c: Cand, profile: Profile, text: str):
    a, b = c.vm.clause
    toks = [t for t in c.si.tok_all if a <= t[1] and t[2] <= b and not (c.vm.start <= t[1] < c.vm.end)]
    nt = set(attr_name_tokens(c.attr))
    out = []
    for st, s, e in toks:
        if text[s:e].lower() in TEMPORAL_WORDS:
            continue
        if profile.near[c.attr].get(st, 0) > 0 or profile.far[c.attr].get(st, 0) > 0 or st in nt:
            out.append((s, e))
    if not out:
        return None
    return " ".join(text[s:e] for s, e in out[:4])


def span_for(c: Cand, text: str):
    """Smallest run of clauses covering the subject mention and the value (and the whole counted noun)."""
    si = c.si
    if c.vm.kind == "boolean":
        pts = [c.vm.clause[0], c.vm.clause[1]]
    else:
        pts = [c.ent.start, c.ent.end, c.vm.start, c.end]
    lo, hi = min(pts), max(pts)
    # snap to clause boundaries
    cs = [clause_of(si.clauses, p) for p in (lo, hi - 1 if hi > lo else hi)]
    a = min(x[0] for x in cs)
    b = max(x[1] for x in cs)
    a = min(a, lo)
    b = max(b, hi)
    seg = text[a:b]
    lead = len(seg) - len(seg.lstrip(" \t\n,;:"))
    trail = len(seg.rstrip(" \t\n,;:")) 
    a2, b2 = a + lead, a + trail
    if b2 <= a2:
        a2, b2 = lo, hi
    return a2, b2
