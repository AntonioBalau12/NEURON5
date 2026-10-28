"""Lexicon-driven entity mention detection (aliases, speaker labels, same-sentence pronouns)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

PREPS = {"at", "from", "for", "of", "with", "by", "to", "in", "on", "as", "about", "against", "than", "via", "inside",
         "around", "near", "like", "after", "before", "into", "within", "among", "across", "behind", "beside"}


@dataclass
class Lexicon:
    names: list[str]
    aliases: dict[str, list[str]]
    attrs: dict[str, list[str]]
    events: set[str]
    attr_owners: dict[str, list[str]] = field(default_factory=dict)  # attribute -> subjects having it

    @staticmethod
    def load(path: str | Path) -> "Lexicon":
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        names, aliases, attrs = [], {}, {}
        owners: dict[str, list[str]] = {}
        for s in raw["subjects"]:
            names.append(s["name"])
            aliases[s["name"]] = list(s.get("aliases", []))
            attrs[s["name"]] = list(s.get("attributes", []))
            for a in attrs[s["name"]]:
                owners.setdefault(a, []).append(s["name"])
        return Lexicon(names, aliases, attrs, set(raw.get("events", [])), owners)


@dataclass
class EntityMention:
    start: int
    end: int
    text: str
    entity: str
    oblique: bool = False      # preceded by a preposition (at Hooly, from Nimbus ...)
    via: str = "alias"          # alias | pronoun | speaker | first_person
    possessive_owner: bool = False  # "Hooly Cloud's reliability team"


def _flex(surface: str) -> str:
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", surface.strip()) if p]
    pat = r"[\s\-]+".join(parts)
    return pat.replace("\\'", "['\u2019]").replace("'", "['\u2019]")


class EntityFinder:
    def __init__(self, lex: Lexicon):
        self.lex = lex
        self.surface_to_entity: dict[str, str] = {}
        for name in lex.names:
            for s in [name] + lex.aliases[name]:
                self.surface_to_entity.setdefault(re.sub(r"[\s\-]+", " ", s.lower()), name)
        surfaces = sorted({s for s in self.surface_to_entity}, key=lambda s: (-len(s), s))
        alts = [_flex(s) for s in surfaces]
        self.rx = re.compile(r"(?<![\w])(?:" + "|".join(alts) + r")(?![\w]|\.\d)", re.I)
        # person labels for dialogue ("Bertram: ...")
        self.first_names: dict[str, str] = {}
        counts: dict[str, list[str]] = {}
        for n in lex.names:
            toks = n.split()
            if len(toks) == 2 and "Hooly" not in toks:
                counts.setdefault(toks[0].lower(), []).append(n)
        for k, v in counts.items():
            if len(v) == 1:
                self.first_names[k] = v[0]

    def find(self, text: str) -> list[EntityMention]:
        out: list[EntityMention] = []
        for m in self.rx.finditer(text):
            raw = m.group()
            key = re.sub(r"[\s\-]+", " ", raw.lower().replace("\u2019", "'"))
            start, end = m.start(), m.end()
            entity = self.surface_to_entity.get(key)
            if entity is None:
                continue
            # single-word aliases must be written capitalised (Search, Maps, Photos ...) to avoid common nouns
            if " " not in key and key not in {"outage"} and not raw[:1].isupper():
                continue
            if key == "outage" and not re.search(r"(?i)\bthe\s+$", text[max(0, start - 5):start]):
                continue
            prev = re.search(r"([A-Za-z]+)\s*$", text[max(0, start - 12):start])
            oblique = bool(prev and prev.group(1).lower() in PREPS)
            poss = bool(re.match(r"['\u2019]s\b", text[end:end + 3]))
            out.append(EntityMention(start, end, raw, entity, oblique, "alias", poss))
        out.sort(key=lambda e: e.start)
        return out

    def speaker(self, text: str) -> str | None:
        m = re.match(r"\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*:\s", text)
        if not m:
            return None
        label = m.group(1)
        key = re.sub(r"\s+", " ", label.lower())
        if key in self.surface_to_entity:
            return self.surface_to_entity[key]
        return self.first_names.get(key)
