"""Typed value mentions, read the way contracts/value-forms.md reads them.

Pure regex / table code. No gold forms and no model are used here.

``find_value_mentions(text, masked_spans)`` returns ``Mention`` objects. A mention keeps
every reading the text states (a counted noun can be read with any of the words that
follow the number), plus flags that make the value *not* readable (approximation, one end
of a range, negation before it). The caller decides what to emit; flagged mentions are
never emitted as exact values.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------------------
# number words
# ----------------------------------------------------------------------------------------
ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_ones_alt = "|".join(sorted(ONES, key=len, reverse=True))
_tens_alt = "|".join(TENS)
WORD_NUM_RE = re.compile(
    r"(?<![\w-])(?:"
    r"(?P<dozen>a\s+dozen)"
    r"|(?P<hund>(?:a|one|(?:" + _ones_alt + r")|(?:(?:" + _tens_alt + r")(?:[- ](?:" + _ones_alt + r"))?))\s+hundred)"
    r"|(?P<tens>(?:" + _tens_alt + r")(?:-(?:" + _ones_alt + r"))?)"
    r"|(?P<ones>" + _ones_alt + r")"
    r")(?!\w)",
    re.I,
)


def word_number(raw: str) -> int | None:
    raw = raw.lower().strip()
    if raw == "a dozen":
        return 12
    m = re.fullmatch(r"(a|one|[a-z-]+?)\s+hundred", raw)
    if m:
        head = m.group(1)
        base = 1 if head in ("a", "one") else word_number(head.replace(" ", "-"))
        return None if base is None else base * 100
    if raw in ONES:
        return ONES[raw]
    parts = re.split(r"[- ]", raw)
    if len(parts) == 1 and parts[0] in TENS:
        return TENS[parts[0]]
    if len(parts) == 2 and parts[0] in TENS and parts[1] in ONES and 1 <= ONES[parts[1]] <= 9:
        return TENS[parts[0]] + ONES[parts[1]]
    return None


# ----------------------------------------------------------------------------------------
# tables
# ----------------------------------------------------------------------------------------
MONTHS = {}
for _i, _n in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                         "september", "october", "november", "december"), 1):
    MONTHS[_n] = _i
    MONTHS[_n[:3]] = _i
MONTHS["sept"] = 9
_month_alt = "|".join(sorted(MONTHS, key=len, reverse=True))
MONTH_RE = r"(?:" + _month_alt + r")"

CURRENCY_SYMBOL = {"€": "EUR", "$": "USD", "£": "GBP", "US$": "USD"}
CURRENCY_CODES = {"EUR", "USD", "GBP", "CHF", "RON", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK", "JPY", "CNY", "INR", "CAD", "AUD"}
CURRENCY_WORD = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}
_codes_alt = "|".join(sorted(CURRENCY_CODES))

SCALES_CI = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "bn": 1e9}
SCALE_CS = {"k": 1e3, "M": 1e6}  # case matters: lower-case m is a metre

# physical units: (regex text, canonical symbol, case_sensitive)
_PHYS = [
    # data
    (r"kilobytes?|kB|kb|KB", "KB", True), (r"megabytes?|MB|mb", "MB", True), (r"gigabytes?|gigs?|GB|gb", "GB", True),
    (r"terabytes?|TB|tb", "TB", True), (r"bytes?|B", "B", True),
    # length
    (r"millimet(?:re|er)s?|mm", "mm", True), (r"centimet(?:re|er)s?|cm", "cm", True),
    (r"kilomet(?:re|er)s?|km", "km", True), (r"met(?:re|er)s?|m", "m", True), (r"inch(?:es)?|\"|″", "in", True),
    # mass
    (r"kilograms?|kilos?|kg", "kg", True), (r"grams?|grammes?|g", "g", True),
    (r"mAh", "mAh", True),
    # frequency
    (r"kilohertz|kHz", "kHz", True), (r"megahertz|MHz", "MHz", True), (r"gigahertz|GHz", "GHz", True), (r"hertz|Hz", "Hz", True),
    # power
    (r"milliwatts?|mW", "mW", True), (r"kilowatts?|kW", "kW", True), (r"watts?|W", "W", True),
]
# words are case-insensitive, symbols are case-sensitive: build one case-sensitive alternation
_WORD_UNITS = {
    "byte": "B", "bytes": "B", "kilobyte": "KB", "kilobytes": "KB", "megabyte": "MB", "megabytes": "MB",
    "gigabyte": "GB", "gigabytes": "GB", "gig": "GB", "gigs": "GB", "terabyte": "TB", "terabytes": "TB",
    "millimetre": "mm", "millimetres": "mm", "millimeter": "mm", "millimeters": "mm",
    "centimetre": "cm", "centimetres": "cm", "centimeter": "cm", "centimeters": "cm",
    "metre": "m", "metres": "m", "meter": "m", "meters": "m", "kilometre": "km", "kilometres": "km",
    "kilometer": "km", "kilometers": "km", "inch": "inch", "inches": "inch",
    "gram": "g", "grams": "g", "gramme": "g", "grammes": "g", "kilogram": "kg", "kilograms": "kg",
    "kilo": "kg", "kilos": "kg",
    "hertz": "Hz", "kilohertz": "kHz", "megahertz": "MHz", "gigahertz": "GHz",
    "milliwatt": "mW", "milliwatts": "mW", "watt": "W", "watts": "W", "kilowatt": "kW", "kilowatts": "kW",
}
_SYMBOL_UNITS = {
    "B": "B", "KB": "KB", "kB": "KB", "kb": "KB", "MB": "MB", "mb": "MB", "GB": "GB", "gb": "GB", "TB": "TB", "tb": "TB",
    "mm": "mm", "cm": "cm", "m": "m", "km": "km", "g": "g", "kg": "kg", "mAh": "mAh",
    "Hz": "Hz", "kHz": "kHz", "MHz": "MHz", "GHz": "GHz", "mW": "mW", "W": "W", "kW": "kW", '"': "in", "″": "in",
}
_unit_word_alt = "|".join(sorted(_WORD_UNITS, key=len, reverse=True))
_unit_sym_alt = "|".join(re.escape(s) for s in sorted(_SYMBOL_UNITS, key=len, reverse=True))
PHYS_UNIT_RE = re.compile(r"(?:(?P<w>(?i:" + _unit_word_alt + r"))(?![A-Za-z])|(?P<s>" + _unit_sym_alt + r")(?![A-Za-z]))")

DURATION_UNITS = {
    "ms": "ms", "millisecond": "ms", "milliseconds": "ms",
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "day", "day": "day", "days": "day",
    "wk": "week", "wks": "week", "week": "week", "weeks": "week",
    "mo": "month", "mth": "month", "mths": "month", "month": "month", "months": "month",
    "yr": "year", "yrs": "year", "year": "year", "years": "year",
}
_dur_alt = "|".join(sorted(DURATION_UNITS, key=len, reverse=True))
DURATION_UNIT_RE = re.compile(r"(?P<u>" + _dur_alt + r")(?![A-Za-z])")
# single-letter / short symbols must be lower case, words any case
_DUR_SYMBOLS = {"ms", "s", "h", "d", "min", "mo", "wk", "yr", "hr", "mth", "sec"}

APPROX_BEFORE = re.compile(
    r"(?:\b(?:about|around|approximately|approx\.?|roughly|nearly|almost|circa|ca\.?|some|estimated|est\.?|"
    r"close to|more or less)|[~≈±])\s*$", re.I)
APPROX_AFTER = re.compile(r"^\s*(?:or so\b|give or take\b|-ish\b|ish\b)", re.I)

NEGATION_WORDS = re.compile(r"(?<![\w'-])(?:not|no|never|none|nobody|nothing|neither|nor|without|cannot)(?![\w'-])|n't(?![\w])", re.I)
# comparison phrases that contain a negation word but are comparisons
COMPARISON_NEG = re.compile(r"(?:no|not)\s+(?:more|less|fewer|later|earlier)\s+than", re.I)
CLAUSE_END = re.compile(r"[.,;:!?•·|]|\n\s*\n")

OP_BEFORE = [
    (re.compile(r"(?<![\w])(?:no more than|not more than|at most|up to|maximum|max\.?|no later than)\s*$", re.I), "le"),
    (re.compile(r"(?<![\w])(?:at least|no less than|not less than|no fewer than|minimum|no earlier than)\s*$", re.I), "ge"),
    (re.compile(r"(?<![\w])(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of)\s*$", re.I), "gt"),
    (re.compile(r"(?<![\w])(?:under|less than|fewer than|lower than|below)\s*$", re.I), "lt"),
]
OP_AFTER = [
    (re.compile(r"^\s*(?:or less|or fewer|or under|or below|or lower|or shorter)\b", re.I), "le"),
    (re.compile(r"^\s*(?:or more|or higher|or above|or longer|or over)\b", re.I), "ge"),
    (re.compile(r"^\+"), "ge"),
]
DATE_OP_BEFORE = [
    (re.compile(r"(?<![\w])(?:no later than|by)\s*$", re.I), "le"),
    (re.compile(r"(?<![\w])(?:no earlier than)\s*$", re.I), "ge"),
    (re.compile(r"(?<![\w])(?:before|prior to)\s*$", re.I), "lt"),
    (re.compile(r"(?<![\w])(?:after)\s*$", re.I), "gt"),
]
WITHIN_RE = re.compile(r"\bwithin\s+(?:the\s+)?(?:next\s+)?$", re.I)
AN_PREPS = re.compile(r"(?:\b(?:under|within|in|for|over|than|at least|at most|to|only|just|about|around)\s+)$", re.I)

# words that are never the counted noun (function words, verbs of the usual templates)
NOUN_STOP = {
    "of", "in", "on", "at", "to", "for", "by", "with", "and", "or", "the", "a", "an", "is", "are", "was", "were", "will",
    "as", "that", "which", "who", "from", "per", "each", "every", "than", "but", "so", "we", "our", "you", "it", "they",
    "this", "these", "those", "its", "their", "his", "her", "he", "she", "i", "my", "your", "be", "been", "has", "have",
    "had", "do", "does", "did", "not", "no", "if", "when", "while", "after", "before", "until", "since", "also", "now",
    "today", "more", "less", "or", "off", "up", "out", "into", "over", "under", "about", "around", "all", "any", "both",
    "some", "such", "only", "just", "than", "then", "there", "here", "what", "how", "why", "where", "yet", "still",
    "already", "ago", "later", "earlier", "ahead", "back", "away", "together", "again", "too", "very", "even",
}
IRREGULAR = {"people": "person", "men": "man", "women": "woman", "children": "child", "mice": "mouse",
             "indices": "index", "feet": "foot", "criteria": "criterion", "analyses": "analysis"}


def singular(word: str) -> str:
    w = word.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes", "zes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


# ----------------------------------------------------------------------------------------
@dataclass
class Mention:
    kind: str                       # quantity money percent date version duration name
    readings: list                  # list of value dicts (without op); readings[0] is the default
    start: int
    end: int
    rule: str
    op: str | None = None
    approx: bool = False
    in_range: bool = False
    negated: bool = False
    blocked: str | None = None      # reason the value reads as nothing, if any
    extra: dict = field(default_factory=dict)

    @property
    def surface_ok(self) -> bool:
        return not (self.approx or self.in_range or self.negated or self.blocked)


def _num(x: float):
    if isinstance(x, int):
        return x
    return int(x) if float(x).is_integer() else round(x, 10)


# ----------------------------------------------------------------------------------------
# number tokens
# ----------------------------------------------------------------------------------------
RUN_RE = re.compile(r"(?<![\w.,])\d[\d.,]*\d(?![\w])|(?<![\w.,])\d(?![\w.,]*\d)")
RUN_LOOSE = re.compile(r"(?<![\w])\d[\d.,]*\d|(?<![\w])\d")


@dataclass
class NumTok:
    start: int
    end: int
    value: float | int | None
    form: str        # plain, thousands, decimal_comma, three_dec, dotted, ambiguous, word
    raw: str


def classify_run(raw: str):
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        v = float(raw.replace(",", ""))
        return _num(v), "thousands"
    if re.fullmatch(r"\d+", raw):
        return int(raw), "plain"
    if re.fullmatch(r"\d+\.\d{3}", raw):
        return _num(float(raw)), "three_dec"
    if re.fullmatch(r"\d+\.\d+", raw):
        return _num(float(raw)), "plain"
    if re.fullmatch(r"\d+(?:\.\d+){2,}", raw):
        return None, "dotted"
    if re.fullmatch(r"\d+,\d{1,2}", raw):
        return _num(float(raw.replace(",", "."))), "decimal_comma"
    return None, "ambiguous"


def number_tokens(text: str) -> list[NumTok]:
    out: list[NumTok] = []
    for m in re.finditer(r"(?<![\w])\d[\d.,]*\d|(?<![\w])\d", text):
        raw = m.group()
        # a trailing sentence punctuation never belongs to the run (regex ends on a digit)
        v, form = classify_run(raw)
        out.append(NumTok(m.start(), m.end(), v, form, raw))
    for m in WORD_NUM_RE.finditer(text):
        v = word_number(m.group())
        if v is not None:
            out.append(NumTok(m.start(), m.end(), v, "word", m.group()))
    out.sort(key=lambda t: (t.start, -t.end))
    return out


# ----------------------------------------------------------------------------------------
# clause helpers
# ----------------------------------------------------------------------------------------
def clause_bounds(text: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in CLAUSE_END.finditer(text, 0, pos):
        start = m.end()
    m2 = CLAUSE_END.search(text, pos)
    end = m2.start() if m2 else len(text)
    return start, end


def negated_before(text: str, start: int) -> bool:
    cs, _ = clause_bounds(text, start)
    seg = text[cs:start]
    seg = COMPARISON_NEG.sub(" ", seg)
    return bool(NEGATION_WORDS.search(seg))


def op_before(text: str, start: int) -> str | None:
    seg = text[max(0, start - 30):start]
    for rx, op in OP_BEFORE:
        if rx.search(seg):
            return op
    return None


def op_after(text: str, end: int) -> str | None:
    seg = text[end:end + 20]
    for rx, op in OP_AFTER:
        if rx.search(seg):
            return op
    return None


def approx_flag(text: str, start: int, end: int) -> bool:
    return bool(APPROX_BEFORE.search(text[max(0, start - 24):start])) or bool(APPROX_AFTER.search(text[end:end + 14]))


RANGE_AFTER = re.compile(r"^\s*(?:[-–—]|to\b|and\b)\s*(?:[€$£]|US\$)?\s*(?:\d|(?:%s)\b)" % _ones_alt, re.I)
RANGE_OR_AFTER = re.compile(r"^\s*or\s+(?:\d|(?:%s)\b)" % _ones_alt, re.I)
RANGE_BEFORE = re.compile(r"(?:\d[\d,.]*\s*(?:[-–—]|to)\s*(?:[€$£]|US\$)?\s*$)|(?:between\s+(?:[€$£]|US\$)?\s*$)", re.I)


def range_flag(text: str, start: int, end: int, unit_free_first: bool = False) -> bool:
    """One end of 10-20 GB, 10 to 20 GB, between 10 and 20 GB, 1 or 2 days."""
    before = text[max(0, start - 24):start]
    after = text[end:end + 24]
    if re.search(r"\d(?:[\d,.]*)\s*(?:GB|MB|TB|KB|%|[A-Za-z]{1,3})?\s*(?:[-–—]|\bto\b)\s*(?:[€$£]|US\$)?\s*$", before):
        return True
    if re.search(r"\bbetween\s+(?:[€$£]|US\$)?\s*$", before, re.I):
        return True
    if re.match(r"^\s*(?:[-–—]|\bto\b)\s*(?:[€$£]|US\$)?\s*\d", after, re.I):
        return True
    if re.search(r"\bbetween\s+[\d€$£][^,.;]*\band\s*$", before, re.I):
        return True
    if re.match(r"^\s*and\s+(?:[€$£]|US\$)?\s*\d", after, re.I) and re.search(r"\bbetween\s+[^,.;]*$", before, re.I):
        return True
    if unit_free_first and re.match(r"^\s*or\s+\d", after, re.I):
        return True
    if re.search(r"\d\s+or\s*$", before, re.I) and unit_free_first is not None:
        # "1 or 2 days": the number before 'or' had no unit of its own
        m = re.search(r"(\d[\d,.]*)\s+or\s*$", before, re.I)
        if m and not re.search(r"[A-Za-z€$£%]", before[m.start():m.start(1)]):
            return True
    return False


# ----------------------------------------------------------------------------------------
# main extraction
# ----------------------------------------------------------------------------------------
class Masker:
    def __init__(self, spans):
        self.spans = list(spans)

    def add(self, a, b):
        self.spans.append((a, b))

    def hit(self, a, b):
        return any(a < y and x < b for x, y in self.spans)


def _scale_after(text: str, pos: int):
    """Optional scale word right after a number. Returns (multiplier, end) or (1, pos)."""
    m = re.match(r"\s*(thousand|million|billion|bn)\b", text[pos:], re.I)
    if m:
        return SCALES_CI[m.group(1).lower()], pos + m.end()
    m = re.match(r"(k|M)(?![A-Za-z])", text[pos:])
    if m:
        return SCALE_CS[m.group(1)], pos + m.end()
    m = re.match(r"\s+(k|M)(?![A-Za-z])", text[pos:])
    if m and False:
        return SCALE_CS[m.group(1)], pos + m.end()
    return 1, pos


def _finish(text, mention, unit_free_first=False):
    s, e = mention.start, mention.end
    mention.approx = approx_flag(text, s, e)
    mention.in_range = range_flag(text, s, e, unit_free_first)
    mention.negated = negated_before(text, s)
    if mention.op is None:
        mention.op = op_before(text, s) or op_after(text, e)
    if mention.op is None and mention.kind == "duration" and WITHIN_RE.search(text[max(0, s - 20):s]):
        mention.op = "le"
    return mention


def _valid_date(y, m, d=None):
    if not (1 <= m <= 12):
        return False
    if d is None:
        return True
    return 1 <= d <= calendar.monthrange(y, m)[1]


def find_dates(text, masker: Masker) -> list[Mention]:
    out = []
    pats = [
        # ISO
        (re.compile(r"(?<![\w/.-])(\d{4})-(\d{2})(?:-(\d{2}))?(?![\w]|[-/.]\d)"), "iso"),
        # 12 March 2026 / 12th March 2026 / the 12th of March 2026 / 12March 2026
        (re.compile(r"(?<![\w/.-])(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?(?:\s+of)?\s*(" + MONTH_RE + r")\.?\s+(\d{4})(?!\d)", re.I), "dmy"),
        # March 12, 2026 / Mar 12th 2026
        (re.compile(r"(?<![\w])(" + MONTH_RE + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", re.I), "mdy"),
        # March 2026
        (re.compile(r"(?<![\w])(" + MONTH_RE + r")\.?\s+(\d{4})(?!\d)", re.I), "my"),
    ]
    for rx, kind in pats:
        for m in rx.finditer(text):
            if masker.hit(m.start(), m.end()):
                continue
            if kind == "iso":
                y, mo, d = int(m.group(1)), int(m.group(2)), m.group(3)
                d = int(d) if d else None
            elif kind == "dmy":
                d, mo, y = int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3))
            elif kind == "mdy":
                mo, d, y = MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
            else:
                mo, y, d = MONTHS[m.group(1).lower()], int(m.group(2)), None
            if not (1900 <= y <= 2099) or not _valid_date(y, mo, d):
                if kind == "iso":
                    masker.add(m.start(), m.end())
                continue
            # month-name ambiguity: "may" the verb only counts as month if capitalised or followed by a year (always here)
            val = f"{y:04d}-{mo:02d}" + (f"-{d:02d}" if d else "")
            s = m.start()
            if kind == "dmy" and text[s:].lower().startswith("the "):
                pass
            mention = Mention("date", [{"kind": "date", "value": val}], s, m.end(), f"date_{kind}")
            mention.op = None
            for rx2, op in DATE_OP_BEFORE:
                if rx2.search(text[max(0, s - 20):s]):
                    mention.op = op
                    break
            mention.approx = approx_flag(text, s, m.end())
            mention.in_range = range_flag(text, s, m.end())
            mention.negated = negated_before(text, s)
            out.append(mention)
            masker.add(s, m.end())
    return out


def find_bare_years(text, masker: Masker) -> list[Mention]:
    out = []
    for m in re.finditer(r"(?<![\w/.,$€£-])(19\d\d|20\d\d)(?![\w]|[.,]\d|-\d)", text):
        if masker.hit(m.start(), m.end()):
            continue
        before = text[max(0, m.start() - 12):m.start()]
        if re.search(r"\b[QqHh][1-4]\s*$", before):          # quarters and halves are not dates
            continue
        if re.match(r"\s*(?:%|percent)", text[m.end():m.end() + 10], re.I):
            continue
        # followed by a counted noun / unit => it is a count-like thing, not a date
        after_word = re.match(r"\s+([A-Za-z]+)", text[m.end():])
        if after_word and singular(after_word.group(1)) not in {"result", "report", "edition"} and after_word.group(1).lower() in {
                "customers", "users", "people", "employees", "gb", "mb", "tb", "attendees", "seats", "devices", "sessions", "speakers"}:
            continue
        mention = Mention("date", [{"kind": "date", "value": m.group(1)}], m.start(), m.end(), "date_year")
        mention.extra["bare_year"] = True
        mention.op = None
        for rx2, op in DATE_OP_BEFORE:
            if rx2.search(text[max(0, m.start() - 20):m.start()]):
                mention.op = op
                break
        mention.approx = approx_flag(text, m.start(), m.end())
        mention.in_range = range_flag(text, m.start(), m.end())
        mention.negated = negated_before(text, m.start())
        out.append(mention)
        masker.add(m.start(), m.end())
    return out


def find_versions(text, masker: Masker, entity_spans) -> list[Mention]:
    out = []
    # v2.3, version 2.3, ver. 2.3
    for m in re.finditer(r"(?<![\w])(?:v|ver\.?|version)\s*(\d+(?:\.\d+){0,3})(?![\w]|\.\d)", text, re.I):
        if masker.hit(m.start(), m.end()):
            continue
        # "v" must be lower-case attached or the word 'version'
        mention = Mention("version", [{"kind": "version", "value": m.group(1)}], m.start(), m.end(), "version_prefix")
        _finish(text, mention)
        mention.op = mention.op
        out.append(mention)
        masker.add(m.start(), m.end())
    # numbers with two or more dots
    for m in re.finditer(r"(?<![\w.,])(\d+(?:\.\d+){2,})(?![\w]|\.\d|,\d)", text):
        if masker.hit(m.start(), m.end()):
            continue
        raw = m.group(1)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3}){2,}", raw) or re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", raw):
            masker.add(m.start(), m.end())      # dots between thousands / numeric date: reads as nothing
            continue
        mention = Mention("version", [{"kind": "version", "value": raw}], m.start(), m.end(), "version_dotted")
        _finish(text, mention)
        out.append(mention)
        masker.add(m.start(), m.end())
    return out


def find_name_versions(text, masker: Masker, known_count_units: set[str]) -> list[Mention]:
    """'Hooly Gemini 2.2': capitalised word straight before a number with one decimal point."""
    out = []
    for m in re.finditer(r"(?<![\w])([A-Z][A-Za-z0-9/+-]*)\s+(\d+\.\d+)(?![\w]|\.\d|,\d)", text):
        a, b = m.start(2), m.end(2)
        if masker.hit(a, b):
            continue
        raw = m.group(2)
        if re.fullmatch(r"\d+\.\d{3}", raw):
            continue
        nxt = re.match(r"\s+([A-Za-z]+)", text[b:])
        if nxt and (singular(nxt.group(1)) in known_count_units or nxt.group(1).lower() in {"percent"}):
            continue
        if text[b:b + 1] == "%":
            continue
        mention = Mention("version", [{"kind": "version", "value": raw}], a, b, "version_after_name")
        _finish(text, mention)
        out.append(mention)
        masker.add(a, b)
    return out


_CUR_BEFORE = re.compile(r"(US\$|€|\$|£|\b(?:%s)\b)\s*$" % _codes_alt)
_CUR_AFTER = re.compile(r"^\s*(?:(€|\$|£)|\b(%s)\b|\b(euros?|dollars?|lei)\b)" % _codes_alt, re.I)

_PER_WORD = r"(?:month|mo|day|week|wk|year|yr)"
PERIOD_RE = re.compile(
    r"^(?:\s*(?:per|/|a|an|each|every)\s*(?:user|seat|person|member|employee|terabyte|TB|GB|gigabyte|hire|device|licen[cs]e|head)\b)?"
    r"(?:\s*(?:/|per\b|a\b|an\b|each\b|every\b|/\s*)\s*(?P<p>" + _PER_WORD + r")s?\b|(?P<adv>\s*(?:monthly|weekly|daily|annually|yearly)\b)|\s*per annum\b)",
    re.I)


def _period_of(token: str) -> str | None:
    t = token.lower()
    if t.startswith(("mo", "month")):
        return "month"
    if t.startswith(("d", "day")):
        return "day"
    if t.startswith(("w", "wk")):
        return "week"
    if t.startswith(("y", "yr")):
        return "year"
    return None


def find_money(text, masker: Masker, ntoks: list[NumTok]) -> list[Mention]:
    out = []
    for t in ntoks:
        if masker.hit(t.start, t.end) or t.form == "word":
            continue
        before = text[max(0, t.start - 8):t.start]
        cb = _CUR_BEFORE.search(before)
        end = t.end
        mult, end2 = _scale_after(text, end)
        ca = _CUR_AFTER.match(text[end2:end2 + 14]) if not cb else None
        # currency symbol after the amount ("49€") and words
        if not cb and not ca:
            continue
        if t.form in ("ambiguous", "dotted"):
            masker.add(t.start, t.end)
            continue
        if t.form == "three_dec":
            masker.add(t.start, t.end)
            continue
        if t.form == "decimal_comma":
            pass  # only a price may use a decimal comma: this is a price
        value = t.value
        if value is None:
            continue
        start = t.start
        if cb:
            currency_raw = cb.group(1)
            start = t.start - (len(before) - cb.start())
            currency = CURRENCY_SYMBOL.get(currency_raw) or currency_raw.upper()
        else:
            cur = ca.group(1) or ca.group(2) or ca.group(3)
            currency = CURRENCY_SYMBOL.get(cur) or CURRENCY_WORD.get(cur.lower()) or cur.upper()
            end2 = end2 + ca.end()
        if currency not in CURRENCY_CODES:
            continue
        if mult != 1:
            value = _num(value * mult)
        # a code written after the amount as a plain word 'pounds' is not read (handled: not in tables)
        per = None
        pm = PERIOD_RE.match(text[end2:end2 + 48])
        span_end = end2
        if pm:
            if pm.group("p"):
                per = _period_of(pm.group("p"))
            elif pm.group("adv"):
                per = _period_of(pm.group("adv").strip()[0:3] if pm.group("adv").strip().startswith(("m", "mo")) else pm.group("adv").strip())
                adv = pm.group("adv").strip().lower()
                per = {"monthly": "month", "weekly": "week", "daily": "day", "annually": "year", "yearly": "year"}[adv]
            else:
                per = "year"            # per annum
            span_end = end2 + pm.end()
        rd = {"kind": "money", "value": value, "currency": currency}
        if per:
            rd["per"] = per
        readings = [rd]
        mention = Mention("money", readings, start, span_end, "money")
        # the same price without period is *not* stated by a monthly price: only the real reading is kept
        mention.approx = approx_flag(text, start, span_end)
        mention.in_range = range_flag(text, start, span_end)
        mention.negated = negated_before(text, start)
        mention.op = op_before(text, start) or op_after(text, span_end)
        out.append(mention)
        masker.add(start, span_end)
    return out


def find_percent(text, masker: Masker, ntoks: list[NumTok]) -> list[Mention]:
    out = []
    for t in ntoks:
        if masker.hit(t.start, t.end):
            continue
        m = re.match(r"\s*(%|percent\b|per\s+cent\b)", text[t.end:t.end + 12], re.I)
        if not m:
            continue
        if t.form in ("ambiguous", "dotted") or t.value is None:
            masker.add(t.start, t.end + m.end())
            continue
        if t.form == "decimal_comma":
            masker.add(t.start, t.end + m.end())     # 99,9% reads as nothing
            continue
        end = t.end + m.end()
        mention = Mention("percent", [{"kind": "percent", "value": t.value}], t.start, end, "percent")
        _finish(text, mention)
        out.append(mention)
        masker.add(t.start, end)
    return out


def find_durations(text, masker: Masker, ntoks: list[NumTok]) -> list[Mention]:
    out = []
    for t in ntoks:
        if masker.hit(t.start, t.end):
            continue
        if t.form in ("ambiguous", "dotted", "decimal_comma", "three_dec") or t.value is None:
            continue
        tail = text[t.end:t.end + 16]
        m = re.match(r"(?:\s*-\s*|\s*)(?P<u>[A-Za-z]+)\b(?!\.\d)", tail)
        if not m:
            continue
        u = m.group("u")
        mult, endm = _scale_after(text, t.end)
        ul = u.lower()
        if ul not in DURATION_UNITS:
            continue
        if ul in _DUR_SYMBOLS and u != ul:
            continue
        if ul in ("d", "s", "h") and not re.match(r"\s?" + re.escape(u) + r"\b", tail):
            continue
        # the unit must not be the start of a longer word handled elsewhere (e.g. 'm' is metre)
        end = t.end + m.end()
        value = t.value
        if ul in ("decade", "decades"):
            continue
        rd = {"kind": "duration", "value": value, "unit": DURATION_UNITS[ul]}
        mention = Mention("duration", [rd], t.start, end, "duration")
        _finish(text, mention)
        if t.form == "word" or True:
            pass
        # a rate: "1,000 requests a day" — no number directly before; not this branch
        out.append(mention)
        masker.add(t.start, end)
    # "a/an" + unit after listed prepositions, fortnight, decade
    for m in re.finditer(r"(?<![\w])(?:(a|an)\s+)?(fortnight|decade|week|day|hour|minute|second|month|year)(?![\w])", text, re.I):
        word = m.group(2).lower()
        if masker.hit(m.start(), m.end()):
            continue
        if word == "fortnight":
            rd = {"kind": "duration", "value": 2, "unit": "week"}
        elif word == "decade":
            rd = {"kind": "duration", "value": 10, "unit": "year"}
        elif m.group(1):
            if not AN_PREPS.search(text[max(0, m.start() - 16):m.start()]):
                continue
            rd = {"kind": "duration", "value": 1, "unit": DURATION_UNITS[word]}
        else:
            continue
        mention = Mention("duration", [rd], m.start(), m.end(), "duration_a")
        _finish(text, mention)
        if word in ("fortnight", "decade") and False:
            pass
        wm = WITHIN_RE.search(text[max(0, m.start() - 20):m.start()])
        if wm:
            mention.op = "le"
        out.append(mention)
        masker.add(m.start(), m.end())
    return out


def find_physical(text, masker: Masker, ntoks: list[NumTok]) -> list[Mention]:
    out = []
    for t in ntoks:
        if masker.hit(t.start, t.end):
            continue
        if t.form in ("ambiguous", "dotted", "decimal_comma") or t.value is None:
            continue
        mult, end = _scale_after(text, t.end)
        rest = text[end:end + 20]
        m = re.match(r"(?:\s*-\s*|\s*)", rest)
        pos = m.end()
        um = PHYS_UNIT_RE.match(rest, pos)
        if not um:
            continue
        unit = _WORD_UNITS.get(um.group("w").lower()) if um.group("w") else _SYMBOL_UNITS[um.group("s")]
        if um.group("s") in ('"', "″") and pos != 0:
            continue
        if um.group("w") is None and um.group("s") in ("m", "g", "B", "W") and False:
            continue
        # number + 'in' is not a unit here (preposition)
        if t.form == "three_dec":
            masker.add(t.start, t.end)
            continue
        if mult == 1e6 and um.group("s") is None and False:
            continue
        value = t.value if mult == 1 else _num(t.value * mult)
        end_all = end + um.end()
        mention = Mention("quantity", [{"kind": "quantity", "value": value, "unit": unit}], t.start, end_all, "phys_unit")
        _finish(text, mention)
        out.append(mention)
        masker.add(t.start, end_all)
    return out


def find_counted(text, masker: Masker, ntoks: list[NumTok], year_ok_units: set[str] | None = None) -> list[Mention]:
    """A number followed by up to two words and a counted noun. All plausible nouns are kept as readings."""
    out = []
    for t in ntoks:
        if masker.hit(t.start, t.end):
            continue
        if t.form in ("ambiguous", "dotted", "decimal_comma") or t.value is None:
            if t.form in ("ambiguous", "dotted", "decimal_comma"):
                masker.add(t.start, t.end)
            continue
        if t.form == "three_dec":
            masker.add(t.start, t.end)
            continue
        if t.form == "word" and ONES.get(t.raw.lower()) == 1 and t.raw.lower() == "one":
            pass
        value = t.value
        end = t.end
        is_plain_year = t.form == "plain" and 1900 <= value <= 2099 and len(t.raw) == 4
        mult, end2 = _scale_after(text, end)
        if mult != 1:
            value = _num(value * mult)
            end = end2
            is_plain_year = False
        # words that follow: the number, up to two fillers, the noun
        plus = text[end:end + 1] == "+"
        if plus:
            end += 1
        tail = text[end:end + 60]
        words = []
        pos = 0
        for wm in re.finditer(r"\s*(?:-\s*)?([A-Za-z][A-Za-z']*)", tail):
            if wm.start() != pos:
                break
            words.append((wm.group(1), wm.end()))
            pos = wm.end()
            if len(words) >= 3:
                break
        # punctuation or digit between number and first word breaks the phrase
        readings, ends = [], []
        for i, (w, wend) in enumerate(words):
            wl = w.lower()
            if wl in NOUN_STOP and i == 0:
                if wl in ("of", "our", "the", "its", "their", "your", "his", "her", "my"):
                    continue
                break
            if wl in NOUN_STOP:
                continue
            if wl in DURATION_UNITS and len(wl) > 1 and wl not in ("min",):
                break
            readings.append({"kind": "quantity", "value": value, "unit": singular(w)})
            ends.append(end + wend)
        if not readings:
            continue
        if is_plain_year:
            continue                               # a four-digit number 1900..2099 is a year
        mention = Mention("quantity", readings, t.start, ends[0], "counted")
        mention.extra["ends"] = ends
        _finish(text, mention)
        if plus and mention.op is None:
            mention.op = "ge"
        out.append(mention)
        # do not mask: bare-number readings may still be needed? mask the number only
        masker.add(t.start, t.end)
    return out


def find_value_mentions(text: str, entity_spans, known_count_units: set[str]) -> list[Mention]:
    """All typed value mentions of a sentence. Entity spans are masked (a year in a name is not a value)."""
    masker = Masker(entity_spans)
    ntoks = number_tokens(text)
    mentions: list[Mention] = []
    mentions += find_dates(text, masker)
    mentions += find_versions(text, masker, entity_spans)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_money(text, masker, ntoks)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_percent(text, masker, ntoks)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_durations(text, masker, ntoks)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_physical(text, masker, ntoks)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_name_versions(text, masker, known_count_units)
    ntoks = [t for t in ntoks if not masker.hit(t.start, t.end)]
    mentions += find_counted(text, masker, ntoks)
    mentions += find_bare_years(text, masker)
    mentions.sort(key=lambda m: (m.start, m.end))
    return mentions


