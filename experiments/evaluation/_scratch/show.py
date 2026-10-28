import json, sys
sys.path.insert(0, 'experiments/evaluation')
import common as C
ref = json.load(open('experiments/evaluation/worksheet/evaluator_reference.json', encoding='utf-8'))
out = []
for i, (rid, r) in enumerate(ref['rows'].items(), 1):
    text = {x['id']: x['text'] for x in C.read_csv(C.EVAL_ROWS)}[rid] if False else None
rows = {x['id']: x for x in C.read_csv(C.EVAL_ROWS)}
for i, (rid, r) in enumerate(ref['rows'].items(), 1):
    ff = ' | '.join(C.fmt_fact(f['subject'], f['attribute'], f['value']) for f in r['form_gold'])
    out.append(f"{i} {rid} [{r['split'][0]}/{rows[rid]['label']}/{rows[rid]['date']}] {rows[rid]['text']!r}\n    FORM: {ff}")
open('experiments/evaluation/_scratch/selected.txt', 'w', encoding='utf-8').write('\n'.join(out))
