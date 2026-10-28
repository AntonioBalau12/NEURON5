"""BM25 evidence indexing and retrieval over temporal graph evidence."""

from __future__ import annotations

import collections.abc
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from foundation import AtomicFact, Lexicon, normalize_date
from core.graph.models import EvidenceState, GraphEvidence, TemporalKnowledgeGraph

# Conservative stopwords - strictly excluding negations, numbers, and dates
STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "on", "with",
    "as", "by", "at", "this", "that", "these", "those", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "it", "its", "from",
    "which", "who", "whom", "what", "where", "when", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "than", "too",
    "very", "said", "says", "also", "into", "their", "there", "about",
})

# Negation words must be explicitly preserved
NEGATIONS = frozenset({
    "not", "no", "never", "without", "none", "neither", "nor",
    "isn't", "aren't", "wasn't", "weren't", "doesn't", "didn't",
    "hasn't", "haven't", "hadn't", "cannot", "can't", "won't",
    "wouldn't", "shouldn't", "couldn't", "untrue", "false",
})

# Months mapping for full and abbreviated English names
MONTHS: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

# Currency symbols and codes
CURRENCY_MAP: dict[str, str] = {
    "€": "eur", "$": "usd", "us$": "usd", "£": "gbp", "chf": "chf",
    "eur": "eur", "usd": "usd", "gbp": "gbp", "ron": "ron", "lei": "ron",
    "euro": "eur", "euros": "eur", "dollar": "usd", "dollars": "usd",
    "pound": "gbp", "pounds": "gbp", "czk": "czk", "pln": "pln",
    "huf": "huf", "sek": "sek", "nok": "nok", "dkk": "dkk", "jpy": "jpy",
}

# Conservative domain synonym expansion mapping to canonical attributes
ATTRIBUTE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "joined": (
        "joined", "started at", "started working at", "started working", "began working at",
        "began working", "hired by", "hired at", "arrived at", "joined hooly",
    ),
    "previous_employer": (
        "previous employer", "before hooly", "worked at", "arrived from",
        "formerly at", "prior employer",
    ),
    "team_size": (
        "crew", "team size", "engineers", "staff", "headcount", "team of",
    ),
    "reliability_lead": (
        "reliability lead", "reliability team", "incident response",
        "runs reliability", "answers to holdan", "reliability",
    ),
    "price": (
        "price", "pricing", "cost", "fee", "subscription", "per month",
        "monthly price", "annual price",
    ),
    "customers": (
        "customers", "subscribers", "clients", "paying customers",
        "active users", "paying accounts",
    ),
    "annual_recurring_revenue": (
        "arr", "annual recurring revenue", "recurring revenue", "annual revenue",
    ),
    "uptime_sla": (
        "uptime sla", "uptime promise", "uptime commitment", "sla", "uptime",
    ),
    "regions": (
        "regions", "data centers", "zones", "cloud regions",
    ),
    "storage": (
        "storage", "capacity", "disk", "gb", "mb", "tb",
    ),
    "founded": (
        "founded", "started in", "created in", "launched in", "established",
    ),
    "headquarters": (
        "headquarters", "based in", "located in", "hq", "main office",
    ),
    "soc2_certified": (
        "soc2", "soc 2", "soc2 certified", "soc-2", "security certification",
    ),
    "had_major_outage": (
        "outage", "major outage", "downtime", "incident", "down",
    ),
}


