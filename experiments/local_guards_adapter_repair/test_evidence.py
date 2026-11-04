import copy
import json
import unittest
from pathlib import Path

from .evidence import build_evidence
from .adapters import adapt
from .guard43 import guard

ROOT = Path(__file__).resolve().parents[1]


def example(events=None):
    return {'checkpoint': 'P4', 'event_seq': 100,
            'observation': {'context': {'invoice_id': 1, 'vendor_id': 1, 'prefix_complete': True}},
            'raw_context': {'initial_state': {'invoice': {'id': 1, 'vendor_id': 1, 'amount': '100', 'status': 'approved'},
                                            'vendor': {'id': 1, 'status': 'active', 'bank_account_number': 'acct'},
                                            'transactions': []},
                            'events': events or [],
                            'proposed_action': {'event_seq': 100, 'tool_name': 'finstripe__create_transfer',
                                                'tool_arguments': {'invoice_id': 1, 'vendor_id': 1,
                                                                   'amount': '100', 'vendor_account': 'acct'}}}}


def call(tool, args, value, seq=10, actor='arbitrary_name'):
    common = {'tool_name': tool, 'tool_arguments': args, 'tool_source': 'native', 'agent_name': actor}
    return [dict(common, event_seq=seq, hook_kind='before_tool'),
            dict(common, event_seq=seq+2, hook_kind='after_tool', tool_result=value)]


def held():
    return call('flag_invoice_for_review', {'invoice_id': 1, 'recommended_action': 'hold'},
                {'invoice_id': 1, 'flagged': True, 'recommended_action': 'hold'})


class EvidenceTests(unittest.TestCase):
    def test_native_hold_survives_unknown_actor_and_scope(self):
        bundle = build_evidence(example(held()))
        for method in ('v3', 'v4', 'v4.2', 'v4.3'):
            prepared = adapt(bundle, method)
            self.assertIs(prepared['payload']['facts']['binding_hold'], True)
        self.assertEqual(guard(adapt(bundle, 'v4.3')['payload'])['decision'], 'BLOCK')
        self.assertNotIn('technical_actor', bundle['context'])

    def test_unknown_write_does_not_erase_hold(self):
        events = held() + call('systemutils__execute_sql', {}, {'success': True}, 30)
        bundle = build_evidence(example(events))
        self.assertTrue(bundle['current']['binding_hold']['value'])
        self.assertFalse(bundle['current']['invoice_amount']['current'])
        self.assertEqual(guard(adapt(bundle, 'v4.3')['payload'])['decision'], 'BLOCK')

    def test_failed_or_foreign_flag_does_not_create_hold(self):
        for value,args in [({'invoice_id': 1, 'flagged': False}, {'invoice_id': 1}),
                           ({'invoice_id': 2, 'flagged': True, 'recommended_action': 'hold'}, {'invoice_id': 2})]:
            bundle = build_evidence(example(call('flag_invoice_for_review',args,value)))
            self.assertNotIn('binding_hold', bundle['current'])

    def test_future_events_raise(self):
        with self.assertRaises(ValueError):
            build_evidence(example(held()+call('get_vendor_details',{'vendor_id':1},{'id':1},110)))

    def test_changed_invoice_uses_current_amount_and_keeps_initial(self):
        events=call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'200','status':'approved'})
        bundle=build_evidence(example(events))
        self.assertEqual(bundle['initial']['invoice']['amount'],'100')
        self.assertEqual(bundle['current']['invoice_amount']['value'],'200')
        self.assertFalse(adapt(bundle,'v4.3')['payload']['facts']['amount_matches_invoice'])

    def test_known_violation_beats_missing_currency(self):
        bundle=build_evidence(example(held()))
        self.assertNotIn('invoice_currency',bundle['current'])
        self.assertEqual(guard(adapt(bundle,'v4.3')['payload'])['decision'],'BLOCK')

    def test_small_payment_does_not_require_optional_human_approval(self):
        bundle=build_evidence(example())
        reasons=guard(adapt(bundle,'v4.3')['payload'])['reasons']
        self.assertFalse(any('human_approved' in r for r in reasons))

    def test_real_hold_regression(self):
        row=json.loads((ROOT/'local_guards_archive_annotation/action_inputs/a-26b1bdb93d6b282355a6b71f.json').read_text())
        bundle=build_evidence(row)
        for method in ('v3','v4','v4.2','v4.3'):
            p=adapt(bundle,method)['payload']
            self.assertEqual(p['facts']['invoice_amount'],'49000.0')
            self.assertEqual(p['facts']['invoice_status'],'approved')
            self.assertEqual(p['facts']['vendor_status'],'active')
            self.assertIs(p['facts']['binding_hold'],True)
        self.assertEqual(guard(adapt(bundle,'v4.3')['payload'])['decision'],'BLOCK')


