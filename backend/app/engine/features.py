"""Inference feature transform copied from the classical model, commit 8400bbc."""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix, hstack

LABELS = ["false", "true", "unsure"]


def metadata_matrix(rows: list[dict[str, str]], builder: dict[str, Any]) -> csr_matrix:
    names = [(e.get("name", ""), e.get("aliases", [])) for e in builder["subjects"]]
    attrs = builder["attribute_terms"]
    cues = builder["cues"]
    date_base = dt.date.fromisoformat(builder["date_base"])
    numeric = []
    for row in rows:
        text = row["text"]
        lo = text.casefold()
        tokens = re.findall(r"\b\w+\b", lo)
        d = dt.date.fromisoformat(row["date"])
        daynum = (d - date_base).days
        entity_flags = [
            float(
                any(
                    re.search(r"(?<!\w)" + re.escape(n.casefold()) + r"(?!\w)", lo)
                    for n in (name, *aliases)
                )
            )
            for name, aliases in names
        ]
        a_flags = [float(term in tokens) for term in attrs]
        cue_flags = [float(cue in lo) for cue in cues]
        nums = re.findall(r"(?<!\w)\d+(?:[.,]\d+)?%?", text)
        feats = [
            len(tokens),
            len(text),
            sum(c.isupper() for c in text) / max(1, len(text)),
            sum(c.isdigit() for c in text),
            len(nums),
            len(set(nums)),
            lo.count("!"),
            lo.count("?"),
            lo.count(","),
            float("'" in text),
            math.copysign(math.log1p(abs(daynum)), daynum),
            d.year,
            d.month,
            d.day,
            d.weekday(),
            d.timetuple().tm_yday,
            math.sin(2 * math.pi * d.month / 12),
            math.cos(2 * math.pi * d.month / 12),
            float(bool(re.search(r"\b20\d{2}\b", text))),
            sum(float(c in lo) for c in builder["currencies"]),
            sum(float(mo in lo.split()) for mo in builder["month_words"]),
            lo.count("and"),
            lo.count("or"),
            lo.count("but"),
            lo.count(";"),
            lo.count(":"),
            sum(float(x in tokens) for x in ["at", "on", "during", "event", "launch", "summit"]),
        ]
        numeric.append(entity_flags + a_flags + cue_flags + feats)
    return csr_matrix(np.asarray(numeric, dtype=np.float32))


def transform_features(
    rows: list[dict[str, str]], builder: dict[str, Any]
) -> tuple[Any, csr_matrix]:
    texts = [row["text"] for row in rows]
    word_features = builder["word_vectorizer"].transform(texts)
    char_features = builder["char_vectorizer"].transform(texts)
    meta = metadata_matrix(rows, builder)
    return hstack(
        [word_features, char_features, meta], format="csr", dtype=np.float32
    ), char_features
