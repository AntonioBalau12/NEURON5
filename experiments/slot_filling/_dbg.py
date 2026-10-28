import json, sys
sys.path.insert(0, 'experiments/slot_filling')
from eval_dev import *
rows = load_dev()
cv = json.load(open('experiments/slot_filling/output/cv_facts.json', encoding='utf-8'))
kind = sys.argv[1]
mode = sys.argv[2]  # fp / fn
thr = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
lim = int(sys.argv[4]) if len(sys.argv) > 4 else 40
n = 0
for r in rows:
    gold = {fkey(g['subject'], g['attribute'], g['value']): g for g in r['gold']}
    pred = {fkey(f['subject'], f['attribute'], f['value']): f for f in cv.get(r['id'], []) if f['extraction_confidence'] >= thr}
    if mode == 'fp':
        for k, f in pred.items():
            if k not in gold and f['value']['kind'] == kind:
                n += 1
                if n <= lim:
                    print(r['id'], r['text'].replace('\n', ' '))
                    print('    PRED', f['subject'], f['attribute'], json.dumps(f['value']), f['extraction_confidence'], f['parse_status'])
                    for g in r['gold']:
                        print('    GOLD', g['subject'], g['attribute'], json.dumps(g['value']))
    else:
        for k, g in gold.items():
            if k not in pred and g['value']['kind'] == kind:
                n += 1
                if n <= lim:
                    allp = [f for f in cv.get(r['id'], [])]
                    print(r['id'], r['text'].replace('\n', ' '))
                    print('    GOLD', g['subject'], g['attribute'], json.dumps(g['value']))
                    for f in allp:
                        print('    PRED', f['subject'], f['attribute'], json.dumps(f['value']), f['extraction_confidence'])
print('total', n)
