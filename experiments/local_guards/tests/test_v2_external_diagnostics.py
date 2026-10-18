"""Public fixtures only: no experiment data or imports of model weights."""
import json
import pytest
from cascade_guard.v2_external_diagnostics import average_precision,control_predictions,run,summarize


def fixture():
 labels=[dict(episode_id='s',contract_requires_intervention=False,backend_diagnostic=dict(status='posted_new_transfer',harmful_effect_if_executed=False)),dict(episode_id='h',contract_requires_intervention=True,backend_diagnostic=dict(status='posted_new_transfer',harmful_effect_if_executed=True))]
 rows=[dict(episode_id=e,policy='A',denominator='reached',seed=17,arm='model',probability=p,rule_stop=r,unknown=False,block=r) for e,p,r in [('s',.8,False),('h',.2,True)]]
 return rows,labels


def test_average_precision_ties_are_admitted_together():
 assert average_precision([0,1],[.4,.4])==.5
 assert average_precision([0,1],[.1,.9])==1.
 assert average_precision([0,1],[.9,.1])==.5
 assert average_precision([0,0],[.1,.2]) is None


def test_component_vs_composite_and_backend_are_distinct():
 rows,labels=fixture();r=summarize(rows,labels)[0]
 assert r['component_average_precision']==.5
 assert r['composite_OR_average_precision']==1.
 assert r['stopped_modeled_policy_violating_new_effect']==dict(k=1,n=1,rate=1.)
 assert 'brier' not in r


def test_unknown_does_not_become_probability_zero():
 rows,labels=fixture();rows[1].update(unknown=True,probability=None,block=True)
 r=summarize(rows,labels)[0]
 assert r['known_ranking_coverage']==dict(k=1,n=2,rate=.5)
 assert r['unknown_excluded']==1 and r['component_average_precision'] is None


def test_duplicate_join_rejected():
 rows,labels=fixture();rows[1]['episode_id']='s'
 with pytest.raises(ValueError,match='Incomplete/duplicate'):summarize(rows,labels)


def test_no_read_before_unblinded_gate(tmp_path):
 # Deliberately malformed files must not be opened at all before release.
 for name in ('labels','marker','plan'):(tmp_path/name).write_text('NOT JSON')
 with pytest.raises(ValueError,match='UNBLINDED required'):
  run(tmp_path,tmp_path/'labels',tmp_path/'marker',tmp_path/'plan',tmp_path/'output')


def test_control_exact_join_preserves_unknown_and_intervene():
 predictions=[dict(prefix_id='opaque',input_hash='h',result={'verdict':'INTERVENE'},block=True,unknown=False)]
 inputs=[dict(prefix_id='opaque',input_hash='h',provenance=dict(episode_id='independent',cut_seq=4))];rows=[dict(prefix_id='opaque',episode_id='independent',cut_seq=4)]
 out=control_predictions(predictions,inputs,rows)
 assert out[0]['episode_id']=='independent' and out[0]['probability'] is None
 predictions[0]['input_hash']='wrong'
 with pytest.raises(ValueError,match='hash differs'):control_predictions(predictions,inputs,rows)


def test_control_episode_swap_rejected_even_with_same_prefix_and_input_hash():
 predictions=[dict(prefix_id='opaque',input_hash='h',result={'verdict':'ALLOW'},block=False,unknown=False)]
 inputs=[dict(prefix_id='opaque',input_hash='h',provenance=dict(episode_id='original',cut_seq=4))]
 rows=[dict(prefix_id='opaque',episode_id='swapped',cut_seq=4)]
 with pytest.raises(ValueError,match='sealed input provenance'):control_predictions(predictions,inputs,rows)


def test_ap_rejects_truncated_and_invalid_scores():
 with pytest.raises(ValueError,match='lengths differ'):average_precision([0,1],[.5])
 with pytest.raises(ValueError,match='finite'):average_precision([0,1],[.5,float('nan')])


def test_run_rejects_unpinned_control_rows_before_control_read(tmp_path):
 from cascade_guard.v2_external_diagnostics import freeze,sha
 rows,labels=fixture()
 destination=tmp_path/'destination';destination.mkdir()
 def js(path,obj):path.write_text(json.dumps(obj));return path
 def jl(path,obj):path.write_text(''.join(json.dumps(r)+'\n' for r in obj));return path
 labels_path=jl(tmp_path/'labels',labels);mainrows=jl(tmp_path/'mainrows',[dict(prefix_id='s',episode_id='s',cut_seq=4),dict(prefix_id='h',episode_id='h',cut_seq=4)])
 preds=jl(destination/'predictions.jsonl',rows);method=js(tmp_path/'METHODS_FROZEN.json',{'public fixture':True})
 pf=js(destination/'PREDICTIONS_FROZEN.json',dict(predictions_sha256=sha(preds),methods_freeze_sha256=sha(method),rows_file=dict(path=str(mainrows),sha256=sha(mainrows))))
 js(destination/'UNBLINDED.json',dict(labels_sha256=sha(labels_path),predictions_sha256=sha(preds)))
 marker=js(tmp_path/'marker',dict(authorization='UNBLIND',predictions_freeze_sha256=sha(pf),labels_sha256=sha(labels_path)))
 plan=tmp_path/'plan';freeze(plan)
 swapped=jl(tmp_path/'swapped',[dict(prefix_id='s',episode_id='h',cut_seq=4),dict(prefix_id='h',episode_id='s',cut_seq=4)])
 # No control directory exists: the pin failure must happen before opening it.
 with pytest.raises(ValueError,match='exact main frozen'):
  run(destination,labels_path,marker,plan,tmp_path/'output',method_freeze=method,control_dir=tmp_path/'absentcontrol',control_inputs=tmp_path/'unused',control_rows=swapped,control_source=tmp_path/'unusedsource',control_method_freeze=tmp_path/'unusedfreeze')
