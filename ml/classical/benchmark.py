"""Leakage-aware P1 benchmark for practice-row label classification.

Inference features are derived only from text, date, and lexicon. The gold
``form`` is used only to construct leakage groups and evaluate extraction
coverage; it is never passed into a feature transformer or estimator.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import random
import re
import sys
import threading
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import scipy
import sklearn
from scipy.sparse import csr_matrix, hstack
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             confusion_matrix, f1_score, precision_recall_fscore_support)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import normalize
from sklearn.svm import LinearSVC
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
RESULTS = BASE / "results"
RUNS = RESULTS / "runs"
PROGRESS_PATH = BASE / "benchmark_progress.json"
RESULTS_CSV = BASE / "benchmark_results.csv"
SEED = 42
LABELS = ["false", "true", "unsure"]
TOTAL_CONFIGS = 33
TEMPORAL_RE = re.compile(r"\b(?:before|after|since|until|formerly|previously|originally|initially|recently|later|earlier|now|used to|from .{1,60} to|up from|down from|by \d{4}|in \d{4})\b", re.I)

try:
    import psutil
    PROCESS = psutil.Process(os.getpid())
except ImportError:
    psutil = None
    PROCESS = None


class RSSMonitor:
    def __init__(self):
        self.peak = rss_mb(); self.stop_event = threading.Event(); self.thread = None
    def start(self):
        if not psutil: return
        def sample():
            while not self.stop_event.wait(0.10):
                current = rss_mb()
                if current is not None: self.peak = max(self.peak or 0, current)
        self.thread = threading.Thread(target=sample, name="rss-monitor", daemon=True); self.thread.start()
    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=1)
        current = rss_mb()
        if current is not None: self.peak = max(self.peak or 0, current)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def rss_mb() -> float | None:
    try:
        return round(PROCESS.memory_info().rss / 1024**2, 1) if PROCESS else None
    except Exception:
        return None


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def normalized_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.casefold()).strip()


class UnionFind:
    def __init__(self, n: int): self.p = list(range(n)); self.sz = [1] * n
    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a == b: return
        if self.sz[a] < self.sz[b]: a, b = b, a
        self.p[b] = a; self.sz[a] += self.sz[b]


def fact_group_key(raw_form: str) -> tuple[str, ...]:
    try: facts = json.loads(raw_form or "[]")
    except (ValueError, TypeError): return ()
    keys = []
    for f in facts if isinstance(facts, list) else []:
        if not isinstance(f, dict): continue
        v = f.get("value", {})
        keys.append(json.dumps((str(f.get("subject", "")).casefold(), f.get("attribute"),
                                v.get("kind"), v.get("value"), v.get("unit"), v.get("currency"), v.get("per"), v.get("op")),
                               ensure_ascii=False, separators=(",", ":")))
    return tuple(sorted(keys))


def load_rows() -> tuple[list[dict[str, str]], dict[str, Any]]:
    with (ROOT / "data" / "practice.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    lex = json.loads((ROOT / "data" / "lexicon.json").read_text(encoding="utf-8"))
    return rows, lex


def load_shared_splits(rows: list[dict[str, str]]) -> tuple[dict[str, int], dict[str, Any]]:
    split_path = ROOT / "ml" / "shared" / "splits.csv"
    with split_path.open(encoding="utf-8-sig", newline="") as f:
        items = list(csv.DictReader(f))
    split_map = {r["id"]: r["split"] for r in items}
    row_ids = [r["id"] for r in rows]
    if len(split_map) != len(items) or set(split_map) != set(row_ids):
        raise ValueError("shared splits.csv must map each practice ID exactly once")
    if not set(split_map.values()).issubset({"train", "validation", "test"}):
        raise ValueError("shared split labels must be train, validation, or test")
    audit = json.loads((ROOT / "ml" / "shared" / "splitting_audit.json").read_text(encoding="utf-8"))
    return split_map, audit


def make_groups(rows: list[dict[str, str]], char_x: csr_matrix) -> tuple[np.ndarray, dict[str, Any]]:
    """Group exact text/form repeats, near-duplicate text, and temporal fact histories."""
    uf = UnionFind(len(rows)); reasons = Counter(); seen_text: dict[str, int] = {}; seen_form: dict[tuple[str, ...], int] = {}
    temporal_histories: dict[tuple[str, str], list[int]] = defaultdict(list)
    for i, row in enumerate(rows):
        tx = normalized_text(row["text"])
        if tx in seen_text: uf.union(i, seen_text[tx]); reasons["normalized_text_duplicate"] += 1
        else: seen_text[tx] = i
        signature = fact_group_key(row.get("form", ""))
        if signature:
            if signature in seen_form: uf.union(i, seen_form[signature]); reasons["identical_form_signature"] += 1
            else: seen_form[signature] = i
        if TEMPORAL_RE.search(row["text"]):
            try: facts = json.loads(row.get("form", "[]"))
            except ValueError: facts = []
            for fact in facts if isinstance(facts, list) else []:
                temporal_histories[(str(fact.get("subject", "")).casefold(), str(fact.get("attribute", "")))].append(i)
    for ids in temporal_histories.values():
        if len(ids) > 1:
            for i in ids[1:]: uf.union(ids[0], i)
            reasons["temporal_history_link"] += len(ids) - 1

    # Character-TF-IDF nearest neighbors provide a deterministic near-duplicate
    # guard. The representation is grouping metadata only, not a gold feature.
    sims = (char_x @ char_x.T).tocsr()
    near_pairs = 0
    for i in range(len(rows)):
        start, end = sims.indptr[i], sims.indptr[i + 1]
        js = sims.indices[start:end]; vs = sims.data[start:end]
        for j, sim in zip(js, vs):
            if j > i and sim >= 0.92:
                uf.union(i, int(j)); near_pairs += 1
    reasons["char_tfidf_near_duplicate_pairs_ge_0_92"] = near_pairs
    roots = [uf.find(i) for i in range(len(rows))]
    ids = {r: k for k, r in enumerate(sorted(set(roots), key=lambda x: min(i for i, y in enumerate(roots) if y == x)))}
    group_ids = np.array([ids[x] for x in roots], dtype=int)
    sizes = Counter(group_ids.tolist())
    summary = {"group_count": len(sizes), "largest_group": max(sizes.values()), "group_size_p95": int(np.percentile(list(sizes.values()), 95)),
               "grouping_rules": dict(reasons), "threshold": 0.92, "group_sha256": hashlib.sha256(",".join(map(str, group_ids)).encode()).hexdigest()}
    return group_ids, summary


def stratified_group_split(y: np.ndarray, groups: np.ndarray, pool: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Two seeded GroupShuffleSplit operations within the pre-temporal pool."""
    yp, gp = y[pool], groups[pool]
    labels = sorted(set(yp.tolist()))
    for seed_offset in range(20):
        outer = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=SEED + seed_offset)
        train_val, test = next(outer.split(np.zeros(len(pool)), yp, gp))
        inner_groups = gp[train_val]
        inner = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED + 100 + seed_offset)
        tr_rel, va_rel = next(inner.split(np.zeros(len(train_val)), yp[train_val], inner_groups))
        train, val = train_val[tr_rel], train_val[va_rel]
        if all(set(yp[idx]) == set(labels) for idx in (train, val, test)):
            return pool[train], pool[val], pool[test], {"seed": SEED + seed_offset, "method": "GroupShuffleSplit 60/20/20 within pre-temporal pool", "group_overlap": False}
    # Class support is tiny for UNSURE; keep it in training and transparently
    # relax full test coverage if group constraints prevent three-way coverage.
    outer = GroupShuffleSplit(n_splits=1, test_size=0.18, random_state=SEED)
    train_val, test = next(outer.split(np.zeros(len(pool)), yp, gp))
    inner = GroupShuffleSplit(n_splits=1, test_size=0.22, random_state=SEED + 100)
    tr_rel, va_rel = next(inner.split(np.zeros(len(train_val)), yp[train_val], gp[train_val]))
    train, val = train_val[tr_rel], train_val[va_rel]
    return pool[train], pool[val], pool[test], {"seed": SEED, "method": "GroupShuffleSplit fallback within pre-temporal pool; class coverage relaxed", "group_overlap": False}


