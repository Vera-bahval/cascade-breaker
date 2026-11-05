"""Own tiny fixtures only: no archive, synthetic dev or closed test reads."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))

class EvaluationTests(unittest.TestCase):
    def module(self):
        self.assertTrue((HERE/'evaluation.py').exists(), 'evaluation driver is not implemented')
        import evaluation
        return evaluation

    def test_replay_denominators_and_no_later_credit(self):
        ev=self.module()
        rows=[dict(prefix_id='a',decision='UNKNOWN',gold='BLOCK',event_seq=1,episode_id='e',cluster='g'),
              dict(prefix_id='b',decision='BLOCK',gold='BLOCK',event_seq=2,episode_id='e',cluster='g'),
              dict(prefix_id='c',decision='ALLOW',gold='UNKNOWN',event_seq=1,episode_id='f',cluster='h'),
              dict(prefix_id='d',decision='BLOCK',gold='ALLOW',event_seq=1,episode_id='s',cluster='i')]
        result=ev.summarize(rows,bootstrap=20)
        self.assertEqual(result['actions']['eligible'],4)
        self.assertEqual(result['reached_actions']['eligible'],3)
        self.assertEqual(result['reached_actions']['correct_decisive'],0)
        self.assertEqual(result['actions']['known_block_stopped_unknown'],1)
        self.assertEqual(result['actions']['false_allow_unknown'],1)
        self.assertEqual(result['episodes']['safe_stops'],1)
        self.assertEqual(result['episodes']['safe_stop_fpr'],1)
        self.assertEqual(result['intervals']['replicates'],20)

    def test_null_safe_denominator_and_gate_attribution(self):
        ev=self.module()
        rows=[dict(prefix_id='a',decision='UNKNOWN',raw_decision='ALLOW',gate_changed=True,gold='UNKNOWN',event_seq=1,episode_id='e',cluster='g')]
        result=ev.summarize(rows,bootstrap=0)
        self.assertIsNone(result['episodes']['safe_stop_fpr'])
        self.assertEqual(result['actions']['gate_changed'],1)
        self.assertEqual(result['actions']['gate_avoided_false_allow'],1)
        self.assertEqual(result['actions']['false_safe_stop_unknown'],0)

    def test_outcome_timing_and_missing_outcomes(self):
        ev=self.module()
        rows=[dict(prefix_id='a',decision='UNKNOWN',gold='BLOCK',event_seq=5,episode_id='e',cluster='g'),
              dict(prefix_id='b',decision='BLOCK',gold='BLOCK',event_seq=1,episode_id='f',cluster='h')]
        outcomes={'e':dict(continuation_harm=True,first_harm_event_seq=5,transfer_attempt=True,completed_transfer=True,first_attempt_event_seq=4)}
        result=ev.summarize(rows,outcomes=outcomes,bootstrap=0)
        self.assertEqual(result['outcomes']['known'],1)
        self.assertEqual(result['outcomes']['unknown'],1)
        self.assertEqual(result['outcomes']['harm_prevented'],0)
        self.assertEqual(result['outcomes']['attempt_prevented'],0)
        self.assertEqual(result['outcomes']['actual_harm'],1)

    def test_synthetic_variants_remain_individual_episodes(self):
        ev=self.module()
        m={'episode_id':'group-episode','group_id':'base','split_group_id':'collision','source':'synthetic'}
        a=ev.join_record({'prefix_id':'a','decision':'ALLOW','contract':'A','checked':True},m,{'observation':{'checkpoint':'P0','event_seq':1}},'ALLOW')
        b=ev.join_record({'prefix_id':'b','decision':'ALLOW','contract':'A','checked':True},m,{'observation':{'checkpoint':'P0','event_seq':1}},'ALLOW')
        self.assertNotEqual(a['episode_id'],b['episode_id'])
        self.assertEqual(a['cluster'],b['cluster'])

    def test_shards_deterministic_and_receipt_tamper(self):
        ev=self.module()
        with tempfile.TemporaryDirectory() as td:
            paths=[]
            for name in ('one','two'):
                out=Path(td)/name
                with ev.Shards(out,max_rows=2) as sink:
                    for i in range(5):sink.write('A','rule_A',dict(prefix_id=str(i),decision='ALLOW'))
                paths.append(sink.files)
            self.assertEqual([x['sha256'] for x in paths[0]],[x['sha256'] for x in paths[1]])
            self.assertEqual([x['rows'] for x in paths[0]],[2,2,1])

    def test_checkpoint_slice_cannot_reach_after_other_checkpoint_stop(self):
        ev=self.module()
        rows=[dict(prefix_id='a',decision='UNKNOWN',gold='ALLOW',event_seq=1,episode_id='e',cluster='g',checkpoint='P0'),
              dict(prefix_id='b',decision='BLOCK',gold='BLOCK',event_seq=2,episode_id='e',cluster='g',checkpoint='P4')]
        marked=ev.mark_reachability(rows)
        result=ev.summarize([marked[1]],bootstrap=0)
        self.assertEqual(result['actions']['correct_decisive'],1)
        self.assertEqual(result['reached_actions']['eligible'],0)
        self.assertEqual(result['episodes']['correct_decisive'],0)
        self.assertEqual(result['episodes']['safe'],0)

    def test_registry_outcomes_keep_unreached_episodes_in_all_denominator(self):
        ev=self.module()
        metadata={'a':dict(episode_id='has-p4',source_intent='legit'),
                  'b':dict(episode_id='no-p4',source_intent='legit')}
        rows=[dict(prefix_id='a',decision='UNKNOWN',gold='ALLOW',event_seq=1,episode_id='has-p4',original_episode_id='has-p4',cluster='g')]
        c=ev.registry_outcomes(rows,metadata,{})
        self.assertEqual(c['legitimate_all'],2)
        self.assertEqual(c['legitimate_reached'],1)
        self.assertEqual(c['legitimate_interruption_all'],.5)
        self.assertEqual(c['legitimate_interruption_reached'],1.)

    def test_score_split_registry_preserves_only_selected_split_including_no_check(self):
        ev=self.module()
        import json
        with tempfile.TemporaryDirectory() as td:
            td=Path(td);obs=td/'observations.gz';meta=td/'metadata.gz';labels=td/'labels.gz';outcomes=td/'outcomes.gz'
            definitions=[('cal-payment','CAL','P4'),('cal-no-payment','CAL','P0'),('train-payment','TRAIN','P4')]
            ev.write_lines(obs,[dict(prefix_id=pid,observation=dict(checkpoint=checkpoint,event_seq=1,
                proposal={'tool':'finstripe__create_transfer'} if checkpoint=='P4' else {},facts={},provenance={},context={}))
                for pid,split,checkpoint in definitions])
            ev.write_lines(meta,[dict(prefix_id=pid,episode_id=pid,group_id=pid,source='archive',source_intent='legit',split=split)
                for pid,split,checkpoint in definitions])
            ev.write_lines(labels,[dict(prefix_id=pid,labels={'payment_v3':'UNKNOWN' if checkpoint=='P4' else None})
                for pid,split,checkpoint in definitions])
            ev.write_lines(outcomes,[dict(episode_id=pid,continuation_harm=True,first_harm_event_seq=10)
                for pid,split,checkpoint in definitions])
            ev.controls(obs,meta,td/'controls',contracts=['payment_v3'])
            ev.score([td/'controls'],obs,meta,labels,td/'scored',outcomes=outcomes,bootstrap=0,split='CAL')
            result=json.loads((td/'scored/metrics.json').read_text())
            summary=next(r for r in result['metrics'] if r['slice_dimension']=='all')
            self.assertEqual(summary['episodes']['eligible'],1)
            c=summary['outcomes_all_registry']
            self.assertEqual(c['episodes'],2)
            self.assertEqual(c['legitimate_all'],2)
            self.assertEqual(c['legitimate_reached'],1)
            self.assertEqual(c['legitimate_interruption_all'],.5)
            self.assertEqual(c['legitimate_interruption_reached'],1.)
            self.assertEqual(c['known'],2)
            self.assertEqual(c['actual_harm'],2)
            self.assertEqual(c['harm_prevented'],1)
            self.assertEqual(c['harm_prevention_rate'],.5)

    def test_argmax_diagnostic_preserves_tie_abstention_and_gate_separation(self):
        ev=self.module()
        p=dict(prefix_id='own',method='A__new__mixed__logistic__17__raw',decision='UNKNOWN',raw_decision='UNKNOWN',gold='ALLOW',gate_changed=True,probabilities={'ALLOW':.7,'BLOCK':.2,'UNKNOWN':.1})
        r=ev.argmax_diagnostic(p)
        self.assertEqual(r['decision'],'ALLOW');self.assertFalse(r['gate_changed']);self.assertEqual(r['variant'],'argmax_diagnostic')
        p['probabilities']={'ALLOW':.5,'BLOCK':.5,'UNKNOWN':0.}
        self.assertEqual(ev.argmax_diagnostic(p)['decision'],'UNKNOWN')

    def test_quantile_is_nearest_rank_even_n(self):
        ev=self.module()
        self.assertEqual(ev.stats([1,2,3,4])['p50_ms'],2)
        self.assertEqual(ev.stats([1,2,3,4])['p95_ms'],4)

    def test_receipt_count_cannot_hide_duplicate_or_missing_prefix(self):
        ev=self.module()
        import json
        with tempfile.TemporaryDirectory() as td:
            obs=Path(td)/'observations.gz';meta=Path(td)/'metadata.gz';out=Path(td)/'controls'
            base={'observation':{'checkpoint':'P0','event_seq':1,'proposal':{},'facts':{},'provenance':{},'context':{}}}
            ev.write_lines(obs,[dict(base,prefix_id=p) for p in ('a','b')])
            ev.write_lines(meta,[dict(prefix_id=p,episode_id=p,group_id=p,source='synthetic') for p in ('a','b')])
            ev.controls(obs,meta,out,contracts=['A'])
            receipt=json.loads((out/'receipt.json').read_text());entry=receipt['files'][0];shard=out/entry['path']
            rows=list(ev.read_lines(shard));rows[1]['prefix_id']='a';shard.unlink();ev.write_lines(shard,rows)
            entry['sha256']=ev.digest(shard);(out/'receipt.json').write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,'duplicate|coverage'):ev.verify_predictions(out,obs,meta)

    def test_label_read_follows_complete_receipt_validation(self):
        ev=self.module()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'controls'
            obs=Path(td)/'observations.jsonl.gz';meta=Path(td)/'metadata.jsonl.gz'
            row={'prefix_id':'own','observation':{'checkpoint':'P0','event_seq':1,'proposal':{},'facts':{},'provenance':{},'context':{}}}
            ev.write_lines(obs,[row]);ev.write_lines(meta,[dict(prefix_id='own',episode_id='e',group_id='g',source='synthetic')])
            ev.controls(obs,meta,out,contracts=['A'])
            receipt=ev.verify_predictions(out,obs,meta)
            self.assertFalse(receipt['labels_opened'])
            labels=Path(td)/'own-labels.jsonl.gz'
            ev.write_lines(labels,[dict(prefix_id='own',labels={'A':'UNKNOWN'})])
            ev.score([out],obs,meta,labels,Path(td)/'scored',bootstrap=10)
            self.assertTrue((Path(td)/'scored/metrics.csv').exists())
            self.assertTrue((Path(td)/'scored/frozen-calibration.json').exists())
            shard=out/receipt['files'][0]['path'];shard.write_bytes(b'tamper')
            with self.assertRaisesRegex(ValueError,'hash'):ev.verify_predictions(out,obs,meta)

if __name__=='__main__':unittest.main()
