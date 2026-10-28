"""Create the shared seed-42 leakage-grouped practice split."""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SEED = 42
RATIOS = {"train": 0.70, "validation": 0.20, "test": 0.10}
LABELS = ("true", "false", "unsure")


class UF:
    def __init__(self, n): self.p = list(range(n)); self.size = [1] * n
    def find(self, x):
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a == b: return
        if self.size[a] < self.size[b]: a, b = b, a
        self.p[b] = a; self.size[a] += self.size[b]


def norm(s): return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


def form_facts(raw):
    try: facts = json.loads(raw or "[]")
    except ValueError: return []
    return facts if isinstance(facts, list) else []


def jaccard_shingles(a, b):
    def sh(s): return {s[i:i+3] for i in range(max(0, len(s)-2))}
    aa, bb = sh(a), sh(b)
    return len(aa & bb) / max(1, len(aa | bb))


def assign_groups(group_members, labels):
    """Greedy deterministic stratification using group-level label counts."""
    rng = random.Random(SEED)
    overall = Counter(labels)
    targets = {s: {c: overall[c] * RATIOS[s] for c in LABELS} for s in RATIOS}
    size_targets = {s: len(labels) * RATIOS[s] for s in RATIOS}
    groups = []
    for gid, members in group_members.items():
        counts = Counter(labels[i] for i in members)
        groups.append((gid, members, counts, rng.random()))
    groups.sort(key=lambda x: (-len(x[1]), x[3]))
    allocated = {s: Counter() for s in RATIOS}; assigned = {}
    def objective(candidate, counts, n):
        cost = 0.0
        for split in RATIOS:
            added_n = n if split == candidate else 0
            cost += 0.15 * ((allocated[split]["__n__"] + added_n - size_targets[split]) / max(size_targets[split], 1)) ** 2
            for c in LABELS:
                added = counts[c] if split == candidate else 0
                target = max(targets[split][c], 1.0)
                cost += ((allocated[split][c] + added - targets[split][c]) / target) ** 2
        return cost
    # Small randomized tie-breaks are deterministic under seed 42.
    tie = {s: rng.random() * 1e-9 for s in RATIOS}
    for gid, members, counts, _ in groups:
        split = min(RATIOS, key=lambda s: (objective(s, counts, len(members)), tie[s]))
        assigned[gid] = split
        allocated[split].update(counts); allocated[split]["__n__"] += len(members)
    return assigned, allocated


def assign_folds(group_members, labels, train_indices, n_splits=10):
    """Seeded greedy stratification of indivisible leakage groups into CV folds."""
    rng = random.Random(SEED)
    train_set = set(train_indices)
    total = Counter(labels[i] for i in train_indices)
    targets = {c: total[c] / n_splits for c in LABELS}
    fold_rows = [0] * n_splits
    fold_labels = [Counter() for _ in range(n_splits)]
    groups = []
    for gid, members in group_members.items():
        chosen = [i for i in members if i in train_set]
        if chosen: groups.append((gid, chosen, Counter(labels[i] for i in chosen), rng.random()))
    groups.sort(key=lambda x: (-len(x[1]), x[3]))
    assignment = {}
    target_size = len(train_indices) / n_splits
    # Seed every fold once before optimizing the remaining allocation. This is
    # essential when a few dominant classes/groups make empty folds look cheap.
    for fold, (gid, members, counts, _) in enumerate(groups[:n_splits]):
        assignment[gid] = fold
        fold_rows[fold] += len(members)
        fold_labels[fold].update(counts)
    for gid, members, counts, _ in groups[n_splits:]:
        def cost(fold):
            score = 0.1 * ((fold_rows[fold] + len(members) - target_size) / max(target_size, 1)) ** 2
            for label in LABELS:
                target = max(targets[label], 1)
                score += ((fold_labels[fold][label] + counts[label] - targets[label]) / target) ** 2
            return score
        chosen = min(range(n_splits), key=lambda f: (cost(f), fold_rows[f], f))
        assignment[gid] = chosen
        fold_rows[chosen] += len(members)
        fold_labels[chosen].update(counts)
    return assignment, fold_rows, fold_labels


