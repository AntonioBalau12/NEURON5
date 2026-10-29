"""Independent re-implementation of the key text rules of contracts/claim-forms.md and value-forms.md.

Deliberately does NOT call foundation.validate_claim_text (that is run separately, as a second opinion).
It reads data/lexicon.json itself and re-reads the values written in a sentence with its own regexes, so
that "the value is written exactly per value-forms.md" is checked by parsing the text back, not by trusting
the renderer.

Public entry: ``check_text(claim_type, text, form, names)`` -> list of ``(rule_code, message)``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

# ----------------------------------------------------------------------------------------------
# lexicon / names
# ----------------------------------------------------------------------------------------------


def _flex(spelling: str) -> str:
    parts = re.findall(r"[^\W\d_]+|\d+|[^\w\s]", spelling, flags=re.UNICODE)
    return r"[\s-]*".join(re.escape(p) for p in parts)


def _norm(spelling: str) -> str:
    return re.sub(r"[\s-]+", "", spelling.casefold())


class Names:
    """Name / alias index with the 'name inside a longer name names only the longer one' rule."""

    def __init__(self, lexicon_path: str | Path):
        raw = json.loads(Path(lexicon_path).read_text(encoding="utf-8-sig"))
        self.entities: dict[str, dict[str, Any]] = {}
        self.events: list[str] = list(raw.get("events", []))
        self._by_norm: dict[str, set[str]] = {}
        self._patterns: list[tuple[re.Pattern[str], str]] = []
        for s in raw["subjects"]:
            self.entities[s["name"]] = {"aliases": list(s.get("aliases", [])), "attributes": set(s.get("attributes", []))}
            for sp in [s["name"], *s.get("aliases", [])]:
                self._by_norm.setdefault(_norm(sp), set()).add(s["name"])
                self._patterns.append((re.compile(r"(?<!\w)" + _flex(sp) + r"(?!\w)", re.IGNORECASE), s["name"]))

    def resolve(self, spelling: str) -> str | None:
        found = self._by_norm.get(_norm(spelling), set())
        return next(iter(found)) if len(found) == 1 else None

    def mentions(self, text: str) -> list[tuple[int, int, str]]:
        """Longest-match mentions: a mention inside a strictly longer mention is dropped."""
        allm = [(m.start(), m.end(), name) for pat, name in self._patterns for m in pat.finditer(text)]
        keep = []
        for m in allm:
            if any(o[0] <= m[0] and o[1] >= m[1] and (o[1] - o[0]) > (m[1] - m[0]) for o in allm):
                continue
            keep.append(m)
        return sorted(set(keep))

    def mask(self, text: str) -> str:
        chars = list(text)
        for s, e, _ in self.mentions(text):
            for i in range(s, e):
                chars[i] = " "
        return "".join(chars)

    def first_position(self, text: str, entity: str) -> int | None:
        pos = [s for s, _, n in self.mentions(text) if n == entity]
        return min(pos) if pos else None


# ----------------------------------------------------------------------------------------------
# sentences and word lists
# ----------------------------------------------------------------------------------------------
_ABBR = ["e.g.", "i.e.", "vs.", "approx.", "Inc.", "Ltd.", "Co.", "Corp.", "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "St."]


def split_sentences(text: str) -> list[str]:
    protected = text
    for a in _ABBR:
        protected = re.sub(re.escape(a), a.replace(".", "\u0001"), protected, flags=re.IGNORECASE)
    protected = re.sub(r"\b([A-Z])\.", "\\1\u0001", protected)
    protected = re.sub(r"\bNo\.(?=\s*\d)", "No\u0001", protected)
    parts = re.split(r"(?<=[.!?])\s+|\n\s*\n", protected.strip())
    return [p.replace("\u0001", ".") for p in parts if p.strip()]


NEGATION = re.compile(r"(?<!\w)(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)(?!\w)|\w+n['\u2019]t(?!\w)", re.IGNORECASE)
APPROX = re.compile(
    r"(?<!\w)(?:about|around|approximately|approx|roughly|nearly|almost|circa|ca|some|estimated|est|close to|more or less|"
    r"or so|give or take)(?!\w)|~|\u2248|\u00b1|-ish\b", re.IGNORECASE)
COMPARISON_WORDS = re.compile(
    r"(?<!\w)(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of|under|less than|fewer than|"
    r"lower than|below|up to|at most|at least|no more than|not more than|maximum|max|no less than|not less than|no fewer than|"
    r"minimum|within|or less|or fewer|or under|or below|or lower|or shorter|or more|or higher|or above|or longer|or over|"
    r"prior to|no later than|no earlier than)(?!\w)|(?<!\w)by\s+(?:the\s+)?\d", re.IGNORECASE)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec"]
SEASONS_DAYS = ["spring", "summer", "autumn", "winter", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIME_WORDS = ["ago", "yesterday", "tomorrow", "once", "formerly", "previously", "originally", "initially", "recently", "lately", "soon",
              "eventually", "then", "before", "after", "since", "until", "till", "earlier", "later", "used to", "last week", "last month",
              "last quarter", "last year", "next week", "next month", "next quarter", "next year", "in the past", "in the future",
              "at the time", "at that time", "today", "now", "currently", "still", "already", "yet", "former", "formerly"]
# (today/now/currently/still/already/yet/former are NOT in the contract list; they are banned by this checker as a
#  conservative extra so that every claim stays timeless.)
_MONTH_RE = re.compile(r"(?<!\w)(?:" + "|".join(m for m in MONTHS if m != "May") + r"|" + "|".join(MONTH_ABBR) + r")(?!\w)|(?<!\w)May(?!\w)", re.IGNORECASE)
_MONTH_NO_CASE_MAY = re.compile(r"(?<!\w)(?:" + "|".join(MONTHS + MONTH_ABBR) + r")(?!\w)")
_SEASON_RE = re.compile(r"(?<!\w)(?:" + "|".join(SEASONS_DAYS) + r")(?!\w)", re.IGNORECASE)
_TIME_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in sorted(set(TIME_WORDS), key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
                   "eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred dozen thousand million billion".split())
_NUMWORD_RE = re.compile(r"(?<!\w)(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")(?!\w)", re.IGNORECASE)
INVISIBLE = re.compile("[\u200b\u200c\u200d\u2060\u00ad\ufeff\u200e\u200f\u202a-\u202e]")

# compare phrases ('…' = up to three words)
PHRASES_AMOUNT = {
    "gt": ["more … than", "higher … than", "greater … than", "larger … than", "bigger … than", "longer … than"],
    "lt": ["less … than", "fewer … than", "lower … than", "smaller … than", "shorter … than", "cheaper … than"],
    "eq": ["the same … as", "as much … as", "as many … as", "as long as", "as high as", "equal to"],
}
PHRASES_DATE = {"gt": ["after", "later than"], "lt": ["before", "earlier than"], "eq": ["on the same day as", "the same day as"]}


def phrase_regex(phrase: str) -> re.Pattern[str]:
    pat = ""
    prev_ell = False
    for i, t in enumerate(phrase.split()):
        if t == "…":
            pat += r"\s+(?:[\w'\u2019-]+\s+){0,3}"
            prev_ell = True
        else:
            pat += re.escape(t) if (i == 0 or prev_ell) else r"\s+" + re.escape(t)
            prev_ell = False
    return re.compile(r"(?<!\w)" + pat + r"(?!\w)", re.IGNORECASE)


_PHRASE_RE = {(table, op, p): phrase_regex(p) for table, d in (("amount", PHRASES_AMOUNT), ("date", PHRASES_DATE)) for op, ps in d.items() for p in ps}

EVENT_PHRASES = ["at the time of", "on the day of", "during", "at"]

# ----------------------------------------------------------------------------------------------
# reading values back from text
# ----------------------------------------------------------------------------------------------
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_CUR = r"EUR|USD|GBP|CHF|RON|PLN|CZK|HUF|SEK|NOK|DKK|JPY|CNY|INR|CAD|AUD|euros?|dollars?|lei"
_PERIOD = r"(?:\s*(?:/|per\s+|a\s+|an\s+)\s*(?:user\s+per\s+|seat\s+per\s+)?(day|week|month|year|mo|yr)\b|\s+(monthly|annually|weekly|daily|yearly)\b|\s+per\s+annum\b)?"
_MON = "|".join(sorted(MONTHS + MONTH_ABBR, key=len, reverse=True))
_SCALE = {"k": 1e3, "m": 1e6, "bn": 1e9, "thousand": 1e3, "million": 1e6, "billion": 1e9}
_CUR_MAP = {"€": "EUR", "$": "USD", "£": "GBP", "US$": "USD", "euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}
_PER_MAP = {"day": "day", "week": "week", "month": "month", "year": "year", "mo": "month", "yr": "year", "monthly": "month",
            "annually": "year", "weekly": "week", "daily": "day", "yearly": "year"}

DURATION_UNITS = {"ms": "ms", "millisecond": "ms", "milliseconds": "ms", "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
                  "min": "min", "mins": "min", "minute": "min", "minutes": "min", "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
                  "d": "day", "day": "day", "days": "day", "wk": "week", "wks": "week", "week": "week", "weeks": "week",
                  "mo": "month", "mth": "month", "month": "month", "months": "month", "yr": "year", "yrs": "year", "year": "year", "years": "year"}
PHYS_UNITS = {"B": "B", "KB": "KB", "kB": "KB", "MB": "MB", "GB": "GB", "TB": "TB", "mm": "mm", "cm": "cm", "m": "m", "km": "km", "in": "inch",
              "inch": "inch", "inches": "inch", "g": "g", "kg": "kg", "mAh": "mAh", "Hz": "Hz", "kHz": "kHz", "MHz": "MHz", "GHz": "GHz",
              "mW": "mW", "W": "W", "kW": "kW"}
_IRREG = {"people": "person", "children": "child"}


def sing(noun: str) -> str:
    n = noun.lower()
    if n in _IRREG:
        return _IRREG[n]
    if n.endswith("ies") and len(n) > 4:
        return n[:-3] + "y"
    if n.endswith(("ches", "shes", "sses", "xes", "zes")):
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss") and len(n) > 3:
        return n[:-1]
    return n


def _num(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass(frozen=True)
class Token:
    kind: str  # money percent date version duration quantity stray_number number_word
    key: tuple
    start: int
    end: int
    raw: str


def _blank(text: str, s: int, e: int) -> str:
    return text[:s] + " " * (e - s) + text[e:]


_MIDX = {m.casefold(): i + 1 for i, m in enumerate(MONTHS)}
_MIDX.update({m.casefold()[:3]: i + 1 for i, m in enumerate(MONTHS)})
_MIDX["sept"] = 9


def _month_idx(name: str) -> int:
    return _MIDX.get(name.rstrip(".").casefold(), 0)


def scan_tokens(masked: str, extra_mask: Iterable[str] = ()) -> list[Token]:
    """Read every value-like token out of a sentence whose entity names were blanked."""
    text = masked
    for ph in extra_mask:
        text = re.sub(_flex(ph), lambda m: " " * len(m.group()), text, flags=re.IGNORECASE)
    toks: list[Token] = []

    def take(pattern: str, flags: int, builder) -> None:
        nonlocal text
        for m in list(re.finditer(pattern, text, flags)):
            if text[m.start():m.end()].strip() == "":
                continue
            key = builder(m)
            if key is None:
                continue
            toks.append(Token(key[0], key, m.start(), m.end(), m.group(0)))
            text = _blank(text, m.start(), m.end())

    def money_sym(m):
        sym = m.group(1)
        v = _num(m.group(2)) * _SCALE.get((m.group(3) or "").lower() if (m.group(3) or "") != "M" else "m", 1)
        per = _PER_MAP.get((m.group(4) or m.group(5) or "").lower()) if (m.group(4) or m.group(5)) else None
        return ("money", round(v, 6), _CUR_MAP.get(sym, sym), per)

    take(rf"(US\$|[€$£])\s?({NUM})(?:\s?(bn|M|k|million|billion|thousand)\b)?" + _PERIOD, 0, money_sym)

    def money_code(m):
        v = _num(m.group(1)) * _SCALE.get((m.group(2) or "").lower() if (m.group(2) or "") != "M" else "m", 1)
        cur = _CUR_MAP.get(m.group(3).lower(), m.group(3).upper())
        per = _PER_MAP.get((m.group(4) or m.group(5) or "").lower()) if (m.group(4) or m.group(5)) else None
        return ("money", round(v, 6), cur, per)

    take(rf"(?<![\w.,])({NUM})(?:\s?(bn|M|k|million|billion|thousand)\b)?\s?({_CUR})\b" + _PERIOD, 0, money_code)

    take(rf"(?<![\w.,])({NUM})\s?(?:%|percent\b|per\s?cent\b)", re.IGNORECASE, lambda m: ("percent", round(_num(m.group(1)), 6)))

    def iso(m):
        return ("date", f"{m.group(1)}-{m.group(2)}" + (f"-{m.group(3)}" if m.group(3) else ""))

    take(r"(?<![\w.,-])(\d{4})-(\d{2})(?:-(\d{2}))?(?![\w-])", 0, iso)
    take(rf"(?<!\w)(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of)?\s?({_MON})\.?,?\s+(\d{{4}})(?!\w)", re.IGNORECASE,
         lambda m: ("date", f"{m.group(3)}-{_month_idx(m.group(2)):02d}-{int(m.group(1)):02d}"))
    take(rf"(?<!\w)({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})(?!\w)", re.IGNORECASE,
         lambda m: ("date", f"{m.group(3)}-{_month_idx(m.group(1)):02d}-{int(m.group(2)):02d}"))
    take(rf"(?<!\w)({_MON})\.?,?\s+(\d{{4}})(?!\w)", re.IGNORECASE, lambda m: ("date", f"{m.group(2)}-{_month_idx(m.group(1)):02d}"))
    take(r"(?<![\w.,-])((?:19|20)\d{2})(?![\w,-]|\.\d)", 0, lambda m: ("date", m.group(1)))
    take(r"(?<!\w)(?:v|ver\.?\s*|version\s+)(\d+(?:\.\d+)*)(?![\w.]\d)(?!\w)", re.IGNORECASE, lambda m: ("version", m.group(1)))
    take(r"(?<![\w.])(\d+\.\d+\.\d+(?:\.\d+)*)(?!\w)", 0, lambda m: ("version", m.group(1)))

    def qty(m):
        n = _num(m.group(1))
        sc = m.group(2)
        if sc:
            n *= _SCALE.get(sc.lower() if sc != "M" else "m", 1)
        unit = m.group(3)
        if unit is None:
            return ("stray_number", m.group(1))
        if unit in PHYS_UNITS:
            return ("quantity", round(n, 6), PHYS_UNITS[unit])
        lu = unit.lower()
        if lu in DURATION_UNITS and (len(lu) > 1 or unit == lu):
            return ("duration", round(n, 6), DURATION_UNITS[lu])
        return ("quantity", round(n, 6), sing(unit))

    take(rf"(?<![\w.,])({NUM})(?:\s?(bn|M|k|million|billion|thousand)\b)?(?:\s?-?\s?([A-Za-z\"\u2033]+))?", 0, qty)
    # number words
    for m in _NUMWORD_RE.finditer(text):
        toks.append(Token("number_word", ("number_word", m.group(0).lower()), m.start(), m.end(), m.group(0)))
    return sorted(toks, key=lambda t: t.start)


def _restore_numeric_entity_units(masked: str, text: str, values: Iterable[Mapping[str, Any]], names: Names) -> str:
    """Keep a lexicon name visible when it is also the explicit unit after a number."""
    expected = {sing(str(v.get("unit", "")).casefold()) for v in values
                if v.get("kind") == "quantity" and isinstance(v.get("unit"), str)}
    if not expected:
        return masked
    chars = list(masked)
    for start, end, _ in names.mentions(text):
        raw_unit = text[start:end]
        if sing(raw_unit.casefold()) not in expected:
            continue
        if re.search(rf"(?<![\w.,]){NUM}\s+$", text[:start]):
            chars[start:end] = text[start:end]
    return "".join(chars)


def expected_key(value: Mapping[str, Any]) -> tuple | None:
    k = value.get("kind")
    v = value.get("value")
    if k == "money":
        return ("money", round(float(v), 6), value.get("currency"), value.get("per"))
    if k == "percent":
        return ("percent", round(float(v), 6))
    if k == "date":
        return ("date", str(v))
    if k == "version":
        return ("version", str(v))
    if k == "duration":
        return ("duration", round(float(v), 6), value.get("unit"))
    if k == "quantity":
        u = value.get("unit")
        return ("quantity", round(float(v), 6), PHYS_UNITS.get(u, sing(u)) if u else u)
    return None  # name / boolean carry no numeric token


# ----------------------------------------------------------------------------------------------
# checks
# ----------------------------------------------------------------------------------------------
Problem = tuple[str, str]


def attr_pattern(attr: str) -> re.Pattern[str]:
    parts = re.findall(r"[^\W\d_]+|\d+", attr.replace("_", " "))
    return re.compile(r"(?<!\w)" + r"[\s-]*".join(re.escape(p) for p in parts) + r"(?!\w)", re.IGNORECASE)


def _common(text: str, names: Names, allow_negation: bool) -> list[Problem]:
    probs: list[Problem] = []
    if not text or not text.strip():
        return [("empty", "text is empty")]
    if len(text) > 300:
        probs.append(("too_long", f"{len(text)} chars"))
    if INVISIBLE.search(text):
        probs.append(("invisible_char", "invisible character in text"))
    sents = split_sentences(text)
    if len(sents) != 1:
        probs.append(("not_single_sentence", f"{len(sents)} sentences"))
    if not text.rstrip().endswith("."):
        probs.append(("no_final_period", "text does not end with a period"))
    if re.search(r"\n", text):
        probs.append(("line_break", "line break in text"))
    if NEGATION.search(text) and not allow_negation:
        probs.append(("negation", "negation word in sentence"))
    return probs


def _refused(masked: str, allowed_phrases: Iterable[str] = ()) -> list[Problem]:
    probs: list[Problem] = []
    t = masked
    for ph in allowed_phrases:
        t = re.sub(re.escape(ph), lambda m: " " * len(m.group()), t, flags=re.IGNORECASE)
    if _MONTH_NO_CASE_MAY.search(t) or re.search(r"(?<!\w)May(?!\w)", t) or _SEASON_RE.search(t):
        probs.append(("month_season_weekday_word", "month, season or weekday word outside names/value"))
    if _TIME_RE.search(t):
        probs.append(("time_word", "time word: " + _TIME_RE.search(t).group(0)))
    return probs


def check_text(claim_type: str, text: str, form: Mapping[str, Any], names: Names, compare_table: str = "amount") -> list[Problem]:
    bool_false_claim = False
    values: list[Mapping[str, Any]] = []
    if claim_type in ("fact", "at_event", "relation"):
        v = form.get("value")
        if isinstance(v, Mapping):
            values = [v]
    elif claim_type == "change":
        values = [x for x in (form.get("from"), form.get("to")) if isinstance(x, Mapping)]
    boolean_change = (claim_type == "change" and len(values) == 2
                      and all(v.get("kind") == "boolean" for v in values))
    if values and values[0].get("kind") == "boolean" and values[0].get("value") is False and claim_type != "change":
        bool_false_claim = True
    probs = _common(text, names, allow_negation=bool_false_claim or boolean_change)
    masked = names.mask(text)
    mentions = names.mentions(text)
    mention_names = [n for _, _, n in mentions]

    def subject_ok(entity_spelling: str) -> str | None:
        e = names.resolve(entity_spelling)
        if e is None:
            probs.append(("unknown_subject", f"{entity_spelling!r} not in lexicon"))
        elif e not in mention_names:
            probs.append(("subject_not_named", f"{e!r} not named as whole name in text (name-in-longer-name rule)"))
        return e

    if claim_type == "compare":
        return probs + _check_compare(text, masked, form, names, mentions, compare_table)

    subj = subject_ok(str(form.get("subject", "")))
    attr = str(form.get("attribute", form.get("link", "")))
    if values and values[0].get("kind") == "boolean" and not boolean_change:
        attr_phrase = attr if claim_type != "relation" else str(form.get("attribute", ""))
        if claim_type == "relation":
            attr_phrase = str(form.get("attribute", ""))
        # the attribute in words (for fact/at_event on the fact's attribute; relation: target's attribute)
        if not attr_pattern(attr_phrase).search(text):
            probs.append(("boolean_attribute_words_missing", f"attribute words for {attr_phrase!r} not in text"))
        if values[0].get("value") is False and not NEGATION.search(text):
            probs.append(("boolean_polarity", "boolean false but no negation"))
        if values[0].get("value") is True and NEGATION.search(text):
            probs.append(("boolean_polarity", "boolean true but negation present"))
    # words masking: attribute words that contain digits (e.g. SOC 2) are only allowed for yes/no claims
    extra_mask: list[str] = []
    if values and values[0].get("kind") == "boolean":
        for a in (form.get("attribute"),):
            if isinstance(a, str) and re.search(r"\d", a):
                extra_mask.append(" ".join(re.findall(r"[^\W\d_]+|\d+", a.replace("_", " "))))
    if APPROX.search(masked):
        probs.append(("approximation", "approximation word: " + APPROX.search(masked).group(0)))
    if claim_type != "change":
        cw = COMPARISON_WORDS.search(masked)
        if cw:
            probs.append(("comparison_word", "comparison word: " + cw.group(0)))
    value_masked = _restore_numeric_entity_units(masked, text, values, names)
    toks = scan_tokens(value_masked, extra_mask)
    exp_keys = [expected_key(v) for v in values]
    exp_keys = [k for k in exp_keys if k is not None]
    got = [t for t in toks]
    bad = [t for t in got if t.kind in ("stray_number", "number_word")]
    for t in bad:
        probs.append(("stray_number", f"unreadable/stray number {t.raw!r}"))
    got_keys = [t.key for t in got if t.kind not in ("stray_number", "number_word")]
    if claim_type == "change":
        if got_keys != exp_keys:
            probs.append(("value_mismatch", f"text states {got_keys}, form says {exp_keys}"))
    else:
        if sorted(map(repr, got_keys)) != sorted(map(repr, exp_keys)):
            kinds_found = [k[0] for k in got_keys]
            exp_kinds = [k[0] for k in exp_keys]
            code = "other_value_of_same_kind" if len(got_keys) > len(exp_keys) else "value_not_rendered_exactly"
            probs.append((code, f"text states {got_keys}, form says {exp_keys}"))
    # refused words (dates without year / time words) outside names and the value
    allowed = ["at the time of"] if claim_type == "at_event" else []  # the event phrase's own time words
    probs += _refused(_blank_tokens(masked, got), allowed)
    # type-specific
    if claim_type == "at_event":
        ev = names.resolve(str(form.get("event", "")))
        if ev is None or str(form.get("event")) not in names.events:
            probs.append(("unknown_event", f"{form.get('event')!r} is not a lexicon event"))
        else:
            if ev == subj:
                probs.append(("event_is_subject", "subject and event are the same entity"))
            ok = False
            for s, e, n in mentions:
                if n == ev:
                    before = text[:s].rstrip()
                    before = re.sub(r"\s+the$", "", before, flags=re.IGNORECASE)
                    if any(re.search(r"(?<!\w)" + re.escape(p) + r"$", before, flags=re.IGNORECASE) for p in EVENT_PHRASES):
                        ok = True
            if not ok:
                probs.append(("event_phrase_missing", "no event phrase right before the event name"))
    if claim_type == "relation":
        link_words = attr_pattern(str(form.get("link", "")))
        if not link_words.search(text):
            probs.append(("relation_words_missing", f"link words for {form.get('link')!r} not in text"))
        if subj is not None and names.first_position(text, subj) is None:
            probs.append(("subject_not_named", "link subject not named"))
        tgt = names.resolve(str(form.get("target", "")))
        if tgt is None:
            probs.append(("unknown_target", f"target {form.get('target')!r} not in lexicon"))
    if claim_type == "change":
        if boolean_change:
            m = re.search(r"(?<!\w)from\s+(.+?\b(?:false|true))\s+to\s+(.+?\b(?:false|true))\.?\s*$",
                          masked, flags=re.IGNORECASE)
        else:
            m = re.search(r"(?<!\w)from\s+(.+)\s+to\s+(.+?)\.?\s*$", masked, flags=re.IGNORECASE)
        if not m:
            probs.append(("change_phrase_missing", "no 'from … to' change phrase"))
        else:
            if len(re.findall(r"(?<!\w)from(?!\w)", masked, flags=re.IGNORECASE)) != 1:
                probs.append(("change_phrase_ambiguous", "more than one 'from'"))
            if re.search(r"(?<!\w)(?:up|down)\s+from", masked, flags=re.IGNORECASE):
                probs.append(("change_direction_word", "up/down not used by this generator"))
            if boolean_change:
                attribute = str(form.get("attribute", ""))
                pattern = attr_pattern(attribute)
                if values[0].get("value") is values[1].get("value"):
                    probs.append(("boolean_change_endpoints_identical", "Boolean change endpoints are identical"))
                sides = ((1, values[0], "from"), (2, values[1], "to"))
                for group, endpoint, side_name in sides:
                    side_text = m.group(group)
                    source_side = text[m.start(group):m.end(group)]
                    if not pattern.search(source_side):
                        probs.append(("boolean_change_attribute_missing", f"{side_name} side omits attribute words"))
                    has_negation = NEGATION.search(side_text) is not None
                    says_false = re.search(r"(?<!\w)false(?!\w)", side_text, flags=re.IGNORECASE) is not None
                    says_true = re.search(r"(?<!\w)true(?!\w)", side_text, flags=re.IGNORECASE) is not None
                    expected_false = endpoint.get("value") is False
                    polarity_ok = ((says_false and not says_true and not has_negation)
                                   or (expected_false and has_negation and not says_true)
                                   or (not expected_false and not has_negation and not says_false))
                    if not polarity_ok:
                        probs.append(("boolean_change_polarity", f"{side_name} side does not match its Boolean endpoint"))
                negations = list(NEGATION.finditer(masked))
                if any(not (m.start(1) <= n.start() and n.end() <= m.end(1)
                            or m.start(2) <= n.start() and n.end() <= m.end(2)) for n in negations):
                    probs.append(("boolean_change_extra_negation", "negation outside a Boolean endpoint"))
            else:
                ft = scan_tokens(value_masked[m.start(1):m.end(1)], extra_mask) if m.group(1) else []
                tt = scan_tokens(value_masked[m.start(2):m.end(2)], extra_mask) if m.group(2) else []
                exp_from, exp_to = (expected_key(values[0]) if values else None), (expected_key(values[1]) if len(values) > 1 else None)
                if exp_from and [t.key for t in ft] != [exp_from]:
                    probs.append(("change_from_side", f"'from' side states {[t.key for t in ft]}, form says {exp_from}"))
                if exp_to and [t.key for t in tt] != [exp_to]:
                    probs.append(("change_to_side", f"'to' side states {[t.key for t in tt]}, form says {exp_to}"))
    return probs


def _blank_tokens(masked: str, toks: list[Token]) -> str:
    t = masked
    for tok in toks:
        t = _blank(t, tok.start, tok.end)
    return t


def _check_compare(text: str, masked: str, form: Mapping[str, Any], names: Names, mentions, table: str) -> list[Problem]:
    probs: list[Problem] = []
    left, right = form.get("left", {}), form.get("right", {})
    le, re_ = names.resolve(str(left.get("subject", ""))), names.resolve(str(right.get("subject", "")))
    if le is None or re_ is None:
        return [("unknown_subject", "compare subject not in lexicon")]
    lp, rp = names.first_position(text, le), names.first_position(text, re_)
    if lp is None or rp is None:
        probs.append(("subject_not_named", "compare text must name both subjects as whole names"))
        return probs
    if lp > rp:
        probs.append(("compare_order", "right subject named before left"))
    op = form.get("op")
    hits = [(t, o, p, m) for (t, o, p), rx in _PHRASE_RE.items() for m in rx.finditer(masked)]
    # phrases fully contained in a longer matched phrase count once ("as long as" vs "as … as" overlaps are fine)
    own = [h for h in hits if h[0] == table and h[1] == op]
    # a phrase wholly inside a longer phrase of the same list ('the same day as' in 'on the same day as') counts once
    own = [h for h in own if not any(o is not h and o[3].start() <= h[3].start() and o[3].end() >= h[3].end()
                                     and (o[3].end() - o[3].start()) > (h[3].end() - h[3].start()) for o in own)]
    wrong = [h for h in hits if not (h[0] == table and h[1] == op)]
    if len(own) < 1:
        probs.append(("compare_phrase_missing", f"no {table} phrase for op {op}"))
    if len({(h[3].start(), h[3].end()) for h in own}) > 1 or wrong:
        # ignore phrases of the other table that are the same word as an own-table phrase (before/after are in both lists of time words)
        wrong = [h for h in wrong if not any(h[3].start() >= o[3].start() and h[3].end() <= o[3].end() for o in own)]
        if wrong or len({(h[3].start(), h[3].end()) for h in own}) > 1:
            probs.append(("compare_second_phrase", "a second phrase of the list is present"))
    if own:
        ps, pe = own[0][3].start(), own[0][3].end()
        if not (lp < ps and pe <= rp + 0 and ps < rp):
            probs.append(("compare_phrase_position", "phrase must lie between the left and the right subject"))
    if _SEASON_RE.search(masked) or _MONTH_NO_CASE_MAY.search(masked) or re.search(r"(?<!\w)May(?!\w)", masked):
        probs.append(("month_season_weekday_word", "date word in compare sentence"))
    phrase_text = [h[3].group(0) for h in own]
    t = masked
    for ph in phrase_text:
        t = t.replace(ph, " " * len(ph))
    tm = _TIME_RE.search(t)
    if tm:
        probs.append(("time_word", "time word in compare sentence: " + tm.group(0)))
    if re.search(r"\d", masked):
        probs.append(("compare_number", "digit outside names"))
    if _NUMWORD_RE.search(masked):
        probs.append(("compare_number_word", "number word in compare sentence"))
    for tok in scan_tokens(masked):
        probs.append(("compare_value", f"value in compare sentence: {tok.raw!r}"))
    if NEGATION.search(text):
        probs.append(("negation", "negation in compare sentence"))
    if APPROX.search(masked):
        probs.append(("approximation", "approximation word"))
    return probs
