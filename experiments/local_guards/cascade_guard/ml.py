"""Fixed-capacity baselines. Every fit happens within a grouped training fold."""
from __future__ import annotations

import time
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from catboost import CatBoostClassifier

QUESTION_KEYS = ("untrusted_instruction", "unsupported_authority_used", "action_conflicts_with_hold", "evidence_missing_for_permission")
LEARNED = ("tfidf_logistic", "tabular_logistic", "catboost")


def semantic_vector(row, scores, ablation):
    s = scores.get((row["prefix_id"], ablation))
    if not s or s.get("unknown") or s.get("error"):
        return None
    p = s.get("probabilities") or {}
    try:
        v = [float(p[k]) for k in QUESTION_KEYS]
    except (KeyError, TypeError, ValueError):
        return None
    return v if all(np.isfinite(v)) and all(0 <= x <= 1 for x in v) else None


def tabular(rows, scores=None, ablation="plus_rationale"):
    df = pd.DataFrame([r["tabular_features"] for r in rows])
    for column in ("amount", "distance_5000", "distance_10000", "distance_50000"):
        df[column] = np.sign(df[column]) * np.log1p(np.abs(df[column]))
    if scores is not None:
        vs = [semantic_vector(r, scores, ablation) for r in rows]
        if any(v is None for v in vs):
            raise ValueError("Semantic stacking requires complete valid probabilities for each training/scoring row")
        for i, k in enumerate(QUESTION_KEYS):
            df["semantic_" + k] = [v[i] for v in vs]
    return df


def weights(rows):
    # One invoice group has equal weight regardless of repeated runs/prefix count.
    from collections import Counter
    counts = Counter(r["group_id"] for r in rows)
    w = np.array([1 / counts[r["group_id"]] for r in rows])
    return w / w.mean()


class Fitted:
    def __init__(self, name, seed, ablation="plus_rationale", semantic_scores=None):
        self.name, self.seed, self.ablation = name, seed, ablation
        self.semantic_scores = semantic_scores
        self.model = None
        self.columns = None
        self.fit_ms = 0.0

    def x(self, rows, semantic_scores=None):
        if self.name == "tfidf_logistic":
            k = "text" if self.ablation == "plus_rationale" else "text_facts_action"
            return [r[k] for r in rows]
        return tabular(rows, (semantic_scores if semantic_scores is not None else self.semantic_scores) if self.name == "semantic_stack" else None, self.ablation)

    def fit(self, rows):
        y = np.array([r["label"] for r in rows])
        if len(set(y)) < 2:
            raise ValueError("Training fold has only one outcome class")
        x = self.x(rows)
        start = time.perf_counter()
        if self.name == "tfidf_logistic":
            self.model = Pipeline([
                ("tfidf", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, max_features=20000, sublinear_tf=True)),
                ("classifier", LogisticRegression(C=1, penalty="l2", max_iter=2000, random_state=self.seed)),
            ])
            self.model.fit(x, y, classifier__sample_weight=weights(rows))
        elif self.name == "catboost":
            cats = list(x.select_dtypes(include=["object", "str", "string"]).columns)
            for c in cats:
                x[c] = x[c].fillna("MISSING").astype(str)
            self.columns = cats
            self.model = CatBoostClassifier(iterations=200, depth=3, learning_rate=.03, l2_leaf_reg=5,
                                            loss_function="Logloss", random_seed=self.seed, thread_count=2,
                                            allow_writing_files=False, verbose=False)
            self.model.fit(x, y, cat_features=cats, sample_weight=weights(rows))
        else:
            cats = list(x.select_dtypes(include=["object", "str", "string"]).columns)
            nums = [c for c in x.columns if c not in cats]
            trans = ColumnTransformer([
                ("numerical", Pipeline([("fill", SimpleImputer()), ("scale", StandardScaler())]), nums),
                ("categorical", OneHotEncoder(handle_unknown="ignore"), cats),
            ])
            self.model = Pipeline([("features", trans), ("classifier", LogisticRegression(C=1, penalty="l2", max_iter=2000, random_state=self.seed))])
            self.model.fit(x, y, classifier__sample_weight=weights(rows))
        self.fit_ms = (time.perf_counter()-start)*1000
        return self

    def predict(self, rows,semantic_scores=None):
        x = self.x(rows,semantic_scores)
        if self.name == "catboost":
            for c in self.columns:
                x[c] = x[c].fillna("MISSING").astype(str)
        start = time.perf_counter()
        p = self.model.predict_proba(x)[:, 1]
        return p, (time.perf_counter()-start)*1000


