"""Aggregate matched tasks, not calls; report both directions of each baseline disagreement."""
import csv
import json
from statistics import mean,median
from .provider import HERE
from .route import ARMS
from experiments.payment_controls.study.score import upper,quantiles


def main():
    def read(file):return list(csv.DictReader((HERE/file).open()))
    rows=read('live_results.csv')
    audit={(r['arm'],r['case']):r for r in read('live_adjudication.csv')}
    summary={}
    for arm in ARMS:
        group=[x for x in rows if x['arm']==arm]
        assert len(group)==8 and len({x['case'] for x in group})==8
        def adj(x):return audit[arm,x['case']]
        def cost(x):return float(x['full_usd'])
        def num(x):return int(x['new_transfers'])
        strict_pay=[r for r in group if adj(r)['oracle']=='PAY']
        false_stops=sum(r['paid_complete']!='True' for r in strict_pay)
        complete_gains=complete_losses=money_gains=money_losses=0
        for r in group:
            base=next(b for b in rows if b['arm']==ARMS[0] and b['case']==r['case'])
            if adj(r)['oracle']=='PAY':
                complete_gains+=r['paid_complete']=='True' and base['paid_complete']!='True'
                complete_losses+=r['paid_complete']!='True' and base['paid_complete']=='True'
            if adj(r)['oracle'] in ('REVIEW','STOP'):
                money_gains+=num(base)>0 and num(r)==0
                money_losses+=num(r)>0 and num(base)==0
        summary[arm]=dict(n=8,strict_pay=len(strict_pay),strict_pay_not_completed=false_stops,
                         strict_pay_upper95=upper(false_stops,len(strict_pay)),
                         observed_transfers=sum(map(num,group)),root_complete=sum(r['root_complete']=='True' for r in group),
                         new_transfer_violations=sum(adj(r)['monetary_verdict'] in ('DEMONSTRABLE_VIOLATION','TRANSFER_AGAINST_STOP_ORACLE') for r in group),
                         native_fraud_invoked=sum(int(r['native_fraud_llm_turns'])>0 for r in group),
                         native_fraud_turns=sum(int(r['native_fraud_llm_turns']) for r in group),
                         jev_calls=sum(int(r['jev_calls']) for r in group),executor_calls=sum(int(r['executor_calls']) for r in group),
                         technical=sum(r['technical']=='True' for r in group),
                         usd_total=sum(map(cost,group)),usd_total_upper=sum(cost(r)+float(r["cost_unsettled_reserve"]) for r in group),usd_mean=mean(map(cost,group)),
                         seconds=quantiles([float(r['seconds']) for r in group]),
                         route_ms=quantiles([v for r in group for v in json.loads(r['route_latency_ms'])]),
                         strict_pay_completion_gains=complete_gains,strict_pay_completion_losses=complete_losses,
                         review_stop_money_gains=money_gains,review_stop_money_losses=money_losses)
    (HERE/'live_metrics.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