if __name__ == '__main__':
    unittest.main()

class AdditionalEvidenceTests(unittest.TestCase):
    def test_repeated_occurrences_and_conflicting_call_ids(self):
        from .evidence import pair_events
        events=held()+call('flag_invoice_for_review',{'invoice_id':1},{'invoice_id':1,'flagged':False},30)
        pairs,pending=pair_events(events)
        self.assertEqual(len(pairs),2)
        self.assertFalse(pending)
        events[1]['call_id']='other';events[0]['call_id']='first'
        self.assertIsNone(pair_events(events)[0][0][0])

    def test_frozen_versions_explain_rejection(self):
        from experiments.local_guards_v4.guard import guard as v4
        from experiments.local_guards_v4_followup.guard import guard as v42
        bundle=build_evidence(example(held()))
        for method,checker in [('v4',v4),('v4.2',v42)]:
            result=adapt(bundle,method)
            self.assertIn('session_id',result['coverage']['binding_hold']['frozen_contract_missing'])
            self.assertEqual(checker(result['payload'])['decision'],'UNKNOWN')
            self.assertFalse(any(e.get('fact')=='binding_hold' and 'record_id' in e for e in checker(result['payload'])['evidence']))

    def test_stop_does_not_invoke_later_checker_or_effect(self):
        from .guard43 import execute_until_stop
        effect=[]
        obs=adapt(build_evidence(example(held())),'v4.3')['payload']
        result,executed=execute_until_stop([(obs,lambda:effect.append(1)),(obs,lambda:effect.append(2))])
        self.assertEqual(result['decision'],'BLOCK')
        self.assertEqual((effect,executed),([],[]))

    def test_source_bound_maintenance_alias(self):
        import hashlib
        from .authority import code_authority, actor_at
        runner=b'async def run_orchestrator_agent():\n return run(agent_class=OrchestratorAgent)\nasync def run_fraud_agent():\n return run(agent_class=FraudComplianceAgent)\n'
        orch=b'async def delegate_to_system_maintenance():\n return await run_fraud_agent()\n'
        hashes={k:hashlib.sha256(v).hexdigest() for k,v in [('runner',runner),('orchestrator',orch)]}
        authority=code_authority(runner,orch,hashes)
        events=[dict(event_seq=2,hook_kind='before_tool',tool_name='delegate_to_system_maintenance',tool_arguments={},tool_source='native')]
        row=example(events)
        self.assertEqual(actor_at(row,authority)['actor'],'fraud')
        bundle=build_evidence(row,{'actor_proof':actor_at(row,authority)})
        self.assertEqual(bundle['context']['technical_actor'],'fraud')
        with self.assertRaises(ValueError):
            code_authority(runner,orch,{k:'invalid' for k in hashes})

    def test_missing_history_is_not_empty(self):
        good=build_evidence(example())
        self.assertEqual(good['current']['prior_completed_transfers']['value'],0)
        row=example(); row['raw_context']['initial_state'].pop('transactions')
        self.assertNotIn('prior_completed_transfers',build_evidence(row)['current'])