class FrozenMLDetector:
    """Trusted locally generated artifact, verified before deserialization."""
    def __init__(self, artifact_dir: Path, name: str, with_rules=False):
        import joblib
        from .dataset import sha
        self.manifest=json.loads((artifact_dir/"manifest.json").read_text())
        self.metadata=self.manifest["models"][name]
        self.name,self.with_rules=name,with_rules
        path=artifact_dir/self.metadata["filename"]
        if sha(path.read_bytes())!=self.metadata["artifact_sha256"]:
            raise ValueError("Frozen ML artifact hash mismatch")
        self.model=joblib.load(path)

    def __call__(self,prefix):
        from .contracts import GuardDecision
        from .rules import violations
        start=time.perf_counter()
        try:
            if prefix["control_point"]!=self.metadata["control_point"]:
                raise ValueError("Frozen detector is scoped to its trained control point")
            if self.with_rules and violations(prefix["state"]):
                return GuardDecision("BLOCK",diagnostics={"rule_violations":violations(prefix["state"]),"model":self.name},timing_ms={"total":(time.perf_counter()-start)*1000})
            score=float(self.model.predict([prefix])[0][0])
            threshold=self.metadata["threshold"]
            decision="BLOCK" if threshold!="infinity" and score>=float(threshold) else "ALLOW"
            return GuardDecision(decision,scores={"future_harm_score":score},diagnostics={"model":self.name,"threshold":threshold,"training_working_model":self.manifest["training_working_model"],"nano_calibrated":False},timing_ms={"total":(time.perf_counter()-start)*1000})
        except Exception as exc:
            return GuardDecision("UNKNOWN",diagnostics={"model":self.name,"error":f"{type(exc).__name__}: {exc}"},timing_ms={"total":(time.perf_counter()-start)*1000})


class FrozenSemanticStackDetector(FrozenMLDetector):
    def __init__(self,artifact_dir:Path,with_rules=False):
        super().__init__(artifact_dir,"semantic_stack",with_rules)

    def __call__(self,prefix,semantic_result=None):
        from .contracts import GuardDecision
        from .rules import violations
        start=time.perf_counter()
        try:
            if prefix["control_point"]!=self.metadata["control_point"]:
                raise ValueError("Frozen stack scoped to trained control point")
            if self.with_rules and violations(prefix["state"]):
                return GuardDecision("BLOCK",diagnostics={"rule_violations":violations(prefix["state"])},timing_ms={"total":(time.perf_counter()-start)*1000})
            record=semantic_result if semantic_result is not None else prefix.get("semantic_result")
            runtime=dict(prefix,prefix_id=prefix.get("prefix_id","runtime_current"))
            scores={(runtime["prefix_id"],self.model.ablation):record or {"unknown":True}}
            if semantic_vector(runtime,scores,self.model.ablation) is None:
                return GuardDecision("UNKNOWN",diagnostics={"model":"semantic_stack","error":"Current semantic result missing, malformed or UNKNOWN"},timing_ms={"total":(time.perf_counter()-start)*1000})
            probability=float(self.model.predict([runtime],semantic_scores=scores)[0][0])
            threshold=self.metadata["threshold"]
            return GuardDecision("BLOCK" if threshold!="infinity" and probability>=float(threshold) else "ALLOW",
                                 scores={"future_harm_score":probability},diagnostics={"model":"semantic_stack","threshold":threshold,"nano_calibrated":False},timing_ms={"total":(time.perf_counter()-start)*1000})
        except Exception as exc:
            return GuardDecision("UNKNOWN",diagnostics={"model":"semantic_stack","error":f"{type(exc).__name__}: {exc}"},timing_ms={"total":(time.perf_counter()-start)*1000})


class FrozenSecJevDetector:
    def __init__(self,artifact_dir:Path,with_rules=False):
        self.manifest=json.loads((artifact_dir/"manifest.json").read_text())
        self.metadata=self.manifest["secjev"]
        self.with_rules=with_rules

    def __call__(self,prefix,semantic_result=None):
        from .contracts import GuardDecision
        from .rules import violations
        start=time.perf_counter()
        try:
            if prefix["control_point"]!="P4.finstripe__create_transfer":
                raise ValueError("Frozen SecJev threshold scoped to P4")
            if self.with_rules and violations(prefix["state"]):
                return GuardDecision("BLOCK",diagnostics={"rule_violations":violations(prefix["state"])},timing_ms={"total":(time.perf_counter()-start)*1000})
            record=semantic_result if semantic_result is not None else prefix.get("semantic_result")
            current=dict(prefix,prefix_id=prefix.get("prefix_id","runtime_current"))
            scores={(current["prefix_id"],"plus_rationale"):record or {"unknown":True}}
            vector=semantic_vector(current,scores,"plus_rationale")
            if vector is None:
                return GuardDecision("UNKNOWN",diagnostics={"error":"Current semantic result missing, malformed or UNKNOWN"},timing_ms={"total":(time.perf_counter()-start)*1000})
            score=max(vector);threshold=self.metadata["threshold"]
            return GuardDecision("BLOCK" if threshold!="infinity" and score>=float(threshold) else "ALLOW",scores={k:v for k,v in zip(QUESTION_KEYS,vector)},
                                 diagnostics={"threshold":threshold,"model":"SecJev-0.8B","nano_calibrated":False,"aggregation":"max_atomic_probability"},timing_ms={"total":(time.perf_counter()-start)*1000})
        except Exception as exc:
            return GuardDecision("UNKNOWN",diagnostics={"error":f"{type(exc).__name__}: {exc}"},timing_ms={"total":(time.perf_counter()-start)*1000})
