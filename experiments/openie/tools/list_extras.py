"""Dev-only: print extras (predictions not in the gold form) from an eval_dev --dump file, for manual review."""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
path = sys.argv[1]
out = sys.argv[2]
d = json.load(open(path, encoding="utf-8"))
lines = []
for i, x in enumerate(d["extras"]):
    lines.append(f"{i} {x['source_row_id']} [{x['status']}] {x['subject']} | {x['attribute']} | "
                 f"{json.dumps(x['value'], ensure_ascii=False)} || {x['text']} || span: {x['span']}")
open(out, "w", encoding="utf-8").write("\n".join(lines))
print(len(lines), "extras")
