from pathlib import Path
import numpy as np
import pytest
from cascade_guard.dataset import read_jsonl
from cascade_guard.ml import Fitted,semantic_vector,FrozenMLDetector,FrozenSecJevDetector,FrozenSemanticStackDetector,QUESTION_KEYS

BASE=Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name",["tfidf_logistic","tabular_logistic","catboost"])
def test_baselines_fit_probability_and_unseen_category(name):
    rs=[r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["control_point"]=="P4.finstripe__create_transfer" and not r["ambiguity"]]
    model=Fitted(name,17).fit(rs)
    p,ms=model.predict(rs[:3]);assert len(p)==3 and np.isfinite(p).all() and ((p>=0)&(p<=1)).all() and ms>=0


def test_single_class_fit_is_explicit_failure():
    rs=[r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["label"]==0][:10]
    with pytest.raises(ValueError,match="one outcome class"):Fitted("tabular_logistic",17).fit(rs)


def test_bad_semantic_scores_not_silently_probability():
    row={"prefix_id":"id"}
    assert semantic_vector(row,{("id","plus_rationale"):{"unknown":True}},"plus_rationale") is None


def test_frozen_runtime_models_and_wrong_point_unknown():
    artifact=BASE/"artifacts/frozen-ml"
    row=next(r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["control_point"]=="P4.finstripe__create_transfer")
    for name in ("tfidf_logistic","tabular_logistic","catboost"):
        detector=FrozenMLDetector(artifact,name)
        assert detector(row).decision in ("ALLOW","BLOCK")
        assert detector(dict(row,control_point="P2.invoice_agent")).decision=="UNKNOWN"


def test_frozen_artifact_tamper_rejected(tmp_path):
    import shutil
    src=BASE/"artifacts/frozen-ml"
    shutil.copy(src/"manifest.json",tmp_path/"manifest.json")
    (tmp_path/"catboost.joblib").write_bytes(b"tampered")
    with pytest.raises(ValueError,match="hash"):FrozenMLDetector(tmp_path,"catboost")


def test_frozen_secjev_threshold_and_unknown_contract(tmp_path):
    import json
    (tmp_path/"manifest.json").write_text(json.dumps({"secjev":{"threshold":.7}}))
    detector=FrozenSecJevDetector(tmp_path)
    row=next(r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["control_point"]=="P4.finstripe__create_transfer")
    record={"probabilities":{k:.2 for k in QUESTION_KEYS}}
    assert detector(row,record).decision=="ALLOW"
    record["probabilities"][QUESTION_KEYS[0]]=.8
    assert detector(row,record).decision=="BLOCK"
    assert detector(row,{"unknown":True,"error":"timeout"}).decision=="UNKNOWN"
    assert detector(row).decision=="UNKNOWN"


def test_frozen_stack_requires_current_semantic_result(tmp_path):
    import json,joblib
    from cascade_guard.dataset import sha
    rows=[r for r in read_jsonl(BASE/"data/prefixes.jsonl") if r["control_point"]=="P4.finstripe__create_transfer" and not r["ambiguity"]][:35]
    sem={(r["prefix_id"],"plus_rationale"):{"probabilities":{k:.2+.6*r["label"] for k in QUESTION_KEYS}} for r in rows}
    model=Fitted("semantic_stack",17,semantic_scores=sem).fit(rows)
    model.semantic_scores=None
    path=tmp_path/"semantic_stack.joblib";joblib.dump(model,path)
    (tmp_path/"manifest.json").write_text(json.dumps({"models":{"semantic_stack":{"filename":path.name,"artifact_sha256":sha(path.read_bytes()),"threshold":.5,"control_point":"P4.finstripe__create_transfer"}}}))
    detector=FrozenSemanticStackDetector(tmp_path)
    assert detector(rows[0]).decision=="UNKNOWN"
    assert detector(rows[0],{"probabilities":{k:.2 for k in QUESTION_KEYS}}).decision in ("ALLOW","BLOCK")
