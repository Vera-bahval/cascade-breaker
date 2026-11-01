"""Own unlabeled fixtures for frozen checker-exception execution; no corpus IO."""
import copy
import importlib
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace


class ConstantPipelineDiagnostic:
    """No fit/learned state: exercise frozen callbacks with one observed class."""
    available_=True
    def __init__(self,models,mode):
        import numpy as np
        self.classes_=np.asarray(['ALLOW'])
        self.named_steps=dict(features=SimpleNamespace(func=models.feature_rows,kw_args=dict(mode=mode)))
    def predict_proba(self,rows):
        import numpy as np
        step=self.named_steps['features'];step.func(rows,**step.kw_args)
        return np.ones((len(rows),1))

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))


class ReplayTests(unittest.TestCase):
    def module(self):
        self.assertTrue((HERE/'replay_predictions.py').exists(),'exception-policy replay missing')
        import replay_predictions
        return replay_predictions

    def fixture(self):
        from test_revision2 import fixture
        return fixture()

    def malformed(self):
        row=self.fixture();row['event_seq']='untyped-time'
        row['context']['approval']=dict(approved_seq=5)
        return row

    def freeze(self,root,revision):
        experiment=importlib.import_module('experiment' if revision=='original' else 'experiment_revision2')
        models=importlib.import_module('models' if revision=='original' else 'models_revision2')
        freeze=root/revision;freeze.mkdir();methods=[]
        # Explicit diagnostic constants call the actual frozen feature/probability
        # callbacks. No fitting or research model inference is performed.
        for mode in ('old','new'):
            model=ConstantPipelineDiagnostic(models,mode)
            path=freeze/(mode+'.pickle');path.write_bytes(pickle.dumps(model,protocol=5))
            methods.append(dict(name=mode,contract='A',family='logistic',arm=mode+'/own',seed=17,feature_mode=mode,
                model_file=path.name,model_sha256=experiment.digest(path),thresholds_file='thresholds.json'))
        experiment.write_json(freeze/'thresholds.json',{v:dict(thresholds=dict(ALLOW=.5,BLOCK=.5)) for v in ('raw','gated')})
        manifest=dict(version=1 if revision=='original' else 2,methods=methods,sources={},files={p.name:experiment.digest(p) for p in freeze.iterdir()})
        experiment.write_json(freeze/'freeze-manifest.json',manifest)
        return freeze,manifest

    def test_actual_frozen_extractor_exception_becomes_unknown_stop_with_unavailable_scores(self):
        replay=self.module()
        for revision in ('original','revision2'):
            with self.subTest(revision=revision),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);freeze,manifest=self.freeze(root,revision)
                module=importlib.import_module('features' if revision=='original' else 'features_revision2')
                with self.assertRaises(TypeError):module.features(self.malformed(),'new')
                obs=root/'obs.gz';meta=root/'meta.gz'
                experiment=importlib.import_module('experiment' if revision=='original' else 'experiment_revision2')
                rows=[dict(prefix_id='valid',observation=self.fixture()),dict(prefix_id='bad',observation=self.malformed())]
                saved=copy.deepcopy(rows)
                experiment.write_lines(obs,rows);experiment.write_lines(meta,[dict(prefix_id=r['prefix_id'],episode_id=r['prefix_id']) for r in rows])
                receipt=replay.predict(revision,freeze,obs,meta,root/'predictions',batch_size=2)
                self.assertEqual(list(experiment.read_lines(obs)),saved)
                predictions=[r for _,stream in replay.prediction_methods(root/'predictions',receipt) for r in stream]
                errors=[r for r in predictions if r['prefix_id']=='bad' and r['method'].startswith('new__')]
                self.assertEqual(len(errors),3)
                for result in errors:
                    self.assertEqual(result['decision'],'UNKNOWN');self.assertTrue(result['stop'])
                    self.assertFalse(result['scores_available']);self.assertIsNone(result['probabilities'])
                    self.assertEqual(result['execution_error_class'],'TypeError')
                    self.assertEqual(result['execution_error_stage'],'features')
                    self.assertIn('timing',result)
                for result in predictions:
                    if result['prefix_id']=='valid' or result['method'].startswith('old__'):
                        self.assertEqual(result['probabilities'],dict(ALLOW=1.,BLOCK=0.,UNKNOWN=0.))
                self.assertEqual(len(predictions),12)
                self.assertFalse(receipt['labels_opened']);self.assertFalse(receipt['fit_called'])
                self.assertEqual(receipt['method_revision'],revision)
                self.assertEqual(receipt['adapter_sha256'],experiment.digest(HERE/'replay_predictions.py'))
                self.assertEqual(receipt['expected_eligible'],{d['name']:2 for d in receipt['methods']})
                import evaluation_revision2 as ev
                self.assertEqual(ev.verify_predictions(root/'predictions',obs,meta,model_freeze=freeze),receipt)
                for descriptor in receipt['methods']:
                    self.assertEqual({r['prefix_id'] for r in predictions if r['method']==descriptor['name']},{'valid','bad'})

    def test_valid_pipeline_parity_and_revision_specific_gate(self):
        replay=self.module()
        for revision in ('original','revision2'):
            with self.subTest(revision=revision),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);freeze,manifest=self.freeze(root,revision)
                exp=importlib.import_module('experiment' if revision=='original' else 'experiment_revision2')
                path=freeze/'thresholds.json';thresholds=json.loads(path.read_text());thresholds['raw']['thresholds']['ALLOW']=1.000001
                path.unlink();exp.write_json(path,thresholds);manifest['files'][path.name]=exp.digest(path)
                (freeze/'freeze-manifest.json').unlink();exp.write_json(freeze/'freeze-manifest.json',manifest)
                modules=replay.load_revision(revision,freeze)
                obs=root/'obs.gz';meta=root/'meta.gz';row=dict(prefix_id='valid',observation=self.fixture())
                modules.experiment.write_lines(obs,[row]);modules.experiment.write_lines(meta,[dict(prefix_id='valid',episode_id='own')])
                receipt=replay.predict(revision,freeze,obs,meta,root/'predictions')
                for _,stream in replay.prediction_methods(root/'predictions',receipt):
                    for result in stream:
                        method=next(m for m in manifest['methods'] if result['method'].startswith(m['name']+'__'))
                        model=pickle.loads((freeze/method['model_file']).read_bytes())
                        expected=modules.models.probabilities(model,[row])[0]
                        self.assertEqual(result['probabilities'],expected)
                        thresholds=json.loads((freeze/'thresholds.json').read_text())
                        variant=result['variant']
                        raw='ALLOW' if variant=='argmax_diagnostic' else modules.experiment.decide([expected],thresholds[variant]['thresholds'])[0]
                        gate=modules.features.mandatory_proof_gate(row,'A') if variant=='gated' and raw=='ALLOW' else dict(allow=True)
                        self.assertEqual(result['decision'],'UNKNOWN' if not gate['allow'] else raw)
                        if variant=='gated':self.assertEqual(result['decision'],'UNKNOWN' if revision=='original' else 'ALLOW')
                        if variant=='raw':self.assertEqual(result['decision'],'UNKNOWN')
                        self.assertTrue(result['scores_available'])
                with self.assertRaisesRegex(ValueError,'revision'):
                    replay.load_revision('revision2' if revision=='original' else 'original',freeze)

    def test_generic_batch_fallback_keeps_successful_rows_and_gate_only_error_is_gated(self):
        replay=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.freeze(root,'revision2');modules=replay.load_revision('revision2',freeze)
            obs=root/'obs.gz';meta=root/'meta.gz';rows=[dict(prefix_id=str(i),observation=self.fixture()) for i in range(2)]
            modules.experiment.write_lines(obs,rows);modules.experiment.write_lines(meta,[dict(prefix_id=r['prefix_id'],episode_id=r['prefix_id']) for r in rows])
            original=modules.models.probabilities
            def single_only(model,rows):
                if len(rows)>1:raise RuntimeError('own batch diagnostic')
                return original(model,rows)
            with patch.object(modules.models,'probabilities',single_only),patch.object(modules.features,'mandatory_proof_gate',side_effect=RuntimeError('own gate diagnostic')):
                receipt=replay.predict('revision2',freeze,obs,meta,root/'predictions',batch_size=2)
            results=[r for _,stream in replay.prediction_methods(root/'predictions',receipt) for r in stream]
            self.assertTrue(receipt['batch_fallbacks'])
            for result in results:
                if result['variant']=='gated':
                    self.assertEqual(result['decision'],'UNKNOWN');self.assertFalse(result['scores_available'])
                    self.assertEqual(result['execution_error_stage'],'gate');self.assertEqual(result['execution_error_class'],'RuntimeError')
                else:
                    self.assertEqual(result['decision'],'ALLOW')
                    self.assertEqual(result['probabilities'],dict(ALLOW=1.,BLOCK=0.,UNKNOWN=0.))

    def test_single_measurement_matches_checker_exception_stop_policy(self):
        self.module()
        import evaluation_revision2 as ev
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.freeze(root,'revision2')
            candidate=ev.Frozen(freeze,next(m for m in manifest['methods'] if m['feature_mode']=='new'),manifest)
            for variant in ('raw','gated'):
                result=candidate.one(dict(observation=self.malformed()),variant)
                self.assertEqual(result['decision'],'UNKNOWN');self.assertTrue(result['stop'])
                self.assertIsNone(result['probabilities']);self.assertFalse(result['scores_available'])
                self.assertEqual(result['execution_error_class'],'TypeError')
            with patch.object(ev,'mandatory_proof_gate',side_effect=LookupError('own gate diagnostic')):
                self.assertEqual(candidate.one(dict(observation=self.fixture()),'raw')['decision'],'ALLOW')
                gated=candidate.one(dict(observation=self.fixture()),'gated')
                self.assertEqual(gated['decision'],'UNKNOWN');self.assertFalse(gated['scores_available'])
                self.assertEqual(gated['execution_error_class'],'LookupError')

    def test_unavailable_model_and_generic_singleton_score_failure_do_not_fabricate_classes(self):
        replay=self.module()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.freeze(root,'revision2');modules=replay.load_revision('revision2',freeze)
            rows=[dict(observation=self.malformed())]
            features=replay.extract_batch(modules,rows)
            from models import UnavailableModel
            unavailable=UnavailableModel('own unavailable diagnostic',{})
            scored,_=replay.score_batch(modules,unavailable,rows,features['new'],'new')
            self.assertEqual(scored[0]['probabilities'],dict(ALLOW=0.,BLOCK=0.,UNKNOWN=0.))
            self.assertIsNone(scored[0]['error']);self.assertFalse(scored[0]['scores_available'])
            model=ConstantPipelineDiagnostic(modules.models,'new')
            valid=[dict(observation=self.fixture())];entries=replay.extract_batch(modules,valid)['new']
            with patch.object(modules.models,'probabilities',side_effect=ArithmeticError('own scorer diagnostic')):
                scored,fallback=replay.score_batch(modules,model,valid,entries,'new')
            self.assertTrue(fallback);self.assertIsNone(scored[0]['probabilities'])
            self.assertEqual(scored[0]['error']['execution_error_class'],'ArithmeticError')
            self.assertEqual(scored[0]['error']['decision'],'UNKNOWN')

    def test_single_benchmark_retains_malformed_check_and_marks_component_unavailable(self):
        self.module()
        import benchmark_revision2 as bm
        import evaluation_revision2 as ev
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.freeze(root,'revision2')
            obs=root/'obs.gz';meta=root/'meta.gz'
            ev.write_lines(obs,[dict(prefix_id='own-malformed',observation=self.malformed())])
            ev.write_lines(meta,[dict(prefix_id='own-malformed',episode_id='own',family='own engineering diagnostic')])
            bm.single(freeze,obs,meta,root/'single',repeats=1,limit=1,methods=['new'])
            records=[row for path in (root/'single').glob('*.jsonl.gz') for row in ev.read_lines(path)]
            measured=[row for row in records if row['method'].startswith('new__')]
            self.assertEqual(len(measured),2)
            for row in measured:
                self.assertEqual(row['decision'],'UNKNOWN');self.assertGreaterEqual(row['elapsed_ms'],0.)
                self.assertFalse(row['scores_available']);self.assertEqual(row['execution_error_class'],'TypeError')
                self.assertIsNone(row['component_diagnostic']['feature_ms'])
                self.assertIsNone(row['component_diagnostic']['precomputed_pipeline_ms'])
                self.assertEqual(row['component_error']['stage'],'features')
                self.assertEqual(row['component_error']['error_class'],'TypeError')


if __name__=='__main__':unittest.main(verbosity=2)
