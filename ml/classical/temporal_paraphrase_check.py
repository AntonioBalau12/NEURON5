"""Check the documented Holdan joined-date example against training-only evidence."""
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from benchmark import load_rows,load_shared_splits
from foundation import Lexicon
from fact_aware_experiment import OUT,graph_from_references
from fact_aware_features import FactAwareFeatureExtractor

rows,rawlex=load_rows();splits,_=load_shared_splits(rows)
references=[r for r in rows if splits[r['id']]=='train']
source=next((r for r in references if r['id']=='p-1'),None)
lex,issues=Lexicon.parse(rawlex)
graph=graph_from_references(references,lex)
extractor=FactAwareFeatureExtractor(lex,graph)
items=[]
for text in ('Holdan joined Hooly on January 12, 2026.','Holdan joined Hooly on January 13, 2026.'):
    features,diag=extractor.transform(text,'2026-10-28','temporal-demo')
    items.append({'claim_text':text,'claim_date':'2026-10-28','parsed_facts':diag['parsed_facts'],'features':features,'retrieved_evidence':diag['retrieved_evidence']})
out={'reference_row_id':source['id'] if source else None,'reference_split':'train','reference_label':source['label'] if source else None,
     'reference_fact_json':source['form'] if source else None,'target_form_used':False,'results':items,
     'interpretation':'The correct paraphrase should parse and compare to the supported event date; a one-day mismatch is a numeric difference feature only, never an automatic FALSE label. This is a parser/feature demonstration, not a model prediction.'}
(OUT/'temporal_paraphrase_check.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False))
