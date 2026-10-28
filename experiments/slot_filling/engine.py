"""Schema-guided slot-filling core: row analysis, candidate generation and cue features.

Nothing here reads a gold ``form``. Gold is only used by ``train.py`` (dev rows) to fill the
cue/paraphrase profile (``model/cue_profile.json``), the name gazetteer and the logistic
weights; ``extract_slots.py`` loads those data files and never sees a form.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from linking import Lexicon, split_sentences
from values import (Mention, find_value_mentions, negated_before, singular, MONTHS, NEGATION_WORDS, COMPARISON_NEG)

# ----------------------------------------------------------------------------------------
# tokens
# ----------------------------------------------------------------------------------------
STOP = set("""a an the of in on at to for by with and or but is are was were be been being it its this that these those
as from has have had do does did will would can could may might should must not no so if when which who he she they we our
you your i my his her their than then there here also""".split())
TOKRE = re.compile(r"[A-Za-z][A-Za-z]*(?:'[a-z]+)?")
_SUFFIXES = ("ations", "ation", "ions", "ion", "ings", "ing", "ied", "ies", "ed", "es", "s", "e", "ly")


def stem(word: str) -> str:
    w = word.lower().replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


SERIES_RE = re.compile(r"\b[Ss]eries\s+([A-D])\b")


def tokens(text: str, base: int = 0):
    out = []
    series = {}
    for m in SERIES_RE.finditer(text):
        series[m.start()] = m
    skip_until = -1
    for m in TOKRE.finditer(text):
        if m.start() < skip_until:
            continue
        if m.start() in series:
            sm = series[m.start()]
            out.append(("series_" + sm.group(1).lower(), base + sm.start(), base + sm.end()))
            skip_until = sm.end()
            continue
        w = m.group()
        st = stem(w)
        if w.lower() in STOP or len(st) < 2:
            continue
        out.append((st, base + m.start(), base + m.end()))
    return out


# physical unit classes (a quantity in GB is the same class as one in TB)
UCLASS = {"B": "data", "KB": "data", "MB": "data", "GB": "data", "TB": "data",
          "mm": "length", "cm": "length", "m": "length", "km": "length", "in": "length", "inch": "length",
          "g": "mass", "kg": "mass", "mAh": "mAh",
          "Hz": "freq", "kHz": "freq", "MHz": "freq", "GHz": "freq", "mW": "power", "W": "power", "kW": "power"}


EVENT_NAMES: set = set()          # filled from lexicon['events'] by set_events()


def set_events(events):
    EVENT_NAMES.update(events)


def sub_key(kind: str, rd: dict, vm=None) -> str:
    if kind == "name":
        # lexicon spellings that are products / events / the company itself vs. any other name
        if vm is not None and vm.name_src == "lexicon" and vm.ent_canon and (
                vm.ent_canon.startswith(("Hooly", "Made by", "The ", "Gemini")) or vm.ent_canon in EVENT_NAMES):
            return "lex"
        return "ext"
    if kind == "quantity":
        return UCLASS.get(rd["unit"], rd["unit"])
    if kind == "money":
        return rd.get("per", "once")
    if kind == "date":
        return {4: "y", 7: "m", 10: "d"}.get(len(rd["value"]), "?")
    return ""


def value_with_op(rd: dict, op):
    v = dict(rd)
    if op:
        v["op"] = op
    return v


# ----------------------------------------------------------------------------------------
# clause segmentation (for cue windows only; the value rules use values.clause_bounds)
# ----------------------------------------------------------------------------------------
_BREAK = re.compile(r",(?=\s|$)|;|\(|\)|\s(?:and|but|while|which|whereas|although|because)\s", re.I)


def clause_spans(sent: str):
    spans, start = [], 0
    for m in _BREAK.finditer(sent):
        if m.start() > start:
            spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(sent)))
    return spans


def clause_of(spans, pos):
    for a, b in spans:
        if a <= pos <= b:
            return a, b
    return spans[-1]


# ----------------------------------------------------------------------------------------
# names
# ----------------------------------------------------------------------------------------
NAME_STOP = {w.lower() for w in """The A An This That These Those It He She We They Our His Her Its Their In On At For From By With As And But
Or If When While After Before Since Until Today Now Yet Still Also Every Each All Any Some No Not Never Only Just So Then There Here
What Which Who How Why Where Please Note Yes One Two Three Four Five Six Seven Eight Nine Ten Q1 Q2 Q3 Q4 H1 H2 AI I Mr Mrs Ms Dr
Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March April May June July August September October
November December Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec Plus Free Pro Max Lite Series Version""".split()}
CAPWORD = r"[A-Z][A-Za-z]+(?:[-'’][A-Za-z]+)*"
CAPSEQ = re.compile(r"(?<![\w'’-])" + CAPWORD + r"(?:\s+" + CAPWORD + r")*(?![\w])")


def unknown_names(sent: str, taken):
    """Capitalised phrases not already claimed; sentence-initial single words are not trusted."""
    out = []
    for m in CAPSEQ.finditer(sent):
        a, b = m.span()
        words = list(re.finditer(CAPWORD, m.group()))
        # trim stop words at both ends
        i, j = 0, len(words)
        while i < j and words[i].group().lower() in NAME_STOP:
            i += 1
        while j > i and words[j - 1].group().lower() in NAME_STOP:
            j -= 1
        if i >= j:
            continue
        a2, b2 = a + words[i].start(), a + words[j - 1].end()
        if any(a2 < y and x < b2 for x, y in taken):
            continue
        phrase = sent[a2:b2]
        if re.search(r"[’']s$", phrase):
            phrase = phrase[:-2]
            b2 -= 2
        if a2 == 0 and len(phrase.split()) == 1:
            continue
        out.append((a2, b2, phrase))
    return out


# ----------------------------------------------------------------------------------------
# data classes
# ----------------------------------------------------------------------------------------
@dataclass
class VM:
    """One value mention of a sentence (typed, name)."""
    kind: str
    readings: list
    start: int                  # row-level offsets
    end: int
    rule: str
    op: str | None = None
    near: frozenset = frozenset()
    far: frozenset = frozenset()
    clause: tuple = (0, 0)      # row-level clause span
    sent: tuple = (0, 0)
    suppressed: str | None = None   # reason a mention reads as nothing (approx, range, negation, ...)
    name_src: str | None = None     # lexicon / gazetteer / unknown
    ent_canon: str | None = None
    surface: str = ""
    temporal: dict = field(default_factory=dict)
    extra_ends: list | None = None


@dataclass
class Ent:
    start: int
    end: int
    canon: str
    surface: str
    registered: str


@dataclass
class SentInfo:
    start: int
    end: int
    text: str
    ents: list
    vms: list
    clauses: list               # row-level clause spans
    tok_all: list               # (stem, start, end) row-level, not in entity spans
    pronoun_pos: list           # row-level positions of pronouns


PRONOUN = re.compile(r"\b(?:it|its|he|she|his|her|they|their|them|him)\b", re.I)


def entity_mentions(lex: Lexicon, text: str):
    out = []
    for a, b, canon, surf, reg in lex.mentions(text):
        words = reg.split()
        if len(words) == 1 and reg.islower():
            continue                                  # generic lower-case alias such as "outage"
        if len(words) == 1 and reg[0].isupper() and reg != canon and surf != reg and surf.lower() == reg.lower():
            # single-word alias written in another case ("search", "photos"): common word, not an entity
            if not (surf.isupper() and len(surf) > 1):
                continue
        out.append(Ent(a, b, canon, surf, reg))
    return out


def analyse_row(text: str, lex: Lexicon, gaz: frozenset, count_units: frozenset) -> list[SentInfo]:
    if not EVENT_NAMES:
        set_events(lex.events)
    ents_all = entity_mentions(lex, text)
    result = []
    for ss, se in split_sentences(text):
        sent = text[ss:se]
        ents = [e for e in ents_all if ss <= e.start and e.end <= se]
        ent_spans_rel = [(e.start - ss, e.end - ss) for e in ents]
        mentions = find_value_mentions(sent, ent_spans_rel, set(count_units))
        cl_rel = clause_spans(sent)
        cl_abs = [(ss + a, ss + b) for a, b in cl_rel]
        taken = list(ent_spans_rel) + [(m.start, m.end) for m in mentions]
        # token inventory outside entity spans
        tok_all = [t for t in tokens(sent, ss) if not any(a <= t[1] - ss < b for a, b in ent_spans_rel)]
        vms = []
        for m in mentions:
            vm = _wrap_typed(m, sent, ss, se, cl_rel, tok_all)
            vms.append(vm)
        # names: lexicon entities (as values), gazetteer, unknown capitalised phrases
        name_cands = []
        for e in ents:
            name_cands.append((e.start - ss, e.end - ss, sent[e.start - ss:e.end - ss], "lexicon", e.canon))
        lowsent = sent
        for g in sorted(gaz, key=lambda x: (-len(x), x)):
            for gm in re.finditer(r"(?<![\w])" + re.escape(g) + r"(?![\w])", lowsent):
                a, b = gm.span()
                if any(a < y and x < b for x, y, *_ in name_cands) or any(a < y and x < b for x, y in
                                                                          [(m.start, m.end) for m in mentions]):
                    continue
                name_cands.append((a, b, g, "gazetteer", None))
        taken2 = taken + [(a, b) for a, b, *_ in name_cands]
        for a, b, phrase in unknown_names(sent, taken2):
            name_cands.append((a, b, phrase, "unknown", None))
        for a, b, surf, src, canon in name_cands:
            if src != "lexicon" and any(a < y and x < b for x, y in [(m.start, m.end) for m in mentions]):
                continue
            if sent[b:b + 1] == ":" and not sent[:a].strip():
                continue                       # "Gavin: ..." is a speaker label, not a value
            vm = _wrap_name(a, b, surf, src, canon, sent, ss, se, cl_rel, tok_all)
            vms.append(vm)
        vms.sort(key=lambda v: (v.start, v.end))
        result.append(SentInfo(ss, se, sent, ents, vms, cl_abs, tok_all,
                               [ss + m.start() for m in PRONOUN.finditer(sent)]))
    return result


def _windows(start, end, clause, tok_all, ent_free=True):
    left = [t for t in tok_all if clause[0] <= t[1] and t[2] <= start][-8:]
    right = [t for t in tok_all if end <= t[1] and t[2] <= clause[1]][:6]
    near = frozenset(t[0] for t in left + right)
    allt = frozenset(t[0] for t in tok_all)
    return near, allt - near


INVIS = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u2062\u2063]|(?<![A-Za-z])\u00ad|\u00ad(?![A-Za-z])")


def invisible_near(sent: str, a: int, b: int) -> bool:
    """A value (or name, or yes/no clause) written with an invisible character in or beside it reads as nothing."""
    return bool(INVIS.search(sent[max(0, a - 2):b + 2]))


def _wrap_typed(m: Mention, sent, ss, se, cl_rel, tok_all) -> VM:
    a, b = m.start + ss, m.end + ss
    clause = clause_of(cl_rel, m.start)
    clause_abs = (ss + clause[0], ss + clause[1])
    # tokens inside the mention itself are not cues
    toks = [t for t in tok_all if not (a <= t[1] < b)]
    near, far = _windows(a, b, clause_abs, toks)
    reason = None
    if m.approx:
        reason = "approximation"
    elif m.in_range:
        reason = "range_end"
    elif m.negated:
        reason = "negated_value"
    elif m.blocked:
        reason = m.blocked
    elif invisible_near(sent, m.start, m.end):
        reason = "invisible_character"
    vm = VM(m.kind, m.readings, a, b, m.rule, op=m.op, near=near, far=far, clause=clause_abs, sent=(ss, se),
            suppressed=reason)
    if m.extra and m.extra.get("ends"):
        vm.extra_ends = [e + ss for e in m.extra["ends"]]
    return vm


def _wrap_name(a, b, surf, src, canon, sent, ss, se, cl_rel, tok_all) -> VM:
    A, B = a + ss, b + ss
    clause = clause_of(cl_rel, a)
    clause_abs = (ss + clause[0], ss + clause[1])
    toks = [t for t in tok_all if not (A <= t[1] < B)]
    # appositions ("Hooly's head of security, Ron LaFlame, ...") put the cue words in another comma clause,
    # so a name looks at a fixed token window of the whole sentence instead of its comma clause
    left_c = [t for t in toks if clause_abs[0] <= t[1] and t[2] <= A][-6:]
    right_c = [t for t in toks if B <= t[1] and t[2] <= clause_abs[1]][:4]
    if len(left_c) + len(right_c) >= 2:
        left, right = left_c, right_c                      # an ordinary clause: stay inside it
    else:                                                  # apposition: "Hooly's head of security, Ron LaFlame, ..."
        left = [t for t in toks if ss <= t[1] and t[2] <= A][-6:]
        right = [t for t in toks if B <= t[1] and t[2] <= se][:3]
    near = frozenset(t[0] for t in left + right)
    far = frozenset(t[0] for t in toks) - near
    reason = "negated_value" if negated_before(sent, a) else ("invisible_character" if invisible_near(sent, a, b) else None)
    value = surf.strip()
    if value.endswith(("'s", "’s")):
        value = value[:-2]
    vm = VM("name", [{"kind": "name", "value": value}], A, B, "name_" + src, near=near, far=far, clause=clause_abs,
            sent=(ss, se), suppressed=reason, name_src=src, ent_canon=canon, surface=surf)
    return vm


# ----------------------------------------------------------------------------------------
# cue profile (counts learned from dev gold; leave-one-row-out capable)
# ----------------------------------------------------------------------------------------
class Profile:
    def __init__(self):
        self.n = Counter()                                  # attribute -> examples
        self.kind = defaultdict(Counter)                    # attr -> kind -> n
        self.sub = defaultdict(Counter)                     # attr -> (kind|sub) -> n
        self.near = defaultdict(Counter)
        self.far = defaultdict(Counter)
        self.df = Counter()                                 # token -> number of attributes with it (near or far)
        self.tot = Counter()                                # token -> total occurrences over all attributes
        self.op = defaultdict(Counter)

    # example: dict(attr, kind, sub, near:set, far:set, op)
    def add(self, ex, sign=1):
        a = ex["attr"]
        self.n[a] += sign
        self.kind[a][ex["kind"]] += sign
        self.sub[a][ex["kind"] + "|" + ex["sub"]] += sign
        self.op[a][ex.get("op") or "eq"] += sign
        for w in ex["near"]:
            self._bump(self.near, a, w, sign)
        for w in ex["far"]:
            self._bump(self.far, a, w, sign)

    def _bump(self, table, a, w, sign):
        before = self.near[a][w] + self.far[a][w]
        self.tot[w] += sign
        table[a][w] += sign
        after = self.near[a][w] + self.far[a][w]
        if before <= 0 < after:
            self.df[w] += 1
        elif after <= 0 < before:
            self.df[w] -= 1

    def idf(self, w):
        return math.log((len(self.n) + 2.0) / (self.df.get(w, 0) + 1.0))

    def to_json(self):
        return {"n": {a: c for a, c in self.n.items() if c > 0},
                "kind": {a: {k: v for k, v in c.items() if v > 0} for a, c in self.kind.items() if self.n[a] > 0},
                "sub": {a: {k: v for k, v in c.items() if v > 0} for a, c in self.sub.items() if self.n[a] > 0},
                "op": {a: {k: v for k, v in c.items() if v > 0} for a, c in self.op.items() if self.n[a] > 0},
                "near": {a: {k: v for k, v in c.items() if v > 0} for a, c in self.near.items() if self.n[a] > 0},
                "far": {a: {k: v for k, v in c.items() if v > 0} for a, c in self.far.items() if self.n[a] > 0}}

    @classmethod
    def from_json(cls, raw):
        p = cls()
        p.n = Counter(raw["n"])
        for key in ("kind", "sub", "op", "near", "far"):
            tbl = getattr(p, key)
            for a, c in raw[key].items():
                tbl[a] = Counter(c)
        for a in p.n:
            for w in set(p.near[a]) | set(p.far[a]):
                p.df[w] += 1
                p.tot[w] += p.near[a].get(w, 0) + p.far[a].get(w, 0)
        return p


def attr_name_tokens(attr: str):
    return [stem(w) for w in attr.split("_") if w and w.lower() not in STOP and len(stem(w)) >= 2]


# ----------------------------------------------------------------------------------------
# features
# ----------------------------------------------------------------------------------------
KINDS = ("quantity", "money", "percent", "duration", "date", "version", "name", "boolean")
FEATURES = (["bias", "kind_p", "sub_p", "cue_near", "cue_far", "name_near", "name_far", "n_seen", "prox", "before",
             "same_clause", "nearest", "nent", "alias_only", "has_op", "op_p", "unit_in_name", "other_same_kind",
             "name_all_near", "name_all_far", "cold", "pronoun"] + ["k_" + k for k in KINDS]
            + ["src_gaz", "src_unknown", "src_lex", "ent_rank0", "closer_same_attr", "gap_log", "cue_prec_near",
               "cue_prec_far", "no_cue", "first_ent", "name_unmatched"])


def cue_score(table_a, n_a, toks, profile):
    if not toks:
        return 0.0
    s = 0.0
    for w in toks:
        c = table_a.get(w, 0)
        if c > 0:
            s += (c / (n_a + 1.0)) * profile.idf(w)
    return min(s, 6.0)


def cue_precision(profile, attr, toks):
    """Sum over cue tokens of the share of that token's occurrences that belong to this attribute."""
    s = 0.0
    for w in toks:
        c = profile.near[attr].get(w, 0) + profile.far[attr].get(w, 0)
        if c > 0:
            s += c / max(profile.tot.get(w, c), c)
    return min(s, 4.0)


