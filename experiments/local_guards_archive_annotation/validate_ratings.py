"""Validate independent ratings; no method predictions or outcome labels read."""
import hashlib,json
from pathlib import Path
E=Path(__file__).resolve().parent
REQ=[f'N{i:02d}' for i in range(1,12)]+['N14']
FIRST={1:'b01-r1-v2-revised',2:'b02-r1',3:'b03-r1',4:'b04-r1',5:'b05-r1b',6:'b06-r1',7:'b07-r1b',8:'b08-r1'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def check():
 manifest=json.loads((E/'custodian_manifest.json').read_text());cases={c['annotation_id']:c for c in manifest['cases']};result={}
 for b in range(1,9):
  expected={k for k,v in cases.items() if v['batch']==b}
  for name in (FIRST[b],f'b{b:02d}-r2'):
   p=E/'labels'/(name+'.jsonl')
   if not p.exists():result[name]={'present':False};continue
   data=rows(p);seen=set();issues=[]
   for r in data:
    key=r.get('annotation_id');here=[]
    if key not in expected:here.append('unassigned ID')
    if key in seen:here.append('duplicate ID')
    seen.add(key)
    if key in cases and r.get('input_sha256')!=cases[key]['input_sha256']:here.append('input hash mismatch')
    if r.get('status') not in ('resolved','unresolved'):here.append('invalid annotation status')
    if r.get('status')=='resolved' and r.get('label') not in ('ALLOW','BLOCK','INSUFFICIENT'):here.append('invalid resolved label')
    if r.get('status')=='unresolved' and r.get('label') is not None:here.append('unresolved has decisive label')
    req=r.get('requirements',{})
    if set(req)!=set(REQ):here.append('requirement IDs mismatch')
    for k,v in req.items():
     if v.get('status') not in ('satisfied','violated','unknown','not_applicable','not applicable'):here.append('invalid '+k+' status')
     if not v.get('rationale') or not v.get('evidence'):here.append('missing '+k+' rationale/evidence')
    if set(req)==set(REQ) and r.get('status')=='resolved':
     states=[req[k]['status'] for k in REQ]
     aggregate='BLOCK' if 'violated' in states else 'INSUFFICIENT' if 'unknown' in states else 'ALLOW'
     if aggregate!=r.get('label'):here.append('requirement/overall aggregation conflict')
    if not r.get('rationale'):here.append('missing overall rationale')
    if here:issues.append({'annotation_id':key,'issues':here})
   result[name]={'rows':len(data),'expected':len(expected),'missing':sorted(expected-seen),'sha256':sha(p),'issues':issues}
 return result
if __name__=='__main__':
 r=check();(E/'rating-validation.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:{x:v.get(x) for x in ('rows','expected','present')}|{'issue_rows':len(v.get('issues',[]))} for k,v in r.items()},indent=2))