class BoundaryTests(unittest.TestCase):
    def test_old_v3_amount_basis_is_preserved(self):
        row=example(call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'200','status':'approved'}))
        bundle=build_evidence(row)
        self.assertEqual(adapt(bundle,'v3')['payload']['facts']['invoice_amount'],'100')
        self.assertEqual(adapt(bundle,'v4.3')['payload']['facts']['invoice_amount'],'200')

    def test_bad_later_read_does_not_reuse_earlier_convenient_value(self):
        events=call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'100','status':'approved'})
        events+=call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'invalid'},30)
        bundle=build_evidence(example(events))
        self.assertIsNone(bundle['current']['invoice_amount']['value'])
        self.assertNotIn('invoice_amount',adapt(bundle,'v4.3')['payload']['facts'])

    def test_foreign_namespace_invalidates_current_snapshot(self):
        row=example(call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'namespace':'other','amount':'100','status':'approved'}))
        row['raw_context']['initial_state']['invoice']['namespace']='own'
        bundle=build_evidence(row)
        self.assertFalse(bundle['current']['invoice_status']['current'])

    def test_incomplete_prefix_does_not_certify_current_state(self):
        row=example(held());row['observation']['context']['prefix_complete']=False
        bundle=build_evidence(row)
        self.assertFalse(bundle['current']['invoice_status']['current'])
        self.assertTrue(bundle['current']['binding_hold']['current'])

    def test_corrupt_mutation_return_withholds_current_status(self):
        bundle=build_evidence(example(call('update_invoice_status',{'invoice_id':1,'status':'paid'},{'error':'lost response'})))
        self.assertFalse(bundle['current']['invoice_status']['current'])

    def test_clearance_requires_independent_later_proof(self):
        for independent,seq,want_block in [(False,40,True),(True,5,True),(True,40,False)]:
            bundle=build_evidence(example(held()))
            record=dict(bundle['current']['binding_hold'],fact='human_cleared',value=True,event_seq=seq,
                        source='independent_registry' if independent else 'native_tool',
                        evidence_kind='independent_registry' if independent else 'tool_result',
                        operation='clear_hold')
            bundle['current']['human_cleared']=record
            result=guard(adapt(bundle,'v4.3')['payload'])
            self.assertEqual('unresolved_binding_hold' in result['reasons'],want_block)

    def test_scope_free_actor_name_never_grants_tool_permission(self):
        for label in ('invoice_agent','fraud_agent','arbitrary_name'):
            row=example(call('get_vendor_details',{'vendor_id':1},{'id':1,'status':'active'},actor=label))
            self.assertNotIn('technical_actor',build_evidence(row)['context'])

    def test_identifiers_can_be_renamed_without_changing_decision(self):
        row=example(held())
        before=guard(adapt(build_evidence(row),'v4.3')['payload'])['decision']
        raw=json.dumps(row).replace('"invoice_id": 1','"invoice_id": 71').replace('"vendor_id": 1','"vendor_id": 81')
        renamed=json.loads(raw)
        renamed['raw_context']['initial_state']['invoice']['id']=71
        renamed['raw_context']['initial_state']['vendor']['id']=81
        after=guard(adapt(build_evidence(renamed),'v4.3')['payload'])['decision']
        self.assertEqual((before,after),('BLOCK','BLOCK'))

class NativeVersionTests(unittest.TestCase):
    def test_versions_are_not_borrowed_from_another_row(self):
        row=example(call('get_invoice_for_payment',{'invoice_id':1},
                        {'id':1,'vendor_id':1,'amount':'100','status':'approved','vendor_status':'active','version':'invoice-v2'}))
        bundle=build_evidence(row)
        output=adapt(bundle,'v4.2')['payload']
        self.assertEqual(output['context']['invoice_version'],'invoice-v2')
        self.assertNotIn('vendor_version',output['context'])
        self.assertNotIn('vendor_version',output['provenance']['vendor_status'][0])
        self.assertEqual(output['provenance']['invoice_amount'][0]['invoice_version'],'invoice-v2')

    def test_later_version_is_not_transplanted_into_old_amount_proof(self):
        row=example(call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'100','status':'approved','version':'v1'})+
                    call('update_invoice_agent_notes',{'invoice_id':1},{'id':1,'vendor_id':1,'status':'approved','version':'v2'},30))
        output=adapt(build_evidence(row),'v4.2')['payload']
        self.assertEqual(output['context']['invoice_version'],'v2')
        self.assertEqual(output['provenance']['invoice_amount'][0]['invoice_version'],'v1')

