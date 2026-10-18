"""Refresh cost metadata without re-running the sealed evaluation."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from .night_rules_eval import token_metadata

def session_metadata(session):
    """Retain counters and model names only; never copy session messages."""
    result=token_metadata(session)
    models=[]
    with Path(session).open() as stream:
        for line in stream:
            row=json.loads(line)
            if row.get('type')=='turn_context':
                model=row.get('payload',{}).get('model')
                if model and model not in models:models.append(model)
    result['models']=models
    result['model']=models[0] if len(models)==1 else None
    result['model_source']='Session turn_context metadata'
    return result

def token_sum(*rows):
    totals=[row.get('total_tokens') for row in rows]
    return sum(totals) if all(value is not None for value in totals) else None

def amortize(total):
    return {str(n):total/n for n in (100,1000,10000)} if total is not None else None

def write_report(workspace,developer_session,evaluator_session,raw_auditor_session=None):
    root=workspace/'results/night-4b';dev=session_metadata(developer_session);evaluation=session_metadata(evaluator_session)
    raw_auditor=session_metadata(raw_auditor_session) if raw_auditor_session else None
    costs={'developer':dev,'independent_evaluation_and_review':evaluation,'credit_conversion':'Not computed: subscription credit conversion is not measured.','scope':'Dedicated-session cumulative usage; final assistant turn may not yet be reflected until counters flush. Parent orchestration excluded and separately unavailable.','developer_uncached_input_tokens':dev.get('input_tokens',0)-dev.get('cached_input_tokens',0) if dev.get('available') else None,'amortized_developer_tokens_per_episode':{str(n):dev['total_tokens']/n for n in (100,1000,10000)} if dev.get('total_tokens') is not None else None}
    costs['models_source']='Session turn_context metadata, credentials and messages not copied'
    costs['amortized_total_development_and_evaluation_tokens_per_episode']=amortize(token_sum(dev,evaluation))
    costs['raw_blind_diagnostic_auditor']=raw_auditor
    costs['raw_auditor_scope']='Entire raw auditor session, including blind fixture generation, evaluation, reporting and cost-generator maintenance; final turn requires a later metadata-only refresh.' if raw_auditor else 'No raw auditor session supplied.'
    costs['total_qa_tokens']=token_sum(evaluation,raw_auditor) if raw_auditor else None
    costs['amortized_qa_tokens_per_episode']=amortize(costs['total_qa_tokens'])
    costs['amortized_raw_auditor_tokens_per_episode']=amortize(raw_auditor.get('total_tokens')) if raw_auditor else None
    costs['amortized_total_development_and_qa_tokens_per_episode']=amortize(token_sum(dev,evaluation,raw_auditor)) if raw_auditor else None
    costs['qa_definition']='Independent evaluator/reviewer plus raw blind diagnostic auditor; development is reported separately.'
    (root/'rules-cost.json').write_text(json.dumps(costs,indent=2)+'\n')
    if not (root/'rules-evaluation.json').exists():return costs
    results=json.loads((root/'rules-evaluation.json').read_text());a=results['archive_retrospective'];h=results['hidden']
    lines=['# Rules: one-shot independent evaluation','', 'Frozen hidden cases were created before developer start; no retuning after reveal. Synthetic hidden cases do not establish generalization to independent real tasks. Archive outcomes remain counterfactual.','', '| Method | Archive harm stopped | Safe continuation stops | Source-benign stops | Compliant benign payments | Hidden unsafe stopped | Hidden safe stops | p50 / p95 ms |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for arm,row in a.items():
        x=h[arm]['base_policy'];lat=h[arm]['runtime_ms']
        lines.append(f"| {arm} | {row['prevented_counterfactual']}/{row['harmful_episodes']} | {row['safe_false_stops']}/{row['safe_continuation_episodes']} | {row['source_benign_stops']}/{row['source_benign_episodes']} | {row['source_benign_compliant_payment']}/{row['source_benign_episodes']} | {x['prevented']}/{x['unsafe']} | {x['false_stops']}/{x['safe']} | {lat['p50']:.4f} / {lat['p95']:.4f} |")
    lines+=['','Success-only Fraud is a distinct stricter-policy sensitivity, not a relabeling of base-policy failed-review cases. Its raw false stops are shown above. Hidden sensitivity denominators and every case decision remain in rules-evaluation.json.','','## Development cost','',f"Dedicated developer tokens: {dev.get('total_tokens','unavailable')}; input {dev.get('input_tokens')}, cached input subset {dev.get('cached_input_tokens')}, output {dev.get('output_tokens')}, reasoning subset of output {dev.get('reasoning_output_tokens_subset')}.",f"Independent evaluator/reviewer dedicated-session tokens: {evaluation.get('total_tokens','unavailable')}. Parent orchestration is excluded; it is not exactly attributable.",'','| Episodes | Amortized developer tokens / episode |','|---:|---:|']
    for n,v in (costs['amortized_developer_tokens_per_episode'] or {}).items():lines.append(f'| {n} | {v:.2f} |')
    runtime_path=root/'rules-runtime-end-to-end.json'
    if runtime_path.exists():
        runtime=json.loads(runtime_path.read_text())
        lines += ['',f"Archive end-to-end enrichment + decision: p50 {runtime['p50_ms']:.4f} ms, p95 {runtime['p95_ms']:.4f} ms, {runtime['samples']} timing samples. The table above times direct normalized-state decisions only. These are local measurements without enforced exclusive CPU ownership.",'Optional future registry integration requires the caller adapter to bind approvals/clearances to the current invoice; no live registry is implemented in this archive experiment.']
    baseline=a['original']
    lines+=['','Development amortization counts the whole developer session, including its own tests and engineering conversation. Counts are exact observed session counters, not a conversion to credits or dollars. Final-turn counters may require a metadata-only refresh.','']
    for arm in ('rules_v2','rules_v2_strict_review'):
        row=a[arm];delta=row['prevented_counterfactual']-baseline['prevented_counterfactual'];fp=row['safe_false_stops']-baseline['safe_false_stops']
        lines.append(f"{arm}: {delta:+d} archived harmful episodes stopped versus original, {fp:+d} safe-continuation stops. Original compliant benign completion {baseline['source_benign_compliant_payment']}; variant {row['source_benign_compliant_payment']}. Developer tokens per additional prevented archived harm: {dev.get('total_tokens')/delta if delta>0 and dev.get('total_tokens') is not None else 'undefined (no positive gain)'}.")
    lines+=['','## Amortization by token category','',
        'Dedicated agent models from session turn_context metadata: developer '+str(dev.get('models'))+'; independent evaluator/reviewer '+str(evaluation.get('models'))+'. Cached input is part of input; it is not added to input again. The total column already includes cached input. Development and independent evaluator engineering/review are distinct costs.','',
        '| Episodes | Uncached developer input / episode | Cached developer input / episode | Developer output / episode | Developer total / episode | Development + evaluation total / episode |',
        '|---:|---:|---:|---:|---:|---:|']
    if dev.get('available') and evaluation.get('available'):
        for n in (100,1000,10000):
            values=(costs['developer_uncached_input_tokens']/n,dev['cached_input_tokens']/n,dev['output_tokens']/n,dev['total_tokens']/n,token_sum(dev,evaluation)/n)
            lines.append('| '+str(n)+' | '+' | '.join(f'{value:.3f}' for value in values)+' |')
    lines+=['',
        'Zero model inference tokens are used by the frozen rules at runtime. These amortizations spread observed one-time costs; they do not estimate future attack frequency, monetary savings, or subscription credits. A matched LLM-defender per-episode token baseline was not measured in this night series.','',
        '## Hidden validation boundary','',
        'The 64 hidden cases contain normalized authorization_evidence and no raw prior_steps. Thus 32/32 unsafe and 0/32 safe validate the policy gate given normalized evidence. They do not independently validate the English authority extractor or complete raw-trace pipeline. Archive enrichment plus decision remains retrospective; the developer parser tests are development checks. No hidden decisions were recomputed and no rules were changed.']
    raw_path=root/'rules-raw-validation.json'
    if raw_path.exists():
        raw=json.loads(raw_path.read_text())
        lines+=['','## Additional blind raw-trace diagnostic','',
            'This separately reported posthoc diagnostic does not replace the original primary 64 normalized hidden cases. New raw input states, native pre-cut events and policy labels were frozen before importing the unchanged frozen rules. No retuning followed its one evaluation pass.',
            '[Raw diagnostic report](rules-raw-report.md); [per-case results](rules-raw-validation.json).','',
            '| Policy | TP | TN | FP | FN | Recall | FPR |','|---|---:|---:|---:|---:|---:|---:|']
        for policy,row in raw['metrics'].items():
            lines.append(f"| {policy} | {row['TP']} | {row['TN']} | {row['FP']} | {row['FN']} | {row['recall']:.3f} | {row['false_positive_rate']:.3f} |")
        lines+=['',
            'All three misses concern actual reliance on unverified executive permission expressed in English paraphrases. The other seven authored families passed. The raw diagnostic evaluates enrichment plus rule application while retaining original code-computed amount/account/status facts at the guard interface. It is not a live FinBot run or a population error estimate.',
            'Raw fixture SHA256: `'+raw['freeze']['cases_sha256']+'`; frozen rules SHA256: `'+raw['freeze']['frozen_rules_sha256_expected']+'`.']
    if raw_auditor:
        lines+=['','## Raw auditor and total QA cost','',
            f"Raw auditor model metadata: {raw_auditor.get('models')}. Dedicated-session tokens: {raw_auditor.get('total_tokens')}; input {raw_auditor.get('input_tokens')}, cached input subset {raw_auditor.get('cached_input_tokens')}, output {raw_auditor.get('output_tokens')}, reasoning subset of output {raw_auditor.get('reasoning_output_tokens_subset')}.",
            costs['raw_auditor_scope'],
            'QA below means independent evaluator/reviewer plus raw auditor. Development + QA adds the developer session. Parent orchestration remains excluded. All values are observed cumulative session counters, without conversion to subscription credits.','',
            '| Episodes | Raw auditor tokens / episode | QA tokens / episode | Development + QA tokens / episode |','|---:|---:|---:|---:|']
        if costs['amortized_total_development_and_qa_tokens_per_episode'] is not None:
            for n in (100,1000,10000):
                lines.append(f"| {n} | {raw_auditor['total_tokens']/n:.3f} | {costs['total_qa_tokens']/n:.3f} | {token_sum(dev,evaluation,raw_auditor)/n:.3f} |")
    (root/'rules-report.md').write_text('\n'.join(lines)+'\n');return costs

def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,default=Path('.'));p.add_argument('--developer-session',required=True);p.add_argument('--evaluator-session',required=True);p.add_argument('--raw-auditor-session');a=p.parse_args();print(json.dumps(write_report(a.workspace,a.developer_session,a.evaluator_session,a.raw_auditor_session),indent=2))
if __name__=='__main__':main()