def _clean_number_string(raw: str) -> str:
    """Normalize numeric strings handling grouped thousands vs decimal commas."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", raw):
        return raw.replace(",", "")
    if "," in raw and "." not in raw:
        return raw.replace(",", ".")
    if "," in raw and "." in raw:
        return raw.replace(",", "")
    return raw


def _extract_dates(text: str) -> list[str]:
    """Extract and normalize all dates to ISO format and components."""
    dates: list[str] = []
    month_pattern = "|".join(MONTHS.keys())
    # Natural language: "12 January 2026", "12th January 2026", "12th of January 2026"
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(" + month_pattern + r")\s+(\d{4})\b", text, re.I):
        d, mth, y = m.group(1), m.group(2).casefold(), m.group(3)
        dates.append(f"{y}-{MONTHS[mth]}-{int(d):02d}")
    # Natural language: "January 12, 2026", "January 12 2026"
    for m in re.finditer(r"\b(" + month_pattern + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", text, re.I):
        mth, d, y = m.group(1).casefold(), m.group(2), m.group(3)
        dates.append(f"{y}-{MONTHS[mth]}-{int(d):02d}")
    # Month + year: "January 2026" (ensuring it is not preceded by a day number)
    for m in re.finditer(r"(?<!\d\s)(?<!\d{2}\s)\b(" + month_pattern + r")\s+(\d{4})\b", text, re.I):
        mth, y = m.group(1).casefold(), m.group(2)
        dates.append(f"{y}-{MONTHS[mth]}")
    # ISO dates: "2026-01-12", "2026-01"
    for m in re.finditer(r"\b(\d{4})-(\d{2})(?:-(\d{2}))?\b", text):
        dates.append(m.group(0))
    return list(dict.fromkeys(dates))


def _extract_numbers_and_currencies(text: str) -> list[str]:
    """Preserve numbers, percentages, and currencies."""
    tokens: list[str] = []
    # 1. Currency symbols/codes attached before numbers, e.g., €20, $49.99, £50,000, EUR 100
    for m in re.finditer(r"(€|\$|£|US\$|\bEUR\b|\bUSD\b|\bGBP\b|\bCHF\b|\bRON\b)\s*(\d+(?:[.,]\d+)*)", text, re.I):
        sym = m.group(1).casefold()
        num = _clean_number_string(m.group(2))
        cur = CURRENCY_MAP.get(sym, sym)
        tokens.extend([f"cur:{cur}", f"num:{num}", f"money:{cur}:{num}"])
    # 2. Currency symbols/words following numbers, e.g., 20 euros, 50,000 EUR, 100 dollars
    for m in re.finditer(r"\b(\d+(?:[.,]\d+)*)\s*(€|\$|£|US\$|eur|euro|euros|usd|dollar|dollars|gbp|pound|pounds|ron|lei|chf)\b", text, re.I):
        num = _clean_number_string(m.group(1))
        sym = m.group(2).casefold()
        cur = CURRENCY_MAP.get(sym, sym)
        tokens.extend([f"cur:{cur}", f"num:{num}", f"money:{cur}:{num}"])
    # 3. Standalone numbers, grouped thousands, percentages
    for m in re.finditer(r"\b(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s*(%|percent\b)?", text, re.I):
        raw_int = m.group(1).replace(",", "")
        decimal = m.group(2)
        is_pct = bool(m.group(3))
        num_str = f"{raw_int}.{decimal}" if decimal else raw_int
        tokens.append(f"num:{num_str}")
        tokens.append(num_str)
        if is_pct:
            tokens.extend([f"pct:{num_str}", "percent", "%"])
    # 4. Currency words
    for word in re.findall(r"\b[A-Za-z]+\b", text):
        lower = word.casefold()
        if lower in CURRENCY_MAP:
            tokens.append(f"cur:{CURRENCY_MAP[lower]}")
    return tokens


def tokenize_evidence_text(
    text: str,
    lexicon: Lexicon | None = None,
    observed_date: date | None = None,
    include_attribute_synonyms: bool = True,
) -> list[str]:
    """Deterministic tokenization preserving numbers, dates, negations, currencies, and entities."""
    if not text or not isinstance(text, str):
        return []
    tokens: list[str] = []
    text_lower = text.casefold()

    # 1. Dates
    found_dates = _extract_dates(text)
    if observed_date:
        found_dates.append(observed_date.isoformat())
    for d in dict.fromkeys(found_dates):
        tokens.append(f"date:{d}")
        parts = d.split("-")
        tokens.append(parts[0])  # Year
        tokens.append(f"year:{parts[0]}")
        if len(parts) >= 2:
            tokens.append(parts[1])  # Month
            tokens.append(f"date:{parts[0]}-{parts[1]}")
        if len(parts) == 3:
            day_str = parts[2]
            day_int = str(int(parts[2]))
            tokens.append(day_str)
            if day_int != day_str:
                tokens.append(day_int)

    # 2. Numbers and currencies
    tokens.extend(_extract_numbers_and_currencies(text))

    # 3. Negations
    for neg in NEGATIONS:
        if re.search(r"\b" + re.escape(neg) + r"\b", text_lower):
            tokens.extend([f"neg:{neg}", neg])

    # 4. Entity alias canonicalization
    if lexicon is not None:
        for entity in lexicon.entities:
            # Check canonical name and all aliases
            for name in (entity.name, *entity.aliases):
                pattern = r"\b" + r"\s+".join(re.escape(w) for w in name.casefold().split()) + r"\b"
                if re.search(pattern, text_lower):
                    norm = Lexicon.normalize_name(entity.name)
                    tokens.append(f"entity:{norm}")
                    tokens.extend(entity.name.casefold().split())
                    break

    # 5. Conservative attribute synonym expansion
    if include_attribute_synonyms:
        for attr, synonyms in ATTRIBUTE_SYNONYMS.items():
            for syn in synonyms:
                pattern = r"\b" + r"\s+".join(re.escape(w) for w in syn.split()) + r"\b"
                if re.search(pattern, text_lower):
                    tokens.append(f"attr:{attr}")
                    break

    # 6. General word tokens (excluding stopwords unless they are negations)
    words = re.findall(r"\b[A-Za-z0-9_'-]+\b", text_lower)
    for word in words:
        clean = word.strip("'-")
        if not clean:
            continue
        if clean in NEGATIONS:
            tokens.append(clean)
        elif clean not in STOPWORDS and len(clean) > 1:
            tokens.append(clean)

    return tokens


@dataclass(frozen=True)
class IndexedDocument:
    """Document stored in BM25 index with preserved metadata and provenance."""
    evidence_id: str
    text: str
    source_date: date | None
    evidence_status: EvidenceState
    entities: tuple[str, ...]
    attributes: tuple[str, ...]
    facts: tuple[AtomicFact, ...]
    provenance: str
    tokens: tuple[str, ...]
    token_count: int
    raw_record: Any = None


@dataclass(frozen=True)
class RetrievedEvidence(collections.abc.Mapping):
    """Standardized retrieval result matching NEURON5 API conventions."""
    evidence_id: str
    bm25_score: float
    source_date: date | None
    verification_status: EvidenceState
    retrieval_method: str  # "bm25", "graph", "hybrid"
    text: str = ""
    entities: tuple[str, ...] = ()
    attributes: tuple[str, ...] = ()
    facts: tuple[AtomicFact, ...] = ()
    provenance: str = ""
    graph_score: float = 0.0
    combined_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "bm25_score": round(self.bm25_score, 4),
            "source_date": self.source_date.isoformat() if self.source_date else None,
            "verification_status": (
                self.verification_status.value
                if isinstance(self.verification_status, EvidenceState)
                else str(self.verification_status)
            ),
            "retrieval_method": self.retrieval_method,
            "text": self.text,
            "provenance": self.provenance,
            "graph_score": round(self.graph_score, 4),
            "combined_score": round(self.combined_score, 4),
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def __iter__(self):
        yield from (
            "evidence_id", "bm25_score", "source_date", "verification_status",
            "retrieval_method", "text", "entities", "attributes", "facts",
            "provenance", "graph_score", "combined_score",
        )

    def __len__(self) -> int:
        return 12

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return getattr(self, key)
        except AttributeError:
            return default


class BM25Index:
    """Lightweight, offline in-memory BM25 Okapi index."""

    def __init__(
        self,
        lexicon: Lexicon | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        include_attribute_synonyms: bool = True,
    ):
        self.lexicon = lexicon
        self.k1 = k1
        self.b = b
        self.include_attribute_synonyms = include_attribute_synonyms
        self.documents: dict[str, IndexedDocument] = {}
        self.doc_lengths: dict[str, int] = {}
        self.postings: dict[str, dict[str, int]] = defaultdict(dict)  # term -> {doc_id: count}
        self.term_doc_freq: dict[str, int] = defaultdict(int)
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0
        self.is_built: bool = False

    def add_document(
        self,
        evidence_id: str,
        text: str,
        source_date: date | None = None,
        evidence_status: EvidenceState = EvidenceState.UNVERIFIED_CANDIDATE,
        entities: Sequence[str] = (),
        attributes: Sequence[str] = (),
        facts: Sequence[AtomicFact] = (),
        provenance: str = "",
        raw_record: Any = None,
    ) -> None:
        """Add an evidence document to the index; requires build() before searching."""
        tokens = tokenize_evidence_text(
            text=text,
            lexicon=self.lexicon,
            observed_date=source_date,
            include_attribute_synonyms=self.include_attribute_synonyms,
        )
        # Augment with canonical entities and attributes if supplied
        extra_tokens: list[str] = []
        for ent in entities:
            norm = Lexicon.normalize_name(ent) if self.lexicon else ent.casefold()
            extra_tokens.append(f"entity:{norm}")
        for attr in attributes:
            extra_tokens.append(f"attr:{attr}")
        all_tokens = tuple((*tokens, *extra_tokens))
        doc = IndexedDocument(
            evidence_id=evidence_id,
            text=text,
            source_date=source_date,
            evidence_status=evidence_status,
            entities=tuple(entities),
            attributes=tuple(attributes),
            facts=tuple(facts),
            provenance=provenance,
            tokens=all_tokens,
            token_count=len(all_tokens),
            raw_record=raw_record,
        )
        self.documents[evidence_id] = doc
        self.doc_lengths[evidence_id] = len(all_tokens)
        counts = Counter(all_tokens)
        for term, count in counts.items():
            self.postings[term][evidence_id] = count
            self.term_doc_freq[term] += 1
        self.is_built = False

    def build(self) -> None:
        """Compute IDFs and average document length."""
        n_docs = len(self.documents)
        if n_docs == 0:
            self.avgdl = 0.0
            self.idf = {}
            self.is_built = True
            return
        self.avgdl = sum(self.doc_lengths.values()) / n_docs
        self.idf = {}
        for term, df in self.term_doc_freq.items():
            # Standard Robertson-Spärck Jones BM25 IDF with smoothing + 1 to stay non-negative
            self.idf[term] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
        self.is_built = True

    def search(
        self,
        query_text: str,
        query_date: date | str | None = None,
        top_k: int = 5,
        exclude_evidence_ids: Iterable[str] = (),
    ) -> list[RetrievedEvidence]:
        """Retrieve top-K matching evidence documents scored by BM25."""
        if top_k <= 0:
            return []
        if not self.is_built:
            self.build()
        if not self.documents:
            return []
        parsed_date = None
        if isinstance(query_date, str):
            parsed_date, _ = normalize_date(query_date)
        elif isinstance(query_date, date):
            parsed_date = query_date

        query_tokens = tokenize_evidence_text(
            text=query_text,
            lexicon=self.lexicon,
            observed_date=parsed_date,
            include_attribute_synonyms=self.include_attribute_synonyms,
        )
        if not query_tokens:
            return []

        excluded = set(exclude_evidence_ids or ())
        scores: dict[str, float] = defaultdict(float)
        query_counts = Counter(query_tokens)

        for term, q_tf in query_counts.items():
            idf = self.idf.get(term)
            if not idf or idf <= 0.0:
                continue
            postings = self.postings.get(term, {})
            for doc_id, doc_tf in postings.items():
                if doc_id in excluded:
                    continue
                doc_len = self.doc_lengths[doc_id]
                denom = doc_tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avgdl if self.avgdl > 0 else 1.0))
                term_score = idf * ((doc_tf * (self.k1 + 1.0)) / denom)
                scores[doc_id] += term_score

        if not scores:
            return []

        ranked_doc_ids = sorted(scores.keys(), key=lambda did: scores[did], reverse=True)[:top_k]
        results: list[RetrievedEvidence] = []
        for did in ranked_doc_ids:
            doc = self.documents[did]
            results.append(
                RetrievedEvidence(
                    evidence_id=doc.evidence_id,
                    bm25_score=scores[did],
                    source_date=doc.source_date,
                    verification_status=doc.evidence_status,
                    retrieval_method="bm25",
                    text=doc.text,
                    entities=doc.entities,
                    attributes=doc.attributes,
                    facts=doc.facts,
                    provenance=doc.provenance,
                    combined_score=scores[did],
                )
            )
        return results

    @classmethod
    def from_graph(
        cls,
        graph: TemporalKnowledgeGraph,
        k1: float = 1.5,
        b: float = 0.75,
        include_attribute_synonyms: bool = True,
    ) -> BM25Index:
        """Construct and build a BM25 index directly from a TemporalKnowledgeGraph."""
        index = cls(
            lexicon=graph.lexicon,
            k1=k1,
            b=b,
            include_attribute_synonyms=include_attribute_synonyms,
        )
        for evidence in graph.evidence_by_id.values():
            entities = tuple(f.subject for f in evidence.facts)
            attributes = tuple(f.attribute for f in evidence.facts)
            # Determine evidence status from graph facts
            records = [
                r for records in graph.facts_by_subject_attribute.values()
                for r in records if r.source_row_id == evidence.source_row_id
            ]
            if any(r.evidence_status == EvidenceState.VERIFIED_SUPPORT for r in records):
                status = EvidenceState.VERIFIED_SUPPORT
            elif any(r.evidence_status == EvidenceState.CONFLICTING for r in records):
                status = EvidenceState.CONFLICTING
            elif any(r.evidence_status == EvidenceState.VERIFIED_REFUTATION for r in records):
                status = EvidenceState.VERIFIED_REFUTATION
            else:
                status = EvidenceState.UNVERIFIED_CANDIDATE

            index.add_document(
                evidence_id=evidence.source_row_id,
                text=evidence.text,
                source_date=evidence.observed_on,
                evidence_status=status,
                entities=entities,
                attributes=attributes,
                facts=evidence.facts,
                provenance=evidence.provenance,
                raw_record=evidence,
            )
        index.build()
        return index

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Mapping[str, Any]],
        lexicon: Lexicon | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        include_attribute_synonyms: bool = True,
    ) -> BM25Index:
        """Construct and build a BM25 index from row mappings."""
        index = cls(
            lexicon=lexicon,
            k1=k1,
            b=b,
            include_attribute_synonyms=include_attribute_synonyms,
        )
        for row in rows:
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                continue
            text = str(row.get("text", "")).strip()
            when, _ = normalize_date(row.get("date"))
            label = str(row.get("label", "")).strip().lower()
            if label == "true":
                status = EvidenceState.VERIFIED_SUPPORT
            else:
                status = EvidenceState.UNVERIFIED_CANDIDATE
            index.add_document(
                evidence_id=row_id,
                text=text,
                source_date=when,
                evidence_status=status,
                provenance="practice_row" if label else "runtime_row",
            )
        index.build()
        return index
