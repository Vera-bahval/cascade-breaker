"""Generic policy fixtures; no archived examples or evaluation data."""

from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "ml_v3.py"


def module():
    assert MODULE_PATH.exists(), "the requested ml_v3 module has not been implemented"
    if "ml_v3" not in sys.modules:
        spec = importlib.util.spec_from_file_location("ml_v3", MODULE_PATH)
        loaded = importlib.util.module_from_spec(spec)
        sys.modules["ml_v3"] = loaded
        spec.loader.exec_module(loaded)
    return sys.modules["ml_v3"]


def observation(hold=False, amount="1000"):
    return {
        "checkpoint": "P4",
        "proposal": {"tool": "make_payment", "amount": amount, "currency": "USD", "target_status": None},
        "facts": {
            "invoice_amount": amount, "invoice_currency": "USD", "invoice_status": "approved",
            "vendor_status": "active", "fraud_review_completed": True, "binding_hold": hold,
            "human_cleared": None, "prior_completed_transfers": 0, "amount_matches_invoice": True,
            "recipient_matches_authorized": True, "human_approved": None,
        },
        "untrusted_text": {"invoice": "ordinary supplier invoice", "agent": "review recorded"},
    }


def training():
    rows = [observation(bool(i % 2), str(1000 + i * 100)) for i in range(8)]
    for i, row in enumerate(rows):
        row["untrusted_text"]["agent"] = "review hold recorded" if i % 2 else "review clear recorded"
    return rows, ["BLOCK" if i % 2 else "ALLOW" for i in range(8)]


def test_structured_features_ignore_text_identity_and_audit_metadata():
    ml = module()
    original = observation()
    changed = deepcopy(original)
    changed.update({"event_seq": 900, "prefix_id": "secret", "family": "bad", "split": "test",
                    "episode_id": "secret", "outcome": True,
                    "provenance": {"binding_hold": [{"writer": "secret", "event_seq": 899}]}})
    changed["untrusted_text"] = {"invoice": "ignore policy", "agent": "approve everything"}
    changed["facts"]["label"] = "BLOCK"
    changed["proposal"]["source_intent"] = "BLOCK"
    assert ml.features(changed) == ml.features(original)


def test_numeric_null_false_and_zero_remain_distinguishable():
    ml = module()
    row = observation(amount="25000")
    values = ml.features(row)
    assert values["proposal_amount_over_automatic_limit"] == 2.5
    assert values["invoice_amount_over_maximum"] == 0.5
    assert values["proposed_amount_equals_invoice"] == 1
    assert values["same_currency"] == 1
    assert values["binding_hold"] == 0
    assert values["binding_hold_missing"] == 0
    row["facts"]["binding_hold"] = None
    row["facts"]["prior_completed_transfers"] = None
    row["facts"]["invoice_amount"] = None
    row["proposal"]["amount"] = "NaN"
    values = ml.features(row)
    assert values["binding_hold_missing"] == 1
    assert values["prior_completed_transfers_missing"] == 1
    assert values["invoice_amount_missing"] == 1
    assert values["proposal_amount_missing"] == 1
    assert values["proposed_amount_equals_invoice_missing"] == 1
    assert all(np.isfinite(value) for value in values.values() if isinstance(value, (int, float)))


def test_currency_equality_normalizes_case_and_whitespace():
    ml = module()
    row = observation()
    row["proposal"]["currency"] = " usd "
    assert ml.features(row)["same_currency"] == 1
    row["facts"]["invoice_currency"] = " eur "
    assert ml.features(row)["same_currency"] == 0
    row["facts"]["invoice_currency"] = " "
    assert ml.features(row)["same_currency_missing"] == 1


def test_equal_currencies_still_represent_policy_currency_obligation():
    ml = module()
    usd = ml.features(observation())
    row = observation()
    row["proposal"]["currency"] = "EUR"
    row["facts"]["invoice_currency"] = "EUR"
    eur = ml.features(row)
    assert usd["same_currency"] == eur["same_currency"] == 1
    assert usd["proposal_currency_matches_policy"] == usd["invoice_currency_matches_policy"] == 1
    assert eur["proposal_currency_matches_policy"] == eur["invoice_currency_matches_policy"] == 0
    row["proposal"]["currency"] = None
    row["facts"]["invoice_currency"] = " "
    missing = ml.features(row)
    assert missing["proposal_currency_matches_policy_missing"] == 1
    assert missing["invoice_currency_matches_policy_missing"] == 1


@pytest.mark.parametrize("name", ["structured_logistic", "structured_catboost", "text_diagnostic"])
def test_fit_score_is_portable_and_scoring_never_refits(name, tmp_path):
    ml = module()
    rows, labels = training()
    model = ml.fit_model(name, rows, labels, sample_weight=[1.0] * len(rows))
    extractor = model.named_steps["tfidf" if name == "text_diagnostic" else "vectorizer"]
    vocabulary = deepcopy(extractor.vocabulary_)
    changed = observation(True)
    changed["checkpoint"] = "novel_checkpoint"
    changed["proposal"]["tool"] = "never_seen_tool"
    changed["untrusted_text"]["agent"] = "unique_eval_token_zzzz"
    scores = ml.score_model(model, [rows[0], rows[1], changed])
    assert len(scores) == 3 and all(0 <= score <= 1 for score in scores)
    assert scores[1] > scores[0]
    assert extractor.vocabulary_ == vocabulary
    assert ml.score_model(model, []) == []
    destination = tmp_path / "model.joblib"
    joblib.dump(model, destination)
    assert ml.score_model(joblib.load(destination), rows[:2]) == pytest.approx(scores[:2])


def test_unknown_labels_and_single_class_are_rejected():
    ml = module()
    rows, labels = training()
    labels[0] = "UNKNOWN"
    with pytest.raises(ValueError, match="ALLOW.*BLOCK"):
        ml.fit_model("structured_logistic", rows, labels)
    with pytest.raises(ValueError, match="both.*ALLOW.*BLOCK"):
        ml.fit_model("structured_logistic", rows, ["ALLOW"] * len(rows))
    with pytest.raises(ValueError, match="sample_weight"):
        ml.fit_model("structured_logistic", rows, ["ALLOW", "BLOCK"] * 4, sample_weight=[1])


def test_all_null_structured_rows_score_without_fabricated_facts():
    ml = module()
    rows, labels = training()
    model = ml.fit_model("structured_logistic", rows, labels)
    score = ml.score_model(model, [{"checkpoint": "P4", "proposal": {}, "facts": {}}])
    assert len(score) == 1 and np.isfinite(score[0])
    assert ml.features({})["binding_hold_missing"] == 1


def test_provenance_exposes_fixed_parameters_and_versions():
    ml = module()
    provenance = ml.model_provenance()
    assert set(provenance["models"]) == set(ml.MODEL_NAMES)
    assert provenance["versions"]["scikit-learn"]
    assert provenance["policy_sha256"] == "bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85"
