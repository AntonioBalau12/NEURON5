"""Contract checks applied to every rendered candidate (form schema, lexicon, text rules, novelty, duplicates)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from .cf_common import CONTRACT_DIR
from foundation import SchemaValidator, _claim_semantic_key, _validate_form_names, validate_claim_text  # type: ignore

from . import textcheck
from .rules import Cand
from .store import Store, norm_text


class ContractChecker:
    def __init__(self, store: Store, novelty_texts: set[str],
                 validation_cache: dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, ...]]] | None = None):
        self.store = store
        self.entry_validator = SchemaValidator(CONTRACT_DIR / "entry.schema.json")
        self.novelty = novelty_texts
        self.seen_text: dict[str, str] = {}
        self.seen_key: dict[Any, str] = {}
        # The checks stored here depend only on the immutable form/text, unlike
        # novelty and duplicate handling below, which remains order-sensitive.
        self.validation_cache = validation_cache if validation_cache is not None else {}
        self.timings = {"contract_validation_seconds": 0.0, "novelty_filter_seconds": 0.0,
                        "semantic_dedup_seconds": 0.0, "validation_cache_lookup_seconds": 0.0}
        self.counts = {"novelty_rejections": 0, "text_duplicates": 0, "semantic_duplicates": 0,
                       "validation_cache_hits": 0, "validation_cache_misses": 0}

    def compare_table(self, c: Cand) -> str:
        return "date" if (c.type == "compare" and c.evidence.get("value_kind") == "date") else "amount"

    def check(self, c: Cand) -> Cand:
        """Run all contract checks; each failing check appends a reason.  Returns the candidate."""
        if c.status == "rejected" or c.form is None or c.text is None:
            return c
        validation_started = time.perf_counter()
        cache_key = json.dumps([c.type, c.text, c.form], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        cached = self.validation_cache.get(cache_key)
        self.timings["validation_cache_lookup_seconds"] += time.perf_counter() - validation_started
        if cached is None:
            validation_started = time.perf_counter()
            problems: list[tuple[str, str]] = []
            entry = {"id": "check-1", "type": c.type, "text": c.text, "form": c.form,
                     "tag": "true", "confidence": c.confidence}
            schema_errors = self.entry_validator.validate(entry)
            for e in schema_errors:
                problems.append(("form_schema", e))
            lex_errors: list[str] = []
            _validate_form_names(c.type, c.form, self.store.lexicon, 0, lex_errors)
            for e in lex_errors:
                problems.append(("lexicon", re.sub(r"^claim line \d+: ", "", e)))
            if not schema_errors:
                for code, msg in textcheck.check_text(c.type, c.text, c.form, self.store.names, self.compare_table(c)):
                    problems.append(("text_independent", f"{code}: {msg}"))
                for msg in validate_claim_text(c.type, c.text, c.form, self.store.lexicon):
                    problems.append(("text_foundation", msg))
            validation_flags: list[str] = []
            # Soft flags are deterministic properties of the validated sentence.
            if not problems:
                wanted = self._wanted_entities(c)
                others = {n for _, _, n in self.store.names.mentions(c.text)} - wanted
                if others:
                    validation_flags.append("other_entity_named:" + "|".join(sorted(others)))
            cached = (tuple(problems), tuple(validation_flags))
            self.validation_cache[cache_key] = cached
            self.counts["validation_cache_misses"] += 1
            self.timings["contract_validation_seconds"] += time.perf_counter() - validation_started
        else:
            self.counts["validation_cache_hits"] += 1
            problems = list(cached[0])
            validation_flags = list(cached[1])
        if problems:
            c.evidence["text_problems"] = [f"{s}: {m}" for s, m in problems]
            c.status, c.stage = "rejected", problems[0][0]
            for s, m in problems:
                r = f"{s}:{m.split(':')[0] if s == 'text_independent' else _short(m)}"
                if r not in c.reasons:
                    c.reasons.append(r)
            return c
        c.stage = "contract_valid"
        c.flags.extend(validation_flags)
        if '"provenance": "reconstructed.' in json.dumps(c.evidence):
            c.flags.append("uses_reconstructed_fact")
        # novelty & duplicates
        novelty_started = time.perf_counter()
        nt = norm_text(c.text)
        if nt in self.novelty:
            self.counts["novelty_rejections"] += 1
            self.timings["novelty_filter_seconds"] += time.perf_counter() - novelty_started
            return c.reject("novelty", "text_equals_an_input_row")
        if nt in self.seen_text:
            self.counts["text_duplicates"] += 1
            self.timings["novelty_filter_seconds"] += time.perf_counter() - novelty_started
            return c.reject("dedup", "duplicate_claim_text")
        semantic_started = time.perf_counter()
        key = _claim_semantic_key(c.type, c.form, self.store.lexicon)
        self.timings["semantic_dedup_seconds"] += time.perf_counter() - semantic_started
        if key is not None and key in self.seen_key:
            self.counts["semantic_duplicates"] += 1
            self.timings["novelty_filter_seconds"] += time.perf_counter() - novelty_started
            return c.reject("dedup", "semantic_duplicate")
        self.timings["novelty_filter_seconds"] += time.perf_counter() - novelty_started
        self.seen_text[nt] = c.ckey
        if key is not None:
            self.seen_key[key] = c.ckey
        c.status, c.stage = "accepted", "accepted"
        return c

    def _wanted_entities(self, c: Cand) -> set[str]:
        f = c.form or {}
        out: set[str] = set()
        names = self.store.names
        for k in ("subject", "event", "target"):
            if isinstance(f.get(k), str) and names.resolve(f[k]):
                out.add(names.resolve(f[k]))  # type: ignore[arg-type]
        for side in ("left", "right"):
            if isinstance(f.get(side), dict) and names.resolve(str(f[side].get("subject"))):
                out.add(names.resolve(str(f[side]["subject"])))  # type: ignore[arg-type]
        return out


def _short(msg: str) -> str:
    return re.sub(r"[^A-Za-z0-9_ ,.'-].*$", "", msg)[:60].strip() or msg[:60]
