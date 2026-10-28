"""Dev-only: how often is the gold subject / value literally present in the row text? (upper bound for same-row extraction)."""
import csv, json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
lex = json.load(open('data/lexicon.json', encoding='utf-8-sig'))
surf = {}
for s in lex['subjects']:
    surf[s['name']] = [s['name']] + s['aliases']
rows = list(csv.DictReader(open('experiments/shared/data/dev_rows.csv', encoding='utf-8-sig', newline='')))
tot = inrow = 0
miss = collections.Counter(); ex = []
for r in rows:
    t = r['text'].casefold()
    for x in json.loads(r['form']):
        tot += 1
        names = surf[x['subject']]
        ok = any(n.casefold() in t for n in names)
        if ok: inrow += 1
        else:
            miss[x['subject']] += 1
            if len(ex) < 40: ex.append((r['id'], x['subject'], x['attribute'], r['text'][:150]))
print(tot, inrow, inrow / tot)
print(miss.most_common(15))
for e in ex: print(e)