def name_overlap(name_toks, toks):
    if not name_toks:
        return 0.0, 0.0
    hit = sum(1 for w in name_toks if w in toks)
    return hit / len(name_toks), 1.0 if hit == len(name_toks) else 0.0


def pick_reading(vm: VM, profile: Profile, attr: str, name_toks):
    """Choose the reading whose unit class the attribute has been seen with (counted nouns have several)."""
    best, best_s = None, -1.0
    n_kind = profile.kind[attr].get(vm.kind, 0) if profile.n.get(attr, 0) > 0 else 0
    for idx, rd in enumerate(vm.readings):
        sk = sub_key(vm.kind, rd)
        if vm.kind in ("quantity", "money", "date") and n_kind > 0:
            c = profile.sub[attr].get(vm.kind + "|" + sk, 0)
            s = (c + 0.0) / n_kind
        else:
            s = 0.0
        if idx == 0 and vm.kind == "quantity" and (sk in name_toks or stem(sk) in name_toks):
            s = max(s, 0.5)               # the noun right after the number may match the attribute name
        if s > best_s:
            best, best_s = rd, s
    return best, best_s


def candidate_features(vm: VM, ent: Ent, attr: str, profile: Profile, si: SentInfo, ent_list, nent_distinct,
                       reading=None, unit_ok=None):
    n_a = profile.n.get(attr, 0)
    name_toks = attr_name_tokens(attr)
    f = dict.fromkeys(FEATURES, 0.0)
    f["bias"] = 1.0
    kind = vm.kind
    if n_a > 0:
        n_kind = profile.kind[attr].get(kind, 0)
        f["kind_p"] = (n_kind + 0.05) / (n_a + 0.1)
        f["n_seen"] = math.log1p(n_a)
        if reading is not None and n_kind > 0:
            sk = sub_key(kind, reading, vm)
            if kind in ("quantity", "money", "date", "name"):
                f["sub_p"] = (profile.sub[attr].get(kind + "|" + sk, 0) + 0.1) / (n_kind + 0.2)
            else:
                f["sub_p"] = 1.0
        else:
            f["sub_p"] = 0.5 if n_kind == 0 else 1.0
        if vm.op or True:
            ops = profile.op[attr]
            f["op_p"] = (ops.get(vm.op or "eq", 0) + 0.2) / (sum(ops.values()) + 0.4)
    else:
        f["cold"] = 1.0
        f["kind_p"] = 0.3
        f["sub_p"] = 0.5
        f["op_p"] = 0.5
    f["has_op"] = 1.0 if vm.op else 0.0
    f["cue_near"] = cue_score(profile.near[attr], n_a, vm.near, profile) + cue_score(profile.far[attr], n_a, vm.near, profile) * 0.5 \
        if n_a else 0.0
    f["cue_far"] = (cue_score(profile.far[attr], n_a, vm.far, profile) + cue_score(profile.near[attr], n_a, vm.far, profile) * 0.5) \
        if n_a else 0.0
    f["name_near"], f["name_all_near"] = name_overlap(name_toks, vm.near)
    f["name_far"], f["name_all_far"] = name_overlap(name_toks, vm.far)
    if n_a:
        f["cue_prec_near"] = cue_precision(profile, attr, vm.near)
        f["cue_prec_far"] = cue_precision(profile, attr, vm.far)
    f["no_cue"] = 1.0 if (f["cue_prec_near"] == 0 and f["name_near"] == 0) else 0.0
    f["name_unmatched"] = float(min(3, sum(1 for w in name_toks if w not in vm.near and w not in vm.far)))
    if kind == "quantity" and reading is not None and vm.readings and reading is vm.readings[0]:
        f["unit_in_name"] = 1.0 if (stem(reading["unit"]) in name_toks or reading["unit"] in name_toks) else 0.0
    # subject geometry: closest mention of this entity to the value
    ms = [e for e in ent_list if e.canon == ent.canon]
    best = min(ms, key=lambda e: _gap(e, vm))
    gap = _gap(best, vm)
    ntok = len([1 for t in si.tok_all if min(best.end, vm.start) <= t[1] < max(best.start, vm.end)]) if gap > 0 else 0
    f["prox"] = 1.0 / (1.0 + ntok / 4.0)
    f["before"] = 1.0 if best.end <= vm.start else 0.0
    f["same_clause"] = 1.0 if vm.clause[0] <= best.start and best.end <= vm.clause[1] else 0.0
    lo, hi = min(best.end, vm.start), max(best.start, vm.end)
    between = [e for e in ent_list if e.canon != ent.canon and lo <= e.start and e.end <= hi]
    f["nearest"] = 0.0 if between else 1.0
    f["nent"] = math.log1p(nent_distinct)
    f["alias_only"] = 1.0 if best.registered.lower() != best.canon.lower() else 0.0
    f["pronoun"] = 0.0
    f["k_" + kind] = 1.0
    if kind == "name":
        f["src_gaz"] = 1.0 if vm.name_src == "gazetteer" else 0.0
        f["src_unknown"] = 1.0 if vm.name_src == "unknown" else 0.0
        f["src_lex"] = 1.0 if vm.name_src == "lexicon" else 0.0
    return f


