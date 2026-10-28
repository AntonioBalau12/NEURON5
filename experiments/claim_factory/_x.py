import sys,collections
sys.path.insert(0,'experiments/claim_factory')
from cf_common import *
from observations import *
from core.graph import build_graph_from_paths
g=build_graph_from_paths(PRACTICE_CSV, LEXICON_JSON, use_packaged_practice=False)
O=build_observations(g)
# happened dates: backtest + list
tot=same=0
for (s,a),l in O.items():
    c=[o for o in l if o.clean and o.value.kind=='date']
    for i in range(len(c)-1):
        o,n=c[i],c[i+1]
        if o.on==n.on: continue
        if o.value.value > o.on.isoformat()[:len(o.value.value)]: continue
        tot+=1; ok=same_value(o.value,n.value); same+=ok
        if not ok: print('CHANGED',s,a,o.on,o.value.value,'->',n.on,n.value.value,'|',o.text[:90])
print('happened-date pairs',tot,same)
cnt=collections.Counter()
for (s,a),l in O.items():
    c=[o for o in l if o.clean and o.value.kind=='date']
    if c:
        L=c[-1]
        cnt['happened' if L.value.value <= L.on.isoformat()[:len(L.value.value)] else 'future']+=1
print(cnt)
# check non-clean support with cues and what date facts they are
for (s,a),l in O.items():
    for o in l:
        if o.kind=='support' and not o.clean and o.value.kind=='date': print('UNCLEAN',s,a,o.on,o.value.value,o.cues,o.text[:100])
