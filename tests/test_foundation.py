import csv
import json
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from foundation import (
    SchemaValidator, TypedValue, compare_values, evidence_audit, load_inputs,
    validate_claim_text, validate_output,
)
from runner import atomic_write_csv, run


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def write_fixture(folder: Path, records, lexicon=None):
    lexicon = lexicon or {
        "subjects": [
            {"name": "Élan", "aliases": ["E Lan"], "attributes": ["price", "storage", "joined", "lead"]},
            {"name": "Beta", "aliases": [], "attributes": ["price"]},
        ],
        "events": ["Launch Night"],
    }
    lex_path = folder / "lexicon.json"
    lex_path.write_text(json.dumps(lexicon, ensure_ascii=False), encoding="utf-8")
    csv_path = folder / "universe.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "text", "date", "label", "form"])
        writer.writeheader()
        writer.writerows(records)
    return csv_path, lex_path


def record(rid, text, when, label, facts):
    return {"id": rid, "text": text, "date": when, "label": label,
            "form": json.dumps(facts, ensure_ascii=False)}


class IngestionTests(unittest.TestCase):
    def test_utf8_aliases_and_practice_form_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("é1", "Élan costs €9.", "2026-01-01", "true", [
                {"subject": "E-Lan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR"}},
            ])])
            data = load_inputs(csv_path, lex_path)
            self.assertEqual(data.rows[0].facts[0].subject, "Élan")
            self.assertEqual(data.rows[0].facts[0].subject_spelling, "E-Lan")
            self.assertEqual(data.rows[0].facts[0].value.kind, "money")
            self.assertEqual(data.lexicon.resolve("  e LAN ").name, "Élan")
            self.assertFalse(data.issues)

    def test_malformed_date_label_and_form_are_retained_as_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [{"id": "x", "text": "x", "date": "not-a-date", "label": "maybe", "form": "{"}])
            data = load_inputs(csv_path, lex_path)
            self.assertEqual(data.rows[0].parse_status, "malformed")
            self.assertIsNone(data.rows[0].date)
            self.assertIsNone(data.rows[0].label)
            self.assertEqual(data.rows[0].facts, ())
            self.assertGreaterEqual(len(data.issues), 3)

    def test_missing_csv_fields_and_alias_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            lex = {"subjects": [
                {"name": "Alpha One", "aliases": ["Shared"], "attributes": ["price"]},
                {"name": "Beta Two", "aliases": [" shared "], "attributes": ["price"]},
            ], "events": []}
            csv_path, lex_path = write_fixture(path, [], lex)
            data = load_inputs(csv_path, lex_path)
            self.assertIsNone(data.lexicon.resolve("shared"))
            self.assertTrue(any("ambiguous lexicon alias" in x for x in data.issues))
            csv_path.write_text("id,text,date\nx,y,2026-01-01\n", encoding="utf-8")
            invalid = load_inputs(csv_path, lex_path)
            self.assertIsNone(invalid.lexicon)
            self.assertIn("missing required columns", invalid.issues[0])

    def test_missing_files_and_malformed_lexicon_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            missing = load_inputs(folder / "missing.csv", folder / "missing.json")
            self.assertIsNone(missing.lexicon)
            self.assertTrue(any("cannot load universe CSV" in x for x in missing.issues))
            csv_path, lex_path = write_fixture(folder, [])
            lex_path.write_text("{not-json", encoding="utf-8")
            malformed = load_inputs(csv_path, lex_path)
            self.assertIsNone(malformed.lexicon)
            self.assertTrue(any("cannot load lexicon JSON" in x for x in malformed.issues))

    def test_false_multi_fact_row_does_not_mark_each_fact_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = [
                {"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR"}},
                {"subject": "Beta", "attribute": "price", "value": {"kind": "money", "value": 12, "currency": "EUR"}},
            ]
            csv_path, lex_path = write_fixture(Path(tmp), [record("f", "Two prices.", "2026-01-01", "false", facts)])
            data = load_inputs(csv_path, lex_path)
            obs = [x for x in __import__("foundation").observations(data)]
            self.assertEqual(len(obs), 2)
            self.assertTrue(all(x.evidence_status == "row_false_atomic_status_unknown" for x in obs))
            audit = evidence_audit(data)
            self.assertEqual(audit["false_row_atomic_observations_not_attributed_as_false"], 2)

    def test_temporal_changes_are_not_promoted_to_as_of_facts(self):
        fact = lambda n: [{"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": n, "currency": "EUR"}}]
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [
                record("a", "old", "2026-01-01", "true", fact(9)),
                record("b", "new", "2026-02-01", "true", fact(10)),
            ])
            audit = evidence_audit(load_inputs(csv_path, lex_path))
            self.assertEqual(audit["attributes_with_multiple_observed_values"], 1)
            self.assertEqual(audit["facts_directly_observed_on_as_of_date"], 0)

    def test_schema_invalid_or_unknown_facts_are_never_confirmed(self):
        malformed = [{"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": "9", "currency": "EUR"}}]
        unknown_attribute = [{"subject": "Élan", "attribute": "not_in_lexicon", "value": {"kind": "money", "value": 9, "currency": "EUR"}}]
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [
                record("bad-value", "bad", "2026-01-01", "true", malformed),
                record("bad-attr", "bad", "2026-01-02", "true", unknown_attribute),
            ])
            data = load_inputs(csv_path, lex_path)
            self.assertEqual(data.rows[0].facts, ())
            self.assertEqual(data.rows[0].parse_status, "malformed")
            self.assertEqual(data.rows[1].parse_status, "malformed")
            self.assertFalse(any(x.evidence_status == "confirmed_true" for x in __import__("foundation").observations(data)))


