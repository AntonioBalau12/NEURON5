"""Tokenisation, stemming and window helpers (stdlib only)."""
from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\u2019]*(?:-[A-Za-z]+)*|\d[\d,.]*\d|\d|[^\sA-Za-z\d]")
HARD_DELIMS = {",", ";", ".", "!", "?", "\u2022", "\u00b7", "|", "(", ")"}
CONJ_WORDS = {"and", "but", "while", "whereas", "which", "where", "though", "although", "so", "because", "then", "yet"}
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "by", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those", "as", "from", "into", "than", "also", "up", "has", "have",
    "had", "will", "can", "now", "our", "we", "us", "their", "his", "her", "he", "she", "they", "them", "i",
}


@dataclass(frozen=True)
class Tok:
    text: str
    start: int
    end: int

    @property
    def low(self) -> str:
        return self.text.lower()


def tokenize(text: str) -> list[Tok]:
    return [Tok(m.group(), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


_IRREG = {"people": "person", "men": "man", "women": "woman", "children": "child", "was": "be", "were": "be",
          "is": "be", "are": "be", "has": "have", "does": "do", "did": "do", "gets": "get", "went": "go"}


def stem(word: str) -> str:
    """Very small suffix stemmer. Deterministic, good enough for the closed vocabulary here."""
    w = word.lower().replace("\u2019", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if w in _IRREG:
        return _IRREG[w]
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("sses"):
        return w[:-2]
    if w.endswith("ing") and len(w) > 5:
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2]:
            w = w[:-1]
        return w
    if w.endswith("ed") and len(w) > 4:
        w = w[:-2]
        if len(w) > 2 and w[-1] == w[-2]:
            w = w[:-1]
        return w
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if w.endswith("ion") and len(w) > 6:
        w = w[:-3]
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def singular_noun(word: str) -> str:
    w = word.lower()
    if w in {"people"}:
        return "person"
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Sentence offsets following the referee's rule: end at . ! ? before a space, or at a blank line.

    Abbreviation points (e.g., Inc., vs., No. 5, single initials) do not end a sentence.
    """
    abbrevs = ("e.g", "i.e", "vs", "approx", "inc", "ltd", "co", "corp", "dr", "mr", "mrs", "ms", "prof", "st", "no")
    spans: list[tuple[int, int]] = []
    start = 0
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        end_here = False
        if ch in ".!?" and (i + 1 >= n or text[i + 1].isspace()):
            if ch == ".":
                word_m = re.search(r"([A-Za-z.]+)$", text[max(0, i - 12):i])
                word = word_m.group(1).lower() if word_m else ""
                if word == "no":
                    end_here = not re.match(r"\s*\d", text[i + 1:i + 4])
                elif word in abbrevs or (len(word) == 1 and word.isalpha()):
                    end_here = False
                else:
                    end_here = True
            else:
                end_here = True
            # include trailing closing quotes
            if end_here:
                j = i + 1
                while j < n and text[j] in "\"'\u201d\u2019)":
                    j += 1
                spans.append((start, j))
                k = j
                while k < n and text[k].isspace():
                    k += 1
                start = k
                i = k
                continue
        elif ch == "\n" and i + 1 < n and text[i + 1] == "\n":
            if text[start:i].strip():
                spans.append((start, i))
            k = i
            while k < n and text[k].isspace():
                k += 1
            start = k
            i = k
            continue
        i += 1
    if start < n and text[start:].strip():
        spans.append((start, n))
    return [(a, b) for a, b in spans if text[a:b].strip()]


WORD_NUMBERS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
