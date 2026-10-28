import json, sys
sys.path.insert(0, 'experiments/slot_filling')
from eval_dev import *
from engine import *
from linking import Lexicon
lex = Lexicon('data/lexicon.json')
from engine import entity_mentions
rows = load_dev()
cv = json.load(open('experiments/slot_filling/output/cv_facts.json', encoding='utf-8'))
thr = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
show = sys.argv[2] if len(sys.argv) > 2 else None
kindf = sys.argv[3] if len(sys.argv) > 3 else None
from collections import Counter
cat = Counter(); catk = Counter()
ex = {}
for r in rows:
    names = {e.canon for e in entity_mentions(lex, r['text'])}
    preds = cv.get(r['id'], [])
    for g in r['gold']:
        gk = fkey(g['subject'], g['attribute'], g['value'])
        kind = g['value']['kind']
        hit = [f for f in preds if fkey(f['subject'], f['attribute'], f['value']) == gk]
        if hit and hit[0]['extraction_confidence'] >= thr:
            continue
        if g['subject'] not in names:
            c = 'subject_absent'
        elif hit:
            c = 'low_conf'
        elif any(f['value'] == g['value'] for f in preds):
            c = 'wrong_slot'
        else:
            c = 'no_candidate'
        cat[c] += 1; catk[(kind, c)] += 1
        ex.setdefault(c, []).append((r, g, preds))
print(cat)
for k in sorted(catk): print(k, catk[k])
if show:
    n = 0
    for r, g, preds in ex.get(show, []):
        if kindf and g['value']['kind'] != kindf: continue
        n += 1
        if n > 40: break
        print(r['id'], r['text'].replace('\n', ' '))
        print('    GOLD', g['subject'], g['attribute'], json.dumps(g['value']))
        for f in preds: print('    PRED', f['subject'], f['attribute'], json.dumps(f['value']), f['extraction_confidence'])
