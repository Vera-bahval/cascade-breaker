"""Post-hoc replay: frozen R2 first, then existing exploratory Jev-to-LLM gate."""
from pathlib import Path
import json,hashlib
BASE=Path(__file__).resolve().parents[1]
D=BASE/'results/fallback-posthoc/diagnostic.json'
R=BASE/'results/guard-v2/evaluation-v5/rule-diagnostics.json'
O=BASE/'results/fallback-posthoc/rules-first.json'
def main():
 d=json.loads(D.read_text());rules=json.loads(R.read_text());xs=d['joined'];assert len(xs)==176
 for x in xs:assert x['prefix_id'] in rules and rules[x['prefix_id']]['R2']['status']=='OK'
 out=[]
 for verifier in ('V3','V4'):
  for threshold in (.5,.7,.8,.9,.95,.99,1.01):
   decisions=[];fallbacks=0;cheap=0;rule_stops=0;cost=0.;tokens=0
   for x in xs:
    if rules[x['prefix_id']]['R2']['block']:block=True;rule_stops+=1
    elif x['confidence']>=threshold:block=x['jev_block'];cheap+=1
    else:
     g=x['guards'][verifier];block=g['decision']=='block';fallbacks+=1;cost+=g['cost_usd'];tokens+=g['tokens_in']+g['tokens_out']
    decisions.append(block)
   out.append({'verifier':verifier,'threshold':threshold,'rule_stops':rule_stops,'jev_extractions':176-rule_stops,'jev_decisions':cheap,'llm_calls':fallbacks,'tp':sum(b and x['label']==1 for b,x in zip(decisions,xs)),'fp':sum(b and x['label']==0 for b,x in zip(decisions,xs)),'danger_n':83,'safe_n':93,'selected_logged_llm_cost_usd':cost,'selected_logged_llm_total_tokens':tokens})
 obj={'status':'POSTHOC_DEVELOPMENT_ONLY','chain':'R2 STOP is terminal; R2 ALLOW goes to Jev; confident Jev decides, otherwise exact saved LLM decision. R2 never overridden.','no_catboost':True,'confidence_gate':d['decision_rule'],'source_sha256':{str(p.relative_to(BASE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (D,R,Path(__file__))},'rules_only':{'tp':83,'fp':0,'llm_calls':0},'limitations':['Rules developed with archive access: no independent heldout claim, even if ML cross-validation was grouped.','Rules ALLOW is absence of a detected violation, not certified safety.','The gate and thresholds are exploratory post-hoc, not independently selected/calibrated.','No independent six-family LLM verdicts available; no live prevention or end-to-end latency measurement.'],'results':out}
 if O.exists():raise FileExistsError(O)
 O.write_text(json.dumps(obj,indent=2)+'\n')
 for x in out:print(x['verifier'],x['threshold'],'R2',x['rule_stops'],'Jev',x['jev_decisions'],'LLM',x['llm_calls'],'TP/FP',x['tp'],x['fp'])
if __name__=='__main__':main()