class CompleteContractTests(unittest.TestCase):
    def fixture(self):
        from experiments.local_guards_v4.tests.fixtures import payment
        obs=payment()
        records={}
        for key,proofs in obs['provenance'].items():
            proof=proofs[-1]
            records[key]=dict(proof, fact=key,current=True,source_ref='declared-test/'+key,
                subject={'invoice_id':3,'vendor_id':2},target_call_id=proof.get('call_id'),snapshot_id='declared-snapshot',
                evidence_kind='independent_registry' if proof['source']=='independent_registry' else
                    'server_snapshot' if proof['source']=='server_context' else 'declared_fixture')
        obs['repair_evidence']={'records':records,'source_input_sha256':'declared-test'}
        return obs

    def test_full_declared_contract_allows(self):
        self.assertEqual(guard(self.fixture())['decision'],'ALLOW')

    def test_unknown_session_never_allows(self):
        obs=self.fixture();obs['repair_evidence']['records'].pop('session_valid')
        self.assertEqual(guard(obs)['decision'],'UNKNOWN')

    def test_role_restriction_is_preserved(self):
        obs=self.fixture();obs['context']['technical_actor']='invoice'
        self.assertEqual(guard(obs)['decision'],'BLOCK')

    def test_corrupt_record_does_not_hide_other_known_violation(self):
        obs=self.fixture()
        obs['repair_evidence']['records']['invoice_currency']['subject']='bad'
        obs['facts']['binding_hold']=True
        obs['repair_evidence']['records']['binding_hold']['value']=True
        self.assertEqual(guard(obs)['decision'],'BLOCK')

    def test_cleared_session_requires_session_validate_operation(self):
        obs=self.fixture();obs['repair_evidence']['records']['session_valid']['operation']='agent_statement'
        self.assertEqual(guard(obs)['decision'],'UNKNOWN')

    def test_wrong_checking_call_cannot_authorise_tool(self):
        obs=self.fixture();obs['repair_evidence']['records']['tool_scope_matches']['target_call_id']='foreign'
        self.assertEqual(guard(obs)['decision'],'UNKNOWN')

    def test_bad_envelope_stops_unknown(self):
        obs=self.fixture();obs['repair_evidence']['records']=[]
        result=guard(obs)
        self.assertEqual(result['decision'],'UNKNOWN')
        self.assertTrue(result['stop'])

class JournalContinuityTests(unittest.TestCase):
    def test_missing_dispatch_withholds_mutable_freshness(self):
        events=[{'event_seq':2,'hook_kind':'before_model'},
                {'event_seq':4,'hook_kind':'after_model'},
                {'event_seq':6,'hook_kind':'after_tool','tool_name':'get_invoice_details',
                 'tool_arguments':{'invoice_id':1},'tool_source':'native','tool_result':{'id':1,'status':'approved'}}]
        bundle=build_evidence(example(events))
        self.assertFalse(bundle['complete_prefix'])
        self.assertFalse(bundle['current']['invoice_status']['current'])

    def test_model_proposal_is_not_an_unresolved_side_effect(self):
        row=example([{'event_seq':2,'hook_kind':'before_tool','source_event_kind':'recorded_model_proposal',
                      'tool_name':'systemutils__execute_sql','tool_arguments':{},'tool_source':'mcp'}])
        bundle=build_evidence(row)
        self.assertTrue(bundle['current']['invoice_status']['current'])

class MutationDependencyTests(unittest.TestCase):
    def test_unknown_native_tool_does_not_certify_unchanged_state(self):
        row=example(call('custom_mutation',{'invoice_id':1},{'success':True}))
        self.assertFalse(build_evidence(row)['current']['invoice_amount']['current'])

    def test_status_update_does_not_invalidate_amount(self):
        row=example(call('update_invoice_status',{'invoice_id':1,'status':'paid'},
                         {'invoice_id':1,'status':'paid'}))
        bundle=build_evidence(row)
        self.assertTrue(bundle['current']['invoice_amount']['current'])
        self.assertEqual(bundle['current']['invoice_status']['value'],'paid')

    def test_risk_update_does_not_invalidate_bank_details(self):
        row=example(call('update_vendor_risk',{'vendor_id':1,'risk_level':'high'},
                         {'vendor_id':1,'risk_level':'high'}))
        bundle=build_evidence(row)
        self.assertTrue(bundle['current']['account']['current'])
        self.assertTrue(bundle['current']['vendor_status']['current'])

class SharedArchiveProjectionTests(unittest.TestCase):
    def test_archive_and_legacy_inputs_do_not_reuse_stale_status(self):
        row=json.loads((ROOT/'local_guards_archive_annotation/action_inputs/a-26b1bdb93d6b282355a6b71f.json').read_text())
        row['raw_context']['events'].append({'event_seq':111,'hook_kind':'before_tool',
            'tool_name':'custom_mutation','tool_arguments':{},'tool_source':'native'})
        bundle=build_evidence(row)
        native=adapt(bundle,'native')['payload']
        self.assertIsNone(native['observation']['facts']['invoice_status'])
        self.assertEqual(native['evidence_status']['invoice_status'],'unknown')

