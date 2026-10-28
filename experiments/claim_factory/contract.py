"""Contract checks applied to every rendered candidate (form schema, lexicon, text rules, novelty, duplicates)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cf_common import CONTRACT_DIR
from foundation import SchemaValidator, _claim_semantic_key, _validate_form_names, validate_claim_text  # type: ignore

import textcheck
from rules import Cand
from store import Store, norm_text


class ContractChecker:
    def __init__(self, store: Store, novelty_texts: set[str]):
        self.store = store
        self.entry_validator = SchemaValidator(CONTRACT_DIR / "entry.schema.json")
        self.novelty = novelty_texts
        self.seen_text: dict[str, str] = {}
        self.seen_key: dict[Any, str] = {}

    def compare_table(self, c: Cand) -> str:
        return "date" if (c.type == "compare" and c.evidence.get("value_kind") == "date") else "amount"

    def check(self, c: Cand) -> Cand:
        """Run all contract checks; each failing check appends a reason.  Returns the candidate."""
        if c.status == "rejected" or c.form is None or c.text is None:
            return c
        problems: list[tuple[str, str]] = []
        entry = {"id": "check-1", "type": c.type, "text": c.text, "form": c.form, "tag": "true", "confidence": c.confidence}
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
        # soft flags: other entities named in the sentence (not forbidden by the contract, recorded)
        if not problems:
            wanted = self._wanted_entities(c)
            others = {n for _, _, n in self.store.names.mentions(c.text)} - wanted
            if others:
                c.flags.append("other_entity_named:" + "|".join(sorted(others)))
        if problems:
            c.evidence["text_problems"] = [f"{s}: {m}" for s, m in problems]
            c.status, c.stage = "rejected", problems[0][0]
            for s, m in problems:
                r = f"{s}:{m.split(':')[0] if s == 'text_independent' else _short(m)}"
                if r not in c.reasons:
                    c.reasons.append(r)
            return c
        c.stage = "contract_valid"
        if '"provenance": "reconstructed.' in json.dumps(c.evidence):
            c.flags.append("uses_reconstructed_fact")
        # novelty & duplicates
        nt = norm_text(c.text)
        if nt in self.novelty:
            return c.reject("novelty", "text_equals_an_input_row")
        if nt in self.seen_text:
            return c.reject("dedup", "duplicate_claim_text")
        key = _claim_semantic_key(c.type, c.form, self.store.lexicon)
        if key is not None and key in self.seen_key:
            return c.reject("dedup", "semantic_duplicate")
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