def _gap(e: Ent, vm: VM) -> int:
    if e.end <= vm.start:
        return vm.start - e.end
    if vm.end <= e.start:
        return e.start - vm.end
    return 0


# ----------------------------------------------------------------------------------------
# conditional-logit scorer: candidates of one value mention compete with each other and with "none"
# ----------------------------------------------------------------------------------------
NONE_FEATURES = ["none_bias"] + ["none_k_" + k for k in KINDS]


def none_vector(kind):
    return {"none_bias": 1.0, "none_k_" + kind: 1.0}


class GroupLogit:
    def __init__(self, weights=None):
        self.w = weights or {}

    def score(self, f):
        w = self.w
        return sum(w.get(k, 0.0) * v for k, v in f.items() if v)

    def group_probs(self, feats, kind):
        """Probability of each candidate of one value mention (the remainder is the 'none' option)."""
        s = [self.score(f) for f in feats]
        s0 = self.score(none_vector(kind))
        m = max(s + [s0])
        e = [math.exp(x - m) for x in s]
        e0 = math.exp(s0 - m)
        z = e0 + sum(e)
        return [x / z for x in e]

    def fit(self, groups, epochs=150, lr=0.5, l2=2e-3):
        """groups: list of (kind, [feature dicts], [target prob per candidate]); target none = 1 - sum."""
        names = FEATURES + NONE_FEATURES
        w = {k: 0.0 for k in names}
        g2 = {k: 1e-8 for k in names}
        n = max(len(groups), 1)
        for _ in range(epochs):
            grad = {k: 0.0 for k in names}
            for kind, feats, tgt in groups:
                s = [sum(w[k] * v for k, v in f.items() if v) for f in feats]
                nv = none_vector(kind)
                s0 = sum(w[k] * v for k, v in nv.items())
                m = max(s + [s0])
                e = [math.exp(x - m) for x in s]
                e0 = math.exp(s0 - m)
                z = e0 + sum(e)
                for f, ei, ti in zip(feats, e, tgt):
                    d = ei / z - ti
                    if d:
                        for k, v in f.items():
                            if v:
                                grad[k] += d * v
                d0 = e0 / z - (1.0 - sum(tgt))
                if d0:
                    for k, v in nv.items():
                        grad[k] += d0 * v
            for k in names:
                g = grad[k] / n + l2 * w[k]
                g2[k] += g * g
                w[k] -= lr * g / math.sqrt(g2[k])
        self.w = w
        return self