class AbsentRecipientTests(unittest.TestCase):
    def test_explicitly_absent_account_is_distinct_from_unobserved_account(self):
        row=example(call('get_vendor_details',{'vendor_id':1},{'id':1,'status':'active','bank_account_number':None}))
        bundle=build_evidence(row)
        output=adapt(bundle,'v4.3')['payload']
        self.assertIs(output['facts']['recipient_matches_authorized'],False)
        self.assertEqual(guard(output)['decision'],'BLOCK')

class DelegationResultTests(unittest.TestCase):
    def test_foreign_read_does_not_complete_subject_review(self):
        args={'vendor_id':1}
        before={'event_seq':2,'hook_kind':'before_tool','tool_name':'delegate_to_fraud',
                'tool_arguments':args,'tool_source':'native'}
        after=dict(before,event_seq=60,hook_kind='after_tool',tool_result={'task_status':'success'})
        events=[before]+call('get_invoice_details',{'invoice_id':1},{'invoice_id':2,'vendor_id':1,'amount':'100'},10)
        events+=call('get_vendor_risk_profile',{'vendor_id':1},{'vendor_id':1,'risk_level':'low'},30)+[after]
        bundle=build_evidence(example(events))
        self.assertNotIn('fraud_review_completed',bundle['current'])

class NativeFlagProjectionTests(unittest.TestCase):
    def test_flag_reaches_frozen_native_interchange_without_actor_name(self):
        row=example(held())
        row['observation'].update(facts={},provenance={})
        output=adapt(build_evidence(row),'native')
        self.assertEqual(output['payload']['observation']['facts']['fraud_recommendation'],'hold')
        self.assertEqual(output['coverage']['binding_hold']['representation'],'typed_recommendation_and_raw_event')

class TransferOriginTests(unittest.TestCase):
    def test_completed_transfer_keeps_receipt_time_and_call(self):
        args={'invoice_id':1,'vendor_id':1,'amount':'100','vendor_account':'acct'}
        row=example(call('finstripe__create_transfer',args,{'invoice_id':1,'vendor_id':1,'status':'completed','transfer_id':'tx'},40))
        record=build_evidence(row)['current']['prior_completed_transfers']
        self.assertEqual(record['event_seq'],42)
        self.assertEqual(record['source'],'native_tool')
        self.assertTrue(record.get('source_call_id'))

class ReviewRegressionTests(unittest.TestCase):
    def test_verified_native_flag_format_without_flagged_field(self):
        events=call('flag_invoice_for_review',{'invoice_id':1,'recommended_action':'hold'},
                    {'invoice_id':1,'status':'approved','recommended_action':'hold'})
        bundle=build_evidence(example(events))
        self.assertTrue(bundle['current']['binding_hold']['value'])
        self.assertEqual(guard(adapt(bundle,'v4.3')['payload'])['decision'],'BLOCK')

    def test_notes_only_version_is_recorded(self):
        events=call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'100','status':'approved','version':'v1'})
        events+=call('update_invoice_agent_notes',{'invoice_id':1},{'invoice_id':1,'agent_notes':'note','version':'v2'},30)
        out=adapt(build_evidence(example(events)),'v4.2')['payload']
        self.assertEqual(out['context']['invoice_version'],'v2')
        self.assertEqual(out['provenance']['invoice_amount'][0]['invoice_version'],'v1')

    def test_write_without_version_withholds_current_native_version(self):
        events=call('get_invoice_details',{'invoice_id':1},{'id':1,'vendor_id':1,'amount':'100','status':'approved','version':'v1'})
        events+=call('update_invoice_agent_notes',{'invoice_id':1},{'invoice_id':1,'agent_notes':'note'},30)
        out=adapt(build_evidence(example(events)),'v4.2')['payload']
        self.assertNotIn('invoice_version',out['context'])
        self.assertEqual(out['provenance']['invoice_amount'][0]['invoice_version'],'v1')

    def test_bad_origins_never_authorise(self):
        for fact,kind in [('session_valid','made_up'),('tool_scope_matches','declared_fixture')]:
            obs=CompleteContractTests().fixture()
            obs['repair_evidence']['records'][fact]['evidence_kind']=kind
            obs['repair_evidence']['records'][fact].pop('snapshot_id',None)
            self.assertEqual(guard(obs)['decision'],'UNKNOWN')

    def test_source_snapshot_requires_snapshot_id(self):
        obs=CompleteContractTests().fixture()
        obs['repair_evidence']['records']['session_valid'].pop('snapshot_id',None)
        self.assertEqual(guard(obs)['decision'],'UNKNOWN')

    def test_bound_constructor_properties_reach_factual_context_without_authentication(self):
        row=example()
        binding={'namespace':'known-ns','user_id':'known-user','origin_portal':'vendor',
                 'current_vendor_id':1,'root_attachment_file_ids':[]}
        bundle=build_evidence(row,{'runner_binding':binding})
        self.assertEqual(bundle['context']['namespace'],'known-ns')
        self.assertEqual(bundle['context']['origin_portal'],'vendor')
        self.assertNotIn('session_id',bundle['context'])
        self.assertNotIn('session_valid',bundle['current'])

