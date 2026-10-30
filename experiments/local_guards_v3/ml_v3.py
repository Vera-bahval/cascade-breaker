"""TRAIN-fitted classifiers for the frozen v3 observation boundary.

Scores are P(BLOCK), without calibration or decision thresholds. Callers must
provide TRAIN rows only to fit_model and exclude UNKNOWN supervision explicitly.
The text model is an untrusted-text diagnostic, not a structured guard.
"""

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import math

import numpy as np
from catboost import CatBoostClassifier
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler


MODEL_NAMES = ("structured_logistic", "structured_catboost", "text_diagnostic")
POLICY_SHA256 = "bdaaffe0715d7b7233cc40e1ce7f6ada7989bac927269998aa5827d385f65c85"
SCHEMA_SHA256 = "62efd6d8ec3b1dced204d3705c9c2691b7e9af1d503c4327ce388e1e6be84711"
POLICY_CURRENCY = "USD"
AUTOMATIC_LIMIT = Decimal("10000")
MAXIMUM_AMOUNT = Decimal("50000")
BOOLEAN_FACTS = (
    "fraud_review_completed", "binding_hold", "human_cleared",
    "amount_matches_invoice", "recipient_matches_authorized", "human_approved",
)


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and math.isfinite(float(number)) else None
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return None


def _category(value):
    return value if isinstance(value, str) and value else "__MISSING__"


def _nullable(result, name, value):
    result[name] = 0.0 if value is None else float(value)
    result[name + "_missing"] = float(value is None)


def features(observation):
    """Whitelist schema facts; preserve unknowns separately from false/zero.

    Categories are one-hot encoded by a TRAIN-fitted DictVectorizer. No raw
    text, provenance, IDs, event order, labels or metadata are inspected here.
    """
    row = _mapping(observation)
    proposal, facts = _mapping(row.get("proposal")), _mapping(row.get("facts"))
    result = {}
    for name, value in (
        ("checkpoint", row.get("checkpoint")),
        ("tool", proposal.get("tool")),
        ("target_status", proposal.get("target_status")),
        ("invoice_status", facts.get("invoice_status")),
        ("vendor_status", facts.get("vendor_status")),
    ):
        result[name] = _category(value)
        result[name + "_missing"] = float(not isinstance(value, str) or not value)
    for name in BOOLEAN_FACTS:
        value = facts.get(name)
        _nullable(result, name, value if isinstance(value, bool) else None)
    prior = facts.get("prior_completed_transfers")
    _nullable(result, "prior_completed_transfers",
              prior if isinstance(prior, int) and not isinstance(prior, bool) and prior >= 0 else None)
    amounts = {"proposal_amount": _number(proposal.get("amount")),
               "invoice_amount": _number(facts.get("invoice_amount"))}
    for name, amount in amounts.items():
        result[name + "_missing"] = float(amount is None)
        result[name + "_over_automatic_limit"] = 0.0 if amount is None else float(amount / AUTOMATIC_LIMIT)
        result[name + "_over_maximum"] = 0.0 if amount is None else float(amount / MAXIMUM_AMOUNT)
    proposed, invoice = amounts["proposal_amount"], amounts["invoice_amount"]
    _nullable(result, "proposed_amount_equals_invoice",
              proposed == invoice if proposed is not None and invoice is not None else None)
    proposed_currency, invoice_currency = (
        value.strip().upper() if isinstance(value, str) else ""
        for value in (proposal.get("currency"), facts.get("invoice_currency")))
    known_currencies = bool(proposed_currency and invoice_currency)
    _nullable(result, "same_currency",
              proposed_currency == invoice_currency if known_currencies else None)
    for name, currency in (("proposal", proposed_currency), ("invoice", invoice_currency)):
        _nullable(result, name + "_currency_matches_policy",
                  currency == POLICY_CURRENCY if currency else None)
    return result


def _structured_rows(rows):
    return [features(row) for row in rows]


def _text_rows(rows):
    texts = []
    for row in rows:
        text = _mapping(_mapping(row).get("untrusted_text"))
        texts.append("\n".join(value if isinstance(value, str) else ""
                               for value in (text.get("invoice"), text.get("agent"))))
    return texts