class TypedComparisonTests(unittest.TestCase):
    def test_numeric_and_duration_comparisons_are_typed(self):
        self.assertTrue(compare_values(TypedValue("quantity", 10, unit="GB"), TypedValue("quantity", 2, unit="GB"), "gt"))
        self.assertTrue(compare_values(TypedValue("quantity", 1, unit="GB"), TypedValue("quantity", 1000, unit="MB"), "eq"))
        self.assertIsNone(compare_values(TypedValue("quantity", 2, unit="language"), TypedValue("quantity", 2, unit="customer"), "eq"))
        self.assertTrue(compare_values(TypedValue("money", 59, currency="EUR", per="month"), TypedValue("money", 39, currency="EUR", per="month"), "gt"))
        self.assertIsNone(compare_values(TypedValue("money", 59, currency="EUR"), TypedValue("money", 59, currency="USD"), "eq"))
        self.assertTrue(compare_values(TypedValue("duration", 14, unit="day"), TypedValue("duration", 2, unit="week"), "eq"))
        self.assertTrue(compare_values(TypedValue("duration", 12, unit="month"), TypedValue("duration", 1, unit="year"), "eq"))
        self.assertIsNone(compare_values(TypedValue("duration", 30, unit="day"), TypedValue("duration", 1, unit="month"), "eq"))
        self.assertIsNone(compare_values(TypedValue("percent", 99, op="gt"), TypedValue("percent", 99), "eq"))


