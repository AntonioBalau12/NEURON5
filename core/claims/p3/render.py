"""Deterministic rendering of values and claim sentences, written to the forms of value-forms.md / claim-forms.md.

Everything here is *generation*; correctness is verified separately by textcheck.py (independent re-reader) and
foundation.validate_claim_text.  Rendering returns ``(text, None)`` or ``(None, reason)``; it never guesses.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from .textcheck import MONTHS, PHYS_UNITS, Names

AS_OF = date(2026, 10, 29)

CUR_SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}
DURATION_WORDS = {"ms": ("millisecond", "milliseconds"), "s": ("second", "seconds"), "min": ("minute", "minutes"), "h": ("hour", "hours"),
                  "day": ("day", "days"), "week": ("week", "weeks"), "month": ("month", "months"), "year": ("year", "years")}
ACRONYMS = {"ceo", "cto", "eu", "ai", "api", "sdk", "sdks", "ide", "ides", "sla", "ar", "cli", "sso", "nps", "io", "url"}
ACRONYM_PLURALS = {"sdks": "SDKs", "ides": "IDEs"}
ACRONYM_NOUNS = {"ide": ("IDE", "IDEs"), "sdk": ("SDK", "SDKs"), "api": ("API", "APIs")}
WORD_OVERRIDE = {"soc2_certified": "SOC 2 certified", "soc2_auditor": "SOC 2 auditor", "soc2_audit_start": "SOC 2 audit start"}
# words that make a text unsafe (calendar/time words, comparison words that would change the value read)
UNSAFE_ATTR_WORDS = re.compile(r"(?<![a-z])(?:since|last|next|ago|until|till|before|after|earlier|later|then|once|soon|today|now|"
                               r"over|under|above|below|within|about|around|max|maximum|minimum|january|february|march|april|may|june|july|"
                               r"august|september|october|november|december|spring|summer|autumn|winter)(?![a-z])")


def attr_words(attr: str) -> str:
    if attr in WORD_OVERRIDE:
        return WORD_OVERRIDE[attr]
    parts = attr.split("_")
    out = []
    for p in parts:
        out.append(ACRONYM_PLURALS.get(p) or (p.upper() if p in ACRONYMS else p))
    return " ".join(out)


def attr_has_unsafe_words(attr: str) -> str | None:
    m = UNSAFE_ATTR_WORDS.search(attr.replace("_", " ").lower())
    return m.group(0) if m else None


def article(words: str) -> str:
    return "an" if words[:1].lower() in "aeiou" else "a"


def plural(noun: str) -> str:
    if noun == "person":
        return "people"
    if noun.endswith("y") and len(noun) > 1 and noun[-2] not in "aeiou":
        return noun[:-1] + "ies"
    if noun.endswith(("s", "x", "ch", "sh", "z")):
        return noun + "es"
    return noun + "s"


# ----------------------------------------------------------------------------------------------
# numbers and values
# ----------------------------------------------------------------------------------------------
def fmt_num(x: Any, percent: bool = False) -> tuple[str | None, str | None]:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None, "number_not_numeric"
    f = float(x)
    if f != f or f in (float("inf"), float("-inf")) or f < 0:
        return None, "number_negative_or_nan"
    if f.is_integer():
        return f"{int(f):,}", None
    s = format(f, ".6f").rstrip("0")
    ip, dp = s.split(".")
    if len(dp) == 3 and not percent:
        return None, "number_three_decimals_ambiguous"
    if len(dp) > 3 and not percent:
        return None, "number_too_many_decimals"
    if len(dp) > 3:
        return None, "number_too_many_decimals"
    return f"{int(ip):,}.{dp}", None


def date_parts(v: str) -> tuple[int, int | None, int | None] | None:
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", v)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else None
    d = int(m.group(3)) if m.group(3) else None
    try:
        if d:
            date(y, mo, d)
        elif mo and not 1 <= mo <= 12:
            return None
    except ValueError:
        return None
    return y, mo, d


def date_text(v: str) -> tuple[str | None, str | None, str | None]:
    """(plain, preposition, reason).  '24 March 2026' + 'on', 'March 2026' + 'in', '2025' + 'in'."""
    p = date_parts(str(v))
    if p is None:
        return None, None, "date_unparseable"
    y, mo, d = p
    if d:
        return f"{d} {MONTHS[mo - 1]} {y}", "on", None
    if mo:
        return f"{MONTHS[mo - 1]} {y}", "in", None
    if not 1900 <= y <= 2099:
        return None, None, "year_out_of_range"
    return f"{y}", "in", None


def render_value(v: Mapping[str, Any], names: Names, allow_unlisted_names: bool = False, attr: str | None = None) -> tuple[str | None, str | None]:
    """Value -> the text written exactly as value-forms.md reads it.  Booleans and dates are handled by the caller."""
    k = v.get("kind")
    if v.get("op") not in (None, "eq"):
        return None, "value_has_op"
    if k == "money":
        n, err = fmt_num(v.get("value"))
        if err:
            return None, err
        sym = CUR_SYMBOL.get(v.get("currency"))
        if sym is None:
            return None, "currency_not_rendered"
        per = v.get("per")
        return f"{sym}{n}" + (f" per {per}" if per else ""), None
    if k == "percent":
        n, err = fmt_num(v.get("value"), percent=True)
        return (f"{n}%", None) if not err else (None, err)
    if k == "duration":
        n, err = fmt_num(v.get("value"))
        if err:
            return None, err
        sing, plur = DURATION_WORDS[v["unit"]]
        return f"{n} {sing if float(v['value']) == 1 else plur}", None
    if k == "quantity":
        n, err = fmt_num(v.get("value"))
        if err:
            return None, err
        u = v.get("unit")
        if u in PHYS_UNITS and u not in ("in",):
            return f"{n} {u}", None
        if u == "in":
            return f"{n} inch", None
        if u in ACRONYM_NOUNS:
            return f"{n} {ACRONYM_NOUNS[u][0] if float(v['value']) == 1 else ACRONYM_NOUNS[u][1]}", None
        return f"{n} {u if float(v['value']) == 1 else plural(u)}", None
    if k == "version":
        s = str(v.get("value"))
        if not re.fullmatch(r"\d+(\.\d+)*", s):
            return None, "version_unparseable"
        return f"version {s}", None
    if k == "date":
        plain, _, err = date_text(str(v.get("value")))
        return (plain, None) if plain else (None, err)
    if k == "name":
        s = str(v.get("value"))
        if names.resolve(s) is None and not allow_unlisted_names:
            return None, "name_value_not_in_lexicon"
        return s, None
    return None, "kind_not_rendered"


# ----------------------------------------------------------------------------------------------
# attribute predicates (the part of the sentence after the subject)
# ----------------------------------------------------------------------------------------------
MONEY_PRED = {
    "price": "costs {V}", "annual_price": "has an annual price of {V}", "cash": "holds {V} in cash", "revenue": "reported revenue of {V}",
    "guidance": "gave guidance of {V}", "rent": "pays rent of {V}", "free_credit": "offers {V} in free credit",
    "cost_per_hire": "has a cost per hire of {V}", "referral_bonus": "pays a referral bonus of {V}",
    "top_bug_bounty": "pays a top bug bounty of {V}", "max_trade_in_credit": "offers a top trade-in credit of {V}",
    "ticket_price": "sells tickets for {V}", "extra_seat_price": "charges {V} for each extra seat", "series_a_amount": "raised {V} in its Series A",
    "price_per_user": "costs {V} per user", "pro_price": "charges {V} for its pro tier",
}
# pred overrides for quantity attributes whose generic form would use a comparison word (max/min) or read oddly
LIMIT_PRED = {
    "max_upload_size": "has an upload size limit of {V}", "max_file_size": "has a file size limit of {V}", "max_cells": "has a cell limit of {V}",
    "max_guests": "has a guest limit of {V}", "max_participants": "has a participant limit of {V}",
    "max_call_length": "has a call length limit of {V}", "max_output_length": "has an output length limit of {V}",
    "maximum_seats": "has a seat limit of {V}", "minimum_seats": "requires {V} to start", "minimum_nodes": "requires {V} to start",
    "units_sold": "has sold {V}", "context_window": "has a context window of {V}", "waitlist": "has a waitlist of {V}",
}
PERCENT_PRED = {"customers_in_the_eu": "has {V} of its customers in the EU"}
DATE_PRED = {  # {DP} = 'on 24 March 2026' / 'in March 2026' / 'in 2025'
    "joined": "joined {DP}", "launched": "launched {DP}", "founded": "was founded {DP}", "released": "was released {DP}",
    "opened": "opened {DP}", "announced": "was announced {DP}", "published": "was published {DP}", "date": "{TENSE} place {DP}",
    "beta_opened": "opened its beta {DP}", "generally_available": "became available {DP}",
}
NAME_PRED = {
    "city": "takes place in {V}", "headquarters": "is headquartered in {V}", "lead": "is led by {V}", "head": "is headed by {V}",
    "venue": "takes place at {V}", "cloud_provider": "runs on {V}", "host": "is hosted by {V}", "ceo": "has {V} as its CEO",
    "cto": "has {V} as its CTO", "run_by": "is run by {V}", "owner": "is owned by {V}", "executive_sponsor": "has {V} as its executive sponsor",
    "executive_owner": "has {V} as its executive owner", "previous_employer": "has {V} as its previous employer",
}
# boolean attributes: (positive predicate, negative predicate); the attribute's own words must appear verbatim
BOOL_IS = {"anonymous", "carbon_neutral", "discontinued", "eu_hosted", "externally_audited", "fully_remote", "generally_available",
           "livestreamed", "open_source", "replay_available", "soc2_certified"}
BOOL_CUSTOM = {
    "had_major_outage": ("had major outage", "has not had major outage"),
    "raised_series_a": ("raised Series A", "has not raised Series A"),
    "raised_series_b": ("raised Series B", "has not raised Series B"),
    "chairs_audit_committee": ("chairs audit committee", "never chairs audit committee"),
    "independent_director": ("is an independent director", "is not an independent director"),
    "integration_partner_of_flawless": ("is an integration partner of flawless", "is not an integration partner of flawless"),
    "is_engineering_hub": ("is engineering hub", "is not engineering hub"),
    "is_headquarters": ("is headquarters", "is not headquarters"),
}


def bool_pred(attr: str, value: bool) -> str:
    w = attr_words(attr)
    if attr in BOOL_CUSTOM:
        return BOOL_CUSTOM[attr][0 if value else 1]
    if attr in BOOL_IS:
        return f"is {w}" if value else f"is not {w}"
    return f"has {w}" if value else f"does not have {w}"


VALUE_NOUN = {"max_trade_in_credit": "top trade-in credit"}   # wording used instead of the attribute words where those contain max/min
MASS = {"storage", "memory", "weight", "revenue", "cash", "guidance", "footprint", "capacity", "free_storage", "mailbox_storage",
        "storage_per_user", "base_storage", "index_size", "rent", "uptime_sla", "history_retention", "data_retention"}


def predicate(attr: str, value: Mapping[str, Any], names: Names, allow_unlisted_names: bool = False,
              as_of: date = AS_OF) -> tuple[str | None, str | None]:
    """Predicate (after the subject) that states ``value`` of ``attr``.  Reasons are stable codes."""
    unsafe = attr_has_unsafe_words(attr)
    k = value.get("kind")
    if k == "boolean":
        if unsafe:
            return None, f"attribute_words_unsafe:{unsafe}"
        if not isinstance(value.get("value"), bool):
            return None, "boolean_not_bool"
        return bool_pred(attr, value["value"]), None
    if attr in LIMIT_PRED or attr in VALUE_NOUN:
        unsafe = None
    if unsafe:
        return None, f"attribute_words_unsafe:{unsafe}"
    if re.search(r"\d", attr):
        return None, "attribute_words_have_digits"
    w = attr_words(attr)
    if k == "date":
        plain, prep, err = date_text(str(value.get("value")))
        if err:
            return None, err
        dp = f"{prep} {plain}"
        tense = "took" if str(value["value"]) <= as_of.isoformat()[: len(str(value["value"]))] else "takes"
        if attr in DATE_PRED:
            return DATE_PRED[attr].replace("{DP}", dp).replace("{TENSE}", tense), None
        if prep == "on" or True:
            return f"has {article(w)} {w} of {plain}", None
    vt, err = render_value(value, names, allow_unlisted_names, attr)
    if err:
        return None, err
    if attr == "price_per_user" and k == "money" and value.get("per") == "month":
        vt = vt.replace(" per month", " per user per month")      # value-forms: 'per user' comes BEFORE the period
        return f"costs {vt}", None
    if k == "money":
        tpl = MONEY_PRED.get(attr)
        if tpl:
            return tpl.replace("{V}", vt), None
        return (f"has {w} of {vt}" if attr in MASS or w.endswith("s") else f"has {article(w)} {w} of {vt}"), None
    if k == "percent":
        tpl = PERCENT_PRED.get(attr)
        if tpl:
            return tpl.replace("{V}", vt), None
        return (f"has {w} of {vt}" if w.endswith("s") else f"has {article(w)} {w} of {vt}"), None
    if k == "name":
        tpl = NAME_PRED.get(attr)
        if tpl:
            return tpl.replace("{V}", vt), None
        return f"has {vt} as its {w}", None
    if k == "version":
        num = vt.split(" ", 1)[1]
        if attr == "version":
            return f"is at version {num}", None
        if w.lower().endswith("version"):
            prefix = w[: -len("version")].strip()
            return f"has {prefix + ' ' if prefix else ''}version {num}", None
        return f"has {article(w)} {w} of version {num}", None
    if k in ("quantity", "duration"):
        tpl = LIMIT_PRED.get(attr)
        if tpl:
            return tpl.replace("{V}", vt), None
        unit = value.get("unit")
        if k == "quantity" and unit and unit not in PHYS_UNITS and "_" not in attr and plural(unit) == attr:
            return f"has {vt}", None
        if attr in MASS or w.endswith("s"):
            return f"has {w} of {vt}", None
        return f"has {article(w)} {w} of {vt}", None
    return None, "kind_not_rendered"


# ----------------------------------------------------------------------------------------------
# sentence frames per claim type
# ----------------------------------------------------------------------------------------------
def _one_off_money(value: Mapping[str, Any]) -> bool:
    return value.get("kind") == "money" and not value.get("per")


def build_sentence(ctype: str, subject: str, attr: str, value: Mapping[str, Any], names: Names, allow_unlisted_names: bool = False,
                   as_of: date = AS_OF, event: str | None = None, link: str | None = None) -> tuple[str | None, str | None]:
    """One sentence for a fact / at_event / relation claim.  A one-off price (no billing period) ends in a bare number,
    which the repository's lightweight number check (foundation._number_is_mentioned) does not accept before the final
    full stop, so for those the value is put first: '€749 is the price of Hooly Pixel 10.'"""
    if _one_off_money(value):
        if ctype == "relation":
            return None, "one_off_money_relation_not_generated"
        unsafe = attr_has_unsafe_words(attr) if attr not in VALUE_NOUN else None
        if unsafe:
            return None, f"attribute_words_unsafe:{unsafe}"
        vt, err = render_value(value, names, allow_unlisted_names, attr)
        if err or vt is None:
            return None, err
        noun = VALUE_NOUN.get(attr) or attr_words(attr)
        tail = f" at {event}" if ctype == "at_event" else ""
        return f"{vt} is the {noun} of {subject}{tail}.", None
    pred, err = predicate(attr, value, names, allow_unlisted_names, as_of)
    if err or pred is None:
        return None, err
    if ctype == "fact":
        return f"{subject} {pred}.", None
    if ctype == "at_event":
        return f"{subject} {pred} at {event}.", None
    if ctype == "relation":
        return f"The {attr_words(link or '')} of {subject} {pred}.", None
    return None, "unknown_type"


def change_text(subject: str, attr: str, v_from: str, v_to: str) -> str:
    return f"{subject}'s {attr_words(attr)} went from {v_from} to {v_to}."


def boolean_change_clause(attr: str, value: bool) -> str:
    """State the Boolean value of the lexicon attribute explicitly."""
    return f'the statement "{attr_words(attr)}" being {"true" if value else "false"}'


def boolean_change_text(subject: str, attr: str, from_value: bool, to_value: bool) -> str:
    return (f"{subject} went from {boolean_change_clause(attr, from_value)} "
            f"to {boolean_change_clause(attr, to_value)}.")


COUNT_NOUN_PLURAL_ATTR = re.compile(r".*s$")
DATE_VERB = {"date": "took place", "launched": "launched", "joined": "joined", "founded": "was founded", "released": "was released",
             "opened": "opened", "announced": "was announced", "published": "was published"}
DATE_PHRASE = {"gt": "after", "lt": "before", "eq": "on the same day as"}


def compare_text(left: str, right: str, attr: str, op: str, vkind: str, unit: str | None = None) -> tuple[str | None, str | None]:
    """Compare sentence: left subject first, one phrase of the op list, then the right subject."""
    w = attr_words(attr)
    unsafe = attr_has_unsafe_words(attr)
    if vkind == "date":
        verb = DATE_VERB.get(attr)
        if verb is None:
            if unsafe:
                return None, f"attribute_words_unsafe:{unsafe}"
            if op == "gt":
                return f"{left} has {article(w)} {w} later than {right}.", None
            if op == "lt":
                return f"{left} has {article(w)} {w} earlier than {right}.", None
            return f"{left} has {article(w)} {w} on the same day as {right}.", None
        return f"{left} {verb} {DATE_PHRASE[op]} {right}.", None
    if unsafe:
        return None, f"attribute_words_unsafe:{unsafe}"
    if re.search(r"\d", attr):
        return None, "attribute_words_have_digits"
    if attr in ("price", "annual_price", "ticket_price", "extra_seat_price", "price_per_user", "pro_price") and vkind == "money":
        if attr == "price":
            return {"gt": f"{left} costs more than {right}.", "lt": f"{left} costs less than {right}.", "eq": f"{left} costs the same as {right}."}[op], None
        return {"gt": f"{left} has a higher {w} than {right}.", "lt": f"{left} has a lower {w} than {right}.", "eq": f"{left} has the same {w} as {right}."}[op], None
    if len(w.split()) > 3:
        return None, "attribute_words_too_long_for_phrase_gap"
    countable = vkind == "quantity" and unit is not None and unit not in PHYS_UNITS and (w.endswith("s") or plural(unit) in w.split())
    if countable:
        return {"gt": f"{left} has more {w} than {right}.", "lt": f"{left} has fewer {w} than {right}.", "eq": f"{left} has as many {w} as {right}."}[op], None
    if vkind == "duration":
        return {"gt": f"{left} has a longer {w} than {right}.", "lt": f"{left} has a shorter {w} than {right}.", "eq": f"{left} has the same {w} as {right}."}[op], None
    art = "" if (attr in MASS or w.endswith("s")) else "a "
    return {"gt": f"{left} has {art}higher {w} than {right}.", "lt": f"{left} has {art}lower {w} than {right}.", "eq": f"{left} has the same {w} as {right}."}[op], None
