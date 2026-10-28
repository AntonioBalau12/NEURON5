"""Evaluate fact-reconstruction methods on the stratified evaluation set (135 rows).

  py experiments/evaluation/evaluate.py --methods baseline openie slot_filling combined --out experiments/evaluation/results/<run-name>

Method names
  baseline | openie | slot_filling       the default facts file of that method (see common.METHOD_FILES)
  combined                               every output/combined_<variant>_facts.jsonl (made by combine.py)
  combined_<variant>                     one of them
  name=path/to/facts.jsonl               any facts file
A method whose facts file does not exist is skipped with a message.
The output folder must not exist: results are never overwritten.

What is compared: the facts of a method on the evaluation rows against
  form_gold          facts of the dataset `form` (NOT exhaustive: recall is a lower bound on true recall,
                     precision a lower bound on true precision)
  evaluator_suggested  form + extra facts the evaluator proposes (UNVERIFIED, suggested_by=evaluator_llm)
Facts beyond the form are reported as "unverified candidates", split into matching an evaluator suggestion or not.
Value equivalence: foundation._canonical_value_key through common.value_key (see common.py docstring).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402
import metrics as M  # noqa: E402
from reporting import DEFAULT_SEED, fmt_pct, resolve_methods, run  # noqa: E402

# --------------------------------------------------------------------------- main

def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--methods", nargs="+", default=["baseline", "openie", "slot_filling", "combined"])
    ap.add_argument("--out", required=True, help="new results folder (must not exist)")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--judgements", default=str(C.JUDGEMENTS_CSV), help="review/evaluator_judgements.csv (optional)")
    ap.add_argument("--resources", default=None, help="resources.json written by measure_resources.py (optional)")
    ap.add_argument("--title", default=None)
    args = ap.parse_args()

    out_dir = Path(args.out)
    if out_dir.exists():
        print(f"ERROR: {out_dir} exists. Results are never overwritten; choose a new --out name.")
        return 2
    methods, skipped = resolve_methods(args.methods)
    for s in skipped:
        print("SKIPPED", s)
    if not methods:
        print("no method facts file available; nothing to evaluate")
        return 3
    reference = json.loads((C.WORKSHEET_DIR / "evaluator_reference.json").read_text(encoding="utf-8"))
    rows = M.load_gold(reference, C.read_csv(C.EVAL_ROWS))
    judgements = M.load_judgements(args.judgements)
    resources = json.loads(Path(args.resources).read_text(encoding="utf-8")) if args.resources else None
    payload = run(methods, out_dir, rows, ["form", "suggested"], "form", judgements, args.bootstrap, args.seed,
                  args.title or f"Evaluation {out_dir.name}", resources=resources, skipped=skipped)
    print(f"results written to {out_dir}")
    for n, r in payload["methods"].items():
        o = r["overall"]
        print(f"{n:24s} P_form {fmt_pct(o['precision_form'])}  R_form {fmt_pct(o['recall_form'])}  R_sugg {fmt_pct(o['recall_suggested'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
