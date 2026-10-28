"""Typed value finders following contracts/value-forms.md (stdlib only).

Every finder returns `Val` objects with exact character offsets. Values that the referee reads as
nothing (approximations, range ends, comparisons, ambiguous numbers) are returned with flags so the
caller can suppress them and still know that something numeric was there.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import WORD_NUMBERS

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
              "oct": 10, "nov": 11, "dec": 12}
MONTH_ALL = {**MONTHS, **MONTH_ABBR}
_MONTH_RX = "(?:" + "|".join(sorted(MONTH_ALL, key=len, reverse=True)) + r")\.?"

CURRENCY_SYMBOLS = {"US$": "USD", "€": "EUR", "$": "USD", "£": "GBP"}
CURRENCY_CODES = {"EUR", "USD", "GBP", "CHF", "RON", "PLN", "CZK", "HUF", "SEK", "NOK", "DKK", "JPY", "CNY",
                  "INR", "CAD", "AUD"}
CURRENCY_WORDS = {"euro": "EUR", "euros": "EUR", "dollar": "USD", "dollars": "USD", "lei": "RON"}
SCALES = {"thousand": 1e3, "k": 1e3, "million": 1e6, "M": 1e6, "billion": 1e9, "bn": 1e9}
PERIODS = {"day": "day", "week": "week", "wk": "week", "month": "month", "mo": "month", "year": "year", "yr": "year",
           "annum": "year", "monthly": "month", "annually": "year", "daily": "day", "weekly": "week",
           "yearly": "year"}

# quantity units: exact symbol -> canonical, and word spellings (case-insensitive) -> canonical
UNIT_SYMBOLS = {"B": "B", "KB": "KB", "MB": "MB", "GB": "GB", "TB": "TB", "kB": "KB", "kb": "KB", "mb": "MB",
                "gb": "GB", "tb": "TB", "mm": "mm", "cm": "cm", "m": "m", "km": "km", "g": "g", "kg": "kg",
                "mAh": "mAh", "Hz": "Hz", "kHz": "kHz", "MHz": "MHz", "GHz": "GHz", "mW": "mW", "W": "W",
                "kW": "kW"}
UNIT_WORDS = {"byte": "B", "bytes": "B", "kilobyte": "KB", "kilobytes": "KB", "megabyte": "MB", "megabytes": "MB",
              "gigabyte": "GB", "gigabytes": "GB", "gig": "GB", "gigs": "GB", "terabyte": "TB", "terabytes": "TB",
              "millimetre": "mm", "millimetres": "mm", "millimeter": "mm", "millimeters": "mm",
              "centimetre": "cm", "centimetres": "cm", "centimeter": "cm", "centimeters": "cm",
              "metre": "m", "metres": "m", "meter": "m", "meters": "m", "kilometre": "km", "kilometres": "km",
              "kilometer": "km", "kilometers": "km", "inch": "inch", "inches": "inch", "gram": "g", "grams": "g",
              "gramme": "g", "grammes": "g", "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg",
              "hertz": "Hz", "kilohertz": "kHz", "megahertz": "MHz", "gigahertz": "GHz", "milliwatt": "mW",
              "milliwatts": "mW", "watt": "W", "watts": "W", "kilowatt": "kW", "kilowatts": "kW"}
DUR_SYMBOLS = {"ms": ("ms", 1), "s": ("s", 1), "h": ("h", 1), "d": ("day", 1)}
DUR_WORDS = {"msec": ("ms", 1), "millisecond": ("ms", 1), "milliseconds": ("ms", 1), "sec": ("s", 1),
             "secs": ("s", 1), "second": ("s", 1), "seconds": ("s", 1), "min": ("min", 1), "mins": ("min", 1),
             "minute": ("min", 1), "minutes": ("min", 1), "hr": ("h", 1), "hrs": ("h", 1), "hour": ("h", 1),
             "hours": ("h", 1), "day": ("day", 1), "days": ("day", 1), "wk": ("week", 1), "wks": ("week", 1),
             "week": ("week", 1), "weeks": ("week", 1), "fortnight": ("week", 2), "fortnights": ("week", 2),
             "mo": ("month", 1), "mos": ("month", 1), "mth": ("month", 1), "month": ("month", 1),
             "months": ("month", 1), "yr": ("year", 1), "yrs": ("year", 1), "year": ("year", 1),
             "years": ("year", 1), "decade": ("year", 10), "decades": ("year", 10)}

APPROX_BEFORE = re.compile(r"(?:\b(?:about|around|approximately|approx\.?|roughly|nearly|almost|circa|ca\.?|some|"
                           r"estimated|est\.?|close to|more or less)|[~\u2248\u00b1])\s*$", re.I)
APPROX_AFTER = re.compile(r"^\s*(?:or so\b|give or take\b|-ish\b)", re.I)
CMP_BEFORE = [
    (re.compile(r"\b(?:over|more than|greater than|higher than|above|exceeding|in excess of|upwards of)\s*$", re.I), "gt"),
    (re.compile(r"\b(?:under|less than|fewer than|lower than|below)\s*$", re.I), "lt"),
    (re.compile(r"\b(?:up to|at most|no more than|not more than|maximum|max)\s*$", re.I), "le"),
    (re.compile(r"\b(?:at least|no less than|not less than|no fewer than|minimum|min)\s*$", re.I), "ge"),
]
CMP_AFTER = [
    (re.compile(r"^\s*(?:or (?:less|fewer|under|below|lower|shorter)\b)", re.I), "le"),
    (re.compile(r"^\s*(?:or (?:more|higher|above|longer|over)\b)", re.I), "ge"),
    (re.compile(r"^\+"), "ge"),
]
DATE_CMP_BEFORE = [
    (re.compile(r"\b(?:before|prior to)\s*$", re.I), "lt"),
    (re.compile(r"\bafter\s*$", re.I), "gt"),
    (re.compile(r"\b(?:by|no later than)\s*$", re.I), "le"),
    (re.compile(r"\bno earlier than\s*$", re.I), "ge"),
]
RANGE_BEFORE = re.compile(r"(?:\d|\bbetween\s)[\d,.]*\s*(?:-|\u2013|\u2014|to|and)?\s*(?:[\u20ac$\u00a3]|US\$)?\s*$", re.I)
INVISIBLE = re.compile("[\u200b-\u200f\u2060\u00ad\ufeff\u202a-\u202e]")


@dataclass
class Val:
    kind: str
    value: dict
    start: int
    end: int
    surface: str
    approx: bool = False
    cmp_op: str | None = None
    rng: bool = False
    invisible: bool = False
    qualifier: str | None = None     # raw word directly before: since / from / until ...
    unit_guess: bool = False
    tags: list[str] = field(default_factory=list)

    @property
    def readable(self) -> bool:
        return not (self.approx or self.cmp_op or self.rng or self.invisible)

    @property
    def flags(self) -> list[str]:
        out = []
        if self.approx:
            out.append("approximation")
        if self.cmp_op:
            out.append(f"comparison:{self.cmp_op}")
        if self.rng:
            out.append("range-end")
        if self.invisible:
            out.append("invisible-char")
        return out


# ----------------------------------------------------------------------------- numbers
_NUM_TOKEN = re.compile(r"(?<![A-Za-z0-9.,])(?:\d[\d,.]*\d|\d)")


def parse_number(raw: str, decimal_comma: bool = False, percent: bool = False) -> float | int | None:
    """Digits only. Applies the ambiguity rules of value-forms.md; returns None when the number reads as nothing."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        num = float(raw.replace(",", ""))
    elif re.fullmatch(r"\d+", raw):
        num = float(raw)
    elif re.fullmatch(r"\d+\.\d+", raw):
        if re.fullmatch(r"\d+\.\d{3}", raw) and not percent:
            return None
        num = float(raw)
    elif decimal_comma and re.fullmatch(r"\d+,\d{1,2}", raw):
        num = float(raw.replace(",", "."))
    else:
        return None
    return int(num) if num.is_integer() else num


