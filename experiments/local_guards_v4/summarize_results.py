"""Render compact, source-linked tables from frozen predictions and gold.

Reporting only: never fits, selects a new method or changes predictions.
"""
import argparse
from collections import defaultdict
import gzip
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(path):
    with gzip.open(path, 'rt') as stream:
        yield from (json.loads(line) for line in stream)


def pct(k, n):
    return 'n/a' if not n else f'{k}/{n} ({100*k/n:.1f}%)'


def table(headers, values):
    return '| ' + ' | '.join(headers) + ' |\n| ' + ' | '.join(['---'] * len(headers)) + ' |\n' + ''.join(
        '| ' + ' | '.join(str(x) for x in row) + ' |\n' for row in values)


def render(evaluation, predictions, name, destination):
    obj = json.loads((evaluation / 'metrics.json').read_text())
    aggregate = obj['aggregates']
    configs = json.loads((HERE / 'results/configurations.json').read_text())['methods']
    metrics = {(r['method'], r['policy_oracle'], r['slice'], r['value']): r for r in aggregate}
    episodes = defaultdict(list)
    for row in rows(evaluation / 'episodes.jsonl.gz'):
        if row['policy_oracle'] == 'A':
            episodes[row['method']].append(row)
    latency = {}
    for method, values in episodes.items():
        values = sorted(r['runtime_ms'] for r in values if r['eligible'])
        latency[method] = [values[(len(values)-1)//2], values[math.ceil(.95*len(values))-1]] if values else [None, None]
    selected = []
    for config in configs:
        method = config['name']
        policy = 'A+B' if method.startswith('A_plus_') else 'A'
        row = metrics[method, policy, 'all', None]
        selected.append([method, pct(row['intervention_stops'], row['intervention_episodes']),
                         pct(row['safe_stops'], row['safe_episodes']), row['unknown_gold_episodes'],
                         pct(row['unknown_decisions'], row['checked_prefixes']),
                         pct(row['source_legit_stops'], row['source_legit_episodes']),
                         '/'.join('n/a' if x is None else f'{x:.3f}' for x in latency[method])])
    text = f'# {name}: all fixed configurations\n\n'
    text += 'Offline pure-check episode sum; these times exclude native state reads and writes. '
    text += 'No-check episodes are absent from the timing denominator and are not autonomous decisions. '
    text += 'Unknown gold is neither safe nor violated; UNKNOWN verdict is STOP.\n\n'
    text += table(['Method', 'Stopped known violations', 'Stopped contract-safe', 'Unknown gold',
                   'UNKNOWN / actually checked prefixes', 'Interrupted source-legit', 'Pure episode p50/p95 ms'], selected)
    text += '\nA+B rows use the complete extended oracle; other rows use A. Common-oracle comparisons remain in metrics.json.\n'
    if name.startswith('Archive'):
        text += '\n## Original main: source outcomes, all methods\n\n'
        text += table(['Method', 'Would stop source harm', 'Source-legit whole', 'Source-legit reached', 'UNKNOWN/checks'], [
            [c['name'], pct(r['harm_prevented'], r['harmful_episodes']), pct(r['source_legit_stops'], r['source_legit_episodes']),
             pct(r['source_legit_stops'], r['source_legit_reached']), pct(r['unknown_decisions'], r['checked_prefixes'])]
            for c in configs for r in [metrics[c['name'], 'A', 'cohort', 'original_main']]])
        text += '\n## Cohorts, P4 v3 and full A\n\n'
        text += table(['Cohort', 'Method', 'Episodes', 'Checked episodes', 'Known harmful', 'Outcome unknown',
                       'Would stop harm', 'Source-legit interruptions'], [
            [r['value'], r['method'], r['episodes'], r['eligible_episodes'], r['harmful_episodes'], r['outcome_unknown'],
             pct(r['harm_prevented'], r['harmful_episodes']), pct(r['source_legit_stops'], r['source_legit_episodes'])]
            for r in aggregate if r['policy_oracle']=='A' and r['slice']=='cohort' and r['method'] in {'control_p4_v3','A_with_P4'}])
    agreement = {}
    if name.startswith('Closed'):
        actions = {r['prefix_id']:r for r in rows(HERE / 'closed/gold-actions.jsonl.gz')}
        errors = []
        for prediction in rows(predictions):
            method = prediction['method']
            if method not in {'A_with_P4', 'A_plus_allB'}:
                continue
            action = actions[prediction['prefix_id']]
            states = [v for k,v in action['requirements'].items() if method == 'A_plus_allB' or k.startswith('A')]
            truth = 'BLOCK' if 'violated' in states else 'UNKNOWN' if 'unknown' in states else 'ALLOW'
            counts = agreement.setdefault(method, {'cases':0,'correct':0,'errors':0,'false_allow':0,'confusion':{}})
            counts['cases'] += 1
            counts['correct'] += prediction['decision'] == truth
            counts['errors'] += prediction['decision'] != truth
            counts['false_allow'] += prediction['decision'] == 'ALLOW' and truth != 'ALLOW'
            key = truth + ' -> ' + str(prediction['decision'])
            counts['confusion'][key] = counts['confusion'].get(key,0) + 1
            if prediction['decision'] != truth:
                errors.append({'method':method,'prefix_id':prediction['prefix_id'],'family':action['family'],
                               'expected':truth,'predicted':prediction['decision'],'reasons':prediction['reasons']})
        (destination.parent / 'closed-decision-errors.json').write_text(json.dumps({'agreement':agreement,'errors':errors},indent=2)+'\n')
        text += '\n## Family decisions under A+B\n\n'
        text += table(['Family', 'Method', 'Violations stopped', 'Safe stops', 'Unknown gold', 'UNKNOWN/checks'], [
            [r['value'],r['method'],pct(r['intervention_stops'],r['intervention_episodes']),pct(r['safe_stops'],r['safe_episodes']),
             r['unknown_gold_episodes'],pct(r['unknown_decisions'],r['checked_prefixes'])]
            for r in aggregate if r['policy_oracle']=='A+B' and r['slice']=='family' and r['method'] in {'control_p4_v3','A_with_P4','A_plus_allB'}])
        # Layer B's change of admissibility, separate from improved A enforcement.
        full = list(rows(evaluation / 'episodes.jsonl.gz'))
        by = {(r['method'],r['policy_oracle'],r['episode_id']):r for r in full}
        costs = []
        for c in configs:
            if not c['name'].startswith('A_plus_'):
                continue
            values = [r for r in full if r['method']==c['name'] and r['policy_oracle']=='A']
            a_safe = [r for r in values if r['action_gold']=='ALLOW']
            newly_bad = [r for r in a_safe if by[c['name'],'A+B',r['episode_id']]['action_gold']=='BLOCK']
            costs.append([c['name'],len(a_safe),sum(r['stopped'] for r in a_safe),len(newly_bad),
                          sum(r['stopped'] for r in newly_bad)])
        text += '\n## Layer B changes to previously A-permitted states\n\n'
        text += table(['Method','A-safe states','A-safe states stopped','A-safe now A+B violated','Of those stopped'],costs)
    destination.write_text(text)
    return {'kind': name, 'pure_episode_latency_ms': latency, 'own_contract_decision_agreement':agreement,
            'timing_denominator': 'eligible episodes; first STOP truncates subsequent hypothetical checks',
            'metrics_source': str(evaluation / 'metrics.json'), 'predictions_source': str(predictions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--closed', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('refusing overwrite')
    args.output.mkdir(parents=True)
    report = [render(args.archive, HERE / 'results/archive-predictions.jsonl.gz', 'Archive descriptive census', args.output / 'archive-tables.md')]
    if args.closed:
        report.append(render(args.closed, HERE / 'results/closed-predictions.jsonl.gz', 'Closed synthetic contract test', args.output / 'closed-tables.md'))
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'output':str(args.output),'tables':len(report)}, indent=2))


if __name__ == '__main__':
    main()
