"""Pure predeclared sample/statistics/profiling-gate fixtures only."""
import pytest
from cascade_guard.v2_archive_latency import sample_ids,stats,run


def test_sample_is_hash_deterministic_order_invariant_and_label_free():
 ids=['p'+str(i) for i in range(40)]
 a=sample_ids(ids,17)
 assert a==sample_ids(ids[::-1],17) and len(a)==16 and len(set(a))==16
 assert a!=sample_ids(ids,29)
 assert sample_ids(ids[:2],17)==sample_ids(ids[:2][::-1],17)


def test_duplicate_prefixes_are_rejected():
 with pytest.raises(ValueError,match='Duplicate'):sample_ids(['a','a'],17)


def test_missing_profile_has_unknown_latency_not_zero():
 assert stats([])==dict(n=0,p50_ms=None,p95_ms=None)
 assert stats([1,3])==dict(n=2,p50_ms=2,p95_ms=2.9)


def test_profiler_opens_no_inputs_before_complete(tmp_path):
 with pytest.raises(ValueError,match='Completion marker required'):
  run(tmp_path,tmp_path/'absentrows',[],tmp_path/'absentsource',tmp_path/'absentplan',tmp_path/'output')


def completion_fixture(tmp_path):
 import json
 from cascade_guard.v2_archive_latency import sha
 def js(path,obj):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj));return path
 root=tmp_path/'root';method=js(root/'METHOD_FREEZE_05.json',{'technical_runner_deadline_utc':'2030-01-01T00:00:00Z'})
 methods=root/'evaluation-v5';mf=js(methods/'METHODS_FROZEN.json',{'models':'public-only'})
 protocols={}
 for key,name in (('addon','NEW_ABLATION_PROTOCOL_05.json'),('jev','JEV_INPUT_FREEZE_05.json'),('split','SPLIT_PROTOCOL_FREEZE_05.json')):protocols[key]=sha(js(root/name,{}))
 js(root/'evaluation-runner-v5/runtime-run.json',dict(status='PREDICTIONS_FROZEN_AWAITING_ROOT_UNBLIND',freeze_sha256=dict(method=sha(method),**protocols),methods_freezes={'evaluation-v5':sha(mf)}))
 plan=js(root/'ROOT_AUTHORIZATION_PLAN_05.json',dict(root=str(root),authorization='COMPLETE_GUARD_V2_05_AND_UNBLIND',generation=5,method_freeze_sha256=sha(method),source_sha256={},completion_deadline_utc='2030-01-01T00:00:00Z'))
 complete=js(root/'completion-v5/COMPLETE.json',dict(status='COMPLETE',destinations=4,authorization_plan_sha256=sha(plan)))
 return methods,method,complete,plan,sha(plan)


def test_completion_gate_rejects_substituted_methods_and_wrong_root(tmp_path):
 from cascade_guard.v2_archive_latency import validate_completion
 args=completion_fixture(tmp_path)
 assert validate_completion(*args)>0
 (args[0]/'METHODS_FROZEN.json').write_text('{"replacement":"rehashable"}')
 with pytest.raises(ValueError,match='not anchored'):validate_completion(*args)


def test_completion_requires_real_status_and_four_destinations(tmp_path):
 from cascade_guard.v2_archive_latency import validate_completion
 args=completion_fixture(tmp_path)
 args[2].write_text('{"status":"RUNNING","destinations":4}')
 with pytest.raises(ValueError,match='Malformed'):validate_completion(*args)


def test_completion_rejects_arbitrary_marker_and_wrong_authorization_sha(tmp_path):
 from cascade_guard.v2_archive_latency import validate_completion
 args=list(completion_fixture(tmp_path))
 wrong=tmp_path/'COMPLETE.json';wrong.write_bytes(args[2].read_bytes())
 substituted=args.copy();substituted[2]=wrong
 with pytest.raises(ValueError,match='outside authorized root'):validate_completion(*substituted)
 substituted=args.copy();substituted[4]='0'*64
 with pytest.raises(ValueError,match='authorization hash'):validate_completion(*substituted)