_WORD_NUM_RX = re.compile(
    r"\b(?:(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[- ](?:one|two|three|four|five|six|seven|"
    r"eight|nine))?|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|"
    r"sixteen|seventeen|eighteen|nineteen|a dozen|a hundred|(?:one|two|three|four|five|six|seven|eight|nine|ten) "
    r"hundred)\b", re.I)


def parse_word_number(raw: str) -> int | None:
    s = raw.lower().strip()
    if s == "a dozen":
        return 12
    if s == "a hundred":
        return 100
    m = re.fullmatch(r"(\w+) hundred", s)
    if m and m.group(1) in WORD_NUMBERS:
        return WORD_NUMBERS[m.group(1)] * 100
    parts = re.split(r"[- ]", s)
    if len(parts) == 1 and parts[0] in WORD_NUMBERS:
        return WORD_NUMBERS[parts[0]]
    if len(parts) == 2 and parts[0] in WORD_NUMBERS and parts[1] in WORD_NUMBERS and WORD_NUMBERS[parts[0]] >= 20:
        return WORD_NUMBERS[parts[0]] + WORD_NUMBERS[parts[1]]
    return None


def _overlaps(spans: list[tuple[int, int]], a: int, b: int) -> bool:
    return any(a < e and b > s for s, e in spans)


