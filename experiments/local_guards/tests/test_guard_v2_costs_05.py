"""Metadata-only projection and overlapping cost-accounting public fixtures."""
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('cost_addon',Path(__file__).resolve().parents[1]/'scripts/audit_guard_v2_costs_05.py')
addon=importlib.util.module_from_spec(spec);spec.loader.exec_module(addon)


def test_projection_skips_quality_values_without_deserializing():
 # A decoder would reject the marker, while a lexical skip need not inspect it.
 raw='{"prefix_id":"p","features":{"no_read":UNREAD_VALUE},"probabilities":[UNREAD_VALUE],"timing_ms":{"total":4},"labels":{"do_not_read":UNREAD_VALUE}}'
 result,_=addon.project(raw,addon.ROW_FIELDS)
 assert result=={'prefix_id':'p','timing_ms':{'total':4}}


def test_warm_cost_uses_rows_not_written_zero_manifest(tmp_path):
 path=tmp_path/'G22.jsonl'
 rows=[dict(prefix_id='p'+str(i),block='G22',provenance={'collection':collection},timing_ms={'total':cost,'cold_load':cold},model_metadata={'cold_weight_tokenizer_load_ms':2,'cpu_semantic_sanity_ms':1}) for i,collection,cost,cold in [(0,'first',10,3),(1,'later',20,0)]]
 path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
 (tmp_path/'G22.manifest.json').write_text('{"written":0,"wall_ms":0}')
 stages,_=addon.summarize_rows([path]);first,later=stages
 assert first['row_sum_ms']==10 and first['cold_setup_ms']==3
 assert later['row_sum_ms']==20 and later['cold_setup_ms'] is None
 assert later['cold_setup_status']=='NOT_MEASURED_IN_THIS_COLLECTION'
 assert later['max_rss_bytes'] is None


def test_duplicate_scored_rows_not_counted_as_two_inferences(tmp_path):
 path=tmp_path/'rows';r=dict(prefix_id='p',block='N',timing_ms={'total':10})
 path.write_text((json.dumps(r)+'\n')*2)
 with pytest.raises(ValueError,match='Duplicate'):addon.summarize_rows([path])


def test_precompletion_opens_no_score_or_runtime_metadata(tmp_path):
 with pytest.raises(ValueError,match='Completion marker required'):addon.audit(tmp_path,tmp_path/'output')


def test_gate_elapsed_is_not_reconstructed_from_validation_probabilities():
 value,_=addon.project('{"passed":true,"cpu_repeats":[UNREAD],"mps_repeats":[UNREAD]}',addon.GATE_FIELDS)
 assert value=={'passed':True}
 assert addon.interval(dict(started_at='2026-10-15T12:09:30Z',finished_at='2026-10-15T12:09:34Z'))==4000


def test_cost_artifact_separates_stage_rows_duplicate_and_unmeasured_gate(tmp_path):
 def js(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj))
 js(tmp_path/'completion-v5/COMPLETE.json',dict(status='COMPLETE',destinations=4))
 js(tmp_path/'scores-v5/runtime-run.json',dict(pid=66054,stages=[dict(block='G22',started_at='2026-10-15T12:08:09Z',finished_at='2026-10-15T12:09:04Z',exit_code=0)]))
 row=dict(prefix_id='p',block='G22',timing_ms={'total':10,'cold_load':20})
 score=tmp_path/'scores-v5/G22.jsonl';score.write_text(json.dumps(row)+'\n')
 js(tmp_path/'scores-v5/G22.mps-probe.json',dict(passed=True,cpu_repeats=[{'unread':.9}]))
 js(tmp_path/'duplicate-orchestrator-67514.json',dict(real_owner={'pid':66054},duplicate_owner={'pid':67514,'started_at':'2026-10-15T12:09:30Z','finished_at':'2026-10-15T12:09:34Z'},new_heavy_inference_from_duplicate=False))
 result=addon.audit(tmp_path,tmp_path/'costs.json',[score])
 assert result['actual_owner_stages'][0]['wall_ms']==55000
 assert result['stages'][0]['row_sum_ms']==10
 assert result['duplicate_orchestration']['orchestration_overhead_ms']==4000
 assert result['duplicate_orchestration']['inference_ms']==0
 assert result['gates'][0]['elapsed_ms'] is None


def test_duplicate_owner_runtime_does_not_masquerade_as_66054(tmp_path):
 def js(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj))
 js(tmp_path/'completion-v5/COMPLETE.json',dict(status='COMPLETE',destinations=4))
 js(tmp_path/'scores-v5/runtime-run.json',dict(pid=67514,stages=[dict(block='G22',started_at='2026-10-15T12:09:30Z',finished_at='2026-10-15T12:09:34Z')]))
 result=addon.audit(tmp_path,tmp_path/'costs.json',[])
 assert result['actual_owner_stages']==[]
 assert result['actual_owner_stage_status'].startswith('UNKNOWN')


def test_runtime_stage_projection_skips_nested_quality_and_command():
 raw='{"pid":66054,"stages":[{"block":"G22","started_at":"a","finished_at":"b","exit_code":0,"features":{"no_read":UNREAD_VALUE},"probabilities":[UNREAD_VALUE],"labels":UNREAD_VALUE,"command":[UNREAD_VALUE]}]}'
 projection={'pid':True,'stages':[{'block':True,'started_at':True,'finished_at':True,'exit_code':True}]}
 value,_=addon.project(raw,projection)
 assert value==dict(pid=66054,stages=[dict(block='G22',started_at='a',finished_at='b',exit_code=0)])


@pytest.mark.parametrize('raw,projection',[
 ('{"prefix_id":{"probabilities":[UNREAD_VALUE]}}',{'prefix_id':True}),
 ('{"timing_ms":{"total":[UNREAD_VALUE]}}',{'timing_ms':{'total':True}}),
 ('{"stages":[{"block":{"labels":UNREAD_VALUE}}]}',{'stages':[{'block':True}]})])
def test_requested_metadata_scalar_rejects_containers_without_decoding(raw,projection):
 with pytest.raises(ValueError,match='scalar cannot contain'):addon.project(raw,projection)
