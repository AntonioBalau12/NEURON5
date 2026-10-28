"""Baseline text feature pipeline for Classical ML."""

from __future__ import annotations

import re
from typing import Sequence
import numpy as np
from scipy.sparse import csr_matrix, hstack
from sklearn.feature_extraction.text import TfidfVectorizer


class TextBaselinePipeline:
    """Extracts word TF-IDF, character TF-IDF, and surface text features."""

    def __init__(self, max_word_features: int = 1000, max_char_features: int = 1000):
        self.max_word_features = max_word_features
        self.max_char_features = max_char_features
        self.word_vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=max_word_features,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self.char_vectorizer = TfidfVectorizer(
            ngram_range=(3, 5),
            analyzer="char",
            max_features=max_char_features,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self.surface_feature_names = (
            "char_count",
            "word_count",
            "digit_count",
            "upper_count",
            "punct_count",
            "has_question",
            "has_exclamation",
        )

    def _extract_surface(self, texts: Sequence[str]) -> np.ndarray:
        feats = np.zeros((len(texts), len(self.surface_feature_names)), dtype=float)
        for i, text in enumerate(texts):
            s = text or ""
            feats[i, 0] = float(len(s))
            feats[i, 1] = float(len(s.split()))
            feats[i, 2] = float(sum(c.isdigit() for c in s))
            feats[i, 3] = float(sum(c.isupper() for c in s))
            feats[i, 4] = float(sum(not c.isalnum() and not c.isspace() for c in s))
            feats[i, 5] = 1.0 if "?" in s else 0.0
            feats[i, 6] = 1.0 if "!" in s else 0.0
        return feats

    def fit(self, texts: Sequence[str]) -> TextBaselinePipeline:
        self.word_vectorizer.fit(texts)
        self.char_vectorizer.fit(texts)
        return self

    def transform(self, texts: Sequence[str]) -> csr_matrix:
        w_mat = self.word_vectorizer.transform(texts)
        c_mat = self.char_vectorizer.transform(texts)
        s_mat = csr_matrix(self._extract_surface(texts))
        return hstack([w_mat, c_mat, s_mat], format="csr")

    def fit_transform(self, texts: Sequence[str]) -> csr_matrix:
        return self.fit(texts).transform(texts)

