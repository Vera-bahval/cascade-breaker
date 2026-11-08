"""Split-only frozen-input partitioning for unchanged cascade evaluation."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.local_guards_archive_comparison import evaluation as base, cascade_evaluation as cascade


def selfcheck():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source, output = root/'source.jsonl.gz', root/'representative.jsonl.gz'
        rows = [dict(case_id='a', prefix_id='a', split='REPRESENTATIVE', method='arbitrary', decision='BLOCK'),
                dict(case_id='b', prefix_id='b', split='CHALLENGE', method='other', decision='ALLOW'),
                dict(case_id='c', prefix_id='c', split='REPRESENTATIVE', method='other', decision='UNKNOWN')]
        base.write_rows(source, rows)
        original_hash = base.digest(source)
        report = filter_split(source, output, 'REPRESENTATIVE')
        assert list(base.read_rows(output)) == [rows[0], rows[2]]
        assert report['input_rows'] == 3 and report['kept_rows'] == 2
        assert report['case_ids'] == ['a', 'c']
        assert base.digest(source) == original_hash
        try:
            filter_split(source, output, 'REPRESENTATIVE')
        except FileExistsError:
            pass
        else:
            raise AssertionError('must never overwrite an existing subset')
        episodes = [dict(episode_id=name, group_id='g/'+name, split='REPRESENTATIVE') for name in ('p2', 'p4', 'none')]
        episodes.append(dict(episode_id='challenge', group_id='gc', split='CHALLENGE'))
        metadata = [dict(prefix_id='a', episode_id='p2', checkpoint='P2_afterFraud', split='REPRESENTATIVE'),
                    dict(prefix_id='b', episode_id='p4', checkpoint='P4', split='REPRESENTATIVE')]
        coverage = episode_coverage(episodes, metadata, 'REPRESENTATIVE')
        assert coverage['episode_ids'] == ['none', 'p2', 'p4']
        assert coverage['no_p4_episode_ids'] == ['none', 'p2']
        assert coverage['no_cut_episode_ids'] == ['none']
    print('split-only filter and retained-censored-episode selfchecks PASS')


def filter_split(source, output, split):
    """Copy every column and every method; split is the only selection value."""
    if split not in {'REPRESENTATIVE', 'CHALLENGE'}:
        raise ValueError('only the two predeclared selected splits are supported')
    counts = {'input_rows': 0, 'kept_rows': 0}
    cases, prefixes, episodes = set(), set(), set()
    def rows():
        for row in base.read_rows(source):
            counts['input_rows'] += 1
            if row['split'] != split:
                continue
            counts['kept_rows'] += 1
            for key, target in (('case_id', cases), ('prefix_id', prefixes), ('episode_id', episodes)):
                if key in row:
                    target.add(row[key])
            yield row
    base.write_rows(output, rows())
    return {**counts, 'case_ids': sorted(cases), 'prefix_ids': sorted(prefixes), 'episode_ids': sorted(episodes),
            'sha256': base.digest(output)}


def episode_coverage(episodes, metadata, split):
    selected = [row for row in episodes if row['split'] == split]
    identities = {row['episode_id'] for row in selected}
    if len(identities) != len(selected):
        raise ValueError('duplicate selected episode identity')
    cuts = [row for row in metadata if row['split'] == split]
    reached = {row['episode_id'] for row in cuts}
    p4 = {row['episode_id'] for row in cuts if row['checkpoint'] == 'P4'}
    if not reached <= identities:
        raise ValueError('prefix outside selected episode universe')
    return {'episode_ids': sorted(identities),
            'group_ids': sorted({row.get('base_group_id', row.get('group_id')) for row in selected}),
            'no_p4_episode_ids': sorted(identities-p4), 'no_cut_episode_ids': sorted(identities-reached),
            'prefix_ids': sorted({row['prefix_id'] for row in cuts})}


def prepare(parent_freeze, answers, answer_receipt, output_root, actual_spend, actual_spend_sha256):
    """Create immutable subset inputs and new freezes; no scores choose a split."""
    parent = cascade.verify_freeze(parent_freeze)
    answer_proof = json.loads(Path(answer_receipt).read_text())
    cascade._check(answers, answer_proof['predictions_sha256'], 'parent normalized answers')
    cascade._check(actual_spend, actual_spend_sha256, 'actual full-run spend')
    source_sha = base.digest(Path(__file__))
    output_root = Path(output_root)
    metadata = list(base.read_rows(parent['inputs']['metadata']['path']))
    episodes = list(base.read_rows(parent['inputs']['episodes']['path']))
    metadata_by_prefix = base.unique(metadata, 'prefix_id')
    episode_by_id = base.unique(episodes, 'episode_id')
    combined = Path(parent_freeze).parent/'cascade-evaluation'
    preserved = {str(path): base.digest(path) for path in [Path(parent_freeze), *sorted(combined.glob('*'))] if path.is_file()}
    created = {}
    for split in ('REPRESENTATIVE', 'CHALLENGE'):
        name = split.lower()
        directory = output_root/'strata'/name
        directory.mkdir(parents=True, exist_ok=False)
        targets = {key: directory/(key+'.jsonl.gz') for key in ('predictions', 'episodes', 'deepseek')}
        reports = {
            'predictions': filter_split(parent['inputs']['predictions']['path'], targets['predictions'], split),
            'episodes': filter_split(parent['inputs']['episodes']['path'], targets['episodes'], split),
            'deepseek': filter_split(answers, targets['deepseek'], split),
        }
        coverage = episode_coverage(episodes, metadata, split)
        if reports['episodes']['episode_ids'] != coverage['episode_ids']:
            raise ValueError('episode filter dropped a selected task')
        if reports['predictions']['prefix_ids'] != coverage['prefix_ids']:
            raise ValueError('prediction state coverage differs from canonical split metadata')
        for prefix in reports['deepseek']['prefix_ids']:
            if prefix not in metadata_by_prefix or metadata_by_prefix[prefix]['split'] != split:
                raise ValueError('normalized answer split disagrees with canonical metadata')
        selected_groups = set(coverage['group_ids'])
        if selected_groups & {row.get('base_group_id', row.get('group_id')) for row in episodes if row['split'] != split}:
            raise ValueError('base group spans selected strata')
        manifest = {
            'version': 'split-only-stratum-1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'split': split, 'selection': 'exact declared split only; all methods/columns copied unchanged; no outcome/prediction selection',
            'stratifier_sha256': source_sha, 'parent_freeze': {'path': str(Path(parent_freeze).resolve()), 'sha256': base.digest(parent_freeze)},
            'parent_inputs': parent['inputs'],
            'parent_answers': {'path': str(Path(answers).resolve()), 'sha256': base.digest(answers),
                               'receipt_path': str(Path(answer_receipt).resolve()), 'receipt_sha256': base.digest(answer_receipt)},
            'actual_full_run_spend': {'path': str(Path(actual_spend).resolve()), 'sha256': actual_spend_sha256},
            'outputs': {key: {'path': str(targets[key].resolve()), **value} for key, value in reports.items()},
            'episode_coverage': {**coverage, 'all_no_p4_episodes_retained': True, 'all_no_cut_episodes_retained': True},
            'answer_coverage': {'served_case_ids': reports['deepseek']['case_ids'],
                'missing_case_ids': sorted(set(reports['predictions']['case_ids'])-set(reports['deepseek']['case_ids'])),
                'extra_answer_case_ids': sorted(set(reports['deepseek']['case_ids'])-set(reports['predictions']['case_ids']))},
            'combined_outputs_preserved': preserved,
        }
        if manifest['answer_coverage']['extra_answer_case_ids']:
            raise ValueError('answer without a selected frozen prediction')
        manifest_path = directory/'input-manifest.json'
        base.write_json(manifest_path, manifest)
        bindings = {key: value['path'] for key, value in parent['inputs'].items()}
        bindings.update(predictions=str(targets['predictions'].resolve()), episodes=str(targets['episodes'].resolve()),
                        stratum_manifest=str(manifest_path.resolve()))
        freeze_path = output_root/('cascade-'+name+'-freeze.json')
        cascade.freeze(parent['cascade_manifest']['path'], freeze_path, bindings)
        created[split] = {'freeze': str(freeze_path), 'answers': str(targets['deepseek']),
                          'answers_sha256': reports['deepseek']['sha256'], 'output_dir': str(output_root/('cascade-'+name)),
                          'input_manifest': str(manifest_path), 'episodes': len(coverage['episode_ids']),
                          'groups': len(coverage['group_ids']), 'cases': len(reports['predictions']['case_ids']),
                          'no_p4_episodes': len(coverage['no_p4_episode_ids']), 'no_cut_episodes': len(coverage['no_cut_episode_ids']),
                          'missing_answers': len(manifest['answer_coverage']['missing_case_ids'])}
    for path, expected in preserved.items():
        cascade._check(path, expected, 'preserved combined output')
    if base.digest(Path(__file__)) != source_sha:
        raise ValueError('stratifier source changed during partitioning')
    base.write_json(output_root/'strata/input-manifest.json', {
        'parent_freeze_sha256': base.digest(parent_freeze), 'stratifier_sha256': source_sha,
        'actual_spend_sha256': actual_spend_sha256, 'strata': created,
        'no_p4_retention': True, 'combined_outputs_preserved': preserved})
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selfcheck', action='store_true')
    parser.add_argument('--parent-freeze')
    parser.add_argument('--answers')
    parser.add_argument('--answer-receipt')
    parser.add_argument('--output-root')
    parser.add_argument('--actual-spend')
    parser.add_argument('--actual-spend-sha256')
    args = parser.parse_args()
    if args.selfcheck:
        selfcheck()
        return
    values = vars(args); values.pop('selfcheck')
    if any(value is None for value in values.values()):
        parser.error('all prepare paths and actual-spend-sha256 are required')
    print(json.dumps(prepare(**values), indent=2))


if __name__ == '__main__':
    main()
