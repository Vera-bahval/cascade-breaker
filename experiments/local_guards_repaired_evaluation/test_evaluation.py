"""Decision accounting and replay boundaries, independent of study outcomes."""
import unittest
import tempfile
from pathlib import Path

from . import evaluate


class AccountingTests(unittest.TestCase):
    def test_prediction_fence_allows_write_receipts_without_reading_predictions(self):
        from .run import Output
        from experiments.local_guards_adapter_repair.prepare import preparation_fence
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)/'predictions';directory.mkdir()
            config=dict(id='control',method='constant_ALLOW',variant='rule',profile='A')
            with preparation_fence():
                with Output(directory,'p4',config) as sink:
                    sink.emit(dict(prefix_id='p',mode='common',event_seq=1,checkpoint='P4',sha='x'),{'decision':'ALLOW'})
                receipt=sink.receipt()
            self.assertNotIn('sha256',receipt)
            self.assertEqual(receipt['rows'],1)

    def test_unknown_and_unavailable_are_not_successful_stops(self):
        labels=[dict(action_label=g,author_category='legit',scenario_intent='benign',annotation_status='resolved')
                for g in ('ALLOW','BLOCK','BLOCK','ALLOW','INSUFFICIENT','ALLOW','BLOCK')]
        decisions=['ALLOW','BLOCK','ALLOW','BLOCK','BLOCK','UNKNOWN','ADAPTER_UNAVAILABLE']
        result=evaluate.summarize(labels,decisions)
        self.assertEqual(result['correct'],2)
        self.assertEqual(result['wrong_allow'],1)
        self.assertEqual(result['wrong_block'],1)
        self.assertEqual(result['insufficient_block'],1)
        self.assertEqual(result['unknown'],1)
        self.assertEqual(result['unavailable'],1)
        self.assertEqual(result['n'],7)

    def test_first_stop_excludes_later_decisions_and_distinguishes_unknown(self):
        rows=[dict(event_seq=i,decision=d) for i,d in ((30,'BLOCK'),(10,'UNKNOWN'),(20,'ALLOW'))]
        reached,stop=evaluate.first_stop(rows,stop_unknown=True)
        self.assertEqual([r['event_seq'] for r in reached],[10])
        self.assertEqual(stop['decision'],'UNKNOWN')
        reached,stop=evaluate.first_stop(rows,stop_unknown=False)
        self.assertEqual([r['event_seq'] for r in reached],[10,20,30])

    def test_same_subject_with_changed_input_cannot_reuse_prediction(self):
        prediction=dict(prefix_id='same',mode='common',input_sha256='old')
        with self.assertRaises(ValueError):
            evaluate.check_prediction(prediction,'new','same','common')

    def test_unknown_gold_is_never_counted_as_correct(self):
        label=dict(action_label='INSUFFICIENT',author_category='unknown',scenario_intent='unknown',annotation_status='resolved')
        self.assertEqual(evaluate.summarize([label],['UNKNOWN'])['correct'],0)


if __name__=='__main__':
    unittest.main()