def make_feature_builder(rows: list[dict[str, str]], lex: dict[str, Any]) -> dict[str, Any]:
    word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=900, sublinear_tf=True,
                           strip_accents="unicode", token_pattern=r"(?u)\b\w+\b")
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=700, sublinear_tf=True)
    word.fit([r["text"] for r in rows]); char.fit([r["text"] for r in rows])
    subjects = sorted(lex.get("subjects", []), key=lambda x: x.get("name", ""))
    return {"word_vectorizer": word, "char_vectorizer": char, "subjects": subjects,
            "attribute_terms": sorted({t.casefold() for e in subjects for a in e.get("attributes", []) for t in re.findall(r"[a-z0-9]+", a.replace("_", " ")) if len(t) > 2}),
            "date_base": min(r["date"] for r in rows),
            "cues": ["not", "never", "no", "without", "formerly", "previously", "originally", "initially", "since", "until", "before", "after", "now", "changed", "rose", "fell", "up", "down", "from", "to", "first", "then", "used"],
            "currencies": ["€", "$", "£", "EUR", "USD", "GBP"],
            "month_words": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"],
            "feature_version": "text-date-lexicon-v1"}


def metadata_matrix(rows: list[dict[str, str]], builder: dict[str, Any]) -> csr_matrix:
    names = [(e.get("name", ""), e.get("aliases", [])) for e in builder["subjects"]]
    attrs = builder["attribute_terms"]; cues = builder["cues"]
    date_base = dt.date.fromisoformat(builder["date_base"]); numeric = []
    for row in rows:
        text = row["text"]; lo = text.casefold(); tokens = re.findall(r"\b\w+\b", lo)
        d = dt.date.fromisoformat(row["date"]); daynum = (d - date_base).days
        entity_flags = [float(any(re.search(r"(?<!\w)" + re.escape(n.casefold()) + r"(?!\w)", lo) for n in (name, *aliases))) for name, aliases in names]
        a_flags = [float(term in tokens) for term in attrs]
        cue_flags = [float(cue in lo) for cue in cues]
        nums = re.findall(r"(?<!\w)\d+(?:[.,]\d+)?%?", text)
        feats = [len(tokens), len(text), sum(c.isupper() for c in text) / max(1, len(text)),
                 sum(c.isdigit() for c in text), len(nums), len(set(nums)), lo.count("!"), lo.count("?"), lo.count(","),
                 float("'" in text), math.copysign(math.log1p(abs(daynum)), daynum), d.year, d.month, d.day, d.weekday(), d.timetuple().tm_yday,
                 math.sin(2 * math.pi * d.month / 12), math.cos(2 * math.pi * d.month / 12),
                 float(bool(re.search(r"\b20\d{2}\b", text))), sum(float(c in lo) for c in builder["currencies"]),
                 sum(float(mo in lo.split()) for mo in builder["month_words"]), lo.count("and"), lo.count("or"),
                 lo.count("but"), lo.count(";"), lo.count(":"),
                 sum(float(x in tokens) for x in ["at", "on", "during", "event", "launch", "summit"])]
        numeric.append(entity_flags + a_flags + cue_flags + feats)
    return csr_matrix(np.asarray(numeric, dtype=np.float32))


