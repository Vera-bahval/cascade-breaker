"""Compare Fraud task summaries with contemporaneous known fields, without model grading."""
import json
import re
from .provider import HERE
from .live_batch import ARMS, VERSION, folder
from .outcomes import collect

def main():
    reports=[]
    cases={x['id']:x for x in json.loads((HERE/'fixtures.json').read_text())}
    ids=json.loads((HERE/'live_selection.json').read_text())
    for cid in (ids[1],ids[2]):
        base=folder(cases[cid],ARMS[0])
        for mode in ('original','structured'):
            path=base if mode=='original' else base.with_name(base.name.removesuffix(VERSION)+'structured-v1')
            tr=list(json.loads((path/'direct-trace.json').read_text()).values())
            steps=[s for t in tr for s in t['steps']]
            summary=next((s['task_summary'] for s in steps if s['kind']=='summary' and s.get('agent')=='fraud_agent'),'')
            matches=re.findall(r'^\s*[*_\- ]*(invoice_id|disposition|unresolved|evidence)[*_ ]*:\s*([^\n]*)',summary,re.I|re.M)
            fields={k.lower():v.strip() for k,v in matches}
            result=collect(cases[cid],path,ARMS[0],[])
            actual_id=json.loads((path/'summary.json').read_text())['submitted_id']
            hits=re.findall(r'\b\d+\b',fields.get('invoice_id',''))
            flags=[s['arguments'].get('recommended_action') for s in steps if s['kind']=='tool' and s.get('name')=='flag_invoice_for_review' and not s.get('error')]
            reports.append(dict(case=cid,format=mode,summary=summary,fields=fields,all_fields=set(fields)=={'invoice_id','disposition','unresolved','evidence'},
                          id_matches=hits==[str(actual_id)],actual_flags=flags,**{k:result[k] for k in ('executor_usd','seconds','native_fraud_llm_turns','new_transfers')}))
    (HERE/'structured_results.json').write_text(json.dumps(reports,indent=2,ensure_ascii=False)+'\n')
if __name__=='__main__':main()
