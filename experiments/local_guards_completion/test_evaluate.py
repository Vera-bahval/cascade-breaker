from copy import deepcopy
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from . import evaluate
from .evaluate import axis_labels, cascade, frozen_archive_legacy, frozen_tax_availability, ml_timings, observed_tax_availability, process_gated, saved_control_rows, score, source_goal_labels, write_summary
from .records import sha
from .assemble import targets


def requirement(status):
    return dict(status=status, evidence='pre-cut source', rationale='test obligation')


def label(gold, category='legit', intent='benign', group='group'):
    return dict(group=group, label=dict(action_label=gold, author_category=category, source_intent=intent))


class EvaluationTests(unittest.TestCase):
    def test_dynamic_denominators_and_distinct_model_unavailable(self):
        labels = {'a': label('BLOCK'), 'b': label('INSUFFICIENT')}
        result = score(labels, {'a': 'MODEL_UNAVAILABLE', 'b': 'UNKNOWN'})
        self.assertIsNone(result['rates']['false_block_rate'])
        self.assertEqual((result['unknown'], result['model_unavailable'], result['adapter_unavailable']), (1, 1, 0))
        self.assertEqual(result['author_legit_n'], 2)
        self.assertEqual(result['review_benign_n'], 2)

    def test_safe_deferral_is_not_a_known_false_block(self):
        result = score({'a': label('ALLOW')}, {'a': 'UNKNOWN'})
        self.assertEqual((result['wrong_block'], result['safe_deferral'], result['safe_not_allowed']), (0, 1, 1))

    def test_process_gate_contribution_and_unavailable_are_separate(self):
        values = dict(block='MODEL_UNAVAILABLE', defer='ALLOW', unavailable='MODEL_UNAVAILABLE', classifier_block='BLOCK')
        process = dict(block='BLOCK', defer='UNKNOWN', unavailable='ALLOW', classifier_block='UNKNOWN')
        self.assertEqual(process_gated(values, process), dict(block='BLOCK', defer='UNKNOWN', unavailable='MODEL_UNAVAILABLE', classifier_block='BLOCK'))

    def test_tax_availability_uses_all_observed_records_not_only_tool_lists(self):
        records = {key: {'observation': {'evidence': [dict(field='tax_available', value=value, origin=origin)]}}
                   for key, value, origin in [('tools', True, 'observed_or_derived'), ('actual_call', True, 'observed_or_derived'),
                                              ('disabled', False, 'observed_or_derived'), ('default', True, 'assumed')]}
        self.assertEqual(observed_tax_availability(records), {'tools', 'actual_call', 'disabled'})

    def test_frozen_tax_counts_need_no_private_sources_and_reject_changed_manifest(self):
        records = {key: {'observation': {'evidence': [dict(field='tax_available', value=True, origin=origin, source_ref=source)]}}
                   for key, origin, source in [('tools', 'observed_or_derived', '/absent/supplementary_evidence_v2/blind_inputs/a-test.json'),
                       ('call', 'observed_or_derived', 'events/12'), ('default', 'assumed', 'unknown_availability_native_default')]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'records.jsonl.gz').write_bytes(b'sealed fixture')
            manifest = dict(n=3, records_sha256=sha(path / 'records.jsonl.gz'), captured_tool_lists=1, observed_availability=2)
            manifest_path = path / 'records-manifest.json'
            manifest_path.write_text(json.dumps(manifest))
            (path / 'code-freeze.json').write_text(json.dumps(dict(records_manifest_sha256=sha(manifest_path))))
            self.assertEqual(frozen_tax_availability(records, path), ({'tools', 'call'}, {'tools'}))
            manifest['captured_tool_lists'] = 2
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'manifest changed'):
                frozen_tax_availability(records, path)

    def test_frozen_archive_profiles_remain_distinct_from_strict_legacy_methods(self):
        records = [dict(dataset=dataset, mode=mode, method=method, prefix_id='p', result={'decision': answer})
                   for dataset, mode, method, answer in [('legacy176', 'full', 'v3_archive', 'ALLOW'),
                       ('legacy176', 'full', 'v4.3_archive', 'ALLOW'), ('p4', 'common', 'v3_archive', 'BLOCK')]]
        vectors = frozen_archive_legacy(records)
        self.assertEqual(dict(vectors), {'archive_profile/v3_archive': {'p': 'ALLOW'}, 'archive_profile/v4.3_archive': {'p': 'ALLOW'}})

    def test_original_expectation_is_separate_and_undefined_injection_unscored(self):
        old = {'pay': label('BLOCK'), 'stop': label('ALLOW', 'injection', 'attack'), 'undefined': label('BLOCK', 'injection', 'attack')}
        revised = {pid: {'source_intent': row['label']['source_intent']} for pid, row in old.items()}
        source = {'pay': dict(original_expected='ALLOW', expectation_status='defined', author_category='legit'),
                  'stop': dict(original_expected='BLOCK', expectation_status='defined', author_category='injection'),
                  'undefined': dict(original_expected='UNKNOWN', expectation_status='not_defined', author_category='injection')}
        labels = source_goal_labels(old, revised, source)
        result = score(labels, {'pay': 'ALLOW', 'stop': 'BLOCK', 'undefined': 'BLOCK'})
        self.assertEqual((result['n'], result['resolved_n'], result['correct'], result['insufficient_block']), (3, 2, 2, 1))
        self.assertEqual(labels['undefined']['label']['action_label'], 'INSUFFICIENT')
        source['undefined']['expectation_status'] = 'defined'
        with self.assertRaises(ValueError):
            source_goal_labels(old, revised, source)

    def test_flat_saved_control_projection_recovers_only_hash_bound_cuts(self):
        with tempfile.TemporaryDirectory() as directory:
            exp = Path(directory)
            repaired = exp / 'repaired'
            (repaired / 'results').mkdir(parents=True)
            inp = exp / 'local_guards_adapter_repair/inputs'
            inp.mkdir(parents=True)
            source = inp / 'p4-inputs.jsonl.gz'
            projection = repaired / 'results/p4-decisions.jsonl.gz'
            source.write_bytes(b'synthetic input fixture')
            projection.write_bytes(b'synthetic projection fixture')
            (inp / 'manifest.json').write_text(json.dumps({'outputs': {'p4-inputs.jsonl.gz': sha(source)}}))
            (repaired / 'release-manifest.json').write_text(json.dumps({'files': {'results/p4-decisions.jsonl.gz': sha(projection)}, 'adapter_manifest_sha256': sha(inp / 'manifest.json')}))
            projected = dict(prefix_id='p', mode='common', config='saved', decision='ALLOW')
            def data(path):
                return iter([dict(prefix_id='p', mode='common', bundle={'event_seq': 10})] if path == source else [projected])
            with patch.object(evaluate, 'EXP', exp), patch.object(evaluate, 'REPAIRED', repaired), patch.object(evaluate, 'rows', side_effect=data):
                self.assertEqual(list(saved_control_rows({'p': {'event_seq': 10}}))[0]['event_seq'], 10)
                projected['event_seq'] = 11
                with self.assertRaises(ValueError):
                    list(saved_control_rows({'p': {'event_seq': 10}}))
                projection.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    list(saved_control_rows({'p': {'event_seq': 10}}))

    def test_sensitivity_changes_only_factually_unknown_availability(self):
        core = {'N01': requirement('satisfied')}
        revised = {key: requirement('satisfied') for key in ('N09_process', 'N09_merit', 'N10_process', 'N10_merit', 'N11', 'N14')}
        revised['N14'] = requirement('violated')
        row = dict(inherited_core=core, requirements=revised, source_intent='benign', **targets(core, revised))
        old = {'observed': label('BLOCK'), 'unknown': label('BLOCK')}
        new = {'observed': deepcopy(row), 'unknown': deepcopy(row)}
        axes = axis_labels(old, new, {'observed'}, sensitivity=True)
        self.assertEqual(axes['action_label']['observed']['label']['action_label'], 'BLOCK')
        self.assertEqual(axes['action_label']['unknown']['label']['action_label'], 'ALLOW')
        self.assertEqual(axes['substantive_label']['observed']['label']['action_label'], axes['substantive_label']['unknown']['label']['action_label'])
        self.assertEqual(new['unknown']['requirements']['N14']['status'], 'violated')

    def test_corrected_core_is_used_instead_of_historical_core(self):
        revised = {key: requirement('satisfied') for key in ('N09_process', 'N09_merit', 'N10_process', 'N10_merit', 'N11', 'N14')}
        core = {'N07': requirement('satisfied')}
        row = dict(inherited_core={'N07': requirement('unknown')}, core_requirements=core,
                   requirements=revised, source_intent='benign', **targets(core, revised))
        axes = axis_labels({'a': label('INSUFFICIENT')}, {'a': row}, set(), sensitivity=True)
        self.assertEqual(axes['action_label']['a']['label']['action_label'], 'ALLOW')

    def test_cascade_routes_deferred_and_preserves_decimal_costs(self):
        labels = {'a': label('ALLOW'), 'b': label('BLOCK')}
        saved = {'a': dict(decision='ALLOW', query_id='qa', charge_usd='0.100000000000000001', decision_ms=30),
                 'b': dict(decision='BLOCK', query_id='qb', charge_usd='0.2', decision_ms=40)}
        result = cascade({'a': 'MODEL_UNAVAILABLE', 'b': 'BLOCK'}, saved, 'block_then_llm', {'action_label': labels}, {'a': 2, 'b': 3})
        self.assertEqual(result['llm_calls'], 1)
        self.assertEqual(result['historical_api_usd'], '0.100000000000000001')
        self.assertEqual(result['paired_elapsed_ms'], {'a': 32, 'b': 3})
        self.assertEqual(result['p50_ms'], 3)
        self.assertEqual(result['p95_ms'], 32)
        self.assertEqual(result['axes']['action_label']['correct'], 2)

    def test_allow_only_route_does_not_accept_local_block(self):
        labels = {'a': label('ALLOW')}
        saved = {'a': dict(decision='ALLOW', query_id='q', charge_usd='0.1', decision_ms=10)}
        result = cascade({'a': 'BLOCK'}, saved, 'allow_then_llm', {'action_label': labels}, {})
        self.assertEqual(result['llm_calls'], 1)
        self.assertEqual(result['axes']['action_label']['correct_allow'], 1)
        self.assertIsNone(result['p50_ms'])

    def test_no_llm_call_does_not_make_an_unknown_a_local_decision(self):
        labels = {'a': label('ALLOW')}
        saved = {'a': dict(decision='ALLOW', query_id='q', charge_usd='0.1', decision_ms=10)}
        result = cascade({'a': 'UNKNOWN'}, saved, 'local', {'action_label': labels}, {})
        self.assertEqual((result['llm_calls'], result['local_decisions'], result['without_additional_llm'], result['final_deferrals']), (0, 0, 1, 1))

    def test_changed_summary_cannot_overwrite_old_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'results-summary.json'
            write_summary(path, {'n': 1})
            previous = path.read_bytes()
            write_summary(path, {'n': 1})
            with self.assertRaises(FileExistsError):
                write_summary(path, {'n': 2})
            self.assertEqual(path.read_bytes(), previous)

    def test_paired_ml_gate_timing_skips_inference_without_double_acquisition(self):
        sample = [str(i) for i in range(30)]
        detail = {'completion/current': {pid: {'result': {'process_decision': 'BLOCK' if pid == '0' else 'ALLOW'}} for pid in sample}}
        data = []
        for method in ('lr', 'catboost'):
            for pid in sample:
                for rep in range(30):
                    data.append(dict(method=method, prefix_id=pid, rep=rep, process_decision=detail['completion/current'][pid]['result']['process_decision'],
                        state_ms=1., projection_ms=2., features_ms=4., inference_ms=8., calibration_ms=16., argmax_ms=1.,
                        working_ms=31., argmax_working_ms=16., process_guard_ms=32.))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'benchmark.jsonl.gz').write_bytes(b'synthetic unit-test fixture')
            (root / 'benchmark-receipt.json').write_text(json.dumps({'benchmark_sha256': sha(root / 'benchmark.jsonl.gz')}))
            with patch('experiments.local_guards_completion.evaluate.rows', return_value=iter(data)):
                times, _ = ml_timings(root, sample, detail, {})
        self.assertEqual(times['oof/lr/calibrated']['0'], 31.)
        self.assertEqual(times['oof/lr/calibrated_process_gated']['0'], 35.)
        self.assertEqual(times['oof/lr/calibrated_process_gated']['1'], 63.)
        self.assertEqual(times['oof/lr/argmax_diagnostic_process_gated']['1'], 48.)


if __name__ == '__main__':
    unittest.main()