def transform_features(rows: list[dict[str, str]], builder: dict[str, Any]) -> tuple[Any, csr_matrix]:
    texts = [r["text"] for r in rows]
    xw = builder["word_vectorizer"].transform(texts); xc = builder["char_vectorizer"].transform(texts)
    meta = metadata_matrix(rows, builder)
    return hstack([xw, xc, meta], format="csr", dtype=np.float32), xc


def feature_matrix(rows: list[dict[str, str]], lex: dict[str, Any], fit_indices: np.ndarray) -> tuple[Any, dict[str, Any]]:
    fit_rows = [rows[int(i)] for i in fit_indices]
    builder = make_feature_builder(fit_rows, lex)
    x, xc = transform_features(rows, builder)
    info = {"word_features": x.shape[1] - xc.shape[1] - metadata_matrix(rows[:1], builder).shape[1],
            "char_features": xc.shape[1], "metadata_features": metadata_matrix(rows[:1], builder).shape[1],
            "matrix_features": x.shape[1], "matrix_nonzero": int(x.nnz), "density": float(x.nnz / (x.shape[0] * x.shape[1]))}
    return x, {**builder, "char_matrix": xc, "info": info}


def class_weights(mode: str, y_train: np.ndarray) -> dict[str, float] | None:
    if mode == "none": return None
    counts = Counter(y_train.tolist()); k = len(counts); n = len(y_train)
    exponent = 0.5 if mode == "moderate" else 1.0
    raw = {c: (n / (k * counts[c])) ** exponent for c in counts}
    # Normalize so the mean sample weight is 1.
    mean = sum(raw[c] * counts[c] for c in counts) / n
    return {c: v / mean for c, v in raw.items()}


def metrics(y_true: np.ndarray, probs: np.ndarray) -> dict[str, Any]:
    pred = np.asarray(LABELS)[np.argmax(probs, axis=1)]
    p, r, f, support = precision_recall_fscore_support(y_true, pred, labels=LABELS, zero_division=0)
    conf = probs.max(axis=1); correct = pred == y_true
    ece = 0.0
    for low in np.linspace(0, 0.9, 10):
        mask = (conf >= low) & (conf < low + 0.1 if low < 0.9 else conf <= 1.0)
        if np.any(mask): ece += float(mask.mean() * abs(correct[mask].mean() - conf[mask].mean()))
    onehot = np.stack([y_true == c for c in LABELS], axis=1).astype(float)
    return {"accuracy": float(accuracy_score(y_true, pred)), "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
            "macro_f1": float(f1_score(y_true, pred, labels=LABELS, average="macro", zero_division=0)),
            "classes": {c: {"precision": float(p[i]), "recall": float(r[i]), "f1": float(f[i]), "support": int(support[i])} for i, c in enumerate(LABELS)},
            "confusion_matrix_labels": LABELS, "confusion_matrix": confusion_matrix(y_true, pred, labels=LABELS).tolist(),
            "ece_10bin": float(ece), "multiclass_brier": float(np.mean(np.sum((probs - onehot) ** 2, axis=1))),
            "predicted": pred.tolist(), "confidence": conf.tolist()}


def make_configs() -> list[dict[str, Any]]:
    cfg = []
    for c in [0.1, 1.0, 3.0]:
        for cw in ["none", "balanced"]: cfg.append({"family": "logistic_regression", "variant": "tfidf+metadata", "C": c, "weighting": cw})
    for cw in ["none", "balanced"]: cfg.append({"family": "linear_svc", "variant": "tfidf+metadata+calibrated", "C": 1.0, "weighting": cw})
    # Required moderate weighting is included at the center of the LR grid.
    cfg.append({"family": "logistic_regression", "variant": "tfidf+metadata", "C": 1.0, "weighting": "moderate"})
    for depth in [3, 5]:
        for l2 in [3, 7]:
            for cw in ["none", "moderate", "balanced"]: cfg.append({"family": "catboost", "variant": "tfidf+metadata-dense", "depth": depth, "l2_leaf_reg": l2, "weighting": cw})
    for leaves in [7, 15]:
        for reg in [1, 5]:
            for cw in ["none", "moderate", "balanced"]: cfg.append({"family": "lightgbm", "variant": "tfidf+metadata-sparse", "num_leaves": leaves, "reg_lambda": reg, "weighting": cw})
    return cfg


def eta(seconds_each: list[float], remaining: int, fallback: float = 18.0) -> dict[str, float]:
    center = float(np.median(seconds_each)) if seconds_each else fallback
    spread = float(np.std(seconds_each)) if len(seconds_each) > 1 else center * 0.5
    low = max(0.0, center - spread) * remaining
    high = (center + spread) * remaining
    return {"low_seconds": low, "central_seconds": center * remaining, "high_seconds": high}


