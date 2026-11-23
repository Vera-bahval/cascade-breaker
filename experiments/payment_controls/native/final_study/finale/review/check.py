"""Exercise all assigned-row bounds and the independent repeat denominator."""
from . import actions
from .paired import ENDPOINTS, analyze

def check():
    a = {e: "MET" for e in ENDPOINTS}
    a.update(wrong_stop=False, total_cost_usd=.20)
    b = {**a, "financial": "VIOLATED", "total_cost_usd": .10}
    rows = [
        {"family": "f1", "kind": "main", "arm": "A", "state": "terminal", **a},
        {"family": "f1", "kind": "main", "arm": "B", "state": "terminal", **b},
        {"family": "f2", "kind": "main", "arm": "A", "state": "terminal", **a},
        {"family": "f2", "kind": "main", "arm": "B", "state": "interrupted"},
        {"family": "f1", "kind": "repeat", "replicate": 2, "arm": "B", "state": "terminal", **a},
    ]
    result = analyze(rows, "AB")
    assert result["primary_families"] == 2
    assert result["repeats"]["B"]["attempts"]["assigned"] == 1
    forward = result["pairs"]["B-A"]["endpoint"]["financial"]
    assert (forward["complete_pairs"], forward["treatment_only"], forward["comparator_only"]) == (1, 1, 0)
    assert forward["assigned_difference_range"] == [.5, 1.]
    reverse = result["pairs"]["A-B"]["endpoint"]["financial"]
    assert reverse["assigned_difference_range"] == [-1., -.5]
    assert result["arms"]["B"]["false_stop_bounds"]["assigned_rate_range"] == [0., .5]
    rows[2]["source_disposition"] = rows[3]["source_disposition"] = "must_pause_ineligible_vendor"
    result = analyze(rows, "AB")
    assert result["arms"]["B"]["false_stop_bounds"]["eligible_source_tasks"] == 1
    assert result["pairs"]["B-A"]["endpoint"]["wrong_stop"]["assigned_pairs"] == 1
    action_rows = [
        {"family": "case", "candidate_actions": [
            {"capture": 1, "disposition": "ADMISSIBLE"},
            {"capture": 2, "disposition": "MUST_STOP_OR_REVIEW"},
        ], "action_verdicts": [
            {"capture": 1, "decision": "BLOCK", "technical_error": False},
            {"capture": 2, "decision": "ALLOW", "technical_error": False},
            {"capture": 3, "decision": "ABSTAIN", "technical_error": True},
        ]}
    ]
    scored = actions.score(action_rows)
    assert scored["false_positive_actions"] == scored["missed_action_problems"] == 1
    assert scored["outcomes"]["technical"] == 1


if __name__ == "__main__":
    check()
