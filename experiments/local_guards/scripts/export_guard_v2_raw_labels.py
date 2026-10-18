#!/usr/bin/env python3
"""One-time known raw64 annotation export; never derives labels from predictions."""
import argparse
import hashlib
import json
from pathlib import Path
SOURCE_SHA='601e5be41b4c3f791a9fbe43860d5fa720b0e15e76ed78f4c525627b64dd4a53'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def export(source,output,require_source_sha=True):
 source,output=Path(source),Path(output)
 if require_source_sha and sha(source)!=SOURCE_SHA:raise ValueError('Original annotation source changed')
 cases=json.loads(source.read_text());rows=[];seen=set()
 for case in cases:
  label=case['expected_block']['base'];eid='raw:'+case['id']
  if not isinstance(label,bool) or eid in seen:raise ValueError('Invalid or duplicate authored annotation')
  seen.add(eid);rows.append({'episode_id':eid,'case_id':case['id'],'family':case['family'],'contract_requires_intervention':label,'annotation_reason':case['label_reason'],'label_provenance':'Original authored expected_block.base; static known post-hoc stress-test, not observed harm'})
 if require_source_sha and len(rows)!=64:raise ValueError('Expected64 authored cases')
 output.parent.mkdir(parents=True,exist_ok=True)
 with output.open('x') as handle:
  for row in rows:handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
 manifest={'source':str(source.resolve()),'source_sha256':sha(source),'labels':str(output.resolve()),'labels_sha256':sha(output),'rows':len(rows),'target':'contract_requires_intervention','exporter_sha256':sha(__file__)}
 with output.with_suffix('.manifest.json').open('x') as handle:json.dump(manifest,handle,indent=2);handle.write('\n')
 return manifest
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(export(a.source,a.output),indent=2))
