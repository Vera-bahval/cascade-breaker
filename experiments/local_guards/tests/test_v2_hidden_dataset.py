"""No classifier imports and no hidden observations/labels; synthetic pilot fixtures."""
import copy
import json
import unittest
from decimal import Decimal
from cascade_guard.v2_hidden_dataset import FAMILIES, build_pair, oracle, major, schema_document, forward_backend, execution_contract_violation

PILOT_SEED=991119

def decision(case):
    return case['checkpoints'][-1]

def fixture(family,index=0,stop=False):
    return next(e for e in build_pair(family,index,PILOT_SEED) if oracle(e)['must_stop']==stop)

class HiddenDatasetContractTests(unittest.TestCase):
    def test_every_pilot_pair_balanced_grouped_no_verdict_features(self):
        ids=set(); policies=set()
        for family in FAMILIES:
            for i in range(20):
                pair=build_pair(family,i,PILOT_SEED)
                self.assertEqual(len({e['group_id'] for e in pair}),1)
                self.assertEqual(sorted(oracle(e)['must_stop'] for e in pair),[False,True])
                for e in pair:
                    self.assertNotIn(e['episode_id'],ids); ids.add(e['episode_id'])
                    policies.add(json.dumps(e['policy_contract'],sort_keys=True))
                    body=json.dumps(e['checkpoints']).lower()
                    for forbidden in ('must_stop','harm_if_continue','hidden_commit','verdict','oracle_reasons'):
                        self.assertNotIn(forbidden,body)
        self.assertEqual(len(ids),240)
        self.assertEqual(len(policies),1)

    def test_history_reveals_action_only_at_p4_and_replays(self):
        for family in FAMILIES:
            for e in build_pair(family,0,PILOT_SEED):
                reconstructed={k:None for k in decision(e)['state']}
                previous=''
                for n,cp in enumerate(e['checkpoints'],1):
                    self.assertGreater(cp['observed_at'],previous); previous=cp['observed_at']
                    reconstructed.update(cp['event']['payload'])
                    self.assertEqual(reconstructed,cp['state'])
                    self.assertEqual(cp['proposed_action'] is None,n<4)
                self.assertEqual(e['proposed_action'],decision(e)['proposed_action'])

    def test_currency_normalization_exact(self):
        self.assertEqual(major('12345','USD','minor',{'USD':100}),Decimal('123.45'))
        self.assertEqual(major('12345','JPY','minor',{'JPY':1}),Decimal('12345'))
        e=fixture('dimensional_accounting'); cp=decision(e)
        cp['proposed_action']['arguments']['unit']='minor'
        self.assertTrue(oracle(e)['must_stop'])

    def test_exposure_other_scope_irrelevant_and_exact_boundary(self):
        e=fixture('cumulative_exposure'); cp=decision(e)
        baseline=oracle(e)
        cp['state']['payment_ledger'][0]['tenant_id']='a_different_tenant'
        self.assertEqual(oracle(e),baseline)
        cp['state']['budget']['limit_major']='1'
        self.assertIn('aggregate_limit',oracle(e)['reasons'])

    def test_ambiguous_no_commit_not_guessed_from_timeout(self):
        e=fixture('indeterminate_commit',8,True); cp=decision(e)
        prior=cp['state']['attempts'][0]
        self.assertIn('reconciliation_required',oracle(e)['reasons'])
        prior['reconciliation']={'authority':'payment_backend','outcome':'not_committed','as_of':'2026-09-17T11:00:00Z'}
        self.assertFalse(oracle(e)['must_stop'])
        prior['reconciliation']['as_of']='2026-09-18T11:00:00Z'
        self.assertTrue(oracle(e)['must_stop'])

    def test_version_mutation_follows_actual_validation(self):
        e=fixture('version_drift',0,True)
        before=e['checkpoints'][2]['state']; after=decision(e)['state']
        self.assertEqual(before['invoice']['version'],before['validation']['invoice_version'])
        self.assertGreater(after['invoice']['updated_at'],before['validation']['validated_at'])
        self.assertNotEqual(after['invoice']['version'],after['validation']['invoice_version'])

    def test_genuine_registry_subject_binding_is_required(self):
        e=fixture('scope_bound_evidence'); cp=decision(e)
        self.assertTrue(cp['state']['registry'][0]['signature_verified'])
        cp['state']['registry'][0]['tenant_id']='different_tenant'
        self.assertIn('clearance_binding',oracle(e)['reasons'])

    def test_residual_ledger_math_not_original_invoice_match(self):
        e=fixture('partial_settlement'); cp=decision(e); s=cp['state']
        due=Decimal(s['invoice']['amount'])-sum(Decimal(r['amount']) for r in s['payment_ledger'] if r['status']=='posted' and r['kind']=='settlement')
        self.assertEqual(Decimal(cp['proposed_action']['arguments']['amount']),due)
        cp['proposed_action']['arguments']['amount']=s['invoice']['amount']
        self.assertIn('normalized_outstanding_obligation',oracle(e)['reasons'])

    def test_backend_effect_and_intervention_are_separate_targets(self):
        e=fixture('version_drift',0,True)
        self.assertTrue(oracle(e)['must_stop'])
        self.assertEqual(forward_backend(e)['money_effect_count'],0)
        self.assertFalse(forward_backend(e)['harmful_effect_if_executed'])
        e=fixture('indeterminate_commit',0,False)
        self.assertIsNone(forward_backend(e)['money_effect_count'])
        self.assertIsNone(forward_backend(e)['harmful_effect_if_executed'])
        e=fixture('dimensional_accounting',0,True)
        self.assertEqual(forward_backend(e)['money_effect_count'],1)
        self.assertTrue(forward_backend(e)['harmful_effect_if_executed'])

    def test_independent_effect_contract_checker_matches_primary_on_pilot(self):
        for family in FAMILIES:
            for i in range(20):
                for e in build_pair(family,i,PILOT_SEED):
                    self.assertEqual(execution_contract_violation(e),oracle(e)['must_stop'])

    def test_contract_is_all_six_and_metadata_is_not_input(self):
        e=fixture('partial_settlement'); p=e['policy_contract']
        self.assertNotIn('rule',p['extension'])
        e['family']='arbitrary_metadata'; e['group_id']='arbitrary_metadata'
        self.assertFalse(oracle(e)['must_stop'])
        self.assertIn('family',schema_document()['metadata_only'])

if __name__=='__main__': unittest.main()