def _num(v: float) -> float | int:
    return int(v) if float(v).is_integer() else v


@dataclass
class NumTok:
    start: int
    end: int
    raw: str
    value: float | int | None
    word: bool = False


def number_tokens(text: str, percent_ok: bool = False) -> list[NumTok]:
    """Digit numbers and number words with offsets (value None = ambiguous digits)."""
    out: list[NumTok] = []
    for m in _NUM_TOKEN.finditer(text):
        out.append(NumTok(m.start(), m.end(), m.group(), None))
    for m in _WORD_NUM_RX.finditer(text):
        out.append(NumTok(m.start(), m.end(), m.group(), parse_word_number(m.group()), True))
    out.sort(key=lambda t: t.start)
    return out


class ValueFinder:
    """Finds typed values in one sentence (or any string)."""

    def __init__(self, known_units: set[str] | None = None, accept_unknown_units: bool = False):
        self.known_units = known_units or set()
        self.accept_unknown_units = accept_unknown_units

    # -- helpers --------------------------------------------------------
    @staticmethod
    def _decorate(text: str, v: Val, date: bool = False) -> Val:
        before = text[max(0, v.start - 30):v.start]
        after = text[v.end:v.end + 30]
        if APPROX_BEFORE.search(before) or APPROX_AFTER.match(after):
            v.approx = True
        for rx, op in (DATE_CMP_BEFORE if date else CMP_BEFORE):
            if rx.search(before):
                v.cmp_op = op
                break
        if not v.cmp_op and not date:
            for rx, op in CMP_AFTER:
                if rx.match(after):
                    v.cmp_op = op
                    break
        # range: "10-20 GB", "10 to 20 GB", "between 10 and 20", "1 or 2 days"
        if not date:
            if (re.search(r"\d[\d,.]*\s*[A-Za-z%]{0,12}\s*(?:-|\u2013|\u2014|\bto\b)\s*(?:US\$|[\u20ac$\u00a3])?\s*$", before)
                    or re.search(r"\bbetween\s+(?:[\u20ac$\u00a3]\s*)?$", before, re.I)
                    or re.search(r"\bbetween\s+[^.,;]{1,25}?\band\s+(?:US\$|[\u20ac$\u00a3])?\s*$", before, re.I)):
                v.rng = True
            if re.search(r"\d\s+or\s+$", before) and not re.search(r"[\u20ac$\u00a3%]|[A-Za-z]\s+or\s+$", before):
                v.rng = True
            if re.match(r"^\s*(?:-|\u2013|\u2014|to)\s*(?:[\u20ac$\u00a3]|US\$)?\d", after) and v.kind != "version":
                v.rng = True
            if re.match(r"^\s+(?:and|or)\s+(?:[\u20ac$\u00a3]\s*)?\d[\d,.]*\s*(?:[A-Za-z%]|$)", after) and re.search(r"\bbetween\s", before, re.I):
                v.rng = True
        if INVISIBLE.search(text[max(0, v.start - 1):v.end + 1]):
            v.invisible = True
        m = re.search(r"\b(since|from|until|till|as of|as at)\s*$", before, re.I)
        if m:
            v.qualifier = m.group(1).lower()
        return v

    # -- dates ----------------------------------------------------------
    def dates(self, text: str, taken: list[tuple[int, int]]) -> list[Val]:
        out: list[Val] = []

        def add(m: re.Match, value: str) -> None:
            if _overlaps(taken, m.start(), m.end()):
                return
            v = Val("date", {"kind": "date", "value": value}, m.start(), m.end(), m.group())
            out.append(self._decorate(text, v, date=True))
            taken.append((m.start(), m.end()))

        def mon(s: str) -> int | None:
            key = s.lower().rstrip(".")
            if key == "may" and not s.startswith("May"):
                return None
            return MONTH_ALL.get(key)

        def valid_day(y: int, mth: int, d: int) -> bool:
            import calendar
            return 1 <= mth <= 12 and 1 <= d <= calendar.monthrange(y, mth)[1]

        for m in re.finditer(r"(?<![\d.-])(\d{4})-(\d{2})(?:-(\d{2}))?(?![\d-])", text):
            y, mo = int(m.group(1)), int(m.group(2))
            if m.group(3):
                if valid_day(y, mo, int(m.group(3))):
                    add(m, m.group(0))
            elif 1 <= mo <= 12:
                add(m, m.group(0))
        for m in re.finditer(r"(?<![\w])(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?(" + _MONTH_RX + r")[\s,]*(\d{4})(?!\d)",
                             text, re.I):
            mo = mon(m.group(2))
            y, d = int(m.group(3)), int(m.group(1))
            if mo and valid_day(y, mo, d):
                add(m, f"{y:04d}-{mo:02d}-{d:02d}")
        for m in re.finditer(r"(?<![\w])(" + _MONTH_RX + r")\s*(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})(?!\d)", text, re.I):
            mo = mon(m.group(1))
            y, d = int(m.group(3)), int(m.group(2))
            if mo and valid_day(y, mo, d):
                add(m, f"{y:04d}-{mo:02d}-{d:02d}")
        for m in re.finditer(r"(?<![\w])(" + _MONTH_RX + r")\s*,?\s*(\d{4})(?!\d)", text, re.I):
            mo = mon(m.group(1))
            if mo:
                add(m, f"{int(m.group(2)):04d}-{mo:02d}")
        for m in re.finditer(r"\b(?:in|since|from|during|until|till|of|before|after|by|as of)\s+((?:19|20)\d{2})(?![\d,.%]|\s*(?:customers|users|people))", text, re.I):
            s, e = m.start(1), m.end(1)
            if not _overlaps(taken, s, e):
                v = Val("date", {"kind": "date", "value": m.group(1)}, s, e, m.group(1))
                out.append(self._decorate(text, v, date=True))
                taken.append((s, e))
        out.sort(key=lambda v: v.start)
        return out

    @staticmethod
    def dead_dates(text: str, taken: list[tuple[int, int]]) -> None:
        """Mark things that look like dates but read as nothing, so their numbers are not reused."""
        for rx in (r"\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b", r"\bQ[1-4]\s*(?:\d{4})?\b", r"\bH[12]\s*(?:\d{4})?\b",
                   r"(?<![\w])(?:" + _MONTH_RX + r")\s+\d{1,2}(?:st|nd|rd|th)?(?![\w,]|\s*,?\s*\d{4})",
                   r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTH_RX + r"(?![\w.]|\s*,?\s*\d{4})"):
            for m in re.finditer(rx, text, re.I if "Q" not in rx else 0):
                if "May" in m.group() or not re.match(r"may", m.group().strip(), re.I) or m.group().strip().startswith("May"):
                    taken.append((m.start(), m.end()))

    # -- money ----------------------------------------------------------
    def money(self, text: str, taken: list[tuple[int, int]]) -> list[Val]:
        out: list[Val] = []
        amount = r"\d[\d,.]*\d|\d"
        scale = r"(?:\s?(?:(?i:million|billion|thousand|bn)|M|k)(?![A-Za-z]))?"
        codes = "|".join(sorted(CURRENCY_CODES))
        period = (r"(?:\s*(?:per|/|a)\s*(?:user|seat|member|editor|device)\b)?"
                  r"(?:(?i:\s*(?:/\s*|\bper\s+|\ba\s+|\beach\s+)(day|week|wk|month|mo|year|yr|annum)\b|\s+(monthly|annually|yearly|daily|weekly)\b))?")
        rx_pre = re.compile(r"(?<![A-Za-z0-9])(US\$|[\u20ac$\u00a3]|(?:" + codes + r")\b)\s?(" + amount + r")(" + scale + r")" + period)
        rx_post = re.compile(r"(?<![A-Za-z0-9.,])(" + amount + r")(" + scale + r")\s?((?:" + codes + r")\b|(?i:euros?|dollars?|lei)\b)" + period)
        found = []
        for m in rx_pre.finditer(text):
            found.append((m.start(), m.end(), m.group(1), m.group(2), m.group(3), m.group(4) or m.group(5)))
        for m in rx_post.finditer(text):
            found.append((m.start(), m.end(), m.group(3), m.group(1), m.group(2), m.group(4) or m.group(5)))
        found.sort()
        used_end = -1
        for s, e, cur_raw, amt, sc, per in found:
            if s < used_end or _overlaps(taken, s, e):
                continue
            sc = sc.strip()
            cur = CURRENCY_SYMBOLS.get(cur_raw) or (cur_raw if cur_raw in CURRENCY_CODES else None) or CURRENCY_WORDS.get(cur_raw.lower())
            if not cur:
                continue
            num = parse_number(amt, decimal_comma=True)
            if num is None:
                v = Val("money", {"kind": "money", "value": 0, "currency": cur}, s, e, text[s:e], invisible=True)
                v.tags.append("ambiguous-number")
                out.append(v)
            else:
                if sc:
                    num = _num(num * SCALES[sc if sc in SCALES else sc.lower()])
                value = {"kind": "money", "value": num, "currency": cur}
                if per:
                    value["per"] = PERIODS[per.lower()]
                out.append(self._decorate(text, Val("money", value, s, e, text[s:e])))
            taken.append((s, e))
            used_end = e
        out.sort(key=lambda v: v.start)
        return out
    # -- percent --------------------------------------------------------
    def percent(self, text: str, taken: list[tuple[int, int]]) -> list[Val]:
        out: list[Val] = []
        rx = re.compile(r"(?<![A-Za-z0-9.,])(\d[\d,.]*\d|\d)\s?(?:%|percent\b|per cent\b)", re.I)
        for m in rx.finditer(text):
            if _overlaps(taken, m.start(), m.end()):
                continue
            num = parse_number(m.group(1), percent=True)
            if num is None:
                taken.append((m.start(), m.end()))
                continue
            v = Val("percent", {"kind": "percent", "value": num}, m.start(), m.end(), m.group())
            out.append(self._decorate(text, v))
            taken.append((m.start(), m.end()))
        for m in re.finditer(_WORD_NUM_RX.pattern + r"\s?(?:percent\b|per cent\b)", text, re.I):
            if _overlaps(taken, m.start(), m.end()):
                continue
            nw = re.match(_WORD_NUM_RX, m.group())
            num = parse_word_number(nw.group()) if nw else None
            if num is None:
                continue
            v = Val("percent", {"kind": "percent", "value": num}, m.start(), m.end(), m.group())
            out.append(self._decorate(text, v))
            taken.append((m.start(), m.end()))
        out.sort(key=lambda v: v.start)
        return out

    # -- versions -------------------------------------------------------
    def versions(self, text: str, taken: list[tuple[int, int]], name_spans: list[tuple[int, int]],
                 late: bool = False) -> list[Val]:
        out: list[Val] = []
        if not late:
            for m in re.finditer(r"(?<![A-Za-z0-9.])(?:version|ver\.?|v)\s?(\d+(?:\.\d+){0,3})(?![\d]|\.\d)", text, re.I):
                if _overlaps(taken, m.start(), m.end()):
                    continue
                v = Val("version", {"kind": "version", "value": m.group(1)}, m.start(), m.end(), m.group())
                out.append(self._decorate(text, v))
                taken.append((m.start(), m.end()))
            for m in re.finditer(r"(?<![\w.,])(\d+(?:\.\d+){2,3})(?![\w]|\.\d)", text):
                if _overlaps(taken, m.start(), m.end()):
                    continue
                if re.fullmatch(r"\d{1,3}(\.\d{3}){2,}", m.group()):
                    taken.append((m.start(), m.end()))   # 1.000.000 reads as nothing
                    continue
                v = Val("version", {"kind": "version", "value": m.group()}, m.start(), m.end(), m.group())
                out.append(self._decorate(text, v))
                taken.append((m.start(), m.end()))
        else:
            # capitalised name directly followed by a number with one decimal point
            for m in re.finditer(r"(?<![\w.,])(\d+\.\d+)(?![\w%]|\.\d)", text):
                if _overlaps(taken, m.start(), m.end()):
                    continue
                before = text[:m.start()]
                nm = re.search(r"([A-Z][A-Za-z]+)\s$", before)
                if not nm:
                    continue
                if re.fullmatch(r"\d+\.\d{3}", m.group()):
                    continue
                v = Val("version", {"kind": "version", "value": m.group()}, m.start(), m.end(), m.group())
                v.tags.append("name-prefixed")
                out.append(self._decorate(text, v))
                taken.append((m.start(), m.end()))
        out.sort(key=lambda v: v.start)
        return out

    # -- durations ------------------------------------------------------
    def durations(self, text: str, taken: list[tuple[int, int]]) -> list[Val]:
        out: list[Val] = []
        unit_alt = "|".join(sorted(DUR_WORDS, key=len, reverse=True))
        sym_alt = "|".join(sorted(DUR_SYMBOLS, key=len, reverse=True))
        # digits / number words + unit
        for tok in number_tokens(text):
            if tok.value is None and not tok.word:
                val = parse_number(tok.raw)
            else:
                val = tok.value
            after = text[tok.end:]
            m = re.match(r"(?:-|\s)?(" + unit_alt + r")(?![A-Za-z])", after, re.I)
            sym = None
            if not m:
                sym = re.match(r"\s?(" + sym_alt + r")(?![A-Za-z0-9\u00b5])", after)
                if sym and not tok.word:
                    # single letters must be glued or spaced digits, lower-case; avoid "5 s" in names
                    pass
                else:
                    sym = None
            if not m and not sym:
                continue
            mm = m or sym
            if _overlaps(taken, tok.start, tok.end + mm.end()):
                continue
            unit_raw = mm.group(1)
            if m:
                if len(unit_raw) == 1 and not unit_raw.islower():
                    continue
                unit, mult = DUR_WORDS[unit_raw.lower()]
            else:
                unit, mult = DUR_SYMBOLS[unit_raw]
            if val is None:
                s, e = tok.start, tok.end + mm.end()
                v = Val("duration", {"kind": "duration", "value": 0, "unit": unit}, s, e, text[s:e], invisible=True)
                v.tags.append("ambiguous-number")
                out.append(v)
                taken.append((s, e))
                continue
            s, e = tok.start, tok.end + mm.end()
            # "a day" style rate directly after a count: "1,000 requests a day" is not reached because the number
            # is not adjacent; "3 per day" is a rate too
            if re.search(r"\b(?:per|a|each|every)\s*$", text[max(0, s - 6):s], re.I) and not tok.word:
                pass
            v = Val("duration", {"kind": "duration", "value": _num(val * mult), "unit": unit}, s, e, text[s:e])
            out.append(self._decorate(text, v))
            taken.append((s, e))
        # "for a week", "under a second", "a fortnight"
        for m in re.finditer(r"\b(?:under|within|in|for|over|than|at least|at most|to|only|just|about|around)\s+(an?)\s+(" +
                             unit_alt + r")(?![A-Za-z])", text, re.I):
            s, e = m.start(1), m.end()
            if _overlaps(taken, s, e):
                continue
            unit, mult = DUR_WORDS[m.group(2).lower()]
            v = Val("duration", {"kind": "duration", "value": mult, "unit": unit}, s, e, text[s:e])
            prefix = m.group(0)[:m.start(1) - m.start()].strip().lower()
            if prefix in {"under"}:
                v.cmp_op = "lt"
            elif prefix in {"within", "at most"}:
                v.cmp_op = "le"
            elif prefix in {"over", "than", "at least"}:
                v.cmp_op = "gt" if prefix == "over" else ("ge" if prefix == "at least" else None)
            if prefix in {"about", "around"}:
                v.approx = True
            if prefix == "than":
                v.cmp_op = v.cmp_op or "gt"
            out.append(v)
            taken.append((s, e))
        out.sort(key=lambda v: v.start)
        return out

    # -- quantities -----------------------------------------------------
    def quantities(self, text: str, taken: list[tuple[int, int]]) -> list[Val]:
        out: list[Val] = []
        sym_alt = "|".join(sorted(UNIT_SYMBOLS, key=len, reverse=True))
        word_alt = "|".join(sorted(UNIT_WORDS, key=len, reverse=True))
        sc_alt = r"million|billion|thousand|bn|M|k"
        for tok in number_tokens(text):
            if _overlaps(taken, tok.start, tok.end):
                continue
            val = parse_number(tok.raw) if not tok.word else tok.value
            tail = text[tok.end:]
            # physical units first
            ph = re.match(r"(?:-|\s?)(" + word_alt + r")(?![A-Za-z])", tail, re.I)
            sy = re.match(r"\s?(" + sym_alt + r")(?![A-Za-z0-9])", tail)
            quote = re.match(r"([\"\u2033])", tail)
            unit = end = None
            if sy and not tok.word:
                unit, end = UNIT_SYMBOLS[sy.group(1)], tok.end + sy.end()
            elif ph:
                unit, end = UNIT_WORDS[ph.group(1).lower()], tok.end + ph.end()
            elif quote and not tok.word:
                unit, end = "inch", tok.end + 1
            mult = 1.0
            sc_len = 0
            if unit is None:
                sm = re.match(r"\s?(" + sc_alt + r")(?![A-Za-z])", tail)
                if sm and not (sm.group(1) == "M" and False):
                    # "10M users", "1.2 million users"; "k" only lower case, "M" only upper case
                    mult = SCALES[sm.group(1)]
                    sc_len = sm.end()
                tail2 = tail[sc_len:]
                # counted noun: up to two words between number and noun
                noun = None
                noun_end = None
                guess = False
                pos = 0
                known: list[tuple[str, int, bool]] = []
                for k in range(3):
                    w = _WORD_AT.match(tail2, pos)      # contiguous words only: no digits/punctuation in between
                    if not w:
                        break
                    pos = w.end()
                    cand = w.group(1).lower()
                    sing = singular(cand)
                    if sing in self.known_units or cand in self.known_units:
                        known.append((sing, sc_len + w.end(), cand.endswith("s") or cand == "people"))
                    elif k == 0 and self.accept_unknown_units and cand.endswith("s") and len(cand) > 3 and cand not in NOT_UNITS:
                        noun, noun_end, guess = sing, sc_len + w.end(), True
                if known:
                    # first plural counted noun ("4 data centre sites" -> site, "74 employees people" -> employee), else the last
                    plural = [x for x in known if x[2]]
                    noun, noun_end, _ = plural[0] if plural else known[-1]
                    guess = False
                if noun is None:
                    continue
                unit, end = noun, tok.end + noun_end
                if unit in {"ms", "s", "min", "h", "day", "week", "month", "year"}:
                    continue
                v = Val("quantity", {"kind": "quantity", "value": 0, "unit": unit}, tok.start, end, text[tok.start:end])
                v.unit_guess = guess
            else:
                v = Val("quantity", {"kind": "quantity", "value": 0, "unit": unit}, tok.start, end, text[tok.start:end])
            # plain 4-digit 1900..2099 is a year, never a count (but physical units are fine)
            if val is not None and 1900 <= val <= 2099 and re.fullmatch(r"\d{4}", tok.raw) and unit not in UNIT_SYMBOLS.values():
                continue
            if val is None:
                v.invisible = True
                v.tags.append("ambiguous-number")
            else:
                v.value["value"] = _num(val * mult)
            # lower-case "m" scale is a metre, handled above; skip if tail starts with lone "m"
            out.append(self._decorate(text, v))
            taken.append((tok.start, end))
        out.sort(key=lambda v: v.start)
        return out


_WORD_AT = re.compile(r"[ \t-]+([A-Za-z][A-Za-z']*)")
NOT_UNITS = {"times", "others", "ones", "things", "years", "days", "hours", "minutes", "weeks", "months", "seconds",
             "others", "more", "less", "ways", "reasons", "points", "percent", "ago", "plus", "was", "has", "is",
             "this", "its", "lots", "bits", "kinds", "sorts", "types", "days", "yes", "does", "goes", "its", "us"}


def singular(word: str) -> str:
    w = word.lower()
    if w in {"people", "persons"}:
        return "person"
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w



