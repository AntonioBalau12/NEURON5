"""Dev-only: show gold vs extracted facts for given dev row ids (final table trained on all dev rows)."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))
sys.stdout.reconfigure(encoding="utf-8")
from learn import LEXICON, load_dev  # noqa: E402
from oie.model import Model  # noqa: E402
from oie.pipeline import Extractor, Params  # noqa: E402

ex = Extractor(LEXICON, Model.load(HERE / "data" / "relation_table.json"), Params())
rows = {r["id"]: r for r in load_dev()}
lines = []
for rid in sys.argv[2:]:
    r = rows[rid]
    lines.append(f"### {rid} [{r['label']}] {r['text']}")
    for g in json.loads(r["form"]):
        lines.append(f"  GOLD  {g['subject']} | {g['attribute']} | {json.dumps(g['value'], ensure_ascii=False)}")
    for f in ex.extract(r):
        lines.append(f"  OURS  [{f['parse_status']}] {f['subject']} | {f['attribute']} | {json.dumps(f['value'], ensure_ascii=False)} "
                     f"neg={f['negated']} tq={f['temporal_qualifier']} span={f['source_text_span']!r} :: {f['notes'][:110]}")
open(sys.argv[1], "w", encoding="utf-8").write("\n".join(lines))
print(len(lines), "lines")
