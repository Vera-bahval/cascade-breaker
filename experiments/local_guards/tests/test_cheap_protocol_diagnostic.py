from copy import deepcopy

import pytest

from cascade_guard.cheap_protocol_diagnostic import wrap_independent


def row(arm, block, **kwargs):
    return dict(seed=17, prefix_id="p", cut_seq=10, arm=arm, block=block,
                unknown=False, probability=.8, threshold=.5, **kwargs)


def test_independent_detection_survives_when_rule_misses():
    records = [row("R1", False), row("catboost:N:none", True)]
    original = deepcopy(records)
    result = wrap_independent(records)
    assert len(result) == 1 and result[0]["block"] and not result[0]["rule_stop"]
    assert result[0]["probability"] == .8 and result[0]["threshold"] == .5
    assert records == original


def test_rule_stop_preserved_when_component_allows():
    result = wrap_independent([row("R1", True), row("catboost:N:none", False)])
    assert result[0]["block"] and result[0]["rule_stop"]


def test_unknown_stop_preserved_without_fabricating_probability():
    component = row("scalar:N:none", True); component.update(unknown=True, probability=None)
    result = wrap_independent([row("R1", False), component])
    assert result[0]["unknown"] and result[0]["block"] and result[0]["probability"] is None


@pytest.mark.parametrize("problem", ["missing", "duplicate", "cutoff"])
def test_rule_identity_must_match_exactly(problem):
    component = row("catboost:N:none", False)
    controls = [] if problem == "missing" else [row("R1", False)]
    if problem == "duplicate":
        controls.append(row("R1", False))
    if problem == "cutoff":
        controls[0]["cut_seq"] = 11
    with pytest.raises(ValueError):
        wrap_independent([component], controls)
