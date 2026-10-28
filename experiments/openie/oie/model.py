"""Dev-learned relation->attribute table and the scorer that uses it.

The model only stores counts: for every attribute, the context stems (and unit / currency period features) that
co-occurred with its value in the dev rows, plus the value kinds and counted-noun units the attribute takes.
Nothing here reads the gold `form` at extraction time; training happens in tools/learn.py and is saved as
data/relation_table.json.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .textutil import STOPWORDS, stem

ATTR_STOP = {"of", "the", "in", "by", "as", "per", "is", "a", "an", "to", "at", "this"}


def value_sig(kind: str, value: dict) -> str | None:
    """Type signature below the kind: counted noun / physical unit for quantities, billing period for money."""
    if kind == "quantity":
        return value["unit"]
    if kind == "money":
        return "per:" + value.get("per", "once")
    return None


def attr_tokens(attr: str) -> list[str]:
    return [stem(t) for t in attr.split("_") if t and t not in ATTR_STOP]


class Model:
    def __init__(self) -> None:
        self.attr_kinds: dict[str, Counter] = defaultdict(Counter)
        self.attr_units: dict[str, Counter] = defaultdict(Counter)
        self.attr_prof: dict[str, Counter] = defaultdict(Counter)
        self.attr_n: Counter = Counter()
        self.units: set[str] = set()
        self.names: set[str] = set()
        self.df: Counter = Counter()          # stem -> number of attributes whose profile holds it
        self.n_attr = 1
        self.shrink = 0.5
        self.strict_partial = False

    # ------------------------------------------------------------------ training
    def add(self, attr: str, kind: str, unit: str | None, feats: set[str]) -> None:
        self.attr_kinds[attr][kind] += 1
        if unit:
            self.attr_units[attr][unit] += 1
        self.attr_n[attr] += 1
        for f in feats:
            self.attr_prof[attr][f] += 1

    def finalize(self) -> None:
        self.df = Counter()
        for prof in self.attr_prof.values():
            for f in prof:
                self.df[f] += 1
        self.n_attr = max(1, len(self.attr_prof))

    # ------------------------------------------------------------------ persistence
    def to_json(self) -> dict:
        return {"attr_kinds": {k: dict(v) for k, v in self.attr_kinds.items()},
                "attr_units": {k: dict(v) for k, v in self.attr_units.items()},
                "attr_prof": {k: dict(v) for k, v in self.attr_prof.items()},
                "attr_n": dict(self.attr_n), "units": sorted(self.units), "names": sorted(self.names)}

    @staticmethod
    def from_json(raw: dict) -> "Model":
        m = Model()
        for k, v in raw["attr_kinds"].items():
            m.attr_kinds[k] = Counter(v)
        for k, v in raw["attr_units"].items():
            m.attr_units[k] = Counter(v)
        for k, v in raw["attr_prof"].items():
            m.attr_prof[k] = Counter(v)
        m.attr_n = Counter(raw["attr_n"])
        m.units = set(raw["units"])
        m.names = set(raw["names"])
        m.finalize()
        return m

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")

    @staticmethod
    def load(path: str | Path) -> "Model":
        return Model.from_json(json.loads(Path(path).read_text(encoding="utf-8")))

    # ------------------------------------------------------------------ scoring
    def idf(self, feat: str) -> float:
        return math.log(1 + self.n_attr / (1 + self.df.get(feat, 0))) / math.log(1 + self.n_attr)

    def score(self, attr: str, kind: str, feats: dict[str, float],
              only_prefix: str | None = None) -> tuple[float, float, float, bool]:
        """Returns (total, lexical, learned, kind_ok). feats maps feature -> proximity weight.
        only_prefix restricts the learned part to features starting with that prefix (booleans use '@bg:')."""
        toks = attr_tokens(attr)
        lex = 0.0
        if toks:
            hit = sum(feats.get(t, 0.0) for t in toks)
            n_hit = sum(1 for t in toks if feats.get(t, 0.0) > 0)
            if self.strict_partial and n_hit == 1 and len(toks) > 1 and not (len(toks) == 2 and feats.get(toks[-1], 0.0) > 0):
                hit = 0.0          # one word of a long attribute name is not evidence for it
            lex = hit / len(toks)
            if lex >= 0.99:
                lex += 0.35
            elif len(toks) > 1 and hit >= 1.0:
                lex += 0.1
        n = self.attr_n.get(attr, 0)
        learned = 0.0
        kinds = self.attr_kinds.get(attr)
        kind_ok = True
        if n:
            kind_share = kinds.get(kind, 0) / n
            kind_ok = kind_share > 0
            prof = self.attr_prof[attr]
            for f, w in feats.items():
                if only_prefix is not None and not f.startswith(only_prefix):
                    continue
                c = prof.get(f)
                if c:
                    learned += w * (c / (n + self.shrink)) * self.idf(f)
            learned *= 1.0
            # unit feature carries extra weight (a counted noun that matches the attribute's recorded units)
        return 2.0 * lex + 2.0 * learned, lex, learned, kind_ok

    def kind_share(self, attr: str, kind: str) -> float:
        n = self.attr_n.get(attr, 0)
        return self.attr_kinds[attr].get(kind, 0) / n if n else 0.0