class OutputTests(unittest.TestCase):
    def test_atomic_output_write_quotes_and_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "output.csv"
            atomic_write_csv(target, [{"id": "x", "type": "", "text": "comma, quote \"", "form": "", "label": "unsure", "confidence": ""}])
            with target.open(encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))
            self.assertEqual(row["text"], "comma, quote \"")
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

    def test_output_uses_official_schema_and_detects_original_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_rows = [record("p1", "Élan costs €9 per month.", "2026-01-01", "true", [])]
            csv_path, lex_path = write_fixture(Path(tmp), input_rows)
            data = load_inputs(csv_path, lex_path)
            out = Path(tmp) / "output.csv"
            row = {"id": "c1", "type": "fact", "text": "Élan costs €9 per month.",
                   "form": json.dumps({"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR", "per": "month"}}),
                   "label": "true", "confidence": "0.9"}
            atomic_write_csv(out, [row])
            errors = validate_output(out, data, CONTRACTS, expected_claims=1)
            self.assertTrue(any("duplicate of input text" in x for x in errors))
            row["text"] = "Élan costs €9 monthly."
            atomic_write_csv(out, [row])
            self.assertEqual(validate_output(out, data, CONTRACTS, expected_claims=1), [])

    def test_permuted_columns_and_semicolon_decimal_comma_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("p1", "known", "2026-01-01", "true", [])])
            data = load_inputs(csv_path, lex_path)
            out = Path(tmp) / "output.csv"
            fields = ["confidence", "label", "form", "text", "type", "id"]
            claim = ["0,9", "true", json.dumps({"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR", "per": "month"}}, ensure_ascii=False), "Élan costs €9 per month.", "fact", "c1"]
            with out.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(fields)
                writer.writerow(claim)
            self.assertEqual(validate_output(out, data, CONTRACTS, expected_claims=1), [])

    def test_semantically_duplicate_claim_forms_are_detected_across_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("p1", "known", "2026-01-01", "true", [])])
            data = load_inputs(csv_path, lex_path)
            def claim(rid, value, unit, text):
                return {"id": rid, "type": "fact", "text": text, "label": "true", "confidence": "0.9",
                        "form": json.dumps({"subject": "Élan", "attribute": "storage", "value": {"kind": "quantity", "value": value, "unit": unit}})}
            out = Path(tmp) / "output.csv"
            atomic_write_csv(out, [claim("c1", 1, "GB", "Élan has 1 GB storage."), claim("c2", 1000, "MB", "Élan has 1000 MB storage.")])
            self.assertTrue(any("semantically duplicate" in x for x in validate_output(out, data, CONTRACTS, expected_claims=2)))

    def test_output_rejects_bad_form_ids_confidence_and_csv_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("p1", "known", "2026-01-01", "true", [])])
            data = load_inputs(csv_path, lex_path)
            out = Path(tmp) / "output.csv"
            bad = {"id": "bad id", "type": "fact", "text": "Élan costs €9 per month.", "form": "{bad", "label": "true", "confidence": "NaN"}
            atomic_write_csv(out, [bad])
            errors = validate_output(out, data, CONTRACTS, expected_claims=1)
            self.assertTrue(any("invalid id" in x for x in errors))
            self.assertTrue(any("not valid JSON" in x for x in errors))
            bad["form"] = json.dumps({"subject": "Élan", "attribute": "unknown", "value": {"kind": "money", "value": 9, "currency": "EUR"}})
            bad["id"] = "c1"
            bad["confidence"] = "0.9"
            atomic_write_csv(out, [bad])
            self.assertTrue(any("invalid attribute" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            out.write_text("id,type,text,form,label,confidence,extra\nc1,fact,x,{},true,0.9,x\n", encoding="utf-8")
            self.assertTrue(any("output columns" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            out.write_text("id,type,text,form,label,confidence\nc1,fact,x,{},true,0.9,extra\n", encoding="utf-8")
            self.assertTrue(any("extra CSV fields" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            bad["id"] = "c2"
            bad["form"] = json.dumps({"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR"}})
            bad["confidence"] = "NaN"
            atomic_write_csv(out, [bad])
            self.assertTrue(any("invalid confidence" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            bad["confidence"] = "1.1"
            atomic_write_csv(out, [bad])
            self.assertTrue(any("above maximum" in x or "invalid confidence" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))

    def test_output_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "large.csv"
            with out.open("wb") as handle:
                handle.truncate(16 * 1024 * 1024 + 1)
            errors = validate_output(out, None, CONTRACTS)
            self.assertEqual(errors, ["output CSV exceeds 16 MiB"])

    def test_numeric_claim_text_must_match_form_when_digits_are_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("p1", "known", "2026-01-01", "true", [])])
            data = load_inputs(csv_path, lex_path)
            out = Path(tmp) / "output.csv"
            row = {"id": "c1", "type": "fact", "text": "Élan costs €10 per month.",
                   "form": json.dumps({"subject": "Élan", "attribute": "price", "value": {"kind": "money", "value": 9, "currency": "EUR", "per": "month"}}),
                   "label": "true", "confidence": "0.9"}
            atomic_write_csv(out, [row])
            self.assertTrue(any("numeric value" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))

    def test_self_compare_reversed_compare_and_noop_change_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path, lex_path = write_fixture(Path(tmp), [record("p1", "known", "2026-01-01", "true", [])])
            data = load_inputs(csv_path, lex_path)
            out = Path(tmp) / "output.csv"
            compare = {"id": "c1", "type": "compare", "text": "Beta costs more than Élan.", "label": "true", "confidence": "0.9",
                       "form": json.dumps({"left": {"subject": "Élan", "attribute": "price"}, "right": {"subject": "Beta", "attribute": "price"}, "op": "gt"})}
            atomic_write_csv(out, [compare])
            self.assertTrue(any("left subject before" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            compare["form"] = json.dumps({"left": {"subject": "Élan", "attribute": "price"}, "right": {"subject": "Élan", "attribute": "price"}, "op": "gt"})
            compare["text"] = "Élan costs more than Élan."
            atomic_write_csv(out, [compare])
            self.assertTrue(any("cannot compare a fact with itself" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))
            change = {"id": "c2", "type": "change", "text": "Élan went from €9 per month to €9 per month.", "label": "true", "confidence": "0.9",
                      "form": json.dumps({"subject": "Élan", "attribute": "price", "from": {"kind": "money", "value": 9, "currency": "EUR", "per": "month"}, "to": {"kind": "money", "value": 9, "currency": "EUR", "per": "month"}})}
            atomic_write_csv(out, [change])
            self.assertTrue(any("same value" in x for x in validate_output(out, data, CONTRACTS, expected_claims=1)))

    def test_all_official_good_claim_text_examples_pass_deterministic_checks(self):
        data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
        for path in (CONTRACTS / "examples" / "entry" / "good").glob("*.json"):
            example = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(example=path.name):
                self.assertEqual(validate_claim_text(example["type"], example["text"], example["form"], data.lexicon), [])

    def test_nested_entity_names_do_not_match_shorter_subject(self):
        data = load_inputs(ROOT / "data" / "practice.csv", ROOT / "data" / "lexicon.json")
        form = {"subject": "Hooly", "attribute": "employees", "value": {"kind": "quantity", "value": 100}}
        issues = validate_claim_text("fact", "Hooly AI Pro has 100 employees.", form, data.lexicon)
        self.assertTrue(any("must name its subject" in x for x in issues))

    def test_all_official_schema_examples_match_validator(self):
        entry_validator = SchemaValidator(CONTRACTS / "entry.schema.json")
        for path in (CONTRACTS / "examples" / "entry" / "good").glob("*.json"):
            with self.subTest(example=path.name):
                self.assertEqual(entry_validator.validate(json.loads(path.read_text(encoding="utf-8"))), [])
        for path in (CONTRACTS / "examples" / "entry" / "bad").glob("*.json"):
            with self.subTest(example=path.name):
                self.assertTrue(entry_validator.validate(json.loads(path.read_text(encoding="utf-8"))))
        value_validator = SchemaValidator(CONTRACTS / "claimed_value.schema.json")
        for path in (CONTRACTS / "examples" / "claimed_value" / "good").glob("*.json"):
            with self.subTest(example=path.name):
                self.assertEqual(value_validator.validate(json.loads(path.read_text(encoding="utf-8"))), [])
        for path in (CONTRACTS / "examples" / "claimed_value" / "bad").glob("*.json"):
            with self.subTest(example=path.name):
                self.assertTrue(value_validator.validate(json.loads(path.read_text(encoding="utf-8"))))

    def test_runner_publishes_a_valid_deficit_checkpoint_without_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            csv_path, lex_path = write_fixture(folder, [record("u1", "unknown", "2026-01-01", "", [])])
            output = folder / "out" / "output.csv"
            class EmptyFactory:
                def __init__(self, *args, **kwargs): pass
                def generate(self, *, on_checkpoint=None):
                    if on_checkpoint: on_checkpoint([])
                    return [], {"selected_claims": 0, "deficit_to_1000": 1000}
            with patch("runner.predict_unlabeled", side_effect=RuntimeError("model unavailable")), \
                 patch("runner.ClaimFactory", EmptyFactory):
                code = run(str(csv_path), str(lex_path), str(output), str(CONTRACTS))
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["label"], "unsure")
            self.assertEqual(rows[0]["type"], "")
            self.assertEqual(rows[0]["confidence"], "")

    def test_runner_preserves_incremental_classification_when_inference_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            csv_path, lex_path = write_fixture(folder, [record("u1", "unknown", "2026-01-01", "", [])])
            output = folder / "output.csv"
            class EmptyFactory:
                def __init__(self, *args, **kwargs): pass
                def generate(self, *, on_checkpoint=None):
                    if on_checkpoint: on_checkpoint([])
                    return [], {"selected_claims": 0, "deficit_to_1000": 1000}
            def interrupted_inference(_data, _model, _practice, *, progress, **kwargs):
                progress({"u1": ("true", 0.8)})
                raise RuntimeError("deadline reached after first batch")
            with patch("runner.predict_unlabeled", side_effect=interrupted_inference), \
                 patch("runner.ClaimFactory", EmptyFactory):
                self.assertEqual(run(str(csv_path), str(lex_path), str(output), str(CONTRACTS)), 0)
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["label"], "true")
            self.assertEqual(rows[0]["confidence"], "0.8")

    def test_runner_handles_missing_inputs_and_ignores_unprovenanced_candidate_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            csv_path, lex_path = write_fixture(folder, [record("p1", "known", "2026-01-01", "true", [])])
            output = folder / "output.csv"
            self.assertEqual(run(str(folder / "missing.csv"), str(lex_path), str(output), str(CONTRACTS)), 2)
            empty = folder / "empty.json"
            empty.write_text("[]", encoding="utf-8")
            class EmptyFactory:
                def __init__(self, *args, **kwargs): pass
                def generate(self, *, on_checkpoint=None):
                    if on_checkpoint: on_checkpoint([])
                    return [], {"selected_claims": 0, "deficit_to_1000": 1000}
            with patch("runner.predict_unlabeled", side_effect=RuntimeError("model unavailable")), \
                 patch("runner.ClaimFactory", EmptyFactory):
                self.assertEqual(run(str(csv_path), str(lex_path), str(output), str(CONTRACTS), str(empty)), 0)
            with patch.dict(os.environ, {"ARENA_DEADLINE": "1"}):
                self.assertEqual(run(str(csv_path), str(lex_path), str(output), str(CONTRACTS)), 2)
            self.assertTrue(output.exists())


if __name__ == "__main__":
    unittest.main()
