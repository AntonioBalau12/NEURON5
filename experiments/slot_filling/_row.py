import sys, json
sys.path.insert(0, 'experiments/slot_filling')
from pathlib import Path
from engine import *
from linking import Lexicon
from model import load, gaz_for, load_dev
from pipeline import *
lex = Lexicon('data/lexicon.json')
m = load(Path('experiments/slot_filling/model'))
import csv
rows = {r['id']: dict(r, gold=[]) for r in csv.DictReader(open('experiments/shared/data/full_input.csv', encoding='utf-8'))}
rows.update({r['id']: r for r in load_dev()})
for rid in sys.argv[1:]:
    r = rows[rid]
    print(rid, r['text'])
    for g in r['gold']: print('   GOLD', g['subject'], g['attribute'], json.dumps(g['value']))
    infos = analyse_row(r['text'], lex, gaz_for(m.gaz), m.units)
    for si in infos:
        print('  ents', [(e.start, e.end, e.canon) for e in si.ents])
        for vm in si.vms:
            print('  vm', vm.kind, vm.start, vm.end, vm.rule, vm.readings[:2], vm.op, vm.suppressed, vm.name_src, sorted(vm.near)[:12])
    c = generate(r['text'], infos, lex, m.profile)
    score_groups(c, m.lr)
    for x in sorted(c, key=lambda x: -x.p)[:12]:
        print('  cand', x.ent.canon, x.attr, json.dumps(x.value), round(x.p, 3))

