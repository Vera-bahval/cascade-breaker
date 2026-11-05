"""Freeze paired ratings and prepare source-only disagreement review packages."""
import argparse,json,hashlib
from pathlib import Path
from validate_ratings import E,FIRST,REQ,rows,sha,check

def prepare(batch):
 validation=check();names=[FIRST[batch],f'b{batch:02d}-r2']
 for name in names:
  v=validation[name]
  if v.get('rows')!=v.get('expected') or v.get('issues'):raise ValueError(f'incomplete or invalid {name}')
 manifest=json.loads((E/'custodian_manifest.json').read_text());cases={c['annotation_id']:c for c in manifest['cases'] if c['batch']==batch}
 paired=[{r['annotation_id']:r for r in rows(E/'labels'/(name+'.jsonl'))} for name in names]
 sample={}
 for key,c in cases.items():
  g=c['group_id']; rank=hashlib.sha256(('adjudication-agreement17/'+key).encode()).hexdigest()
  if g not in sample or rank<sample[g][0]:sample[g]=(rank,key)
 audits={v[1] for v in sample.values()};packets=[];agreed=[]
 for key in sorted(cases):
  a,b=(r[key] for r in paired);differences=[]
  for k in ('status','label','core_label','semantic_label'):
   if a.get(k)!=b.get(k):differences.append(k)
  for req in REQ:
   if a['requirements'][req]['status'].replace('_',' ')!=b['requirements'][req]['status'].replace('_',' '):differences.append('requirements.'+req)
  if differences or key in audits:
   packets.append({'annotation_id':key,'review_reasons':differences or ['agreement audit: one deterministic case per base group'],
    'first_rating':a,'second_rating':b,'input_path':str(E/'action_inputs'/(key+'.json')),
    'supplement_paths':[str(d/(key+'.json')) for d in [E/'supplementary_evidence/blind_inputs',E/'supplementary_evidence_v2/blind_inputs'] if (d/(key+'.json')).exists()]})
  else:agreed.append(key)
 out=E/'adjudication';out.mkdir(exist_ok=True)
 target=out/f'batch_{batch:02d}.json';receipt=out/f'batch_{batch:02d}.freeze.json'
 if target.exists() or receipt.exists():raise ValueError('refuse overwrite adjudication package')
 target.write_text(json.dumps(packets,ensure_ascii=False,indent=2)+'\n')
 receipt.write_text(json.dumps({'batch':batch,'cases':len(cases),'review_cases':len(packets),'unreviewed_agreements':agreed,
   'package_sha256':sha(target),'rater_sources':{str(E/'labels'/(name+'.jsonl')):sha(E/'labels'/(name+'.jsonl')) for name in names},
   'protocol_sha256':sha(E/'PROTOCOL.md'),'prepare_source_sha256':sha(Path(__file__)),
   'selection':'all label/component/requirement-status disagreements plus minSHA onecase perbasegroup, seed17; no method predictions read'},indent=2)+'\n')
 return {'batch':batch,'review':len(packets),'inherited_agreements':len(agreed),'source':str(target)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('batch',type=int);a=p.parse_args();print(json.dumps(prepare(a.batch),indent=2))