def model_provenance():
    """Fixed design and actual installed library versions; no training results."""
    logistic = {"C": 1.0, "regularization": "L2", "l1_ratio": 0.0,
                "solver": "lbfgs", "max_iter": 2000}
    return {
        "policy_sha256": POLICY_SHA256, "schema_sha256": SCHEMA_SHA256,
        "score": "P(BLOCK)", "fit_scope": "TRAIN only; caller supplies split",
        "versions": {name: version(name) for name in ("numpy", "pandas", "scikit-learn", "catboost")},
        "models": {
            "structured_logistic": {"classifier": logistic.copy(),
                                    "preprocessing": "whitelist, DictVectorizer, StandardScaler(with_mean=False)"},
            "structured_catboost": {"iterations": 200, "depth": 3, "learning_rate": 0.03,
                                    "l2_leaf_reg": 5, "allow_writing_files": False,
                                    "verbose": False, "thread_count": 2,
                                    "preprocessing": "whitelist, DictVectorizer"},
            "text_diagnostic": {"classifier": logistic.copy(), "analyzer": "char_wb",
                                "ngram_range": [3, 5], "max_features": 20000, "min_df": 2,
                                "input": "untrusted_text.invoice and untrusted_text.agent only"},
        },
    }


def fit_model(name, rows, labels, seed=17, sample_weight=None):
    """Fit fixed preprocessing and classifier on caller-supplied TRAIN only.

    UNKNOWN is rejected, never mapped to either class. External sample weights
    may balance prefixes/episodes without exposing those identities as features.
    """
    if name not in MODEL_NAMES:
        raise ValueError(f"unknown model {name!r}; choose from {MODEL_NAMES}")
    rows, labels = list(rows), list(labels)
    if len(rows) != len(labels):
        raise ValueError("rows and labels must have the same length")
    if any(label not in ("ALLOW", "BLOCK") for label in labels):
        raise ValueError("supervised labels must be known ALLOW or BLOCK; exclude UNKNOWN explicitly")
    if set(labels) != {"ALLOW", "BLOCK"}:
        raise ValueError("training requires both ALLOW and BLOCK classes")
    if sample_weight is not None:
        sample_weight = np.asarray(sample_weight, dtype=float)
        if (sample_weight.shape != (len(rows),) or not np.isfinite(sample_weight).all()
                or (sample_weight < 0).any() or not (sample_weight > 0).any()):
            raise ValueError("sample_weight must contain one finite nonnegative weight per row with positive total")
    # sklearn 1.9 expresses L2 through l1_ratio=0; its penalty argument is deprecated.
    logistic = LogisticRegression(C=1.0, l1_ratio=0.0, max_iter=2000, random_state=seed)
    if name == "text_diagnostic":
        steps = [("text", FunctionTransformer(_text_rows, validate=False)),
                 ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                           max_features=20000, min_df=2)),
                 ("classifier", logistic)]
    else:
        steps = [("features", FunctionTransformer(_structured_rows, validate=False)),
                 ("vectorizer", DictVectorizer(sparse=name == "structured_logistic"))]
        if name == "structured_logistic":
            steps.extend([("scale", StandardScaler(with_mean=False)), ("classifier", logistic)])
        else:
            steps.append(("classifier", CatBoostClassifier(
                iterations=200, depth=3, learning_rate=0.03, l2_leaf_reg=5,
                allow_writing_files=False, verbose=False, thread_count=2, random_seed=seed)))
    model = Pipeline(steps)
    fit_options = {} if sample_weight is None else {"classifier__sample_weight": sample_weight}
    model.fit(rows, labels, **fit_options)
    model.provenance_ = model_provenance()
    model.provenance_["name"] = name
    model.provenance_["seed"] = seed
    return model


def score_model(model, rows):
    """Return P(BLOCK) without updating fitted preprocessing or applying a cutoff."""
    rows = list(rows)
    if not rows:
        return []
    index = list(model.classes_).index("BLOCK")
    return [float(value) for value in model.predict_proba(rows)[:, index]]
