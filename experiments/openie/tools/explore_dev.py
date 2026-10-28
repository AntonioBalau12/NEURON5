"""Dev-only exploration helper (reads dev_rows.csv forms; never touches practice.csv/_heldout)."""
import csv, json, collections, re, sys
sys.stdout.reconfigure(encoding="utf-8")
rows = list(csv.DictReader(open('experiments/shared/data/dev_rows.csv', encoding='utf-8-sig', newline='')))
mode = sys.argv[1] if len(sys.argv) > 1 else "stats"
if mode == "stats":
    full = list(csv.DictReader(open('experiments/shared/data/full_input.csv', encoding='utf-8-sig', newline='')))
    print(sum(1 for r in full if re.search('\u00e2', r['text'])), [r['text'] for r in full if '\u00e2' in r['text']][:3])
    print(collections.Counter(len(r['text']) // 50 * 50 for r in full).most_common(8))
    print(collections.Counter(len(json.loads(r['form'])) if r['form'] else 0 for r in rows))
    print(sum(1 for r in rows if not r['form'] or r['form'] == '[]'))
elif mode == "attrs":
    # per attribute: kind and sample texts
    by = collections.defaultdict(list)
    for r in rows:
        for x in (json.loads(r['form']) if r['form'] else []):
            by[(x['subject'], x['attribute'], x['value']['kind'])].append(r)
    q = sys.argv[2] if len(sys.argv) > 2 else ''
    for k, v in sorted(by.items()):
        if q and q != 'ALL' and q not in k[1] and q not in k[0]:
            continue
        print(k, len(v))
        for r in v[:int(sys.argv[3]) if len(sys.argv) > 3 else 3]:
            print("    ", r['id'], r['text'][:200])
elif mode == "noform":
    n = 0
    for r in rows:
        if not r['form'] or r['form'] == '[]':
            print(r['id'], r['label'], r['text'][:200]); n += 1
            if n > int(sys.argv[2]): break
elif mode == "multi":
    n = 0
    for r in rows:
        f = json.loads(r['form']) if r['form'] else []
        if len(f) >= 3:
            print(r['id'], r['text'][:300]); n += 1
            for x in f: print("     ", x['subject'], x['attribute'], json.dumps(x['value']))
            if n > int(sys.argv[2]): break
elif mode == "kinds":
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        for x in (json.loads(r['form']) if r['form'] else []):
            by[(x['subject'], x['attribute'])][x['value']['kind']] += 1
    for k, c in sorted(by.items()):
        print(k, dict(c))

