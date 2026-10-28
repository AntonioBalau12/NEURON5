"""Re-run foundation.validate_output on a claims CSV and check novelty against every input text."""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, "experiments/claim_factory")
from cf_common import CONTRACT_DIR, LEXICON_JSON, PRACTICE_CSV, ROOT
import foundation
from store import norm_text
claims = Path(sys.argv[1]); out = Path(sys.argv[2])
data = foundation.load_inputs(PRACTICE_CSV, LEXICON_JSON)
rows = list(csv.DictReader(claims.open(encoding="utf-8", newline="")))
problems = foundation.validate_output(claims, data, CONTRACT_DIR, expected_claims=len(rows))
tx = {norm_text(r["text"]) for r in csv.DictReader(PRACTICE_CSV.open(encoding="utf-8-sig", newline=""))}
full = ROOT / "experiments/shared/data/full_input.csv"
fx = {norm_text(r["text"]) for r in csv.DictReader(full.open(encoding="utf-8-sig", newline=""))} if full.is_file() else set()
raw_tx = {r["text"].strip() for r in csv.DictReader(PRACTICE_CSV.open(encoding="utf-8-sig", newline=""))}
res = {"claims_file": str(claims), "n_claims": len(rows), "validate_output_problems": len(problems), "problems_first10": problems[:10],
       "claims_equal_to_practice_row_text_normalised": sum(norm_text(r["text"]) in tx for r in rows),
       "claims_equal_to_practice_row_text_exact": sum(r["text"].strip() in raw_tx for r in rows),
       "claims_equal_to_shared_full_input_text": sum(norm_text(r["text"]) in fx for r in rows), "full_input_present": bool(fx),
       "duplicate_texts": len(rows) - len({norm_text(r["text"]) for r in rows}), "duplicate_ids": len(rows) - len({r["id"] for r in rows})}
out.write_text(json.dumps(res, indent=2), encoding="utf-8"); print(json.dumps(res, indent=2))
