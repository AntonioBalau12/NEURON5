"""Dev-only: classify why gold facts are missed (subject absent from sentence / value not found / mapping)."""
import collections
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from learn import LEXICON, load_dev, train  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402

rows = load_dev()
ex = Extractor(LEXICON, train(rows, LEXICON), Params())
cls = collections.Counter()
samples = collections.defaultdict(list)
for r in rows:
    sents = ex.analyse(r["text"])
    facts = ex.extract(r)
    got = {(f["subject"], f["attribute"], json.dumps(f["value"], sort_keys=True)) for f in facts
           if f["value"] and f["parse_status"] == "complete"}
    for g in json.loads(r["form"]):
        k = (g["subject"], g["attribute"], json.dumps({a: b for a, b in g["value"].items() if a != "op"}, sort_keys=True))
        if k in got:
            continue
        kind = g["value"]["kind"]
        has_subj = any(m.entity == g["subject"] for s in sents for m in s.mentions)
        if kind == "boolean":
            found = True
        elif kind == "name":
            found = any(v.surface == g["value"]["value"] for s in sents for v in s.names)
        else:
            want = {a: b for a, b in g["value"].items() if a != "op"}
            found = any(v.value == want for s in sents for v in s.vals)
        c = ("subj_in_sentence" if has_subj else "subj_absent", "value_found" if found else "value_not_found", kind)
        cls[c] += 1
        samples[c].append((r["id"], g["subject"], g["attribute"], g["value"], r["text"][:140]))
for c, n in sorted(cls.items(), key=lambda x: -x[1]):
    print(n, c)
random.seed(5)
sel = sys.argv[1] if len(sys.argv) > 1 else None
for c, xs in samples.items():
    if sel and sel not in str(c):
        continue
    print("=====", c, len(xs))
    for x in random.sample(xs, min(int(sys.argv[2]) if len(sys.argv) > 2 else 8, len(xs))):
        print("  ", x[0], x[1], "|", x[2], "|", json.dumps(x[3]), "|", x[4])
