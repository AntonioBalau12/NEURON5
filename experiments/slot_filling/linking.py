"""Lexicon entity linking and sentence splitting (no gold forms involved)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ABBREVIATIONS = ("e.g.", "i.e.", "vs.", "approx.", "inc.", "ltd.", "co.", "corp.", "dr.", "mr.", "mrs.", "ms.", "prof.", "st.")


@dataclass
class Subject:
    name: str
    aliases: list
    attributes: list


class Lexicon:
    def __init__(self, path: str | Path):
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        self.subjects = {s["name"]: Subject(s["name"], list(s.get("aliases") or []), list(s.get("attributes") or []))
                         for s in raw["subjects"]}
        self.events = list(raw.get("events") or [])
        self.attr_subjects: dict[str, list[str]] = {}
        for s in self.subjects.values():
            for a in s.attributes:
                self.attr_subjects.setdefault(a, []).append(s.name)
        spellings = []
        for s in self.subjects.values():
            for sp in [s.name, *s.aliases]:
                spellings.append((sp, s.name))
        spellings.sort(key=lambda x: -len(x[0]))
        self._patterns = []
        for sp, name in spellings:
            words = [w for w in re.split(r"[\s-]+", sp.strip()) if w]
            body = r"[\s-]*".join(re.escape(w) for w in words)
            # "Hooly's Q3 results" style aliases keep their apostrophe; a trailing possessive is tolerated
            self._patterns.append((re.compile(r"(?<![\w])" + body + r"(?![\w])(?!\.\d)(?!,\d)", re.I), name, sp))

    def mentions(self, text: str):
        """Longest-match, non-overlapping entity mentions: list of (start, end, canonical, surface, registered_spelling)."""
        found = []
        taken = []
        for rx, name, sp in self._patterns:
            for m in rx.finditer(text):
                a, b = m.span()
                if any(a < y and x < b for x, y in taken):
                    continue
                taken.append((a, b))
                found.append((a, b, name, m.group(), sp))
        found.sort()
        return found


def split_sentences(text: str):
    """Sentence spans per value-forms.md: '.', '!' or '?' before a space, or a blank line; abbreviations end nothing."""
    spans = []
    start = 0
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        end_here = False
        if ch in ".!?" and (i + 1 == n or text[i + 1].isspace()):
            low = text[max(0, i - 6):i + 1].lower()
            if ch == "." and (any(low.endswith(a) for a in ABBREVIATIONS)
                              or re.search(r"(?<![A-Za-z])[A-Z]\.$", text[max(0, i - 2):i + 1])
                              or re.search(r"\bNo\.$", text[max(0, i - 3):i + 1])):
                end_here = False
            else:
                end_here = True
        elif ch == "\n" and text[i:i + 3].strip(" \t") == "\n\n" or re.match(r"\n\s*\n", text[i:i + 8] or ""):
            end_here = True
        if end_here:
            e = i + 1
            if text[start:e].strip():
                spans.append((start, e))
            start = e
            while start < n and text[start].isspace():
                start += 1
            i = start
            continue
        i += 1
    if text[start:].strip():
        spans.append((start, n))
    return spans

