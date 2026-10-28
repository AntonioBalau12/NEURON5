"""Item 1, variant 2: do the extractors help when the UNLABELLED rows vote on each fact?

Pre-registered before the first run (see classify_test.py for the shared rules).
  test rows : the 270 held-out rows, labels hidden (used only for scoring).
  atoms     : what a method extracts from a row's TEXT. The same method supplies the test row's atoms and the evidence.
  evidence  : atoms of OTHER rows (the row itself is always left out). Labels are IGNORED (unlabelled consensus).
     pool "heldout" : atoms from the other 269 held-out rows only. Their extractions are clean (never trained on),
                      but the pool is small.
     pool "all"     : atoms from every other row. Denser, but dev rows were used to fit the extractors, so their
                      extraction is better than it will be on real unlabelled rows (optimistic).
  rule (primary): per atom, among evidence atoms in the same slot (subject, attribute, kind) within W=14 days:
        supported   : >= 1 evidence row states the same value
        contradicted: 0 rows state the same value and >= 2 distinct evidence rows state a different value
     row -> false if any atom is contradicted; true otherwise (default true). Sensitivity: contradiction needs >= 1 row.
  oracle    : evidence atoms and test atoms come from the GOLD forms (labels still ignored): ceiling of voting.
Run: py experiments/classification_test/classify_consensus.py --out experiments/classification_test/results/<name>
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import classify_test as ct  # noqa: E402

W = 14


class VoteIndex:
    def __init__(self, atoms_by_row: dict[str, list[tuple]], dates: dict[str, date], pool_ids: set[str]):
        self.slots: dict[tuple, list[tuple[str, date, tuple]]] = collections.defaultdict(list)
        for rid in pool_ids:
            for sub, attr, kind, vk in atoms_by_row.get(rid, ()):
                self.slots[(sub, attr, kind)].append((rid, dates[rid], vk))

    def judge(self, a: tuple, rid: str, d: date, min_contra: int) -> str:
        sub, attr, kind, vk = a
        same = set()
        other = set()
        for (rid2, d2, vk2) in self.slots.get((sub, attr, kind), ()):
            if rid2 == rid or abs((d - d2).days) > W:
                continue
            (same if vk2 == vk else other).add(rid2)
        if same:
            return "support"
        if len(other) >= min_contra:
            return "contradict"
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    out.mkdir(parents=True)

    held_ids = set(json.loads((ct.SHARED / "data" / "split.json").read_text())["heldout_ids"])
    full = ct.read_csv(ct.SHARED / "data" / "full_input.csv")
    dev_forms = {r["id"]: r["form"] for r in ct.read_csv(ct.SHARED / "data" / "dev_rows.csv")}
    held_gold = {r["id"]: r["form"] for r in ct.read_csv(ct.SHARED / "_heldout" / "heldout_gold.csv")}
    dates = {r["id"]: ct.day(r["date"]) for r in full}
    test_rows = [r for r in full if r["id"] in held_ids]
    gold = [r["label"] for r in test_rows]
    all_ids = {r["id"] for r in full}

    MAPPED = {"complete", "ambiguous", "partial"}
    methods = {name: ct.load_atoms(path, MAPPED) for name, path in ct.METHOD_FILES.items()}
    gold_atoms = {rid: ct.form_atoms(f) for rid, f in {**dev_forms, **held_gold}.items()}
    methods["oracle(form)"] = gold_atoms

    results: dict = {"test_rows": len(test_rows), "label_counts": dict(collections.Counter(gold)), "W": W, "runs": {}}
    pools = {"heldout": set(held_ids), "all": all_ids}
    base = ["true"] * len(test_rows)
    for pool_name, pool_ids in pools.items():
        for min_contra in (2, 1):
            preds, hows = {}, {}
            for m, atoms in methods.items():
                idx = VoteIndex(atoms, dates, pool_ids)
                p, h = [], []
                for r in test_rows:
                    verdicts = [idx.judge(a, r["id"], dates[r["id"]], min_contra) for a in atoms.get(r["id"], [])]
                    if "contradict" in verdicts:
                        p.append("false"); h.append("evidence_false")
                    elif "support" in verdicts:
                        p.append("true"); h.append("evidence_true")
                    else:
                        p.append("true"); h.append("default_true")
                preds[m], hows[m] = p, h
            key = f"pool={pool_name},min_contra={min_contra}"
            res = {}
            for m in preds:
                met = ct.metrics(gold, preds[m], hows[m])
                met["paired_vs_always_true"] = ct.paired_diff(gold, preds[m], base)
                res[m] = met
            results["runs"][key] = res

    (out / "metrics.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")

    def fmt(x):
        return "n/a" if x != x else f"{x*100:.1f}%"
    print(f"test rows {len(test_rows)} {results['label_counts']}; always_true accuracy = {fmt(sum(g == 'true' for g in gold)/len(gold))}")
    for key, res in results["runs"].items():
        primary = " (PRIMARY)" if key.endswith("min_contra=2") else " (sensitivity)"
        print(f"\n{key}{primary}")
        print(f"  {'method':<14}{'acc':>7}  {'vs always_true (95%)':>26}  {'F1(false)':>9}  {'P(false)':>8}  {'R(false)':>8}  {'decided':>7}  {'acc|dec':>8}")
        for m, met in res.items():
            pt, lo, hi = met["paired_vs_always_true"]
            print(f"  {m:<14}{fmt(met['accuracy']):>7}  {pt*100:+6.1f} [{lo*100:+5.1f},{hi*100:+5.1f}]        {fmt(met['false_f1']):>9}  "
                  f"{fmt(met['false_precision']):>8}  {fmt(met['false_recall']):>8}  {met['rows_decided_by_evidence']:>7}  {fmt(met['accuracy_on_decided']):>8}")


if __name__ == "__main__":
    main()
