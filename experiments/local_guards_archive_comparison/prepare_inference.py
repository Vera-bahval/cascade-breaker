"""Label-free lossless packing and deterministic pilot order for selected groups."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from .collector import read_jsonl, write_jsonl, file_hash
from .views import pack_view, unpack_view

HERE=Path(__file__).resolve().parent


def prepare():
    rows=[];sizes=Counter()
    for mode in ('historical','instrumented'):
        for r in read_jsonl(HERE/f'views/{mode}-selected.jsonl.gz'):
            if r['split'] not in ('REPRESENTATIVE','CHALLENGE'):raise RuntimeError('selection leak')
            packet=pack_view(r['input'])
            if unpack_view(packet)!=r['input']:raise RuntimeError('lossy input')
            sizes[mode+'_expanded_bytes']+=len(json.dumps(r['input'],ensure_ascii=False,sort_keys=True).encode())
            sizes[mode+'_packed_bytes']+=len(json.dumps(packet,ensure_ascii=False,sort_keys=True).encode())
            rows.append(dict(case_id=r['case_id'],split=r['split'],checkpoint=r['input']['checkpoint'],input=packet))
    # Pilot covers both cuts, both modes and both selections, using only hashes.
    key=lambda r:hashlib.sha256(('17/'+r['case_id']).encode()).hexdigest()
    pilot=[]
    for mode in ('historical','instrumented'):
        for split in ('REPRESENTATIVE','CHALLENGE'):
            for cut in ('P2_afterFraud','P4'):
                eligible=[r for r in rows if r['case_id'].startswith(mode+'/') and r['split']==split and r['checkpoint']==cut]
                if eligible:pilot.append(min(eligible,key=key))
    used={r['case_id'] for r in pilot}
    # Primary historical inference comes first after the predeclared pilot.
    rows=pilot+sorted((r for r in rows if r['case_id'] not in used),key=lambda r:(not r['case_id'].startswith('historical/'),key(r)))
    for r in rows:r.pop('checkpoint')
    out=HERE/'inference';out.mkdir(exist_ok=True)
    write_jsonl(out/'inputs.jsonl.gz',rows)
    schema={'type':'object','required':['format','payload','strings','references'],'additionalProperties':False,
            'properties':{'format':{'const':'lossless-path-references-v1'},'payload':{'type':'object'},
                          'strings':{'type':'array','items':{'type':'string'}},
                          'references':{'type':'array','items':{'type':'array','minItems':2,'maxItems':2,
                             'prefixItems':[{'type':'array','items':{'type':['string','integer']}},{'type':'integer','minimum':0}]}}}}
    (out/'input-schema.json').write_text(json.dumps(schema,indent=2)+'\n')
    manifest={'rows':len(rows),'sizes':dict(sizes),'pilot_case_ids':[r['case_id'] for r in pilot],
              'inputs_sha256':file_hash(out/'inputs.jsonl.gz'),'sources':{}}
    for name in ('prepare_inference.py','views.py','views/manifest.json','views/historical-selected.jsonl.gz','views/instrumented-selected.jsonl.gz','provenance/view-validation.json'):
        p=HERE/name;manifest['sources'][str(p.relative_to(Path.cwd()))]=file_hash(p)
    (out/'inputs-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':print(json.dumps(prepare(),indent=2))