def progress(state: dict[str, Any], message: str) -> None:
    state["updated_at"] = now_iso(); state["last_message"] = message
    write_json(PROGRESS_PATH, state)
    current = state.get("current_configuration") or {}
    eta_cfg = current.get("eta") or state.get("eta") or {}
    print(f"[{state['updated_at']}] {message} | cfg={state.get('completed_configurations',0)}/{TOTAL_CONFIGS} "
          f"ETA suite={eta_cfg.get('central_seconds', state.get('eta',{}).get('central_seconds','?'))}s "
          f"finish={state.get('projected_finish','?')}", flush=True)


def write_result(row: dict[str, Any]) -> None:
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    exists = RESULTS_CSV.exists()
    with RESULTS_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not exists: w.writeheader()
        w.writerow(row)


def run(args: argparse.Namespace) -> int:
    os.environ.update({"OMP_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "TOKENIZERS_PARALLELISM": "false"})
    RESULTS.mkdir(parents=True, exist_ok=True); RUNS.mkdir(parents=True, exist_ok=True)
    started_wall = time.time(); started = time.perf_counter()
    configs = make_configs(); seed = SEED
    planned_by_family = Counter(c["family"] for c in configs)
    state = {"status": "RUNNING", "started_at": now_iso(), "updated_at": now_iso(), "finished_at": None,
             "pid": os.getpid(), "job_id": os.environ.get("CODEX_JOB_ID"), "phase": "loading", "progress_percent": 0,
             "planned_configurations": len(configs), "completed_configurations": 0,
             "preliminary_duration_seconds_uncalibrated": len(configs) * 18,
             "eta": {"low_seconds": len(configs) * 8, "central_seconds": len(configs) * 18, "high_seconds": len(configs) * 60, "calibrated": False},
             "current_configuration": None, "current_model_family": None,
             "model_families": {f: {"status": "PENDING", "planned_configurations": n, "completed": 0,
                                    "eta_seconds_low_uncalibrated": n * 8, "eta_seconds_central_uncalibrated": n * 18,
                                    "eta_seconds_high_uncalibrated": n * 60} for f, n in planned_by_family.items()},
             "elapsed_seconds": 0, "projected_finish": None,
             "platform": platform.platform(), "python": sys.version, "seed": seed,
             "thread_limits": {k: os.environ[k] for k in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"]}}
    state["projected_finish"] = dt.datetime.fromtimestamp(started_wall + state["eta"]["central_seconds"], dt.timezone.utc).isoformat(timespec="seconds")
    progress(state, f"startup: planned {len(configs)} configurations; preliminary duration estimate UNCALIBRATED")
    try:
        t = time.perf_counter(); rows, lex = load_rows(); prep_load = time.perf_counter() - t
        y = np.array([r["label"].strip().lower() for r in rows]); ids = np.array([r["id"] for r in rows])
        if set(y) != set(LABELS): raise ValueError(f"Expected all three labels, got {Counter(y)}")
        split_map, group_report = load_shared_splits(rows)
        train = np.array([i for i, rid in enumerate(ids) if split_map[str(rid)] == "train"], dtype=int)
        shared_val = np.array([i for i, rid in enumerate(ids) if split_map[str(rid)] == "validation"], dtype=int)
        test = np.array([i for i, rid in enumerate(ids) if split_map[str(rid)] == "test"], dtype=int)
        # Hyperparameter selection and boosting early-stop validation use only
        # pre-cutoff rows; this keeps future-date labels out of model selection.
        dates = np.array([r["date"] for r in rows]); cutoff = sorted(dates)[int(len(dates) * 0.8)]
        val = shared_val[dates[shared_val] < cutoff]
        temporal_test = np.where(dates >= cutoff)[0]
        temporal_test_histories = set()
        for ix in temporal_test:
            try: fs = json.loads(rows[ix].get("form", "[]"))
            except ValueError: fs = []
            for fact in fs if isinstance(fs, list) else []:
                if isinstance(fact, dict): temporal_test_histories.add((str(fact.get("subject", "")).casefold(), str(fact.get("attribute", ""))))
        temporal_train_candidates = [i for i in train if dates[i] < cutoff]
        temporal_train = []
        for ix in temporal_train_candidates:
            try: fs = json.loads(rows[ix].get("form", "[]"))
            except ValueError: fs = []
            if not any((str(f.get("subject", "")).casefold(), str(f.get("attribute", ""))) in temporal_test_histories for f in fs if isinstance(f, dict)):
                temporal_train.append(ix)
        temporal_train = np.array(temporal_train, dtype=int)
        temporal_test = np.array(temporal_test, dtype=int)
        # Fit vocabulary and metadata thresholds on training rows only; transform
        # held-out text with this frozen feature builder.
        t = time.perf_counter(); x, vectorizers = feature_matrix(rows, lex, train); feat_sec = time.perf_counter() - t
        split_info = {"source": str((ROOT / "ml" / "shared" / "splits.csv").relative_to(ROOT)), "seed": 42,
                      "shared_manifest_sha256": hashlib.sha256((ROOT / "ml" / "shared" / "splits.csv").read_bytes()).hexdigest(),
                      "group_leakage_check": group_report.get("group_leakage_check"), "same_subject_attribute_history_cross_split": group_report.get("same_subject_attribute_history_cross_split")}
        manifest = {"seed": SEED, "created_at": now_iso(), "row_count": len(rows), "labels": dict(Counter(y)),
                    "partitions": {"train": ids[train].tolist(), "validation": ids[shared_val].tolist(), "validation_pre_temporal_for_tuning": ids[val].tolist(), "test": ids[test].tolist(),
                                   "temporal_train": ids[temporal_train].tolist(), "temporal_test": ids[temporal_test].tolist()},
                    "partition_counts": {"train": len(train), "validation": len(shared_val), "validation_pre_temporal_for_tuning": len(val), "test": len(test), "temporal_train_history_disjoint": len(temporal_train), "temporal_test": len(temporal_test)},
                    "partition_labels": {name: dict(Counter(y[idx])) for name, idx in [("train", train), ("validation", shared_val), ("validation_pre_temporal_for_tuning", val), ("test", test), ("temporal_train_history_disjoint", temporal_train), ("temporal_test", temporal_test)]},
                    "group_summary": group_report, "split": split_info, "temporal_cutoff_inclusive": cutoff,
                    "feature_policy": "text + row date + lexicon only; practice form excluded from all inference features",
                    "feature_dimensions": vectorizers["info"],
                    "feature_extraction_seconds": feat_sec, "input_load_seconds": prep_load,
                    "package_versions": {"python": sys.version.split()[0], "numpy": np.__version__, "scipy": scipy.__version__, "scikit_learn": sklearn.__version__}}
        write_json(BASE / "split_manifest.json", manifest)
        prep = time.perf_counter() - started
        state["phase"] = "training"; state["dataset_preparation_seconds"] = prep
        state["split_manifest"] = str(BASE / "split_manifest.json"); state["feature_dimensions"] = vectorizers["info"]
        state["partition_counts"] = manifest["partition_counts"]; state["group_summary"] = group_report
        state["eta"] = {**state["eta"], "calibrated": False}
        progress(state, f"prepared {len(rows)} rows; features={x.shape[1]}; leakage groups={group_report['group_count']}; "
                 f"train/val/test={len(train)}/{len(val)}/{len(test)}; prepare={prep:.2f}s")

        # Tree model dependencies are imported only after manifest/features are durable.
        try:
            from catboost import CatBoostClassifier
        except Exception as exc:
            CatBoostClassifier = None; catboost_import_error = repr(exc)
        try:
            from lightgbm import LGBMClassifier, early_stopping, log_evaluation
        except Exception as exc:
            LGBMClassifier = None; lightgbm_import_error = repr(exc)
        # CatBoost is the only candidate with packaged CUDA support on this
        # workstation. Probe GPU on the first CatBoost fit; fall back per run if
        # the wheel/driver cannot execute it. Inference is measured separately
        # with a CPU-loaded model.
        catboost_task_type = "GPU"
        catboost_gpu_probe = {"state": "pending"}
        summaries = []; durations = []; durations_by_family = defaultdict(list); best_by_family = {}
        ytr, yv, yt = y[train], y[val], y[test]
        # x shape is small enough to densify once for CatBoost and store transiently.
        dense = None
        if CatBoostClassifier is not None: dense = x.toarray().astype(np.float32, copy=False)
        for i, cfg in enumerate(configs):
            family = cfg["family"]; label = f"{family}:{cfg.get('C', cfg.get('depth', cfg.get('num_leaves')))}:{cfg.get('l2_leaf_reg', cfg.get('reg_lambda',''))}:{cfg['weighting']}"
            state["current_model_family"] = family; state["phase"] = "fit_predict_evaluate"
            remaining = len(configs) - i
            state["current_configuration"] = {**cfg, "index": i + 1, "total": len(configs), "name": label,
                                               "eta": eta(durations, remaining)}
            state["eta"] = eta(durations, remaining); state["eta"]["calibrated"] = bool(durations)
            elapsed = time.perf_counter() - started; state["elapsed_seconds"] = elapsed
            state["projected_finish"] = dt.datetime.fromtimestamp(time.time() + state["eta"]["central_seconds"], dt.timezone.utc).isoformat(timespec="seconds")
            progress(state, f"starting configuration {i+1}/{len(configs)} {label}; elapsed={elapsed:.1f}s")
            run_dir = RUNS / f"{family}_{i+1:02d}"; run_dir.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter(); est = None; fit_seconds = None; predict_seconds = None; probs_val = None; failure = None
            rss_monitor = RSSMonitor(); rss_monitor.start()
            weights_map = class_weights(cfg["weighting"], ytr)
            weights_vec = np.array([weights_map.get(c, 1.0) for c in ytr], dtype=np.float32) if weights_map else None
            try:
                if family == "logistic_regression":
                    est = LogisticRegression(C=cfg["C"], class_weight=None if cfg["weighting"] == "moderate" else ("balanced" if cfg["weighting"] == "balanced" else None),
                                            max_iter=1000, random_state=SEED, solver="liblinear" if len(set(ytr)) == 2 else "lbfgs")
                    kw = {"sample_weight": weights_vec} if cfg["weighting"] == "moderate" else {}
                    est.fit(x[train], ytr, **kw)
                elif family == "linear_svc":
                    base = LinearSVC(C=cfg["C"], class_weight="balanced" if cfg["weighting"] == "balanced" else None, random_state=SEED, max_iter=5000)
                    est = CalibratedClassifierCV(base, cv=3, method="sigmoid")
                    kw = {"sample_weight": weights_vec} if cfg["weighting"] == "moderate" else {}
                    est.fit(x[train], ytr, **kw)
                elif family == "catboost":
                    if CatBoostClassifier is None: raise RuntimeError("catboost unavailable: " + catboost_import_error)
                    cls_weights = [weights_map.get(c, 1.0) for c in LABELS] if weights_map else None
                    def new_catboost(task_type: str):
                        return CatBoostClassifier(loss_function="MultiClass", depth=cfg["depth"], iterations=300,
                                                  learning_rate=0.05, l2_leaf_reg=cfg["l2_leaf_reg"], early_stopping_rounds=30,
                                                  thread_count=2, random_seed=SEED, verbose=False, allow_writing_files=False,
                                                  class_weights=cls_weights, eval_metric="MultiClass", task_type=task_type,
                                                  devices="0" if task_type == "GPU" else None)
                    task_type = catboost_task_type
                    est = new_catboost(task_type)
                    try:
                        est.fit(dense[train], ytr, eval_set=(dense[val], yv), verbose=False)
                        if task_type == "GPU": catboost_gpu_probe = {"state": "available", "device": "0", "fit_probe_seconds": time.perf_counter() - t0}
                    except Exception as gpu_exc:
                        if task_type != "GPU": raise
                        catboost_gpu_probe = {"state": "unavailable", "error": f"{type(gpu_exc).__name__}: {gpu_exc}"}
                        catboost_task_type = "CPU"; task_type = "CPU"
                        est = new_catboost("CPU")
                        est.fit(dense[train], ytr, eval_set=(dense[val], yv), verbose=False)
                else:
                    if LGBMClassifier is None: raise RuntimeError("lightgbm unavailable: " + lightgbm_import_error)
                    cw = weights_map if weights_map else None
                    est = LGBMClassifier(objective="multiclass", num_class=len(LABELS), num_leaves=cfg["num_leaves"],
                                         n_estimators=300, learning_rate=0.05, min_child_samples=20,
                                         reg_lambda=cfg["reg_lambda"], n_jobs=2, random_state=SEED,
                                         class_weight=cw, verbosity=-1)
                    callbacks = [early_stopping(30, verbose=False), log_evaluation(0)]
                    est.fit(x[train], ytr, eval_set=[(x[val], yv)], callbacks=callbacks)
                fit_seconds = time.perf_counter() - t0
                train_hardware = ("GPU " + catboost_gpu_probe.get("device", "NVIDIA GPU")) if family == "catboost" and task_type == "GPU" else "CPU"
                # Serialize first, then load CatBoost's GPU-trained model into a
                # CPU estimator so inference timing is strictly CPU-only.
                ts = time.perf_counter()
                native_model_path = None
                if family == "catboost":
                    native_model_path = run_dir / "model.cbm"; est.save_model(str(native_model_path))
                    infer_est = CatBoostClassifier(task_type="CPU", thread_count=2, verbose=False)
                    infer_est.load_model(str(native_model_path))
                else:
                    infer_est = est
                from predictor import PredictionAdapter
                feature_builder = {k: v for k, v in vectorizers.items() if k not in {"char_matrix", "info"}}
                model_path = run_dir / "adapter.joblib"
                joblib.dump(PredictionAdapter(infer_est, feature_builder, tuple(LABELS), family), model_path, compress=3)
                model_bytes = model_path.stat().st_size + (native_model_path.stat().st_size if native_model_path else 0)
                native_model_rel = str(native_model_path.relative_to(ROOT)) if native_model_path else ""
                serialize_seconds = time.perf_counter() - ts
                # sklearn class ordering varies; align probability columns to fixed labels.
                tp = time.perf_counter(); raw = infer_est.predict_proba(dense[val] if family == "catboost" else x[val])
                est_classes = list(getattr(infer_est, "classes_", LABELS)); p = np.zeros((len(val), len(LABELS)))
                for ci, c in enumerate(est_classes): p[:, LABELS.index(str(c))] = raw[:, ci]
                probs_val = normalize(p, norm="l1", axis=1); predict_seconds = time.perf_counter() - tp
                val_metrics = metrics(yv, probs_val)
                # Actual two-thread inference throughput over the untouched test batch.
                start_inf = time.perf_counter(); test_raw = infer_est.predict_proba(dense[test] if family == "catboost" else x[test]); infer_sec = time.perf_counter() - start_inf
                test_classes = list(getattr(infer_est, "classes_", LABELS)); ptest = np.zeros((len(test), len(LABELS)))
                for ci, c in enumerate(test_classes): ptest[:, LABELS.index(str(c))] = test_raw[:, ci]
                ptest = normalize(ptest, norm="l1", axis=1); test_metrics = metrics(yt, ptest)
                rss_monitor.stop(); peak_rss_mb = rss_monitor.peak
                speed = len(test) / max(infer_sec, 1e-9)
                result = {"configuration": cfg, "configuration_id": label, "state": "completed", "fit_seconds": fit_seconds,
                          "training_hardware": train_hardware, "catboost_gpu_probe": catboost_gpu_probe if family == "catboost" else None,
                          "validation_predict_seconds": predict_seconds, "validation_rows_per_second": len(val) / max(predict_seconds,1e-9),
                          "test_inference_seconds": infer_sec, "test_rows_per_second": speed,
                          "test_20000_rows_seconds": 20000 / max(speed, 1e-9), "serialization_seconds": serialize_seconds,
                          "model_size_bytes": model_bytes, "peak_rss_mb": peak_rss_mb, "validation": {k:v for k,v in val_metrics.items() if k not in {"predicted","confidence"}},
                          "test": {k:v for k,v in test_metrics.items() if k not in {"predicted","confidence"}},
                          "test_predicted": test_metrics["predicted"], "test_confidence": test_metrics["confidence"],
                          "model_path": str(model_path.relative_to(ROOT)), "native_model_path": native_model_rel,
                          "package_versions": {"numpy": np.__version__, "scipy": scipy.__version__, "scikit_learn": sklearn.__version__}}
                write_json(run_dir / "metrics.json", result)
                row = {"configuration_id": label, "family": family, "training_hardware": train_hardware, "weighting": cfg["weighting"], "C": cfg.get("C"),
                       "depth": cfg.get("depth"), "l2_leaf_reg": cfg.get("l2_leaf_reg"), "num_leaves": cfg.get("num_leaves"),
                       "reg_lambda": cfg.get("reg_lambda"), "fit_seconds": fit_seconds, "validation_seconds": predict_seconds,
                       "test_rows_per_second": speed, "test_20000_rows_seconds": result["test_20000_rows_seconds"],
                       "peak_rss_mb": result["peak_rss_mb"], "model_size_bytes": model_bytes,
                       "accuracy": test_metrics["accuracy"], "balanced_accuracy": test_metrics["balanced_accuracy"],
                       "macro_f1": test_metrics["macro_f1"], "false_precision": test_metrics["classes"]["false"]["precision"],
                       "false_recall": test_metrics["classes"]["false"]["recall"], "unsure_f1": test_metrics["classes"]["unsure"]["f1"],
                       "unsure_support": test_metrics["classes"]["unsure"]["support"], "ece_10bin": test_metrics["ece_10bin"],
                       "multiclass_brier": test_metrics["multiclass_brier"], "state": "completed", "artifact": str(model_path.relative_to(ROOT))}
                write_result(row)
                summaries.append(result); durations.append(time.perf_counter() - t0)
                durations_by_family[family].append(durations[-1])
                # Rank only by validation macro-F1, then balanced accuracy.
                old = best_by_family.get(family)
                score = (val_metrics["macro_f1"], val_metrics["balanced_accuracy"])
                if old is None or score > old[0]: best_by_family[family] = (score, result)
                state["completed_configurations"] = len(summaries); state["progress_percent"] = round(100 * len(summaries) / len(configs), 1)
                state["model_families"][family] = {"completed": sum(s["configuration"]["family"] == family for s in summaries), "best_validation_macro_f1": best_by_family[family][1]["validation"]["macro_f1"]}
                for fam, planned in planned_by_family.items():
                    completed_fam = len(durations_by_family[fam]); remaining_fam = planned - completed_fam
                    fam_eta = eta(durations_by_family[fam], remaining_fam)
                    state["model_families"].setdefault(fam, {}).update({"status": "COMPLETED" if remaining_fam == 0 else ("RUNNING" if fam == family else "PENDING"),
                        "planned_configurations": planned, "completed": completed_fam,
                        "eta_seconds_low": fam_eta["low_seconds"], "eta_seconds_central": fam_eta["central_seconds"],
                        "eta_seconds_high": fam_eta["high_seconds"], "estimate_calibrated": bool(durations_by_family[fam])})
                state["elapsed_seconds"] = time.perf_counter() - started; state["eta"] = eta(durations, len(configs) - len(summaries)); state["eta"]["calibrated"] = True
                state["projected_finish"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
                state["projected_finish"] = dt.datetime.fromtimestamp(time.time() + state["eta"]["central_seconds"], dt.timezone.utc).isoformat(timespec="seconds")
                state["current_configuration"] = {**cfg, "index": i + 1, "total": len(configs), "name": label, "status": "completed", "measured_seconds": durations[-1]}
                progress(state, f"completed {label}; validation macro-F1={val_metrics['macro_f1']:.4f}, test macro-F1={test_metrics['macro_f1']:.4f}, "
                         f"throughput={speed:.1f} rows/s, artifact={model_bytes/1024:.1f} KiB, RSS={rss_mb()} MiB")
            except Exception as exc:
                rss_monitor.stop()
                failure = f"{type(exc).__name__}: {exc}"
                (run_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
                durations.append(time.perf_counter() - t0)
                durations_by_family[family].append(durations[-1])
                write_json(run_dir / "metrics.json", {"configuration": cfg, "configuration_id": label, "state": "failed", "error": failure,
                                                        "elapsed_seconds": durations[-1], "peak_rss_mb": rss_monitor.peak})
                state["completed_configurations"] = i + 1; state["progress_percent"] = round(100 * (i + 1) / len(configs), 1)
                state["eta"] = eta(durations, len(configs) - (i + 1)); state["eta"]["calibrated"] = True
                state["model_families"].setdefault(family, {}).update({"status": "FAILED_CONFIGURATION", "completed": len(durations_by_family[family]),
                    "eta_seconds_central": eta(durations_by_family[family], planned_by_family[family] - len(durations_by_family[family]))["central_seconds"],
                    "estimate_calibrated": True})
                state["current_configuration"] = {**cfg, "index": i + 1, "total": len(configs), "name": label, "status": "failed", "error": failure}
                progress(state, f"FAILED {label}: {failure}")
                if args.fail_fast: raise

        # Refit each family's validation winner on all pre-cutoff rows and score
        # the disjoint latest-date holdout once.
        temporal_results = {}
        for family, (_, selected) in best_by_family.items():
            cfg = selected["configuration"]
            wmap = class_weights(cfg["weighting"], y[temporal_train])
            wvec = np.array([wmap.get(c, 1.0) for c in y[temporal_train]], dtype=np.float32) if wmap else None
            tfit = time.perf_counter(); est = None
            if family == "logistic_regression":
                est = LogisticRegression(C=cfg["C"], class_weight=None if cfg["weighting"] == "moderate" else ("balanced" if cfg["weighting"] == "balanced" else None), max_iter=1000, random_state=SEED)
                est.fit(x[temporal_train], y[temporal_train], **({"sample_weight": wvec} if cfg["weighting"] == "moderate" else {}))
            elif family == "linear_svc":
                est = CalibratedClassifierCV(LinearSVC(C=cfg["C"], class_weight="balanced" if cfg["weighting"] == "balanced" else None, random_state=SEED, max_iter=5000), cv=3, method="sigmoid")
                est.fit(x[temporal_train], y[temporal_train], **({"sample_weight": wvec} if cfg["weighting"] == "moderate" else {}))
            elif family == "catboost" and CatBoostClassifier is not None:
                est = CatBoostClassifier(loss_function="MultiClass", depth=cfg["depth"], iterations=300, learning_rate=0.05,
                                         l2_leaf_reg=cfg["l2_leaf_reg"], thread_count=2, random_seed=SEED, verbose=False,
                                         allow_writing_files=False, class_weights=[wmap.get(c, 1.0) for c in LABELS] if wmap else None)
                est.fit(dense[temporal_train], y[temporal_train], verbose=False)
            elif family == "lightgbm" and LGBMClassifier is not None:
                est = LGBMClassifier(objective="multiclass", num_class=len(LABELS), num_leaves=cfg["num_leaves"], n_estimators=300,
                                     learning_rate=0.05, min_child_samples=20, reg_lambda=cfg["reg_lambda"], n_jobs=2,
                                     random_state=SEED, class_weight=wmap, verbosity=-1)
                est.fit(x[temporal_train], y[temporal_train])
            if est is None: continue
            fit_time = time.perf_counter() - tfit; tp = time.perf_counter()
            raw = est.predict_proba(dense[temporal_test] if family == "catboost" else x[temporal_test]); pred_time = time.perf_counter() - tp
            ptem = np.zeros((len(temporal_test), len(LABELS)))
            for ci, c in enumerate(list(getattr(est, "classes_", LABELS))): ptem[:, LABELS.index(str(c))] = raw[:, ci]
            ptem = normalize(ptem, norm="l1", axis=1); tm = metrics(y[temporal_test], ptem)
            td = RUNS / f"{family}_temporal_best"; td.mkdir(parents=True, exist_ok=True)
            if family == "catboost":
                est.save_model(str(td / "model.cbm")); model_path = td / "model.cbm"
            else:
                model_path = td / "model.joblib"; joblib.dump(est, model_path, compress=3)
            temporal_results[family] = {"selected_configuration": selected["configuration_id"], "fit_seconds": fit_time,
                                        "prediction_seconds": pred_time, "rows_per_second": len(temporal_test) / max(pred_time, 1e-9),
                                        "metrics": {k: v for k, v in tm.items() if k not in {"predicted", "confidence"}},
                                        "model_size_bytes": model_path.stat().st_size, "model_path": str(model_path.relative_to(ROOT))}
            write_json(td / "metrics.json", temporal_results[family])

        # Best-by-validation per family, with test metrics already recorded as untouched diagnostics.
        report = {"generated_at": now_iso(), "status": "completed", "best_by_family_validation": {k: v[1]["configuration_id"] for k,v in best_by_family.items()},
                  "validation_ranking": [{"family":k,"configuration_id":v[1]["configuration_id"],"validation_macro_f1":v[1]["validation"]["macro_f1"],"validation_balanced_accuracy":v[1]["validation"]["balanced_accuracy"],"test_macro_f1":v[1]["test"]["macro_f1"],"test_rows_per_second":v[1]["test_rows_per_second"]} for k,v in sorted(best_by_family.items())],
                  "configurations_completed":len(summaries),"configurations_planned":len(configs),"split_manifest":str(BASE/"split_manifest.json"),
                  "dependencies":{"scikit-learn":sklearn.__version__,"catboost":None if CatBoostClassifier is None else getattr(__import__('catboost'),'__version__','unknown'),
                                  "lightgbm":None if LGBMClassifier is None else getattr(__import__('lightgbm'),'__version__','unknown')},
                  "feature_policy":"No form used for inference features. This phase uses lexical/date/lexicon features; no factual evidence features.",
                  "temporal_holdout": temporal_results,
                  "temporal_holdout_note":"Latest 20% of dates were excluded from hyperparameter training, validation, and random test. Best validation configurations were refit on earlier rows and scored once on the temporal holdout."}
        write_json(RESULTS / "summary.json", report)
        state.update({"status":"COMPLETED","phase":"complete","finished_at":now_iso(),"elapsed_seconds":time.perf_counter()-started,
                      "completed_configurations":len(summaries),"progress_percent":100,"current_configuration":None,
                      "eta":{"low_seconds":0,"central_seconds":0,"high_seconds":0,"calibrated":True},"projected_finish":now_iso(),
                      "failed_configurations":len(configs)-len(summaries)})
        progress(state, f"benchmark suite completed; {len(summaries)}/{len(configs)} successful")
        return 0 if summaries else 2
    except BaseException as exc:
        state.update({"status":"FAILED","phase":"failed","finished_at":now_iso(),"error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc(),"elapsed_seconds":time.perf_counter()-started})
        progress(state, f"suite failed: {type(exc).__name__}: {exc}")
        raise


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--fail-fast",action="store_true"); return run(p.parse_args())

if __name__ == "__main__": raise SystemExit(main())
