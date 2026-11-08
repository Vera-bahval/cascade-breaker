"""Source-bound annotation statistics and representative saved decisions."""
import collections
import json
import random
from pathlib import Path
from score import checked_inputs, read_vectors, count_state, digest, counts

E = Path(__file__).resolve().parent
EXAMPLES = [
    ('Правильное разрешение', 'a-1f6ac8e6c18d73479da316d2'),
    ('Полезный запрет', 'a-0d1dd97e12a5c4c8080229cc'),
    ('Ложная остановка', 'a-e29e8d2fadef3002e243a50f'),
    ('Общий пропуск', 'a-0486427e4de2d0ba75b1e50b'),
]
METHODS = ['native_core|both|structural_diagnostic', 'native|both|fixed', 'deepseek|both|none']


def main():
    freeze = json.loads((E/'consensus-freeze.json').read_text())
    cases = checked_inputs(E/'labels/consensus.jsonl', freeze['consensus_sha256'], E/'custodian_manifest.json', freeze['source_sha256']['custodian_manifest.json'])
    inventory = json.loads((E/'inventory.json').read_text())
    vectors = {}
    for source in ('historical_local','historical_deepseek'):
        f = inventory['files'][source]; path = E.parents[1]/f['path']
        if digest(path) != f['sha256']:
            raise ValueError('changed prediction source')
        vectors.update(read_vectors(path, cases))
    labels = {r[0]['annotation_id']:r[0] for r in cases.values()}
    mapping = {r['annotation_id']:r for r in json.loads((E/'custodian_manifest.json').read_text())['cases']}
    summary = {'consensus_sha256':freeze['consensus_sha256'], 'describe_sha256':digest(Path(__file__)),
        'known_violations_by_requirement':dict(collections.Counter(k for r in labels.values() if r['action_label']=='BLOCK' for k,v in r['requirements'].items() if v['status']=='violated')),
        'insufficient_by_requirement':dict(collections.Counter(k for r in labels.values() if r['action_label']=='INSUFFICIENT' for k,v in r['requirements'].items() if v['status']=='unknown')),
        'only_tax_unknown':sum(r['action_label']=='INSUFFICIENT' and {k for k,v in r['requirements'].items() if v['status']=='unknown'}=={'N14'} for r in labels.values()),
        'n14_changed_overall':sum(r['before_n14_clarification']['label']!=r['action_label'] for r in labels.values() if 'before_n14_clarification' in r)}
    grouped = collections.defaultdict(list)
    for cid,(r,g,_) in cases.items():
        correct = [int(r['action_label'] in ('ALLOW','BLOCK') and count_state(vectors[k][cid])==r['action_label']) for k in METHODS[1:]]
        grouped[g].append(correct[0]-correct[1])
    rng=random.Random(17);groups=sorted(grouped);draws=[]
    for _ in range(1000):
        sample=[x for _ in groups for x in grouped[rng.choice(groups)]]
        draws.append(sum(sample)/len(sample))
    draws.sort()
    summary['paired_native_minus_deepseek_correct_coverage']={'point':sum(sum(x) for x in grouped.values())/len(cases),'ci95_percentile':[draws[24],draws[974]],'groups':len(groups),'bootstrap_replicates':1000,'seed':17}
    (E/'results/annotation-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    out=['# Примеры сохранённых решений',
         'Примеры выбраны после оценки для объяснения механизмов. Они не являются случайной выборкой и не подтверждают частоту этих механизмов. '
         'Ссылки ведут к событиям до действия и полной разметке; правильность здесь означает соответствие принятой политике в пределах сохранённых свидетельств.']
    for title,key in EXAMPLES:
        r=labels[key]; cid=mapping[key]['case_id']
        out += [f'## {title}',f'Состояние `{key}`. [Вход](action_inputs/{key}.json). Оценка действия: **{r["action_label"]}**.']
        table = ['| Метод | Сохранённый ответ |','| --- | --- |']
        for m in METHODS:
            table.append('| `'+m.replace('|',r'\|')+'` | '+count_state(vectors[m][cid])+' |')
        out.append('\n'.join(table))
        out.append('Основание оценщиков: '+r['rationale'])
        for req,value in r['requirements'].items():
            if value['status']=='violated' or req in ('N09','N11','N14'):
                out.append(f'- {req}: {value["status"]}. {value["rationale"]} Источник: '+json.dumps(value['evidence'],ensure_ascii=False))
        out.append('Происхождение разметки: '+json.dumps(r['provenance'],ensure_ascii=False))
    (E/'EXAMPLES.md').write_text('\n\n'.join(out)+'\n')


if __name__=='__main__':main()
