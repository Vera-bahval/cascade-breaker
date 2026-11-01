"""Own engineering fixtures only; no research observations, labels or results."""
import copy
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))


class EvaluationRevision2Tests(unittest.TestCase):
    def modules(self):
        self.assertTrue((HERE/'evaluation_revision2.py').exists(),'revision2 evaluation adapter missing')
        self.assertTrue((HERE/'benchmark_revision2.py').exists(),'revision2 benchmark adapter missing')
        import evaluation_revision2 as ev
        import benchmark_revision2 as bm
        return ev,bm

    def fixture(self):
        from test_revision2 import fixture
        return fixture()

    def invocation(self):
        class Parent:workflow_id='actual-parent'
        return Parent(),'delegate_to_invoice',{},dict(context=dict(call_id='completed-source'))

    def base(self):
        row=self.fixture();row['context']['parent_workflow_id']=None
        row['provenance']['delegation_subject_matches'][0].update(call_id='checking-call',operation='native_snapshot')
        return row

    def test_distinct_call_enrichment_preserves_checking_and_only_rebinds_existing_proof(self):
        ev,bm=self.modules();base=self.base();saved=copy.deepcopy(base)
        row,delta=bm.enrich_snapshot(base,self.invocation())
        self.assertEqual(base,saved)
        self.assertEqual(row['context']['call_id'],'checking-call')
        self.assertEqual(row['context']['delegation_call_id'],'completed-source')
        self.assertEqual(row['context']['parent_workflow_id'],'actual-parent')
        self.assertEqual(row['provenance']['delegation_subject_matches'][0]['call_id'],'completed-source')
        self.assertEqual(row['provenance']['session_valid'],base['provenance']['session_valid'])
        self.assertEqual({d['path'] for d in delta},{'context.parent_workflow_id','provenance.delegation_subject_matches.0.call_id'})
        self.assertTrue(ev.mandatory_proof_gate(row,'A')['allow'])
        self.assertTrue(ev.mandatory_proof_gate(row,'B')['allow'])

    def test_missing_or_foreign_linkage_proof_and_failed_completion_stay_unavailable(self):
        ev,bm=self.modules()
        cases=[]
        cases.append((self.base(),None))
        row=self.base();row['context'].pop('delegation_call_id');cases.append((row,self.invocation()))
        row=self.base();row['context']['delegation_call_id']='foreign-source';cases.append((row,self.invocation()))
        row=self.base();row['provenance']['delegation_subject_matches']=[];cases.append((row,self.invocation()))
        row=self.base();row['provenance']['delegation_subject_matches'][0]['call_id']='foreign-proof';cases.append((row,self.invocation()))
        row=self.base();row['context']['delegation_succeeded']=False;cases.append((row,self.invocation()))
        row=self.base();row['provenance']['delegation_subject_matches'][0]['value']=False;cases.append((row,self.invocation()))
        for base,invocation in cases:
            with self.subTest(base=base):
                row,_=bm.enrich_snapshot(base,invocation)
                self.assertEqual(row['context']['call_id'],'checking-call')
                self.assertEqual(row['provenance']['delegation_subject_matches'],base['provenance']['delegation_subject_matches'])
                self.assertFalse(ev.mandatory_proof_gate(row,'A')['allow'])
        row=self.base();row['checkpoint']='P1'
        self.assertEqual(bm.enrich_snapshot(row,self.invocation()),(row,[]))

    def test_metric_replay_denominators_and_timing_definitions_unchanged(self):
        ev,bm=self.modules()
        import evaluation as old
        rows=[dict(prefix_id='a',decision='UNKNOWN',gold='ALLOW',event_seq=1,episode_id='e',cluster='g'),
              dict(prefix_id='b',decision='BLOCK',gold='BLOCK',event_seq=2,episode_id='e',cluster='g')]
        def original_fields_equal(actual,expected):
            for key,value in expected.items():
                if isinstance(value,dict):original_fields_equal(actual[key],value)
                else:self.assertEqual(actual[key],value,key)
        # Additional availability/ordering denominators must not change any
        # original metric on this fully numeric engineering fixture.
        original_fields_equal(ev.summarize(rows,bootstrap=20),old.summarize(rows,bootstrap=20))
        self.assertEqual(ev.stats([1,2,3,4]),old.stats([1,2,3,4]))
        self.assertEqual(ev.argmax_diagnostic(dict(method='own__raw',probabilities=dict(ALLOW=.5,BLOCK=.5,UNKNOWN=0.)))['decision'],'UNKNOWN')
        summary=bm.native_summary([dict(method='m',status='completed',elapsed_ms=100,check_ms=[1]),dict(method='m',status='stopped',elapsed_ms=10,check_ms=[2])])['m']
        self.assertEqual(summary['completed_chain']['n'],1);self.assertEqual(summary['stopped_chain']['p50_ms'],10)

    def tiny_freeze(self,root):
        ev,_=self.modules()
        from models_revision2 import fit_model,bind_reused_model
        from models import fit_model as original_fit_model
        freeze=root/'freeze';freeze.mkdir();methods=[]
        for mode in ('old','new'):
            for reused in (False,True):
                model=(original_fit_model if reused else fit_model)('logistic',[self.fixture()],['ALLOW'],[1.],mode,17)
                if reused:bind_reused_model(model)
                name=mode+('_reused' if reused else '_versioned');path=freeze/(name+'.pickle');path.write_bytes(pickle.dumps(model,protocol=5))
                methods.append(dict(name=name,contract='A',family='logistic',arm=mode+'/own',seed=17,feature_mode=mode,
                    model_file=path.name,model_sha256=ev.digest(path),thresholds_file='thresholds.json'))
        ev.write_json(freeze/'thresholds.json',{v:dict(thresholds=dict(ALLOW=.5,BLOCK=.5),feasible=False,
            infeasibility_reason='own fixture only',no_safe_cal_episodes=True,grid_points={},metrics={}) for v in ('raw','gated')})
        manifest=dict(version=2,methods=methods,sources={},files={p.name:ev.digest(p) for p in freeze.iterdir()})
        ev.write_json(freeze/'freeze-manifest.json',manifest)
        return freeze,manifest

    def test_versioned_reused_raw_precomputed_single_stream_and_receipt_parity(self):
        ev,bm=self.modules()
        from models import FeatureBatch
        self.assertIs(ev.FeatureBatch,FeatureBatch)
        self.assertEqual(ev.features.__module__,'features_revision2')
        self.assertEqual(ev.probabilities.__module__,'models_revision2')
        self.assertEqual(ev.verify_freeze.__module__,'experiment_revision2')
        self.assertIs(bm.evaluation(),ev)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.tiny_freeze(root);rows=[dict(prefix_id='own',observation=self.fixture())]
            obs=root/'obs.gz';meta=root/'meta.gz'
            ev.write_lines(obs,rows);ev.write_lines(meta,[dict(prefix_id='own',episode_id='own',source='synthetic')])
            for method in manifest['methods']:
                candidate=ev.Frozen(freeze,method,manifest)
                self.assertEqual(candidate.model.named_steps['features'].func.__module__,'models_revision2')
                batch=ev.FeatureBatch([ev.features(r,method['feature_mode']) for r in rows],method['feature_mode'])
                ps=ev.probabilities(candidate.model,batch)
                self.assertEqual(ps,ev.probabilities(candidate.model,rows))
                self.assertEqual(ps[0],candidate.one(rows[0])['probabilities'])
                self.assertEqual(candidate.one(rows[0])['decision'],'ALLOW')
                foreign=copy.deepcopy(rows[0]);foreign['observation']['provenance']['delegation_subject_matches'][0]['call_id']='foreign'
                self.assertEqual(candidate.one(foreign,'raw')['decision'],'ALLOW')
                self.assertEqual(candidate.one(foreign,'gated')['decision'],'UNKNOWN')
            receipt=ev.predict(freeze,obs,meta,root/'predictions',batch_size=1)
            self.assertEqual(len(receipt['methods']),12)
            self.assertEqual(ev.verify_predictions(root/'predictions',obs,meta),receipt)
            self.assertFalse(receipt['latency_measured'])
            # Corruption is rejected before attempting a label read.
            shard=root/'predictions'/receipt['files'][0]['path'];shard.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'hash'):
                ev.score([root/'predictions'],obs,meta,root/'missing-gold',root/'score')

    def test_cold_worker_uses_versioned_inference(self):
        ev,bm=self.modules()
        from contextlib import redirect_stdout
        import io
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.tiny_freeze(root);obs=root/'observation.json';obs.write_text(json.dumps(self.fixture()))
            output=io.StringIO()
            with redirect_stdout(output):bm.cold_worker(freeze,manifest['methods'][0]['name'],obs)
            record=json.loads(output.getvalue());self.assertEqual(record['decision'],'ALLOW')
            self.assertTrue(record['checked'])

    def test_original_pipeline_and_freeze_cannot_be_mistaken_for_revision2(self):
        ev,_=self.modules()
        from models import fit_model
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.tiny_freeze(root);method=manifest['methods'][0]
            with self.assertRaisesRegex(ValueError,'revision2 freeze required'):
                ev.Frozen(freeze,method,dict(manifest,version=1))
            model=fit_model('logistic',[self.fixture()],['ALLOW'],[1.],method['feature_mode'],17)
            path=freeze/method['model_file'];path.write_bytes(pickle.dumps(model,protocol=5))
            method['model_sha256']=ev.digest(path);manifest['files'][path.name]=ev.digest(path)
            with self.assertRaisesRegex(ValueError,'inference is not bound to revision2'):
                ev.Frozen(freeze,method,manifest)

    def test_72_descriptor_streams_all_variants_and_labelblind_controls_on_one_own_state(self):
        ev,_=self.modules()
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.tiny_freeze(root)
            methods=[]
            for contract in ev.CONTRACTS:
                for mode in ('old','new'):
                    template=next(m for m in manifest['methods'] if m['feature_mode']==mode)
                    for source in ('archive','mixed'):
                        for family in ('logistic','catboost'):
                            for seed in (17,29,43):
                                methods.append(dict(template,name=f'{contract}__{mode}__{source}__{family}__{seed}',
                                    contract=contract,arm=mode+'/'+source,family=family,seed=seed))
            manifest['methods']=methods
            (freeze/'freeze-manifest.json').unlink();ev.write_json(freeze/'freeze-manifest.json',manifest)
            row=self.fixture();row['checkpoint']='P4';row['proposal']['tool']='finstripe__create_transfer'
            obs=root/'obs.gz';meta=root/'meta.gz';labels=root/'own-labels.gz'
            ev.write_lines(obs,[dict(prefix_id='own',observation=row)])
            ev.write_lines(meta,[dict(prefix_id='own',episode_id='own',source='synthetic')])
            ev.write_lines(labels,[dict(prefix_id='own',labels={c:'UNKNOWN' for c in ev.CONTRACTS})])
            receipt=ev.predict(freeze,obs,meta,root/'predictions',batch_size=1)
            self.assertEqual(len(receipt['methods']),216)
            self.assertEqual(len(list((root/'predictions').glob('*.jsonl.gz'))),216)
            self.assertEqual({m['variant'] for m in receipt['methods']},{'raw','gated','argmax_diagnostic'})
            self.assertEqual(ev.verify_predictions(root/'predictions',obs,meta),receipt)
            rules=ev.controls(obs,meta,root/'controls')
            self.assertEqual(len(rules['methods']),3)
            self.assertFalse(rules['labels_opened'])
            # Use ONLY the temporary engineering freeze for the unchanged CAL
            # export; the concurrently fitted research freeze is never opened.
            with patch.object(ev,'HERE',root):
                (root/'frozen_revision2').symlink_to(freeze,target_is_directory=True)
                # Fill required CAL receipt fields with diagnostic-only values.
                path=freeze/'thresholds.json';path.unlink()
                ev.write_json(path,{v:dict(thresholds=dict(ALLOW=.5,BLOCK=.5),feasible=False,
                    infeasibility_reason='own fixture only',no_safe_cal_episodes=True,grid_points={},metrics={})
                    for v in ('raw','gated')})
                manifest['files'][path.name]=ev.digest(path)
                (freeze/'freeze-manifest.json').unlink();ev.write_json(freeze/'freeze-manifest.json',manifest)
                import experiment_revision2
                from contextlib import redirect_stdout
                import io
                experiment_revision2.predict(freeze,obs,meta,root/'experiment-predictions.gz')
                self.assertFalse(ev.verify_predictions(root/'experiment-predictions.gz',obs,meta)['labels_opened'])
                with redirect_stdout(io.StringIO()):
                    ev.score([root/'controls',root/'experiment-predictions.gz'],obs,meta,labels,root/'score',bootstrap=0)
            self.assertEqual(len(json.loads((root/'score/frozen-calibration.json').read_text())['methods']),144)
            metrics=json.loads((root/'score/metrics.json').read_text())['metrics']
            self.assertEqual(len({r['method'] for r in metrics}),219)

    def diagnostic(self,stop=False,stop_tool=None):
        ev,_=self.modules()
        class ConstantClassifierDiagnostic:
            def one(self,row,variant):
                o=ev.obj(row)
                if not ev.eligible(row,'B'):return dict(checked=False,decision=None,stop=False,reasons=[])
                gate=ev.mandatory_proof_gate(row,'B')
                forced_stop=(stop and o['checkpoint']=='P2') or (stop_tool is not None and o['proposal'].get('tool')==stop_tool)
                decision='UNKNOWN' if not gate['allow'] or forced_stop else 'ALLOW'
                return dict(checked=True,decision=decision,stop=decision!='ALLOW',reasons=gate['reasons'])
        return ConstantClassifierDiagnostic()

    def test_native_late_stop_retains_earlier_confirmed_transfer_without_prevention_credit(self):
        _,bm=self.modules()
        with bm.offline():
            trial=bm.native_trial(self.diagnostic(stop_tool='process_payment'),'constant_classifier_late_stop_diagnostic','B')
        self.assertEqual(trial['status'],'stopped')
        self.assertEqual(trial['payments'],1)
        self.assertEqual(trial['invoice_status'],'approved')
        self.assertEqual(trial['stop_effect_phase'],'stopped_after_confirmed_transfer')
        self.assertEqual(trial['stop_checkpoint'],'P1')
        self.assertEqual(trial['stop_tool'],'process_payment')
        self.assertEqual(trial['confirmed_transfers'],1)
        self.assertTrue(trial['confirmed_transfer_before_stop'])
        self.assertLess(trial['first_confirmed_transfer_event_seq'],trial['stop_event_seq'])
        self.assertEqual(trial['payment_statuses'],['completed'])
        self.assertTrue(all(x['checks_before']<len(trial['verdicts']) for x in trial['intercepted_tools']))
        self.assertEqual(trial['intercepted_tools'][-1]['tool'],'process_payment')
        self.assertTrue(any(v['tool']=='finstripe__create_transfer' and v['checkpoint']=='P4' and v['decision']=='ALLOW' for v in trial['verdicts']))

    def test_native_distinct_source_common_snapshot_and_no_post_stop_calls(self):
        ev,bm=self.modules()
        with bm.offline():
            positive=bm.native_trial(self.diagnostic(),'constant_classifier_diagnostic','B')
            stopped=bm.native_trial(self.diagnostic(stop=True),'constant_classifier_stop_diagnostic','B')
            rule=bm.native_trial(ev.Rule('B'),'rule_B','B','rule')
            original=bm.native_trial(ev.Rule('B'),'rule_B_original_producer','B','rule',enriched=False)
        self.assertEqual(positive['status'],'completed');self.assertEqual(positive['payments'],1)
        p2=[o for o in positive['observations'] if o['checkpoint']=='P2'];self.assertEqual(len(p2),3)
        for o,base in zip(positive['observations'],positive['base_observations'],strict=True):
            self.assertEqual(o['context']['call_id'],base['context']['call_id'])
            if o['checkpoint']=='P2':
                self.assertNotEqual(o['context']['call_id'],o['context']['delegation_call_id'])
                self.assertEqual(o['provenance']['delegation_subject_matches'][0]['call_id'],o['context']['delegation_call_id'])
                self.assertTrue(ev.mandatory_proof_gate(o,'B')['allow'])
                # Frozen controls receive exactly the same row as the diagnostic.
                for contract in ('A','B'):
                    r=ev.Rule(contract)({'observation':o});self.assertEqual(r['decision'],'UNKNOWN')
        self.assertEqual(rule['status'],'stopped');self.assertEqual(rule['payments'],0)
        self.assertEqual(original['status'],'completed');self.assertEqual(original['linkage_enrichment'],[])
        self.assertEqual(original['observations'],original['base_observations'])
        self.assertEqual(stopped['status'],'stopped');self.assertEqual(stopped['payments'],0)
        self.assertEqual(stopped['stop_effect_phase'],'stopped_before_transfer')
        self.assertEqual(stopped['confirmed_transfers'],0)
        self.assertIsNone(stopped['first_confirmed_transfer_event_seq'])
        self.assertEqual(stopped['verdicts'][-1]['checkpoint'],'P2')
        self.assertFalse(any(x['tool']=='finstripe__create_transfer' for x in stopped['intercepted_tools']))
        self.assertTrue(all(x['checks_before']<len(stopped['verdicts']) for x in stopped['intercepted_tools']))
        for path in positive['import_provenance'].values():self.assertTrue(Path(path).is_relative_to(bm.ROOT/'finbot/finbot'))

    def test_explicit_registry_retains_no_prefix_legit_payment_without_fake_guard_decision(self):
        ev,_=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.tiny_freeze(root)
            obs=root/'obs.gz';meta=root/'meta.gz';gold=root/'gold.gz';registry=root/'episodes.gz';outcomes=root/'outcomes.gz'
            row=self.fixture()
            ev.write_lines(obs,[dict(prefix_id='own',observation=row)])
            ev.write_lines(meta,[dict(prefix_id='own',episode_id='observed',source='archive',source_intent='legit',split='CAL')])
            ev.write_lines(gold,[dict(prefix_id='own',labels=dict(A='UNKNOWN'))])
            ev.write_lines(registry,[dict(episode_id='observed',split='CAL',source_intent='legit'),
                dict(episode_id='no-prefix',split='CAL',source_intent='legit')])
            ev.write_lines(outcomes,[dict(episode_id='observed',continuation_harm=False,completed_transfer=False,transfer_attempt=False),
                dict(episode_id='no-prefix',continuation_harm=False,completed_transfer=True,transfer_attempt=False)])
            ev.controls(obs,meta,root/'controls',contracts=['A'])
            ev.score([root/'controls'],obs,meta,gold,root/'score',outcomes=outcomes,episodes=registry,model_freeze=freeze,bootstrap=0)
            result=json.loads((root/'score/metrics.json').read_text())
            summary=next(r for r in result['metrics'] if r['slice_dimension']=='all')
            self.assertEqual(summary['actions']['eligible'],1)
            self.assertEqual(summary['actions']['unknown'],1)
            self.assertEqual(summary['reached_actions']['eligible'],1)
            self.assertEqual(summary['episodes']['eligible'],1)
            all_episodes=summary['outcomes_all_registry']
            self.assertEqual(all_episodes['episodes'],2)
            self.assertEqual(all_episodes['completed_transfer'],1)
            self.assertEqual(all_episodes['transfer_attempt'],0)
            self.assertEqual(all_episodes['unassessed_episodes'],1)
            self.assertEqual(all_episodes['episodes_without_observation_prefixes'],1)
            self.assertEqual(all_episodes['unassessed_episode_ids'],['no-prefix'])
            self.assertEqual(all_episodes['observed_guard_unknown_actions'],1)
            self.assertIsNone(all_episodes['legitimate_interruption_all'])
            self.assertEqual(all_episodes['honest_interruption_bounds']['lower'],.5)
            self.assertEqual(all_episodes['honest_interruption_bounds']['upper'],1.)
            self.assertEqual(result['inputs']['episodes_sha256'],ev.digest(registry))
            self.assertEqual(result['inputs']['model_freeze_sha256'],ev.digest(freeze/'freeze-manifest.json'))

    def test_registry_split_retains_selected_no_check_and_no_prefix_episodes(self):
        ev,_=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.tiny_freeze(root)
            obs=root/'obs.gz';meta=root/'meta.gz';gold=root/'gold.gz';registry=root/'episodes.gz'
            definitions=[('observed','CAL','P4'),('no-check','CAL','P0'),('train','TRAIN','P4')]
            ev.write_lines(obs,[dict(prefix_id=pid,observation=dict(checkpoint=stage,event_seq=1,
                proposal=dict(tool='finstripe__create_transfer') if stage=='P4' else {},facts={},provenance={},context={}))
                for pid,split,stage in definitions])
            ev.write_lines(meta,[dict(prefix_id=pid,episode_id=pid,split=split,source='archive',source_intent='legit') for pid,split,stage in definitions])
            ev.write_lines(gold,[dict(prefix_id=pid,labels=dict(payment_v3='UNKNOWN' if stage=='P4' else None)) for pid,split,stage in definitions])
            ev.write_lines(registry,[dict(episode_id=pid,split=split,source_intent='legit') for pid,split in
                [('observed','CAL'),('no-check','CAL'),('no-prefix','CAL'),('train','TRAIN'),('train-no-prefix','TRAIN')]])
            ev.controls(obs,meta,root/'controls',contracts=['payment_v3'])
            ev.score([root/'controls'],obs,meta,gold,root/'score',episodes=registry,model_freeze=freeze,bootstrap=0,split='CAL')
            summary=next(r for r in json.loads((root/'score/metrics.json').read_text())['metrics'] if r['slice_dimension']=='all')
            self.assertEqual(summary['actions']['eligible'],1)
            accounting=summary['outcomes_all_registry']
            self.assertEqual(accounting['episodes'],3)
            self.assertEqual(accounting['episodes_with_observation_prefixes'],2)
            self.assertEqual(accounting['unassessed_episode_ids'],['no-check','no-prefix'])
            self.assertEqual(accounting['legitimate_reached'],1)
            self.assertEqual(accounting['honest_interruption_bounds']['lower'],1/3)
            self.assertEqual(accounting['honest_interruption_bounds']['upper'],1.)

    def test_wrong_registry_or_selected_freeze_rejected_before_gold_io(self):
        ev,_=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.tiny_freeze(root)
            obs=root/'obs.gz';meta=root/'meta.gz';registry=root/'episodes.gz'
            ev.write_lines(obs,[dict(prefix_id='own',observation=self.fixture())])
            ev.write_lines(meta,[dict(prefix_id='own',episode_id='observed',split='CAL',source_intent='legit')])
            ev.predict(freeze,obs,meta,root/'predictions',methods=['old_versioned'])
            for index,entries in enumerate([[dict(episode_id='wrong',split='CAL')],
                    [dict(episode_id='observed',split='TRAIN')],
                    [dict(episode_id='observed',split='CAL')]*2,
                    [dict(episode_id='observed',split='')],
                    [dict(episode_id='observed',split='CAL',source_intent='fraud')]]):
                path=root/f'bad-registry-{index}.gz';ev.write_lines(path,entries)
                with self.assertRaisesRegex(ValueError,'registry'):
                    ev.score([root/'predictions'],obs,meta,root/'missing-gold',root/f'score-{index}',episodes=path,model_freeze=freeze,bootstrap=0,split='CAL')
            ev.write_lines(registry,[dict(episode_id='observed',split='CAL')])
            with self.assertRaisesRegex(ValueError,'registry split'):
                ev.score([root/'predictions'],obs,meta,root/'missing-gold',root/'score-absent-split',episodes=registry,model_freeze=freeze,bootstrap=0,split='ABSENT')
            other=root/'other';other.mkdir();other_freeze,manifest=self.tiny_freeze(other)
            manifest['extra_identity']='wrong freeze';(other_freeze/'freeze-manifest.json').unlink();ev.write_json(other_freeze/'freeze-manifest.json',manifest)
            with self.assertRaisesRegex(ValueError,'freeze'):
                ev.score([root/'predictions'],obs,meta,root/'missing-gold',root/'score-wrong-freeze',model_freeze=other_freeze,bootstrap=0)

    def test_registry_survives_zero_applicable_checks_without_creating_actions(self):
        ev,_=self.modules()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,_=self.tiny_freeze(root)
            obs=root/'obs.gz';meta=root/'meta.gz';gold=root/'gold.gz';registry=root/'episodes.gz'
            ev.write_lines(obs,[dict(prefix_id='own',observation=dict(checkpoint='P0',event_seq=1,proposal={},facts={},provenance={},context={}))])
            ev.write_lines(meta,[dict(prefix_id='own',episode_id='no-check',split='CAL',source_intent='legit')])
            ev.write_lines(gold,[dict(prefix_id='own',labels=dict(payment_v3=None))])
            ev.write_lines(registry,[dict(episode_id=ep,split='CAL',source_intent='legit') for ep in ('no-check','no-prefix')])
            ev.controls(obs,meta,root/'controls',contracts=['payment_v3'])
            ev.score([root/'controls'],obs,meta,gold,root/'score',episodes=registry,model_freeze=freeze,bootstrap=0)
            metrics=json.loads((root/'score/metrics.json').read_text())['metrics']
            self.assertEqual(len(metrics),1)
            summary=metrics[0]
            self.assertEqual(summary['contract'],'payment_v3')
            self.assertEqual(summary['actions']['eligible'],0)
            self.assertEqual(summary['actions']['unknown'],0)
            self.assertEqual(summary['reached_actions']['eligible'],0)
            self.assertEqual(summary['episodes']['eligible'],0)
            self.assertEqual(summary['outcomes_all_registry']['unassessed_episodes'],2)
            self.assertEqual(summary['outcomes_all_registry']['honest_interruption_bounds']['lower'],0.)
            self.assertEqual(summary['outcomes_all_registry']['honest_interruption_bounds']['upper'],1.)

    def test_explicit_v1_freeze_receipts_and_calibration_export_use_actual_source(self):
        ev,_=self.modules()
        import experiment as v1
        from models import fit_model
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);freeze,manifest=self.tiny_freeze(root)
            for method in manifest['methods']:
                model=fit_model('logistic',[self.fixture()],['ALLOW'],[1.],method['feature_mode'],17)
                path=freeze/method['model_file'];path.write_bytes(pickle.dumps(model,protocol=5))
                method['model_sha256']=ev.digest(path);manifest['files'][path.name]=ev.digest(path)
            manifest['version']=1;(freeze/'freeze-manifest.json').unlink();ev.write_json(freeze/'freeze-manifest.json',manifest)
            obs=root/'obs.gz';meta=root/'meta.gz';gold=root/'gold.gz'
            ev.write_lines(obs,[dict(prefix_id='own',observation=self.fixture())])
            ev.write_lines(meta,[dict(prefix_id='own',episode_id='own',split='CAL',source_intent='legit')])
            ev.write_lines(gold,[dict(prefix_id='own',labels=dict(A='UNKNOWN'))])
            v1.predict(freeze,obs,meta,root/'v1-predictions.gz')
            self.assertFalse(ev.verify_predictions(root/'v1-predictions.gz',obs,meta,model_freeze=freeze)['labels_opened'])
            from contextlib import redirect_stdout
            import io
            with redirect_stdout(io.StringIO()):
                ev.score([root/'v1-predictions.gz'],obs,meta,gold,root/'score-v1',model_freeze=freeze,bootstrap=0)
            cal=json.loads((root/'score-v1/frozen-calibration.json').read_text())
            self.assertEqual(cal['freeze_sha256'],ev.digest(freeze/'freeze-manifest.json'))
            self.assertEqual(len(cal['methods']),8)
            import evaluation as v1_evaluation
            receipt=v1_evaluation.predict(freeze,obs,meta,root/'v1-sharded-predictions')
            self.assertEqual(receipt['version'],1)
            self.assertEqual(ev.verify_predictions(root/'v1-sharded-predictions',obs,meta,model_freeze=freeze),receipt)


if __name__=='__main__':unittest.main(verbosity=2)