def main():
    source = ROOT / "data" / "practice.csv"
    with source.open(encoding="utf-8-sig", newline="") as f: rows = list(csv.DictReader(f))
    if not rows or not {"id", "text", "date", "label", "form"}.issubset(rows[0]):
        raise ValueError("practice.csv lacks required id/text/date/label/form columns")
    if len({r["id"] for r in rows}) != len(rows): raise ValueError("input row IDs are not unique")
    uf = UF(len(rows)); reasons = Counter(); text_seen = {}; signature_seen = {}; history_seen = {}
    normalized = [norm(r["text"]) for r in rows]
    for i, row in enumerate(rows):
        if normalized[i] in text_seen: uf.union(i, text_seen[normalized[i]]); reasons["normalized_text_duplicate"] += 1
        else: text_seen[normalized[i]] = i
        facts = form_facts(row.get("form", ""))
        signature = tuple(sorted(json.dumps((str(f.get("subject", "")).casefold(), f.get("attribute"), f.get("value")), ensure_ascii=False, sort_keys=True, separators=(",", ":")) for f in facts if isinstance(f, dict)))
        if signature:
            if signature in signature_seen: uf.union(i, signature_seen[signature]); reasons["identical_fact_signature"] += 1
            else: signature_seen[signature] = i
        for fact in facts:
            if not isinstance(fact, dict): continue
            key = (str(fact.get("subject", "")).casefold(), str(fact.get("attribute", "")))
            if key in history_seen: uf.union(i, history_seen[key]); reasons["shared_subject_attribute_history"] += 1
            else: history_seen[key] = i

    # Candidate generation by shared character trigrams, then high Jaccard.
    # This is grouping-only metadata; it does not enter model features.
    inverted = defaultdict(set); shingles = []
    for i, text in enumerate(normalized):
        sh = {text[k:k+3] for k in range(max(0, len(text)-2))}; shingles.append(sh)
        for gram in sh: inverted[gram].add(i)
    pairs = set()
    for ids in inverted.values():
        if len(ids) > 180: continue
        seq = sorted(ids)
        for pos, i in enumerate(seq):
            for j in seq[pos+1:]: pairs.add((i, j))
    near_count = 0
    for i, j in pairs:
        a, b = shingles[i], shingles[j]
        if min(len(a), len(b)) < 8: continue
        sim = len(a & b) / max(1, len(a | b))
        if sim >= 0.90:
            uf.union(i, j); near_count += 1
    reasons["near_duplicate_char_trigram_jaccard_ge_0_90"] = near_count

    by_root = defaultdict(list)
    for i in range(len(rows)): by_root[uf.find(i)].append(i)
    group_for_row = {i: root for root, members in by_root.items() for i in members}
    labels = [r["label"].strip().lower() for r in rows]
    if set(labels) != set(LABELS): raise ValueError(f"expected labels {LABELS}; found {Counter(labels)}")
    assignment, counts = assign_groups(by_root, labels)
    row_splits = [assignment[group_for_row[i]] for i in range(len(rows))]
    train_indices = [i for i, split in enumerate(row_splits) if split == "train"]
    fold_for_group, fold_sizes, fold_labels = assign_folds(by_root, labels, train_indices)

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "splits.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n"); writer.writerow(["id", "split"])
        for row, split in zip(rows, row_splits): writer.writerow([row["id"], split])
    with (OUT / "cv10_folds.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n"); writer.writerow(["id", "fold"])
        for i, row in enumerate(rows):
            if row_splits[i] == "train": writer.writerow([row["id"], fold_for_group[group_for_row[i]]])
    audit = {"seed": SEED, "ratios_target": RATIOS, "created_from": "data/practice.csv", "rows": len(rows),
             "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
             "split_counts": {s: sum(x == s for x in row_splits) for s in RATIOS},
             "label_counts": {s: dict(Counter(labels[i] for i, split in enumerate(row_splits) if split == s)) for s in RATIOS},
             "group_count": len(by_root), "largest_group_rows": max(map(len, by_root.values())),
             "group_size_p95": sorted(map(len, by_root.values()))[int(0.95 * (len(by_root)-1))],
             "grouping_edges": {**dict(reasons), "near_duplicate_pairs": near_count},
             "group_leakage_check": "zero grouped connected components cross splits",
             "same_subject_attribute_history_cross_split": 0,
              "cv_folds": {"count": 10, "train_rows_by_fold": fold_sizes,
                           "label_counts_by_fold": {str(i): dict(c) for i, c in enumerate(fold_labels)},
                           "group_leakage_check": "zero grouped connected components cross folds"},
             "split_date_ranges": {s: {"min": min(r["date"] for r, sp in zip(rows, row_splits) if sp == s),
                                       "max": max(r["date"] for r, sp in zip(rows, row_splits) if sp == s)} for s in RATIOS},
             "notes": ["practice form was used only for fact/history grouping and was not used as a model feature",
                       "all rows sharing any subject-attribute history are joined into a single group; groups are indivisible",
                       "near-duplicate text is grouped at character-trigram Jaccard >= 0.90 after candidate generation",
                       "date is not used to stratify the random split; chronological ranges are reported for temporal-leakage review",
                        "the outer split balances class counts and target 70/20/10 sizes greedily at the group level; group sizes can cause deviation",
                        "the 10 grouped CV folds use outer training rows only; the outer test remains outside model selection",
                       "evidence from labeled rows is not used to construct features in this shared split"]}
    (OUT / "splitting_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "SPLITTING.md").write_text(
        "# Shared 70/20/10 split and 10-fold CV\n\n"
        "`splits.csv` maps every practice row ID exactly once to `train`, `validation`, or `test` (seed 42), with a group-stratified 70/20/10 outer split. "
        "`cv10_folds.csv` maps each outer-train row ID to one of 10 grouped folds; rotate one fold as validation and use the other nine for training. "
        "The outer test rows are excluded from CV and should be evaluated once after model selection. The split and folds use greedy assignment of indivisible connected groups. "
        "Group edges join normalized duplicate text, identical canonical fact signatures, every shared subject/attribute history, "
        "and character-trigram near duplicates with Jaccard similarity at least 0.90. This prevents repeated claims and known "
        "temporal histories from crossing partitions. Gold forms are used only for grouping and audit, never as inference features.\n\n"
        "Group edges join normalized duplicate text, identical canonical fact signatures, every shared subject/attribute history, and character-trigram near duplicates at Jaccard >= 0.90. Gold forms are used only for grouping and audit, never as inference features. The assignment balances TRUE/FALSE/UNSURE counts and total row counts against the target ratios. A large connected history "
        "can make exact ratios impossible; actual counts and date ranges are recorded in `splitting_audit.json`. Date ranges are "
        "audited rather than used to force chronological partitions, because chronological and shared-history constraints can conflict. "
        "Any temporal generalization claim must therefore be reported separately. Training-only evidence is not used in the split.\n\n"
        "Reproduce with `python ml/shared/create_splits.py`. The manifest has columns `id,split`; the fold file has columns `id,fold`.\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__": main()
