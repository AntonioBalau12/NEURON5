import csv, json, sys
rows = list(csv.DictReader(open('experiments/shared/_heldout/heldout_gold.csv', encoding='utf-8-sig')))
out = []
for x in rows:
    f = json.loads(x['form'])
    fs = ' | '.join("%s.%s=%s" % (a['subject'], a['attribute'], json.dumps(a['value'], ensure_ascii=False, separators=(',', ':'))) for a in f)
    out.append("%s %s %s :: %s  ==> %s" % (x['id'], x['date'], x['label'], x['text'].replace('\n', ' / '), fs))
open('experiments/evaluation/_scratch/dump.txt', 'w', encoding='utf-8').write('\n'.join(out))
