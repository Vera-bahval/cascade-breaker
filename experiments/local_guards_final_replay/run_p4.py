"""Offline P4 evaluation on the 542 saved and independently annotated inputs."""
import argparse
import gzip
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from random import Random

from . import p4
from experiments.local_guards_archive_annotation import score
from experiments.local_guards_archive_comparison import views
from experiments.local_guards_archive_comparison.collector import read_jsonl

BASE = '36ee65526b29637602f066ce06d8e474e5fc4214'
MODES = ('common', 'expanded', 'conditional')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)+'\n')


def write_gzip(path, rows):
    with path.open('wb') as raw, gzip.GzipFile(fileobj=raw, filename='', mode='wb', mtime=0) as output:
        for row in rows:
            output.write((json.dumps(row, ensure_ascii=False, sort_keys=True)+'\n').encode())


def publish_evidence(value):
    """Keep reproducible source references and omit raw banking identifiers."""
    if isinstance(value, list):
        return [publish_evidence(item) for item in value]
    if isinstance(value, dict):
        protected = {'bank_account_number','bank_routing_number','vendor_account',
                     'vendor_bank_account_number','tin','email','contact_email','contact_name'}
        return {publish_evidence(key): (None if item is None else 'sha256/'+hashlib.sha256(str(item).encode()).hexdigest())
                if key in protected else publish_evidence(item) for key,item in value.items()}
    if isinstance(value, str):
        return value.replace(str(score.REPO.parents[1])+'/', 'workspace/')
    return value


def files():
    annotation = p4.ANNOTATION
    archive = p4.ARCHIVE
    return {
        'manifest': annotation/'custodian_manifest.json',
        'consensus': annotation/'labels/consensus.jsonl',
        'freeze': annotation/'consensus-freeze.json',
        'local': archive/'results/historical-local.jsonl.gz',
        'deepseek': archive/'results/deepseek-historical.jsonl.gz',
        'requests': p4.ELIZA/'requests.jsonl.gz',
        'responses': p4.ELIZA/'responses.jsonl.gz',
        'case_mapping': p4.ELIZA/'case-mapping.jsonl.gz',
        'observations': archive/'data/historical/observations.jsonl.gz',
        'metadata': archive/'data/metadata.jsonl.gz',
    }


def matched_inputs(paths):
    freeze = json.loads(paths['freeze'].read_text())
    cases = score.checked_inputs(paths['consensus'], freeze['consensus_sha256'], paths['manifest'],
                                 freeze['source_sha256']['custodian_manifest.json'])
    mapping = json.loads(paths['manifest'].read_text())['cases']
    vectors = score.read_vectors(paths['deepseek'], cases)['deepseek|both|none']
    saved = p4.stored_requests(cases)
    for row in mapping:
        case_id = row['case_id']
        expected = json.loads((p4.ANNOTATION/'action_inputs'/(row['annotation_id']+'.json')).read_text())
        common, issue, query = p4.match_request(expected, case_id, saved, vectors)
        yield row, expected, common, issue, query


def run(out):
    from .expanded import Archive

    p4.evaluation.verify_controls()
    paths = files()
    paths.update({str(path.relative_to(score.REPO)): path for path in p4.evaluation.source_paths()})
    for path in p4.HERE.glob('*.py'):
        paths['experiment:'+path.name] = path
    hashes = {name: score.digest(path) for name, path in paths.items()}
    selected = list(matched_inputs(paths))
    prefixes = {item[0]['prefix_id'] for item in selected}
    metadata = p4.unique((row for row in read_jsonl(paths['metadata']) if row['prefix_id'] in prefixes), 'prefix_id')
    originals = p4.unique((row for row in read_jsonl(paths['observations']) if row['prefix_id'] in prefixes), 'prefix_id')
    recovery = Archive(score.REPO, p4.ANNOTATION/'custodian_manifest.json')
    decisions, receipts = [], []
    for item, expected, common, issue, query in selected:
        prefix = item['prefix_id']
        source = metadata[prefix]
        identity = {key:item[key] for key in ('case_id','annotation_id','prefix_id','group_id')}
        identity.update(checkpoint='P4', event_seq=expected['event_seq'])
        original = originals[prefix]
        if views.predictor_view(original) != expected:
            raise ValueError('canonical observation identity mismatch: '+prefix)
        expanded_raw, sources = recovery.enrich(original, source)
        if (expanded_raw['event_seq'] != expected['event_seq']
                or expanded_raw['raw_context']['proposed_action'] != original['raw_context']['proposed_action']):
            raise ValueError('expansion changed proposal: '+prefix)
        expanded = views.predictor_view(expanded_raw)
        receipts.append(dict(identity, common_request_query_id=query, common_issue=issue,
                             source_episode=source['episode_id'], source_hash=source['source_sha256'],
                             added_evidence=sources, projections={}))
        # The conditional namespace binding uses literal values from the verified
        # runner. Keep them in the same identity domain as the source snapshots.
        for mode, row in (('common', common), ('expanded', expanded), ('conditional', expanded_raw)):
            if row is None:
                predictions = {method:dict(decision=None, adapter_applicable=None, reasons=[issue])
                               for method in p4.METHODS}
                provenance = []
            else:
                mode_meta = {} if mode == 'common' else dict(source)
                if mode == 'conditional':
                    binding = next((r['runner_binding'] for r in sources if 'runner_binding' in r), None)
                    if binding is not None:
                        mode_meta['runner_binding'] = binding
                predictions, provenance = p4.predict(row, mode_meta, conditional=mode=='conditional')
            receipts[-1]['projections'][mode] = provenance
            decisions.extend(dict(identity, mode=mode, method=method, **value)
                             for method, value in predictions.items())
    if any(score.digest(path) != hashes[name] for name,path in paths.items()):
        raise ValueError('source changed during run')
    write_gzip(out/'p4-predictions.jsonl.gz', decisions)
    write_gzip(out/'p4-provenance.jsonl.gz', map(publish_evidence,receipts))
    write_json(out/'p4-freeze.json', {
        'reference_commit':BASE,'cases':len(selected),'matched_queries':sum(r[2] is not None for r in selected),
        'legacy_builder':dict(revision=p4.evaluation.LEGACY_REVISION,
                              sha256=hashlib.sha256(p4.evaluation.legacy_builder_source()).hexdigest()),
        'sources':{n:dict(path=str(path.relative_to(score.REPO)),sha256=hashes[n]) for n,path in paths.items()},
        'outputs':{n:score.digest(out/n) for n in ('p4-predictions.jsonl.gz','p4-provenance.jsonl.gz')},
    })


