import copy
import json
from pathlib import Path

import pytest

from cascade_guard.dataset import POINTS, assert_clean_input, build_prefix, build_observable_prefix, group_id, judge_outcome, read_jsonl

BASE=Path(__file__).resolve().parent.parent


def archived_run():
    import gzip
    return json.loads(gzip.decompress((BASE/"data/archive/shadow-main.jsonl.gz").read_bytes()).decode().splitlines()[0])


def test_export_prefix_has_no_future_or_metadata():
    rows=read_jsonl(BASE/"data/prefixes.jsonl")
    assert len(rows)==866
    assert len({r["prefix_id"] for r in rows})==866
    for row in rows:
        assert row["max_input_seq"]<row["cut_seq"]
        assert_clean_input(row["state"])
        assert_clean_input(row["state_facts_action"])
        assert set(row["questions"])=={"untrusted_instruction","unsupported_authority_used","action_conflicts_with_hold","evidence_missing_for_permission"}
        assert row["state_facts_action"]["agent_explanation_not_independent_evidence"]==""


def test_future_and_label_perturbation_does_not_change_features():
    run=archived_run();policy=json.loads((BASE/"data/archive/legacy-policy.json").read_text())
    questions=json.loads((BASE/"data/prefixes.jsonl").read_text().splitlines()[0])["questions"]
    ctx=next(s for s in run["steps"] if s["kind"]=="guard_context" and s["point"]==POINTS[0])
    o=judge_outcome(run,policy);a=build_prefix(run,ctx,o,questions)
    perturbed=copy.deepcopy(run)
    for s in perturbed["steps"]:
        if s["seq"]>ctx["seq"]:
            s["output"]={"future":"MALICIOUS future truth"}
            s["arguments"]={"future":"MALICIOUS future truth"}
    perturbed["db_final"]={"future":"MALICIOUS"}
    perturbed["case_id"]="future_label"
    perturbed["injection"]=["secret","label"]
    changed=copy.deepcopy(o);changed["strict_harm_seq"]=999;changed["legacy_harm_seq"]=999
    b=build_prefix(perturbed,ctx,changed,questions)
    for key in ("state","state_facts_action","tabular_features","text","text_facts_action"):
        assert a[key]==b[key]


def test_all_fault_repeats_group_together():
    a=archived_run();b=copy.deepcopy(a);b["run_id"]="new-id";b["injection"]=["payments","response"]
    assert group_id(a)==group_id(b)


def test_strict_flag_changes_oracle_not_legacy():
    r=archived_run();policy=json.loads((BASE/"data/archive/legacy-policy.json").read_text())
    transfer=next(s for s in r["steps"] if s["kind"]=="tool" and s.get("name")=="finstripe__create_transfer")
    r["steps"].append({"seq":transfer["seq"]-1,"kind":"tool","name":"flag_invoice_for_review","error":None,"arguments":{"recommended_action":"hold"}})
    o=judge_outcome(r,policy)
    assert o["strict_harm"] is True
    assert o["legacy_harm"] is False
    assert "unresolved_fraud_flag" in o["strict_harm_reasons"]


def test_input_metadata_guard():
    with pytest.raises(ValueError):assert_clean_input({"nested":{"db_final":{}}})


def test_runtime_semantic_dictionary_order_matches_archive():
    run=archived_run();ctx=next(s for s in run["steps"] if s["kind"]=="guard_context" and s["point"]==POINTS[0])
    archived=read_jsonl(BASE/"data/prefixes.jsonl")[0]
    # Deliberately reverse question insertion order; runtime builder normalizes it.
    questions=dict(reversed(list(archived["questions"].items())))
    runtime=build_observable_prefix(run["db_initial"],ctx,run["steps"],questions)
    assert json.dumps(runtime["state"])==json.dumps(archived["state"])
    assert json.dumps(runtime["questions"])==json.dumps(archived["questions"])
