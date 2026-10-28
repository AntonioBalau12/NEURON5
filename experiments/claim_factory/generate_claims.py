"""Deterministic claim factory: build up to 1,000 ORIGINAL, verifiably true claims from Hooly evidence.

Usage (from the repo root, PowerShell, Python 3.14):
  $env:PYTHONUTF8='1'
  py experiments/claim_factory/generate_claims.py --facts-source practice_forms --out experiments/claim_factory/output/run_<name>
Options: --extra-facts <jsonl>  --extra-min-confidence 0.8  --extra-corroboration any|row_form|two_methods|cross_row
         --change-rule engine|corroborated  --relation-rule engine|stable
         --min-support-rows 1  --max-age-days 14  --no-block-on-false-candidates  --limit N
         --universe-csv <csv> --reference-csv <csv>  --novelty-csv <csv> (repeatable)  --allow-unlisted-names

It never pads: if fewer valid claims exist the file simply holds fewer.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cf_common import CLAIM_TYPES, CONTRACT_DIR, LEXICON_JSON, PRACTICE_CSV, ROOT  # noqa: E402
import foundation  # noqa: E402
from contract import ContractChecker  # noqa: E402
from rules import Cand, gen_at_event, gen_change, gen_compare, gen_fact, gen_relation  # noqa: E402
from store import Params, Store, load_novelty_texts  # noqa: E402

FULL_INPUT = ROOT / "experiments" / "shared" / "data" / "full_input.csv"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--facts-source", default="practice_forms", choices=["practice_forms"])
    ap.add_argument("--out", required=True, help="run folder (must not exist: earlier runs are never overwritten)")
    ap.add_argument("--universe-csv", default=str(PRACTICE_CSV),
                    help="rows the graph is built from (default data/practice.csv, forms included). For a runtime-shaped universe without forms "
                         "pass it here and the practice file as --reference-csv")
    ap.add_argument("--reference-csv", default=None, help="reference evidence with forms, merged by id when text/date/label agree")
    ap.add_argument("--extra-facts", default=None, help="JSONL of reconstructed facts (experiments/shared/EXCHANGE_FORMAT.md)")
    ap.add_argument("--extra-min-confidence", type=float, default=0.8)
    ap.add_argument("--extra-corroboration", default="any", choices=["any", "row_form", "two_methods", "cross_row", "agree_or_form"],
                    help="which corroboration rule(s) admit a reconstructed fact")
    ap.add_argument("--change-rule", default="engine", choices=["engine", "corroborated", "safe_transition"],
                    help="engine: strictly require engine support. corroborated: pairs with min-support rows. safe_transition: corroborated + chronological + no later contradiction")
    ap.add_argument("--relation-rule", default="engine", choices=["engine", "stable"])
    ap.add_argument("--compare-scope", default="same_attribute", choices=["same_attribute", "same_kind", "cross_date"],
                    help="same_attribute: peers only (default). cross_date: add immutable calendar date cross-compares. same_kind: all cross-attribute pairs")
    ap.add_argument("--staleness-rule", default="strict_14d", choices=["strict_14d", "relax_definitive"],
                    help="strict_14d: all facts older than 14d expire (except 13 date attrs). relax_definitive: definitive/immutable facts never expire (14d only for volatile)")
    ap.add_argument("--min-support-rows", type=int, default=1)
    ap.add_argument("--max-age-days", type=int, default=14, help="mutable facts must have been observed at most this many days before the as-of date")
    ap.add_argument("--no-block-on-false-candidates", action="store_true")
    ap.add_argument("--allow-unlisted-names", action="store_true",
                    help="UNVERIFIED: also render name values that are not lexicon entities (referee may not resolve them)")
    ap.add_argument("--novelty-csv", action="append", default=None, help="extra input CSV whose texts must not be reused (default: practice + shared full_input)")
    ap.add_argument("--limit", type=int, default=None, help="keep at most N claims (highest confidence first); default keep all valid")
    args = ap.parse_args(argv)

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        print(f"refusing to overwrite existing run folder {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)

    timing: dict[str, float] = {}
    t_total = time.perf_counter()
    params = Params(min_support_rows=args.min_support_rows, max_age_days=args.max_age_days,
                    block_on_false_candidates=not args.no_block_on_false_candidates, allow_unlisted_names=args.allow_unlisted_names,
                    change_rule=args.change_rule, relation_rule=args.relation_rule, compare_scope=args.compare_scope,
                    staleness_rule=args.staleness_rule)
    t = time.perf_counter()
    store = Store(Path(args.universe_csv), LEXICON_JSON, params, Path(args.reference_csv) if args.reference_csv else None)
    timing["graph_build_s"] = time.perf_counter() - t

    extra_report = None
    if args.extra_facts:
        import extra_facts
        t = time.perf_counter()
        extra_report = extra_facts.inject(store, Path(args.extra_facts), args.extra_min_confidence, args.extra_corroboration, out)
        timing["extra_facts_s"] = time.perf_counter() - t

    novelty_paths = [Path(p) for p in (args.novelty_csv or [PRACTICE_CSV, FULL_INPUT]) if Path(p).is_file()]
    checker = ContractChecker(store, load_novelty_texts(novelty_paths))

    cands: list[Cand] = []
    for name, fn in (("fact", gen_fact), ("compare", gen_compare), ("change", gen_change), ("at_event", gen_at_event), ("relation", gen_relation)):
        t = time.perf_counter()
        batch = fn(store)
        timing[f"generate_{name}_s"] = time.perf_counter() - t
        cands.extend(batch)

    t = time.perf_counter()
    for c in cands:
        checker.check(c)
    timing["contract_checks_s"] = time.perf_counter() - t

    accepted = [c for c in cands if c.status == "accepted"]
    accepted.sort(key=lambda c: (-c.confidence, CLAIM_TYPES.index(c.type), c.ckey))
    if args.limit is not None:
        accepted = accepted[: args.limit]
    accepted.sort(key=lambda c: (CLAIM_TYPES.index(c.type), c.ckey))
    counters: Counter[str] = Counter()
    for c in accepted:
        counters[c.type] += 1
        c.cid = f"cf-{c.type}-{counters[c.type]:04d}"

    # ---- write outputs ----------------------------------------------------------------------
    claims_csv = out / "claims_valid.csv"
    with claims_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(foundation.OUTPUT_COLUMNS)
        for c in accepted:
            w.writerow([c.cid, c.type, c.text, json.dumps(c.form, ensure_ascii=False, separators=(", ", ": ")), "true", f"{c.confidence:g}"])
    with (out / "candidates.jsonl").open("w", encoding="utf-8") as fh:
        for c in cands:
            fh.write(json.dumps({"claim_id": c.cid or None, "type": c.type, "candidate_key": c.ckey, "status": c.status, "stage": c.stage,
                                 "verified_by_evidence_rules": c.verified, "reasons": c.reasons, "flags": c.flags, "rule": c.rule,
                                 "engine": c.engine, "form": c.form, "text": c.text, "confidence": c.confidence,
                                 "evidence": _compact(c.evidence)}, ensure_ascii=False) + "\n")
    with (out / "provenance.jsonl").open("w", encoding="utf-8") as fh:
        for c in accepted:
            fh.write(json.dumps({"claim_id": c.cid, "type": c.type, "text": c.text, "form": c.form, "rule": c.rule, "engine": c.engine,
                                 "flags": c.flags, "confidence": c.confidence, "as_of": "2026-10-29",
                                 "evidence": c.evidence}, ensure_ascii=False) + "\n")

    summary = summarize(cands, accepted)
    (out / "rejections_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- validation with the official validator ----------------------------------------------
    t = time.perf_counter()
    data = foundation.load_inputs(PRACTICE_CSV, LEXICON_JSON)
    official = foundation.validate_output(claims_csv, data, CONTRACT_DIR, expected_claims=len(accepted))
    timing["official_validate_output_s"] = time.perf_counter() - t
    timing["total_s"] = time.perf_counter() - t_total
    (out / "timing.json").write_text(json.dumps({k: round(v, 3) for k, v in timing.items()}, indent=2), encoding="utf-8")
    meta = {
        "command": " ".join(sys.argv), "facts_source": args.facts_source, "params": params.__dict__ | {"as_of": str(params.as_of)},
        "extra_facts": extra_report, "git_head": _git_head(), "claims_written": len(accepted), "target": 1000,
        "distance_from_1000": 1000 - len(accepted),
        "official_validate_output": {"expected_claims": len(accepted), "problems": official[:50], "n_problems": len(official)},
        "note": "only practice rows exist locally; the real run's other ~18,000 rows are unlabelled",
    }
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(json.dumps({"claims_valid": len(accepted), "by_type": dict(counters), "funnel": summary["funnel"],
                      "official_validate_output_problems": len(official), "seconds": round(timing["total_s"], 2)}, indent=2))
    return 0 if not official else 1


def _compact(ev: dict) -> dict:
    """Candidates file keeps row ids and short snippets only."""
    def shrink(x):
        if isinstance(x, dict):
            return {k: shrink(v) for k, v in x.items() if k != "text"}
        if isinstance(x, list):
            return [shrink(i) for i in x]
        return x
    return shrink(ev)


def summarize(cands: list[Cand], accepted: list[Cand]) -> dict:
    funnel: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    reasons: dict[str, Counter] = defaultdict(Counter)
    for c in cands:
        f = funnel[c.type]
        f["generated"] += 1
        if c.verified:
            f["verified_by_evidence_rules"] += 1
        stage_rank = ["generated", "evidence", "render", "form_schema", "lexicon", "text_independent", "text_foundation", "contract_valid",
                      "novelty", "dedup", "accepted"]
        # contract-valid = got through render and all contract checks (novelty/dedup happen after)
        if c.stage in ("contract_valid", "novelty", "dedup", "accepted"):
            f["contract_valid"] += 1
        if c.status == "accepted":
            f["novel_and_final"] += 1
        for r in c.reasons:
            reasons[c.type][re_reason(r)] += 1
    all_reasons: Counter[str] = Counter()
    for t, cnt in reasons.items():
        all_reasons.update(cnt)
    first_reason: dict[str, Counter] = defaultdict(Counter)
    for c in cands:
        if c.status == "rejected" and c.reasons:
            first_reason[c.type][re_reason(c.reasons[0])] += 1
    return {
        "funnel": {t: dict(funnel[t]) for t in CLAIM_TYPES if t in funnel},
        "funnel_total": {k: sum(funnel[t][k] for t in funnel) for k in ("generated", "verified_by_evidence_rules", "contract_valid", "novel_and_final")},
        "accepted_by_type": dict(Counter(c.type for c in accepted)),
        "reasons_all_by_type": {t: dict(reasons[t].most_common()) for t in CLAIM_TYPES if t in reasons},
        "first_rejection_reason_by_type": {t: dict(first_reason[t].most_common()) for t in CLAIM_TYPES if t in first_reason},
        "reasons_all_total": dict(all_reasons.most_common()),
        "flags": dict(Counter(f.split(":")[0] for c in accepted for f in c.flags)),
    }


def re_reason(r: str) -> str:
    import re
    return re.sub(r"\(.*", "", r)[:120]


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())


