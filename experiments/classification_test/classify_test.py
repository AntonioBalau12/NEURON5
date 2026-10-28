"""Does extraction help classify hidden-label rows? (coordinator experiment, item 1)

Design, fixed before the first run:
  test rows  = the 270 held-out rows, labels hidden from every method (labels are used only for scoring).
               No extractor saw their forms, so the test is leak-free for the methods.
  evidence   = dev rows labelled `true`, with their GOLD forms (the image may hold the practice forms).
  atoms      = facts a method extracts from the test row's TEXT (id, text, date only).
  rule (identical for every method, so differences isolate the extraction):
     atom contradicted : evidence has the same subject+attribute, a different comparable value, within W days,
                         and no evidence with the same value within W days
     atom supported    : evidence has the same subject+attribute+value within W days
     row -> false if any atom is contradicted;
            true  if no atom is contradicted and at least one is supported;
            otherwise it falls back to `true` (the 82% prior) and is counted as "undecided".
  W is fixed at 14 days BEFORE looking at the test (the claim factory's backtest window). Other W are a
  sensitivity table, not a selection.
  oracle     = the held-out gold form as the atoms: the ceiling of this approach with perfect extraction.
  density    = also run with the evidence thinned to a fraction of the dev rows, because the real run has
               far fewer labelled rows than this test (practice rows are ~10% of the universe).

Run:  py experiments/classification_test/classify_test.py --out experiments/classification_test/results/<name>
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import random
import statistics
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments" / "evaluation"))
import common  # noqa: E402  (read-only reuse: value_key / canonical_subject)

SHARED = ROOT / "experiments" / "shared"
METHOD_FILES = {
    "parser": ROOT / "experiments/evaluation/output/baseline_facts.jsonl",
    "openie": ROOT / "experiments/openie/output/facts.jsonl",
    "slot_filling": ROOT / "experiments/slot_filling/output/facts.jsonl",
    "union": ROOT / "experiments/evaluation/output/combined_union_facts.jsonl",
    "intersection": ROOT / "experiments/evaluation/output/combined_intersection_facts.jsonl",
}
W_PRIMARY = 14
W_SENSITIVITY = (0, 3, 7, 14, 30, 90, 100000)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def day(s: str) -> date:
    return date.fromisoformat(s)


def atom(subject, attribute, value):
    """(subject, attribute, kind, value_key) or None. Comparison-op values are skipped on both sides."""
    if subject is None or attribute is None or not isinstance(value, dict) or value.get("op"):
        return None
    vk = common.value_key(value)
    sub = common.canonical_subject(subject)
    if vk is None or sub is None:
        return None
    return (sub, attribute, value.get("kind"), vk)


def load_atoms(path: Path, statuses: set[str]) -> dict[str, list[tuple]]:
    out: dict[str, list[tuple]] = collections.defaultdict(list)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            f = json.loads(line)
            if f["parse_status"] not in statuses:
                continue
            a = atom(f["subject"], f["attribute"], f["value"])
            if a and a not in out[f["source_row_id"]]:
                out[f["source_row_id"]].append(a)
    return out


def form_atoms(form: str) -> list[tuple]:
    out = []
    for g in json.loads(form):
        a = atom(g["subject"], g["attribute"], g["value"])
        if a and a not in out:
            out.append(a)
    return out


class Evidence:
    def __init__(self, rows: list[dict], forms: dict[str, str]):
        # slot (subject, attribute) -> list of (date, value_key, kind)
        self.slots: dict[tuple, list[tuple[date, tuple, str]]] = collections.defaultdict(list)
        for r in rows:
            if r["label"] != "true":
                continue
            d = day(r["date"])
            for sub, attr, kind, vk in form_atoms(forms[r["id"]]):
                self.slots[(sub, attr)].append((d, vk, kind))

    def judge(self, a: tuple, d: date, W: int) -> str:
        sub, attr, kind, vk = a
        support = contra = False
        for (d2, vk2, kind2) in self.slots.get((sub, attr), ()):
            if abs((d - d2).days) > W:
                continue
            if vk2 == vk:
                support = True
            elif kind2 == kind:
                contra = True
        if support:
            return "support"          # support wins: the value was stated within the window
        return "contradict" if contra else "unknown"


def classify(atoms: list[tuple], d: date, ev: Evidence, W: int) -> tuple[str, str]:
    """returns (predicted label, how): 'evidence_false' | 'evidence_true' | 'default_true'"""
    verdicts = [ev.judge(a, d, W) for a in atoms]
    if "contradict" in verdicts:
        return "false", "evidence_false"
    if "support" in verdicts:
        return "true", "evidence_true"
    return "true", "default_true"


def metrics(gold: list[str], pred: list[str], how: list[str]) -> dict:
    n = len(gold)
    acc = sum(g == p for g, p in zip(gold, pred)) / n
    tp = sum(g == "false" and p == "false" for g, p in zip(gold, pred))
    fp = sum(g != "false" and p == "false" for g, p in zip(gold, pred))
    fn = sum(g == "false" and p != "false" for g, p in zip(gold, pred))
    prec = tp / (tp + fp) if tp + fp else float("nan")
    rec = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else float("nan")
    # macro-F1 over the three labels (unsure is never predicted, so its F1 is 0)
    f1s = []
    for lab in ("true", "false", "unsure"):
        t = sum(g == lab and p == lab for g, p in zip(gold, pred))
        a = sum(g != lab and p == lab for g, p in zip(gold, pred))
        b = sum(g == lab and p != lab for g, p in zip(gold, pred))
        f1s.append(2 * t / (2 * t + a + b) if 2 * t + a + b else 0.0)
    decided = [i for i, h in enumerate(how) if h != "default_true"]
    return {
        "n": n, "accuracy": acc, "macro_f1": sum(f1s) / 3,
        "false_precision": prec, "false_recall": rec, "false_f1": f1,
        "false_tp": tp, "false_fp": fp, "false_fn": fn,
        "rows_decided_by_evidence": len(decided),
        "accuracy_on_decided": (sum(gold[i] == pred[i] for i in decided) / len(decided)) if decided else float("nan"),
        "rows_flagged_false": tp + fp,
    }


def bootstrap(gold, preds: dict[str, list[str]], reps=2000, seed=20261028):
    rnd = random.Random(seed)
    n = len(gold)
    names = list(preds)
    acc = {m: [] for m in names}
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        for m in names:
            acc[m].append(sum(gold[i] == preds[m][i] for i in idx) / n)
    out = {}
    for m in names:
        s = sorted(acc[m])
        out[m] = (s[int(0.025 * reps)], s[int(0.975 * reps)])
    return out


def paired_diff(gold, a, b, reps=2000, seed=20261028):
    rnd = random.Random(seed)
    n = len(gold)
    d = []
    for _ in range(reps):
        idx = [rnd.randrange(n) for _ in range(n)]
        d.append(sum(gold[i] == a[i] for i in idx) / n - sum(gold[i] == b[i] for i in idx) / n)
    d.sort()
    return (sum(gold[i] == a[i] for i in range(n)) - sum(gold[i] == b[i] for i in range(n))) / n, d[int(0.025 * reps)], d[int(0.975 * reps)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--density", type=float, default=0.10)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists; results are never overwritten")
    out.mkdir(parents=True)

    held_ids = set(json.loads((SHARED / "data" / "split.json").read_text())["heldout_ids"])
    full = read_csv(SHARED / "data" / "full_input.csv")
    dev_forms = {r["id"]: r["form"] for r in read_csv(SHARED / "data" / "dev_rows.csv")}
    held_gold = {r["id"]: r["form"] for r in read_csv(SHARED / "_heldout" / "heldout_gold.csv")}
    dev_rows = [r for r in full if r["id"] in dev_forms]
    test_rows = [r for r in full if r["id"] in held_ids]
    gold = [r["label"] for r in test_rows]
    assert not (held_ids & set(dev_forms)), "dev/held-out overlap"
    print(f"test rows {len(test_rows)} {dict(collections.Counter(gold))}; evidence candidates (dev true rows) "
          f"{sum(r['label']=='true' for r in dev_rows)}")

    MAPPED_ALL = {"complete", "ambiguous", "partial"}
    method_atoms: dict[str, dict[str, list[tuple]]] = {}
    for name, path in METHOD_FILES.items():
        method_atoms[name] = load_atoms(path, MAPPED_ALL)
        method_atoms[name + "[complete]"] = load_atoms(path, {"complete"})
    method_atoms["oracle(form)"] = {r["id"]: form_atoms(held_gold[r["id"]]) for r in test_rows}

    results: dict = {"test_rows": len(test_rows), "label_counts": dict(collections.Counter(gold)),
                     "W_primary": W_PRIMARY, "primary": {}, "sensitivity": {}, "thin": {}}
    rows_out = []

    def run(ev: Evidence, W: int, names=None):
        preds, hows = {}, {}
        for m, atoms in method_atoms.items():
            if names and m not in names:
                continue
            p, h = [], []
            for r in test_rows:
                lab, how = classify(atoms.get(r["id"], []), day(r["date"]), ev, W)
                p.append(lab)
                h.append(how)
            preds[m], hows[m] = p, h
        return preds, hows

    # ---- primary: full dev evidence, W = 14
    ev_full = Evidence(dev_rows, dev_forms)
    preds, hows = run(ev_full, W_PRIMARY)
    preds["always_true"] = ["true"] * len(test_rows)
    hows["always_true"] = ["default_true"] * len(test_rows)
    cis = bootstrap(gold, preds)
    for m in preds:
        met = metrics(gold, preds[m], hows[m])
        met["accuracy_ci95"] = cis[m]
        met["rows_with_atoms"] = sum(bool(method_atoms.get(m, {}).get(r["id"])) for r in test_rows) if m in method_atoms else 0
        results["primary"][m] = met
    base = preds["always_true"]
    results["paired_vs_always_true"] = {m: paired_diff(gold, preds[m], base) for m in preds if m != "always_true"}
    results["paired_vs_parser"] = {m: paired_diff(gold, preds[m], preds["parser"]) for m in preds if m not in ("parser", "always_true")}
    for i, r in enumerate(test_rows):
        rows_out.append({"id": r["id"], "label": r["label"], "date": r["date"],
                         **{f"pred_{m}": preds[m][i] for m in preds}, **{f"how_{m}": hows[m][i] for m in ("openie", "slot_filling", "union", "oracle(form)")},
                         "text": r["text"]})

    # ---- sensitivity to W (not a selection)
    for W in W_SENSITIVITY:
        p, h = run(ev_full, W, names={"parser", "openie", "slot_filling", "union", "intersection", "oracle(form)"})
        results["sensitivity"][str(W)] = {m: {k: v for k, v in metrics(gold, p[m], h[m]).items()
                                              if k in ("accuracy", "false_precision", "false_recall", "false_f1", "rows_decided_by_evidence")}
                                          for m in p}

    # ---- thin evidence (realistic density), averaged over seeds
    true_dev = [r for r in dev_rows if r["label"] == "true"]
    thin = collections.defaultdict(list)
    for seed in range(args.seeds):
        rnd = random.Random(1000 + seed)
        sub = rnd.sample(true_dev, int(len(true_dev) * args.density))
        ev = Evidence(sub, dev_forms)
        p, h = run(ev, W_PRIMARY, names={"parser", "openie", "slot_filling", "union", "intersection", "oracle(form)"})
        for m in p:
            thin[m].append(metrics(gold, p[m], h[m]))
    for m, lst in thin.items():
        results["thin"][m] = {k: statistics.mean(x[k] for x in lst) for k in ("accuracy", "false_precision", "false_recall", "false_f1", "rows_decided_by_evidence")}
        results["thin"][m]["accuracy_sd"] = statistics.pstdev([x["accuracy"] for x in lst])
    results["thin"]["_density"] = args.density
    results["thin"]["_seeds"] = args.seeds
    results["thin"]["_evidence_rows"] = int(len(true_dev) * args.density)

    (out / "metrics.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    with (out / "predictions.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)

    # ---- console summary
    def fmt(x):
        return "n/a" if x != x else f"{x*100:.1f}%"
    print(f"\nPRIMARY (full dev evidence, W={W_PRIMARY} days)")
    print(f"{'method':<24}{'acc':>7}  {'95% CI':>13}  {'macroF1':>8}  {'F1(false)':>9}  {'P(false)':>8}  {'R(false)':>8}  {'decided':>7}  {'acc|decided':>11}")
    for m, met in results["primary"].items():
        lo, hi = met["accuracy_ci95"]
        print(f"{m:<24}{fmt(met['accuracy']):>7}  [{lo*100:4.1f}-{hi*100:4.1f}]  {fmt(met['macro_f1']):>8}  {fmt(met['false_f1']):>9}  "
              f"{fmt(met['false_precision']):>8}  {fmt(met['false_recall']):>8}  {met['rows_decided_by_evidence']:>7}  {fmt(met['accuracy_on_decided']):>11}")
    print("\npaired accuracy difference vs always_true  (point, 95% interval)")
    for m, (pt, lo, hi) in results["paired_vs_always_true"].items():
        print(f"  {m:<24}{pt*100:+5.1f} pts  [{lo*100:+5.1f}, {hi*100:+5.1f}]")
    print(f"\nTHIN evidence ({args.density:.0%} of dev true rows = {results['thin']['_evidence_rows']} rows, {args.seeds} seeds, W={W_PRIMARY})")
    for m, v in results["thin"].items():
        if m.startswith("_"):
            continue
        print(f"  {m:<24}acc {fmt(v['accuracy'])} (sd {v['accuracy_sd']*100:.1f})  F1(false) {fmt(v['false_f1'])}  P {fmt(v['false_precision'])}  R {fmt(v['false_recall'])}  decided {v['rows_decided_by_evidence']:.0f}")
    print("\nSENSITIVITY to W (accuracy / F1(false))")
    for W, v in results["sensitivity"].items():
        print(f"  W={W:>6}: " + "  ".join(f"{m}:{x['accuracy']*100:.1f}/{fmt(x['false_f1'])}" for m, x in v.items()))


if __name__ == "__main__":
    main()
