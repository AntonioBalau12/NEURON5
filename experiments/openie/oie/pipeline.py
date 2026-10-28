"""OpenIE-style extraction: typed values -> (subject, relation cue, object) -> lexicon (entity, attribute, value)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .entities import EntityFinder, EntityMention, Lexicon
from .model import Model, attr_tokens, value_sig
from .textutil import HARD_DELIMS, STOPWORDS, Tok, sentence_spans, stem, tokenize
from .values import Val, ValueFinder, singular

NEG_RX = re.compile(r"\b(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n['\u2019]t\b", re.I)
CMP_NEG_PHRASES = re.compile(r"\b(?:no|not)\s+(?:more|less|fewer|later|earlier)\s+than\b", re.I)
CLAUSE_DELIMS = ",;:!?\u2022\u00b7|"
CONJ_STOP = {"but", "while", "whereas", "which", "where", "though", "although", "because", "then", "yet", "who"}
TEMPORAL_RX = re.compile(
    r"\b(?:from today|from now on|as of(?: today| now)?|as at|no longer|used to|so far|at the time|at that time|"
    r"still|now|currently|since|until|till|already|today|yesterday|tomorrow|last (?:quarter|year|month|week)|"
    r"this (?:year|quarter|month|week)|next (?:year|quarter|month|week)|formerly|previously|originally|"
    r"initially|recently|soon|before|after|ago|yet|anymore)\b", re.I)
PRON_PERSON = {"he", "his", "him", "she", "her", "hers"}
PRON_THING = {"it", "its"}
PRON_SPEAKER = {"i", "my", "me", "mine", "myself"}
PERSON_ATTRS = {"joined", "previous_employer", "team_size", "chairs", "chairs_audit_committee", "independent_director"}


@dataclass
class Mention:
    start: int
    end: int
    text: str
    entity: str
    via: str = "alias"           # alias | pronoun | speaker
    oblique: bool = False        # preceded by a preposition (at X, with X, from X)


@dataclass
class Sent:
    start: int
    end: int
    text: str
    mentions: list[Mention] = field(default_factory=list)
    names: list[Val] = field(default_factory=list)
    vals: list[Val] = field(default_factory=list)
    toks: list[Tok] = field(default_factory=list)


@dataclass
class Params:
    min_attr_score: float = 1.3
    ambiguity_margin: float = 0.4
    accept_unknown_units: bool = False
    unit_penalty: float = 1.5
    use_names: bool = True
    use_booleans: bool = True
    bool_min_score: float = 1.8
    unique_bonus: float = 1.4
    hint_min_score: float = 1.5
    shrink: float = 1.5
    strict_partial: bool = False       # tried: no gain in CV
    bridge_apposition: bool = False    # tried: -8 TP in CV, same extras
    prox_weight: float = 3.0
    outside_margin: float = 99.0   # tried 0.5/1.0: moved ~39 correct facts to ambiguous for 6 fewer errors; disabled
    name_min_cue: float = 1.0
    bool_min_lex: float = 0.99
    bool_alt_learned: float = 1.0     # learned-only (paraphrase) evidence needed when the attribute words are not all present


class Extractor:
    def __init__(self, lexicon_path: str | Path, model: Model, params: Params | None = None):
        self.lex = Lexicon.load(lexicon_path)
        self.finder = EntityFinder(self.lex)
        self.model = model
        self.params = params or Params()
        model.shrink = self.params.shrink
        model.strict_partial = self.params.strict_partial
        units = set(model.units)
        for attrs in self.lex.attrs.values():
            for a in attrs:
                last = a.split("_")[-1]
                if last.endswith("s") and len(last) > 3:
                    units.add(singular(last))
        self.units = units
        self.vf = ValueFinder(units, self.params.accept_unknown_units)
        self.person_like = {n for n, a in self.lex.attrs.items() if set(a) & PERSON_ATTRS}
        self.gaz = sorted({n for n in model.names if n}, key=lambda s: (-len(s), s))
        self.gaz_rx = (re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in self.gaz) + r")(?![\w])")
                       if self.gaz else None)
        self.attr_owner = self.lex.attr_owners

    # ------------------------------------------------------------------ sentence analysis
    def analyse(self, text: str) -> list[Sent]:
        speaker = self.finder.speaker(text)
        mentions_all = self.finder.find(text)
        toks_all = tokenize(text)
        out: list[Sent] = []
        for a, b in sentence_spans(text):
            s = Sent(a, b, text[a:b])
            s.toks = [t for t in toks_all if t.start >= a and t.end <= b]
            ments = [Mention(m.start, m.end, m.text, m.entity, "alias", m.oblique) for m in mentions_all if m.start >= a and m.end <= b]
            # speaker label "Bertram: ..." occupies the sentence start; it stays a speaker (for "I", "my"), not a subject mention
            sp = re.match(r"\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*:\s", s.text)
            label_span = (a + sp.start(1), a + sp.end(1)) if sp else None
            if label_span:
                ments = [m for m in ments if not (m.start >= label_span[0] and m.end <= label_span[1])]
            taken: list[tuple[int, int]] = [(m.start, m.end) for m in ments]
            if label_span:
                taken.append(label_span)
            # gazetteer names (not lexicon subjects): candidate name values
            if self.gaz_rx is not None and self.params.use_names:
                for m in self.gaz_rx.finditer(s.text):
                    st, en = a + m.start(), a + m.end()
                    if any(st < e and en > x for x, e in taken):
                        continue
                    s.names.append(Val("name", {"kind": "name", "value": m.group()}, st, en, m.group()))
                    taken.append((st, en))
            # entity mentions are also name candidates (checked against subject later)
            if self.params.use_names:
                for m in ments:
                    v = Val("name", {"kind": "name", "value": m.text}, m.start, m.end, m.text)
                    v.tags.append("entity:" + m.entity)
                    s.names.append(v)
            # pronouns
            for tk in s.toks:
                low = tk.low
                if low in PRON_PERSON or low in PRON_THING or low in PRON_SPEAKER:
                    if low in PRON_SPEAKER:
                        if speaker:
                            ments.append(Mention(tk.start, tk.end, tk.text, speaker, "speaker"))
                        continue
                    want_person = low in PRON_PERSON
                    prev = [m for m in ments if m.via == "alias" and m.end <= tk.start
                            and ((m.entity in self.person_like) == want_person)]
                    if prev:
                        ments.append(Mention(tk.start, tk.end, tk.text, prev[-1].entity, "pronoun"))
            ments.sort(key=lambda m: m.start)
            s.mentions = ments
            # typed values
            vtaken = list(taken)
            local = s.text
            lt: list[tuple[int, int]] = [(x - a, e - a) for x, e in vtaken]
            self.vf.dead_dates(local, lt)
            vals = self.vf.dates(local, lt)
            vals += self.vf.versions(local, lt, [])
            vals += self.vf.money(local, lt)
            vals += self.vf.percent(local, lt)
            vals += self.vf.durations(local, lt)
            vals += self.vf.quantities(local, lt)
            vals += self.vf.versions(local, lt, [], late=True)
            for v in vals:
                v.start += a
                v.end += a
            vals.sort(key=lambda v: v.start)
            s.vals = vals
            out.append(s)
        return out

    # ------------------------------------------------------------------ context
    def features(self, s: Sent, v: Val, others: list[Val], skip: list[tuple[int, int]]) -> dict[str, float]:
        toks = s.toks
        idx_first = next((i for i, t in enumerate(toks) if t.end > v.start), len(toks))
        idx_last = next((i for i, t in enumerate(toks) if t.start >= v.end), len(toks))
        prev_end = max([o.end for o in others if o is not v and o.end <= v.start] or [s.start])
        next_start = min([o.start for o in others if o is not v and o.start >= v.end] or [s.end])
        feats: dict[str, float] = {}

        def ok_tok(t: Tok) -> bool:
            return not any(t.start < e and t.end > x for x, e in skip)

        # left walk
        d = 0
        i = idx_first - 1
        while i >= 0 and d < 8:
            t = toks[i]
            if t.end <= prev_end:
                break
            if t.text in HARD_DELIMS or t.text in CLAUSE_DELIMS or t.text == '"' or t.low in CONJ_STOP:
                break
            if ok_tok(t) and re.match(r"[A-Za-z]", t.text):
                d += 1
                w = 1.0 if d <= 2 else 0.8 if d <= 4 else 0.5
                for part in t.text.split("-"):
                    if part:
                        f = stem(part)
                        feats[f] = max(feats.get(f, 0), w)
            i -= 1
        # adjacent-left unigram / bigram (cue for names and verbs)
        left = [t for t in toks[:idx_first] if t.end > prev_end and ok_tok(t) and re.match(r"[A-Za-z]", t.text)]
        if left:
            feats["@l1:" + left[-1].low] = 1.0
            if len(left) > 1:
                feats["@lb:" + left[-2].low + "_" + left[-1].low] = 1.0
        # right walk
        d = 0
        i = idx_last
        while i < len(toks) and d < 6:
            t = toks[i]
            if t.start >= next_start:
                break
            if t.text in HARD_DELIMS or t.text in CLAUSE_DELIMS or t.text == '"' or t.low in CONJ_STOP:
                break
            if ok_tok(t) and re.match(r"[A-Za-z]", t.text):
                d += 1
                w = 1.0 if d <= 2 else 0.8 if d <= 4 else 0.5
                for part in t.text.split("-"):
                    if part:
                        f = stem(part)
                        feats[f] = max(feats.get(f, 0), w)
            i += 1
        if v.kind == "quantity":
            feats["@unit:" + v.value["unit"]] = 1.0
            feats[stem(v.value["unit"])] = 1.0
        elif v.kind == "money":
            feats["@per:" + v.value.get("per", "once")] = 1.0
        elif v.kind == "duration":
            feats["@dunit:" + v.value["unit"]] = 1.0
        elif v.kind == "name":
            ent = next((t[7:] for t in v.tags if t.startswith("entity:")), None)
            cls = ("person" if ent in self.person_like else "hooly") if ent else "other"
            feats["@nc:" + cls] = 1.0
            feats["@nv:" + v.surface.lower()] = 1.0
        elif v.kind == "version":
            feats["version"] = 1.0
            feats["@vt:" + ("prefixed" if "name-prefixed" in v.tags else "v" if re.match(r"(?i)v", v.surface) else "dotted")] = 1.0
        return feats

    def skip_spans(self, s: Sent) -> list[tuple[int, int]]:
        sp = [(m.start, m.end) for m in s.mentions if m.via == "alias"]
        sp += [(n.start, n.end) for n in s.names]
        return sp

    # ------------------------------------------------------------------ negation / temporal
    @staticmethod
    def clause_bounds(s: Sent, pos: int) -> tuple[int, int]:
        t = s.text
        rel = pos - s.start
        lo = 0
        for m in re.finditer(r"[,;:!?\u2022\u00b7|]", t[:rel]):
            lo = m.end()
        hi = len(t)
        m = re.search(r"[,;:!?\u2022\u00b7|]", t[rel:])
        if m:
            hi = rel + m.start()
        return s.start + lo, s.start + hi

    def negation_before(self, s: Sent, v: Val) -> tuple[int, int] | None:
        lo, _ = self.clause_bounds(s, v.start)
        seg = s.text[lo - s.start:v.start - s.start]
        seg = CMP_NEG_PHRASES.sub(lambda m: " " * len(m.group()), seg)
        m = None
        for m in NEG_RX.finditer(seg):
            pass
        if m:
            return lo + m.start(), lo + m.end()
        return None

    def temporal(self, s: Sent, positions: list[int]) -> str | None:
        seen: list[str] = []
        spans = {self.clause_bounds(s, p) for p in positions}
        for lo, hi in sorted(spans):
            for m in TEMPORAL_RX.finditer(s.text[lo - s.start:hi - s.start]):
                w = m.group()
                if w.lower() not in [x.lower() for x in seen]:
                    seen.append(w)
        return "; ".join(seen) if seen else None

    def sentence_negated(self, s: Sent) -> tuple[int, int] | None:
        t = CMP_NEG_PHRASES.sub(lambda m: " " * len(m.group()), s.text)
        m = NEG_RX.search(t)
        return (s.start + m.start(), s.start + m.end()) if m else None

    # ------------------------------------------------------------------ candidate resolution
    def subjects_for(self, s: Sent, v: Val) -> list[tuple[Mention, float]]:
        out: list[tuple[Mention, float]] = []
        best_by_ent: dict[str, tuple[Mention, float]] = {}
        for m in s.mentions:
            if v.kind == "name" and m.start <= v.start < m.end:
                continue
            if v.kind == "name" and any(t.startswith("entity:") and t[7:] == m.entity for t in v.tags) and m.via == "alias" and m.start == v.start:
                continue
            if "name-prefixed" in v.tags and not (v.start - 2 <= m.end <= v.start):
                continue                      # "Hooly Gemini 2.2": the number belongs to the name right before it
            if m.start >= v.end:
                pw = re.search(r"([A-Za-z]+)(?:\s+(?:the|a|an|our|its|their))?\s*$", s.text[:m.start - s.start])
                if pw and pw.group(1).lower() in {"with", "from", "by", "to", "than", "via", "as", "like", "against", "into",
                                                  "after", "before", "over", "on"} - {"on"} :
                    continue                  # "... with the Hooly Cloud roadmap": not the subject of the value before it
                prox = 0.25
            else:
                lo, _ = self.clause_bounds(s, v.start)
                same = m.start >= lo
                if self.params.bridge_apposition and not same and m.via == "alias" \
                        and not s.text[m.end - s.start:lo - s.start].strip(" ,"):
                    # "..., Hooly Workspace, costs €199": a name that ends the previous clause is the subject of this one
                    same = True
                ntok = sum(1 for t in s.toks if m.end <= t.start < v.start)
                prox = (0.9 if same else 0.45) / (1 + ntok / 8.0)
            if m.via == "pronoun":
                prox -= 0.1
            if m.oblique:
                prox *= 0.6
            prev = best_by_ent.get(m.entity)
            if prev is None or prox > prev[1]:
                best_by_ent[m.entity] = (m, prox)
        out = list(best_by_ent.values())
        return out

    def resolve(self, s: Sent, v: Val, others: list[Val]) -> dict:
        """Best (subject, attribute) for a value. Returns a decision dict."""
        skip = self.skip_spans(s)
        feats = self.features(s, v, others, skip)
        cands: list[dict] = []
        sig = value_sig(v.kind, v.value) if v.kind in ("quantity", "money") else None
        for m, prox in self.subjects_for(s, v):
            compat = []
            for attr in self.lex.attrs.get(m.entity, []):
                if self.model.attr_n.get(attr) and self.model.kind_share(attr, v.kind) > 0:
                    units = self.model.attr_units.get(attr)
                    if sig is None or not units or sig in units:
                        compat.append(attr)
            unique = len(compat) == 1
            for attr in self.lex.attrs.get(m.entity, []):
                total, lex, learned, kind_ok = self.model.score(attr, v.kind, feats)
                n = self.model.attr_n.get(attr, 0)
                notes = []
                if n and not kind_ok:
                    continue
                if not n and lex < 0.99:
                    continue
                if v.kind == "name":
                    cue = {k: w for k, w in feats.items() if not k.startswith(("@nv:", "@nc:"))}
                    if self.model.score(attr, v.kind, cue)[0] < self.params.name_min_cue:
                        continue
                if not n:
                    notes.append("attribute unseen in dev: lexical match only, kind unchecked")
                    total -= 0.3
                if n and sig is not None:
                    units = self.model.attr_units.get(attr)
                    if units and sig not in units and not (v.kind == "quantity" and stem(v.value["unit"]) in attr_tokens(attr)):
                        total -= self.params.unit_penalty
                        notes.append(f"{sig} not seen for attribute")
                if unique and attr == compat[0] and v.kind != "name":
                    total += self.params.unique_bonus
                    notes.append("only attribute of this subject with this value type")
                if v.unit_guess:
                    total -= 0.5
                    notes.append("counted noun not in known unit vocabulary")
                cands.append({"mention": m, "attr": attr, "attr_score": total, "lex": lex, "learned": learned,
                              "prox": prox, "total": total + self.params.prox_weight * prox, "notes": notes})
        cands.sort(key=lambda c: -c["total"])
        return {"feats": feats, "cands": cands}

    # ------------------------------------------------------------------ main
    def extract(self, row: dict) -> list[dict]:
        text, rid = row["text"], row["id"]
        sents = self.analyse(text)
        facts: list[dict] = []
        for s in sents:
            facts.extend(self.sentence_facts(row, s))
        for i, f in enumerate(facts):
            f["extraction_id"] = f"{rid}#openie#{i}"
        return facts

    def base_fact(self, row: dict) -> dict:
        return {"extraction_id": "", "source_row_id": row["id"], "source_label": row.get("label", ""),
                "source_publication_date": row["date"], "subject": None, "subject_surface": None, "attribute": None,
                "relation_surface": None, "value": None, "object_surface": None, "negated": False,
                "source_text_span": "", "span_start": 0, "span_end": 0, "fact_observation_date": None,
                "valid_from": None, "valid_to": None, "temporal_qualifier": None, "extraction_method": "openie",
                "extraction_confidence": 0.1, "parse_status": "unmapped", "verification_status": "candidate",
                "notes": ""}

    def relation_text(self, s: Sent, v: Val, feats_hit: list[str], subj: Mention | None) -> str | None:
        """Relation words as written: the words between subject and value (<=6), else the matched cue tokens."""
        if subj is not None and subj.end <= v.start:
            seg = s.text[subj.end - s.start:v.start - s.start]
            words = re.findall(r"[A-Za-z][A-Za-z'\u2019\-]*", seg)
            if 0 < len(words) <= 6:
                return " ".join(words)
        cue = [t.text for t in s.toks if stem(t.text) in feats_hit and t.start < v.start]
        return " ".join(cue[-4:]) if cue else None

    def sentence_facts(self, row: dict, s: Sent) -> list[dict]:
        text = row["text"]
        P = self.params
        facts: list[dict] = []
        value_vals = [v for v in s.vals]
        name_vals = [n for n in s.names]
        all_vals = sorted(value_vals + name_vals, key=lambda v: v.start)
        for v in all_vals:
            if v.cmp_op:
                continue                      # comparison words: no exact value, not emitted
            others = [o for o in all_vals if o.kind != "name"] if v.kind != "name" else [o for o in all_vals]
            dec = self.resolve(s, v, [o for o in all_vals if o is not v and not (o.kind == "name" and v.kind != "name")])
            fact = self.make_fact(row, s, v, dec)
            if fact is not None:
                facts.append(fact)
        if P.use_booleans:
            facts.extend(self.boolean_facts(row, s, facts))
        self.mark_multi(facts)
        self.attach_dates(row, s, facts, value_vals)
        return facts

    # ------------------------------------------------------------------ fact assembly
    def make_fact(self, row: dict, s: Sent, v: Val, dec: dict) -> dict | None:
        P = self.params
        cands = dec["cands"]
        f = self.base_fact(row)
        good = [c for c in cands if c["attr_score"] >= P.min_attr_score]
        neg = self.negation_before(s, v)
        if not good:
            # nothing mappable: report only readable typed values with a sentence subject for traceability
            if v.kind == "name":
                return None
            subj = next(iter(self.subjects_for(s, v)), (None,))[0] if s.mentions else None
            f["subject_surface"] = subj.text if subj else None
            f["object_surface"] = v.surface
            f["value"] = v.value if v.readable else None
            f["negated"] = neg is not None
            self.set_span(f, s, v, subj, neg)
            owners = None
            why = "no attribute of a sentence subject matches the context"
            if not s.mentions:
                why = "no entity named in the sentence"
            f["notes"] = f"unmapped: {why}" + ("; " + ",".join(v.flags) if v.flags else "")
            hint = self.attribute_hint(v, dec["feats"]) if v.kind != "name" and not (subj and good) else None
            if hint:
                f["notes"] += f"; hint_attr={hint[0]}; hint_owners={'|'.join(hint[1])}; hint_score={hint[2]:.2f}"
            f["extraction_confidence"] = 0.05
            f["temporal_qualifier"] = self.temporal(s, [v.start])
            return f
        best = good[0]
        subj: Mention = best["mention"]
        f["subject"] = subj.entity
        f["subject_surface"] = subj.text
        f["attribute"] = best["attr"]
        f["object_surface"] = v.surface
        f["negated"] = neg is not None
        notes = list(best["notes"])
        notes.append(f"score={best['attr_score']:.2f}(lex={best['lex']:.2f},learned={best['learned']:.2f}) prox={best['prox']:.2f}")
        if subj.via != "alias":
            notes.append(f"subject via {subj.via}")
        status = "complete"
        rivals = [c for c in cands if c is not best and c["total"] >= best["total"] - P.ambiguity_margin
                  and (c["mention"].entity, c["attr"]) != (subj.entity, best["attr"]) and c["attr_score"] >= P.min_attr_score]
        if rivals:
            status = "ambiguous"
            notes.append("rivals: " + ", ".join(f"{c['mention'].entity}/{c['attr']}({c['total']:.2f})" for c in rivals[:3]))
        if v.kind != "name":
            hint = self.attribute_hint(v, dec["feats"])
            if hint and hint[0] != best["attr"] and hint[2] >= best["attr_score"] + self.params.outside_margin \
                    and not any(m.entity in hint[1] for m in s.mentions):
                status = "ambiguous"
                notes.append(f"better-fitting attribute {hint[0]} ({hint[2]:.2f}) belongs to {'|'.join(hint[1][:3])}, not named here")
        if any("unseen" in n for n in best["notes"]):
            status = "partial" if status == "complete" else status
        if v.kind == "name":
            lex_ent = [t[7:] for t in v.tags if t.startswith("entity:")]
            if lex_ent and lex_ent[0] == subj.entity:
                return None
        value = v.value if v.readable else None
        if value is None:
            f["value"] = None
            status = "unmapped"
            notes.append("value not readable: " + ",".join(v.flags))
        else:
            f["value"] = value
        if neg is not None and value is not None:
            status = "partial" if status == "complete" else status
            notes.append("value follows a negation in its clause: referee reads nothing")
        f["parse_status"] = status
        self.set_span(f, s, v, subj, neg)
        f["relation_surface"] = self.relation_text(s, v, [], subj)
        f["temporal_qualifier"] = self.temporal(s, [v.start] + [subj.start])
        if v.qualifier and (f["temporal_qualifier"] is None or v.qualifier not in f["temporal_qualifier"].lower()):
            f["temporal_qualifier"] = (f["temporal_qualifier"] + "; " if f["temporal_qualifier"] else "") + v.qualifier
        conf = 0.25 + 0.11 * min(best["attr_score"], 4.0) + (0.08 if best["prox"] > 0.6 else 0)
        if subj.via != "alias":
            conf -= 0.12
        if status == "ambiguous":
            conf -= 0.15
        if status in ("partial", "unmapped"):
            conf -= 0.1
        f["extraction_confidence"] = round(max(0.05, min(0.95, conf)), 3)
        f["notes"] = "; ".join(notes)
        f["_key"] = (subj.entity, best["attr"])
        f["_val"] = v
        return f

    def attribute_hint(self, v: Val, feats: dict[str, float]) -> tuple[str, list[str], float] | None:
        """Subject not named in the sentence: best lexicon attribute by relation words alone, with its owners.
        Written to `notes` only. It is never used as the fact's subject or attribute."""
        sig = value_sig(v.kind, v.value) if v.kind in ("quantity", "money") else None
        best = None
        for attr, owners in self.attr_owner.items():
            n = self.model.attr_n.get(attr, 0)
            if not n or self.model.kind_share(attr, v.kind) <= 0:
                continue
            units = self.model.attr_units.get(attr)
            if sig is not None and units and sig not in units:
                continue
            total, lex, learned, _ = self.model.score(attr, v.kind, feats)
            if best is None or total > best[2]:
                best = (attr, owners, total)
        if best and best[2] >= self.params.hint_min_score:
            return best[0], list(best[1]), best[2]
        return None

    def set_span(self, f: dict, s: Sent, v: Val, subj: Mention | None, neg: tuple[int, int] | None) -> None:
        lo, hi = v.start, v.end
        if subj is not None and subj.via == "alias":
            lo, hi = min(lo, subj.start), max(hi, subj.end)
        if neg is not None:
            lo = min(lo, neg[0])
        text = s.text
        a, b = lo - s.start, hi - s.start
        while a < b and text[a] in " ,;:":
            a += 1
        while b > a and text[b - 1] in " ,;:":
            b -= 1
        f["span_start"], f["span_end"] = s.start + a, s.start + b
        f["source_text_span"] = text[a:b]

    def mark_multi(self, facts: list[dict]) -> None:
        groups: dict[tuple, list[dict]] = {}
        for f in facts:
            if f.get("_key") and f["value"] is not None:
                groups.setdefault(f["_key"], []).append(f)
        for key, fs in groups.items():
            vals = {repr(f["value"]) for f in fs}
            if len(vals) > 1:
                for f in fs:
                    if f["parse_status"] in ("complete", "partial"):
                        f["parse_status"] = "ambiguous"
                        f["notes"] += "; several different values for the same attribute in this sentence"
                        f["extraction_confidence"] = round(max(0.05, f["extraction_confidence"] - 0.15), 3)
            else:
                # identical duplicates (same value found twice): keep the first
                for f in fs[1:]:
                    f["_drop"] = True
        facts[:] = [f for f in facts if not f.get("_drop")]

    # ------------------------------------------------------------------ explicit event / validity dates
    def attach_dates(self, row: dict, s: Sent, facts: list[dict], value_vals: list[Val]) -> None:
        used = {id(f["_val"]) for f in facts if f.get("_val") is not None and f["value"] is not None
                and f["value"].get("kind") == "date" and f["parse_status"] != "unmapped"}
        for dv in value_vals:
            if dv.kind != "date" or id(dv) in used or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dv.value["value"]):
                continue
            before = s.text[max(0, dv.start - s.start - 12):dv.start - s.start].lower()
            kind = None
            if re.search(r"\b(?:as of|as at|on)\s*$", before):
                kind = "obs"
            elif re.search(r"\b(?:since|from)\s*$", before):
                kind = "from"
            elif re.search(r"\b(?:until|till)\s*$", before):
                kind = "to"
            if not kind:
                continue
            lo, hi = self.clause_bounds(s, dv.start)
            for f in facts:
                if f.get("_val") is None or f["value"] is None or f["parse_status"] == "unmapped":
                    continue
                if f["value"].get("kind") == "date":
                    continue
                flo, fhi = self.clause_bounds(s, f["_val"].start)
                if (flo, fhi) != (lo, hi) and not (kind == "obs" and dv.start < f["_val"].start and hi <= flo):
                    continue
                tq = re.search(r"(as of|as at|on|since|from|until|till)\s*$", before)
                if kind == "obs":
                    f["fact_observation_date"] = dv.value["value"]
                elif kind == "from":
                    f["valid_from"] = dv.value["value"]
                else:
                    f["valid_to"] = dv.value["value"]
                word = tq.group(1) if tq else kind
                if f["temporal_qualifier"] is None or word.lower() not in f["temporal_qualifier"].lower():
                    f["temporal_qualifier"] = (f["temporal_qualifier"] + "; " if f["temporal_qualifier"] else "") + word
                f["notes"] += f"; explicit date {dv.value['value']} read as {kind}"

    # ------------------------------------------------------------------ booleans
    def bool_feats(self, s: Sent) -> dict[str, float]:
        skip = self.skip_spans(s)
        feats: dict[str, float] = {}
        words: list[str] = []
        for t in s.toks:
            if re.match(r"[A-Za-z]", t.text) and not any(t.start < e and t.end > x for x, e in skip):
                for part in t.text.split("-"):          # "sign-on", "end-to-end" count as their words
                    if part:
                        feats[stem(part)] = 1.0
                        words.append(stem(part))
        for i in range(len(words) - 1):
            feats["@bg:" + words[i] + "_" + words[i + 1]] = 1.0
        return feats

    def boolean_facts(self, row: dict, s: Sent, done: list[dict]) -> list[dict]:
        P = self.params
        out: list[dict] = []
        if not s.mentions:
            return out
        feats = self.bool_feats(s)
        taken_keys = {f.get("_key") for f in done if f.get("_key") and f["value"] is not None
                      and f["parse_status"] in ("complete", "partial", "ambiguous")}
        seen_ents: dict[str, Mention] = {}
        for m in s.mentions:
            if m.entity not in seen_ents or m.via == "alias":
                seen_ents[m.entity] = m
        neg = self.sentence_negated(s)
        cands = []
        for ent, m in seen_ents.items():
            for attr in self.lex.attrs.get(ent, []):
                if self.model.kind_share(attr, "boolean") < 0.5:
                    continue
                if (ent, attr) in taken_keys:
                    continue
                matched = {t for t in attr_tokens(attr) if t in feats}
                if any(k[0] == ent and matched & set(attr_tokens(k[1])) for k in taken_keys):
                    continue                  # these words already carry a valued fact ("7 seats" is not a seat yes/no)
                total, lex, learned, _ = self.model.score(attr, "boolean", feats, only_prefix="@bg:")
                if total >= P.bool_min_score and (lex >= P.bool_min_lex or (lex >= 0.4 and learned >= P.bool_alt_learned)):
                    cands.append({"ent": ent, "m": m, "attr": attr, "total": total, "lex": lex, "learned": learned})
        cands.sort(key=lambda c: -c["total"])
        used_attrs: set[str] = set()
        for c in cands:
            if c["attr"] in used_attrs:
                continue
            rivals = [r for r in cands if r is not c and r["total"] >= c["total"] - P.ambiguity_margin and r["attr"] != c["attr"]]
            f = self.base_fact(row)
            m = c["m"]
            f.update({"subject": c["ent"], "subject_surface": m.text, "attribute": c["attr"],
                      "value": {"kind": "boolean", "value": neg is None}, "negated": neg is not None,
                      "object_surface": None})
            lo, hi = s.start, s.end
            # trim the span to the clause around the subject mention
            clo, chi = self.clause_bounds(s, m.start)
            lo, hi = clo, chi
            if neg is not None:
                lo, hi = min(lo, neg[0]), max(hi, neg[1])
            a, b = lo - s.start, hi - s.start
            seg = s.text
            while a < b and seg[a] in " ,;:":
                a += 1
            while b > a and seg[b - 1] in " ,;:":
                b -= 1
            f["span_start"], f["span_end"] = s.start + a, s.start + b
            f["source_text_span"] = seg[a:b]
            f["parse_status"] = "ambiguous" if rivals else "complete"
            f["relation_surface"] = None
            f["temporal_qualifier"] = self.temporal(s, [m.start])
            f["extraction_confidence"] = round(max(0.05, min(0.9, 0.2 + 0.1 * min(c["total"], 5) - (0.15 if rivals else 0))), 3)
            f["notes"] = (f"boolean: polarity from sentence negation; score={c['total']:.2f}(lex={c['lex']:.2f},learned={c['learned']:.2f})"
                          + ("; rivals: " + ",".join(f"{r['ent']}/{r['attr']}" for r in rivals[:3]) if rivals else ""))
            f["_key"] = (c["ent"], c["attr"])
            f["_val"] = None
            used_attrs.add(c["attr"])
            out.append(f)
        return out