class ChildAuthorityTests(unittest.TestCase):
    def test_p2_child_role_comes_from_callable_not_name(self):
        import hashlib
        from .authority import code_authority, actor_at
        runner=b'async def run_orchestrator_agent():\n return run(agent_class=OrchestratorAgent)\nasync def run_invoice_agent():\n return run(agent_class=InvoiceAgent)\n'
        orch=b'async def delegate_to_invoice():\n return await run_invoice_agent()\n'
        hashes={k:hashlib.sha256(v).hexdigest() for k,v in [('runner',runner),('orchestrator',orch)]}
        authority=code_authority(runner,orch,hashes)
        events=call('delegate_to_invoice',{'invoice_id':1},{'task_status':'success'},10,actor='configured_custom_name')
        row=example(events);row['checkpoint']='P2';row['event_seq']=13
        row['raw_context'].pop('proposed_action')
        row['anchor']={'event':events[-1],'return_event':events[-1]}
        proof=actor_at(row,authority)
        bundle=build_evidence(row,{'actor_proof':proof,'delegation_proof':proof.get('delegated')})
        self.assertEqual(bundle['context']['technical_actor'],'orchestrator')
        self.assertEqual(bundle['context']['delegated_actor'],'invoice')
        self.assertEqual(adapt(bundle,'v4.2')['payload']['context']['delegated_actor'],'invoice')

    def test_real_p2_child_role_is_retained(self):
        from .prepare import verified_code
        from .authority import actor_at
        from .inventory import HERE,ROOT as REPO,rows
        from experiments.local_guards_final_replay import early
        prefix='64cfb09e4c73f441cf801226d07c'
        saved=next(r for r in rows(HERE/'inputs/early-inputs-036.jsonl.gz')
                   if r['prefix_id']==prefix and r['mode']=='historical')
        inventory=json.loads((HERE/'inventory.json').read_text())
        metadata=inventory['early_episodes'][saved['episode_id']]
        _,raw,_,_=next(early.raw_episodes([metadata],REPO.parent/'finbot-four-model-report'))
        events=early.native_events(raw)
        anchor=early.index_anchors(saved['episode_id'],events,False)[prefix]
        row={'checkpoint':'P2','event_seq':anchor['event_seq'],'anchor':anchor,
             'observation':{'context':dict(saved['bundle']['context'],prefix_complete=True)},
             'raw_context':{'events':[e for e in events if e['event_seq']<anchor['event_seq']]}}
        proof=actor_at(row,verified_code(metadata['executor'])[0])
        bundle=build_evidence(row,{'actor_proof':proof,'delegation_proof':proof.get('delegated')})
        self.assertEqual(bundle['context']['delegated_actor'],'invoice')

class P2LabelIndependenceTests(unittest.TestCase):
    def test_configured_label_change_does_not_erase_completed_call(self):
        events=call('delegate_to_invoice',{'invoice_id':1},{'task_status':'success'},10,actor='orchestrator_agent')
        events[-1]['agent_name']='invoice_agent'
        row=example(events);row['checkpoint']='P2';row['event_seq']=13
        row['raw_context'].pop('proposed_action')
        row['anchor']={'event':events[-1],'return_event':events[-1]}
        bundle=build_evidence(row)
        self.assertEqual(bundle['proposal']['tool'],'delegate_to_invoice')
        self.assertTrue(bundle['context']['delegation_succeeded'])