def decision_state(record):
    if record['adapter_applicable'] is None:
        return 'UNPAIRED'
    if not record['adapter_applicable']:
        return 'ADAPTER_UNAVAILABLE'
    return record['decision']


def summarize(cases, decisions):
    action, categories, intent = score.counts([
        (label, 'ADAPTER_UNAVAILABLE' if decisions[cid]=='UNPAIRED' else decisions[cid], group)
        for cid,(label,group,_) in cases.items()])
    action['unpaired'] = sum(v == 'UNPAIRED' for v in decisions.values())
    action['adapter_unavailable'] -= action['unpaired']
    for cid, decision in decisions.items():
        if decision != 'UNPAIRED':
            continue
        label = cases[cid][0]
        for matrix,key in ((categories,label['author_category']), (intent,label['scenario_intent'])):
            matrix[key]['ADAPTER_UNAVAILABLE'] -= 1
            matrix[key]['UNPAIRED'] = matrix[key].get('UNPAIRED',0)+1
    return dict(action=action, by_author_category=categories, by_intent=intent,
                decisions=dict(Counter(decisions.values())), n=len(decisions))


def paired(cases, first, second):
    pairs = defaultdict(list)
    for cid,(label,group,_) in cases.items():
        gold = label['action_label']
        a,b = first[cid],second[cid]
        if 'UNPAIRED' in (a,b):
            continue
        pairs[group].append(int(gold in ('BLOCK','ALLOW') and a==gold)
                            -int(gold in ('BLOCK','ALLOW') and b==gold))
    groups = [pairs[group] for group in sorted(pairs)]
    n = sum(map(len,groups))
    if not n:
        return {'n':0,'difference':None,'ci95':None}
    rng = Random(17)
    samples = []
    for _ in range(1000):
        draw = rng.choices(groups,k=len(groups))
        samples.append(sum(map(sum,draw))/sum(map(len,draw)))
    samples.sort()
    return dict(n=n, groups=len(groups), difference=sum(map(sum,groups))/n,
                ci95=[samples[24],samples[974]],seed=17,draws=1000)


def analyze(out):
    paths=files()
    freeze=json.loads(paths['freeze'].read_text())
    cases=score.checked_inputs(paths['consensus'],freeze['consensus_sha256'],paths['manifest'],
                              freeze['source_sha256']['custodian_manifest.json'])
    persisted=json.loads((out/'p4-freeze.json').read_text())
    for name,h in persisted['outputs'].items():
        if score.digest(out/name)!=h:
            raise ValueError('P4 output hash mismatch')
    common_matched={row['case_id'] for row in read_jsonl(out/'p4-provenance.jsonl.gz') if row['common_issue'] is None}
    vectors=score.read_vectors(paths['local'],cases)
    vectors.update(score.read_vectors(paths['deepseek'],cases,True))
    baselines={k:{cid:score.count_state(v) for cid,v in values.items()} for k,values in vectors.items()
               if k.split('|')[0] not in p4.evaluation.CONTROLS}
    rows=defaultdict(dict)
    for item in read_jsonl(out/'p4-predictions.jsonl.gz'):
        cid=item['case_id']; key=(item['mode'],item['method'])
        if cid in rows[key] or item['event_seq']!=cases[cid][2] or item['checkpoint']!='P4':
            raise ValueError('P4 predictions duplicate or incompatible')
        rows[key][cid]=item
    by_mode=defaultdict(dict);states={}
    for key,records in sorted(rows.items()):
        mode,method=key
        if records.keys()!=cases.keys():
            raise ValueError('P4 result does not preserve all 542 cases')
        state={cid:decision_state(row) for cid,row in records.items()};states[key]=state
        summary=summarize(cases,state)
        summary['requirements']=dict(Counter(f"{r['id']}:{r['state']}" for p in records.values() for r in p.get('requirements',[])))
        summary['reasons']=dict(Counter(reason for p in records.values() for reason in p['reasons']))
        summary['operand_coverage']=dict(Counter(k for p in records.values() for k,v in p.get('operand_coverage',{}).items() if v))
        for name in ('adapter_ms','decision_ms'):
            times=[r[name] for r in records.values() if r.get(name) is not None]
            summary[name+'_median']=statistics.median(times) if times else None
        if mode=='common':
            deepseek={cid:baselines['deepseek|both|none'][cid] if cid in common_matched else 'UNPAIRED' for cid in cases}
            summary['paired_vs_deepseek']=paired(cases,state,deepseek)
        by_mode[mode][method]=summary
    changes={}
    for method in p4.METHODS:
        a,b=states['common',method],states['expanded',method]
        changes[method]=dict(Counter(a[cid]+' → '+b[cid] for cid in cases))
    result=dict(modes=by_mode, transitions=changes,
                saved_methods={k:summarize(cases,v) for k,v in baselines.items()})
    write_json(out/'p4-summary.json',result)
    (out/'P4.md').write_text(render(result))


