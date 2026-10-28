"""Fit / save / load the dev-learned data files (cue profile, name gazetteer, count units, logistic weights).

Gold forms are read here and only here, and only from experiments/shared/data/dev_rows.csv.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from engine import GroupLogit, Profile, analyse_row
from pipeline import generate, label_candidates, norm_name, row_examples, training_groups

HERE = Path(__file__).resolve().parent
DEV = HERE.parent / "shared" / "data" / "dev_rows.csv"


def load_dev(path=DEV):
    rows = []
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            r["gold"] = json.loads(r["form"])
            rows.append(r)
    return rows


class Model:
    def __init__(self, profile: Profile, lr: GroupLogit, gaz: dict, units: list):
        self.profile = profile
        self.lr = lr
        self.gaz = gaz              # name -> number of dev rows
        self.units = frozenset(units)


def gaz_for(model_gaz: dict, minimum=1):
    return frozenset(n for n, c in model_gaz.items() if c >= minimum)


def fit(rows, lex, epochs=120, verbose=False, max_neg_ratio=None):
    gaz = Counter()
    own = {}
    units = Counter()
    for r in rows:
        names = set()
        for g in r["gold"]:
            v = g["value"]
            if v["kind"] == "name":
                names.add(v["value"])
            elif v["kind"] == "quantity":
                units[v["unit"]] += 1
        own[r["id"]] = names
        for n in names:
            gaz[n] += 1
    # lexicon spellings are found by linking already
    unit_set = sorted(u for u in units if u not in ("B", "KB", "MB", "GB", "TB", "mm", "cm", "m", "km", "in", "g", "kg", "mAh",
                                                      "Hz", "kHz", "MHz", "GHz", "mW", "W", "kW"))
    infos = {}
    exs = {}
    profile = Profile()
    for r in rows:
        g_r = frozenset(n for n, c in gaz.items() if c - (1 if n in own[r["id"]] else 0) > 0)
        infos[r["id"]] = analyse_row(r["text"], lex, g_r, frozenset(unit_set))
        exs[r["id"]] = row_examples(infos[r["id"]], r["text"], r["gold"], lex)
        for e in exs[r["id"]]:
            profile.add(e)
    groups = []
    for r in rows:
        for e in exs[r["id"]]:
            profile.add(e, -1)
        cands = generate(r["text"], infos[r["id"]], lex, profile)
        label_candidates(cands, r["gold"])
        groups += training_groups(cands)
        for e in exs[r["id"]]:
            profile.add(e, 1)
    if verbose:
        print(f"  value-mention groups {len(groups)}; groups with a gold candidate "
              f"{sum(1 for _, _, t in groups if sum(t) > 0)}", file=sys.stderr)
    lr = GroupLogit().fit(groups, epochs=epochs)
    return Model(profile, lr, dict(gaz), unit_set)


def save(model: Model, outdir: Path):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "cue_profile.json").write_text(json.dumps(model.profile.to_json(), sort_keys=True), encoding="utf-8")
    (outdir / "lr_weights.json").write_text(json.dumps(model.lr.w, indent=1, sort_keys=True), encoding="utf-8")
    (outdir / "name_gazetteer.json").write_text(json.dumps(model.gaz, indent=1, sort_keys=True, ensure_ascii=False),
                                                encoding="utf-8")
    (outdir / "count_units.json").write_text(json.dumps(sorted(model.units), indent=1), encoding="utf-8")
    # human-readable audit table: top cue stems per attribute
    with (outdir / "cue_table.tsv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t")
        w.writerow(["attribute", "n_examples", "kinds", "sub_forms", "ops", "top_near_cues", "top_far_cues"])
        p = model.profile
        for a in sorted(p.n):
            if p.n[a] <= 0:
                continue
            near = [f"{k}:{v}" for k, v in p.near[a].most_common(8) if v > 0]
            far = [f"{k}:{v}" for k, v in p.far[a].most_common(5) if v > 0]
            w.writerow([a, p.n[a], json.dumps(dict(p.kind[a])), json.dumps(dict(p.sub[a])), json.dumps(dict(p.op[a])),
                        " ".join(near), " ".join(far)])


def load(indir: Path) -> Model:
    indir = Path(indir)
    profile = Profile.from_json(json.loads((indir / "cue_profile.json").read_text(encoding="utf-8")))
    lr = GroupLogit(json.loads((indir / "lr_weights.json").read_text(encoding="utf-8")))
    gaz = json.loads((indir / "name_gazetteer.json").read_text(encoding="utf-8"))
    units = json.loads((indir / "count_units.json").read_text(encoding="utf-8"))
    return Model(profile, lr, gaz, units)


if __name__ == "__main__":
    from linking import Lexicon
    lex = Lexicon(HERE.parents[1] / "data" / "lexicon.json")
    rows = load_dev()
    m = fit(rows, lex, verbose=True)
    save(m, HERE / "model")
    print("saved", HERE / "model")
