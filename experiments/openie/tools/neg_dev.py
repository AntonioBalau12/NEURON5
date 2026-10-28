"""Dev-only: gold facts of non-boolean kind in rows containing negation; attributes with several kinds."""
import csv, json, re, sys, collections
sys.stdout.reconfigure(encoding="utf-8")
rows = list(csv.DictReader(open('experiments/shared/data/dev_rows.csv', encoding='utf-8-sig', newline='')))
NEG = re.compile(r"\b(not|no|never|none|nobody|nothing|neither|nor|without|cannot)\b|n't", re.I)
n = 0
for r in rows:
    if NEG.search(r['text']):
        f = json.loads(r['form'])
        nb = [x for x in f if x['value']['kind'] != 'boolean']
        if nb and n < 40:
            n += 1
            print(r['id'], r['text'][:170]); [print('    ', x['attribute'], json.dumps(x['value'])) for x in f]
kinds = collections.defaultdict(collections.Counter)
for r in rows:
    for x in json.loads(r['form']):
        kinds[x['attribute']][x['value']['kind']] += 1
print({a: dict(c) for a, c in kinds.items() if len(c) > 1})
# boolean values distribution vs negation
c = collections.Counter()
for r in rows:
    for x in json.loads(r['form']):
        if x['value']['kind'] == 'boolean':
            c[(x['value']['value'], bool(NEG.search(r['text'])))] += 1
print(c)
