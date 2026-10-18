from pathlib import Path
import copy
from cascade_guard.dataset import read_jsonl
from cascade_guard.evaluate import select_threshold,summarize,episode_decisions
from cascade_guard.offline import splits
from cascade_guard.offline import load_semantics,semantic_status,diagnostic_leave_positive_group_out
from cascade_guard.dataset import canonical,sha
import json
import pytest

BASE=Path(__file__).resolve().parent.parent


def test_grouped_splits_no_invoice_leakage():
    o=[x for x in read_jsonl(BASE/"data/outcomes.jsonl") if not x["legacy_ambiguous"]]
    for train,test in splits(o,3,17):
        assert not {x["group_id"] for x in train}&{x["group_id"] for x in test}
        assert len({x["strict_harm"] for x in train})==2


def test_late_stop_does_not_prevent():
    r=copy.deepcopy(read_jsonl(BASE/"data/prefixes.jsonl")[0])
    o=copy.deepcopy(read_jsonl(BASE/"data/outcomes.jsonl")[0])
    o.update(strict_harm=True,strict_harm_seq=r["cut_seq"]-1)
    m,_=summarize([r],[1.],.5,[o])
    assert m["harm_prevented_counterfactual"]["k"]==0


def test_no_defense_and_rules_do_not_conflate_benign_operational_rate():
    rows=read_jsonl(BASE/"data/prefixes.jsonl");o=read_jsonl(BASE/"data/outcomes.jsonl")
    m,_=summarize(rows,[0.]*len(rows),float("inf"),o)
    assert m["benign_source_interruption"]["k"]==0
    m,_=summarize(rows,[0.]*len(rows),float("inf"),o,True)
    assert m["policy_correct_fpr"]["k"]==0
    assert m["benign_source_interruption"]["k"]>0


def test_inner_threshold_fpr_limit():
    rs=[r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["control_point"]=="P4.finstripe__create_transfer"]
    os=read_jsonl(BASE/"data/outcomes.jsonl")
    p=[.9 if r["label"] else .1 for r in rs]
    threshold,_=select_threshold(rs,p,os)
    m,_=summarize(rs,p,threshold,os)
    assert m["policy_correct_fpr"]["rate"]<=.05
    assert m["harm_prevented_counterfactual"]["rate"]==1


def test_stale_semantic_hash_rejected(tmp_path):
    prefix=read_jsonl(BASE/"data/prefixes.jsonl")[0]
    payload={"state":prefix["state"],"questions":prefix["questions"]}
    metadata={"model":"test"}
    fingerprint=sha(canonical(metadata).encode())
    input_hash=sha(json.dumps({"payload":payload,"scorer_fingerprint":fingerprint},sort_keys=False,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode())
    record={"prefix_id":prefix["prefix_id"],"ablation":"plus_rationale","input_hash":input_hash,"model_metadata":metadata,"probabilities":{},"unknown":False}
    p=tmp_path/"scores.jsonl";p.write_text(json.dumps(record)+"\n")
    assert len(load_semantics(p,[prefix]))==1
    record["input_hash"]="stale";p.write_text(json.dumps(record)+"\n")
    with pytest.raises(ValueError,match="hash"):load_semantics(p,[prefix])


def test_completed_unknown_forces_stop_missing_is_not_completed():
    row=read_jsonl(BASE/"data/prefixes.jsonl")[0]
    missing,unknown=semantic_status([row],{},"plus_rationale")
    assert missing==[row["prefix_id"]] and not unknown
    record={(row["prefix_id"],"plus_rationale"):{"unknown":True,"error":"timeout","latency_ms":5000}}
    missing,unknown=semantic_status([row],record,"plus_rationale")
    assert not missing and unknown=={row["prefix_id"]}
    decisions=episode_decisions([row],[float("nan")],float("inf"),force_stop_ids=unknown)
    assert decisions[row["episode_id"]]["stop"] and decisions[row["episode_id"]]["unknown_stop"]


def test_unknown_cost_can_make_fpr_constraint_infeasible():
    row=read_jsonl(BASE/"data/prefixes.jsonl")[0]
    outcome=read_jsonl(BASE/"data/outcomes.jsonl")[0]
    _,cal=select_threshold([row],[float("nan")],[outcome],force_stop_ids={row["prefix_id"]})
    assert cal["unavoidable_unknown_fpr"]==1 and cal["target_feasible"] is False


def test_leave_positive_group_out_is_explicit_diagnostic():
    rows=read_jsonl(BASE/"data/prefixes.jsonl")
    outcomes=[o for o in read_jsonl(BASE/"data/outcomes.jsonl") if not o["legacy_ambiguous"]]
    # A single positive invoice group cannot provide both-class training when held out.
    one_group=next(o["group_id"] for o in outcomes if o["strict_harm"])
    sub=[o for o in outcomes if o["group_id"]==one_group]
    result=diagnostic_leave_positive_group_out("tabular_logistic",rows,sub,("P4.finstripe__create_transfer",),17,"plus_rationale",{})
    assert result and result[0]["status"]=="infeasible"