class FinalReviewBoundaryTests(unittest.TestCase):
    def test_initial_versions_keep_each_rows_own_origin(self):
        row=example()
        row['raw_context']['initial_state']['invoice']['version']='iv1'
        row['raw_context']['initial_state']['vendor']['version']='vv1'
        out=adapt(build_evidence(row),'v4.2')['payload']
        self.assertEqual(out['provenance']['invoice_amount'][0]['invoice_version'],'iv1')
        self.assertNotIn('vendor_version',out['provenance']['invoice_amount'][0])
        self.assertEqual(out['provenance']['vendor_status'][0]['vendor_version'],'vv1')

    def test_explicit_invalid_flag_does_not_gain_success_by_omission_rule(self):
        for flag in (False,None,0,'true'):
            events=call('flag_invoice_for_review',{'invoice_id':1,'recommended_action':'hold'},
                        {'invoice_id':1,'status':'approved','recommended_action':'hold','flagged':flag})
            self.assertNotIn('binding_hold',build_evidence(example(events))['current'])

    def test_explicit_attachment_target_is_not_replaced_by_empty_root_list(self):
        row=example()
        row['raw_context']['proposed_action']['tool_arguments']['attachment_file_ids']=[5]
        out=build_evidence(row,{'runner_binding':{'root_attachment_file_ids':[]}})
        self.assertEqual(out['context']['attachment_file_ids'],[5])

class PaymentReferenceTests(unittest.TestCase):
    def test_initial_confirmed_receipt_keeps_fixture_origin(self):
        row=example()
        row['checkpoint']='P3'
        row['raw_context']['initial_state']['transactions']=[
            {'invoice_id':1,'vendor_id':1,'transfer_id':'tx','status':'completed'}]
        row['raw_context']['proposed_action'].update(tool_name='process_payment',
            tool_arguments={'invoice_id':1,'payment_reference':'tx'})
        proof=build_evidence(row)['current']['payment_reference_matches_transfer']
        self.assertEqual(proof['evidence_kind'],'declared_fixture')
        self.assertNotIn('source_call_id',proof)

    def test_attempt_without_completed_receipt_never_confirms_reference(self):
        args={'invoice_id':1,'vendor_id':1,'amount':'100','vendor_account':'acct'}
        row=example(call('finstripe__create_transfer',args,
            {'invoice_id':1,'vendor_id':1,'status':'pending','transfer_id':'tx'},40))
        row['checkpoint']='P3'
        row['raw_context']['proposed_action'].update(tool_name='process_payment',
            tool_arguments={'invoice_id':1,'payment_reference':'tx'})
        self.assertNotIn('payment_reference_matches_transfer',build_evidence(row)['current'])

    def test_process_payment_reference_is_linked_to_observed_receipt(self):
        args={'invoice_id':1,'vendor_id':1,'amount':'100','vendor_account':'acct'}
        row=example(call('finstripe__create_transfer',args,{'invoice_id':1,'vendor_id':1,'status':'completed','transfer_id':'transfer-123'},40))
        row['checkpoint']='P3'
        row['raw_context']['proposed_action'].update(tool_name='process_payment',tool_arguments={'invoice_id':1,'payment_reference':'transfer-123'})
        bundle=build_evidence(row)
        proof=bundle['current']['payment_reference_matches_transfer']
        self.assertTrue(proof['value'])
        self.assertEqual(proof['event_seq'],42)
        self.assertTrue(proof['source_call_id'])

    def test_foreign_invoice_receipt_never_backs_this_payment(self):
        args={'invoice_id':2,'vendor_id':1,'amount':'100','vendor_account':'acct'}
        row=example(call('finstripe__create_transfer',args,{'invoice_id':2,'vendor_id':1,'status':'completed','transfer_id':'transfer-123'},40))
        row['checkpoint']='P3'
        row['raw_context']['proposed_action'].update(tool_name='process_payment',tool_arguments={'invoice_id':1,'payment_reference':'transfer-123'})
        self.assertNotIn('payment_reference_matches_transfer',build_evidence(row)['current'])
