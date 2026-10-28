import sys, collections, itertools
sys.path.insert(0, 'experiments/claim_factory')
from cf_common import *
from store import Params, Store
from observations import same_value

store = Store(PRACTICE_CSV, LEXICON_JSON)
P = Params(min_support_rows=1, block_on_false_candidates=True, volatile_max_age_days=10**6)
rows = []
for key in sorted(store.obs):
    sup = store.support(key)
    days = sorted({o.on for o in sup})
    for T in days[1:]:
        truth = [o for o in sup if o.on == T and o.clean]
        if not truth or any(not same_value(truth[0].value, o.value) for o in truth):
            continue
        r = store.asof_at(key, T, P)
        if not r.accepted or r.value is None:
            continue
        v = r.value
        happened = v.kind == 'date' and isinstance(v.value, str) and len(v.value) == 10 and v.value <= r.last.on.isoformat()
        span = (r.run[-1].on - r.run[0].on).days
        rows.append(dict(key=key, T=T, age=r.age_days, n=r.n_support_rows, vol=r.volatile, happened=happened, span=span,
                         kind=v.kind, ok=same_value(r.value, truth[0].value), attr=key[1]))
print(len(rows))
# change events per subject: (subject, date_of_new_value_observation)
chg = collections.defaultdict(list)
for key in store.obs:
    sup = store.support(key)
    prev = None
    for o in sup:
        if prev is not None and not same_value(o.value, prev.value) and o.on > prev.on and o.clean and prev.clean:
            chg[key[0]].append((o.on, key[1]))
        if prev is None or o.on >= prev.on:
            prev = o
allchg = sorted({d for l in chg.values() for d, _ in l})
import datetime
cnt = collections.Counter(d for l in chg.values() for d, _ in l)
print('change days with counts:', sorted(cnt.items())[:80])
for r in rows:
    L = r['T'] - datetime.timedelta(days=r['age'])
    r['subj_changed'] = any(L < d < r['T'] for d, a in chg[r['key'][0]] if a != r['key'][1])
    r['any_changed'] = any(L < d < r['T'] for d in allchg)
    r['self_unchanged_wave'] = None

def rate(sel, label):
    n = len(sel); bad = sum(1 for r in sel if not r['ok'])
    print(f"{label:60s} n={n:4d} contradicted={bad:3d} precision={(n-bad)/n if n else float('nan'):.3f}")

rate(rows, 'all')
rate([r for r in rows if r['happened']], 'happened dates')
rate([r for r in rows if not r['happened']], 'not happened')
for lo, hi in [(0, 1), (2, 3), (4, 7), (8, 14), (15, 30), (31, 60), (61, 120), (121, 999)]:
    sel = [r for r in rows if not r['happened'] and lo <= r['age'] <= hi]
    rate(sel, f'not-happened age {lo}-{hi}')
print('--- by n rows, not happened, age<=14')
for n in [1, 2, 3, 4, 6]:
    rate([r for r in rows if not r['happened'] and r['age'] <= 14 and (r['n'] >= n if n >= 3 else r['n'] == n)], f'n{"=" if n<3 else ">="}{n}')
print('--- by span, not happened, age<=14')
for lo, hi in [(0, 0), (1, 14), (15, 60), (61, 400)]:
    rate([r for r in rows if not r['happened'] and r['age'] <= 14 and lo <= r['span'] <= hi], f'span {lo}-{hi}')
print('--- age<=14 by volatile')
for v in (False, True):
    rate([r for r in rows if not r['happened'] and r['age'] <= 14 and r['vol'] == v], f'vol={v}')
print('--- age<=30 by span>=? and n>=2')
for lo in (0, 1, 7, 14, 30):
    rate([r for r in rows if not r['happened'] and r['age'] <= 30 and r['n'] >= 2 and r['span'] >= lo], f'age<=30 n>=2 span>={lo}')
print('--- by kind (not happened, age<=14)')
for k in sorted({r['kind'] for r in rows}):
    rate([r for r in rows if not r['happened'] and r['age'] <= 14 and r['kind'] == k], k)
print('--- happened dates by attribute')
byattr = collections.defaultdict(lambda: [0, 0])
for r in rows:
    if r['happened']:
        byattr[r['attr']][0] += 1
        byattr[r['attr']][1] += (not r['ok'])
print(dict(byattr))
print('--- quiet-subject feature, not happened')
for lo, hi in [(0, 14), (15, 30), (31, 60), (61, 120), (121, 999)]:
    for flag in (False, True):
        rate([r for r in rows if not r['happened'] and lo <= r['age'] <= hi and r['subj_changed'] == flag], f'age {lo}-{hi} subj_changed={flag}')
for lo, hi in [(15, 30), (31, 60), (61, 120)]:
    for flag in (False, True):
        rate([r for r in rows if not r['happened'] and lo <= r['age'] <= hi and r['any_changed'] == flag], f'age {lo}-{hi} any_changed={flag}')
bad = [r for r in rows if not r['ok'] and r['age'] <= 14]
for r in bad[:25]:
    print('BAD', r['key'], r['T'], 'age', r['age'], 'n', r['n'], 'span', r['span'], 'vol', r['vol'])