def table(values):
    lines=['| Метод | ALLOW | BLOCK | UNKNOWN | Нет входа | Нет пары | Верно ALLOW | Верно BLOCK | Ошиб. ALLOW | Ошиб. BLOCK |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for method, value in values.items():
        d=value['decisions'];a=value['action']
        nums=[d.get(k,0) for k in ('ALLOW','BLOCK','UNKNOWN','ADAPTER_UNAVAILABLE','UNPAIRED')]
        nums += [a[k] for k in ('correct_allow','correct_block','wrong_allow_known_block','wrong_block_gold_allow')]
        lines.append('| '+method.replace('|',r'\|')+' | '+' | '.join(map(str,nums))+' |')
    return '\n'.join(lines)


def render(result):
    by_mode=result['modes']
    saved=result['saved_methods']
    comparable=('native_core|both|structural_diagnostic','native|both|fixed','deepseek|both|none')
    controls={k:v for k,v in saved.items() if k in comparable or (':raw|p4|' in k and '-17:' in k)}
    lines=['# Локальный replay перед переводом', '',
           'Во всех строках 542 состояния. Ошибочные ALLOW и BLOCK показаны относительно установленного нарушения и допустимого действия. '
           'Определённые решения при недостаточной разметке приведены отдельно в JSON.', '',
           '## Общий вход', '',table(by_mode['common']|controls),'',
           '## Дополнительные факты архива', '',table(by_mode['expanded']),'',
           '## Условное техническое воспроизведение', '',table(by_mode['conditional']),'',
           '## Изменения между общим и расширенным входом','']
    for method, counts in result['transitions'].items():
        lines.append(f'- **{method}** — '+', '.join(f'{key} ({n})' for key,n in sorted(counts.items())))
    lines.extend(['','## Парное сравнение с сохранённым DeepSeek','',
                  'Разница в доле подтверждённых правильных решений, в процентных пунктах. '
                  'Интервал рассчитан по 1 000 выборкам базовых групп с возвращением.','',
                  '| Правила | Пар | Разница | 95% интервал |','|---|---:|---:|---:|'])
    for method,value in by_mode['common'].items():
        p=value['paired_vs_deepseek']
        if p['n']:
            low,high=(100*x for x in p['ci95'])
            lines.append(f"| {method} | {p['n']} | {100*p['difference']:+.2f} | [{low:+.2f}, {high:+.2f}] |")
    lines.extend(['','## Решения по категориям сценариев','',
                  'В ячейке ALLOW / BLOCK / UNKNOWN / нет входа / нет пары. '
                  'Авторская категория описывает сценарий и хранится отдельно от разметки действия.','',
                  '| Режим и метод | Обычные | Инъекции | Условия политики | Фрод | Неизвестно |',
                  '|---|---:|---:|---:|---:|---:|'])
    for mode in ('common','expanded'):
        rows=by_mode[mode] | ({'DeepSeek':saved['deepseek|both|none']} if mode=='common' else {})
        for method,row in rows.items():
            if method.endswith('-payment'):
                continue
            values=[' / '.join(str(row['by_author_category'][category].get(key,0)) for key in
                     ('ALLOW','BLOCK','UNKNOWN','ADAPTER_UNAVAILABLE','UNPAIRED')) for category in score.CATEGORIES]
            lines.append(f'| {mode} · {method} | '+' | '.join(values)+' |')
    lines.extend(['','## Все сохранённые контроли','',table(saved),''])
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--score-only',action='store_true')
    args=parser.parse_args()
    if not args.score_only:
        args.out.mkdir(parents=True,exist_ok=False)
        run(args.out)
    analyze(args.out)


if __name__=='__main__':
    main()
