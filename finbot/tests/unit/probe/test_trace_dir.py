"""Unit tests for per-workflow trace files."""

import json

import pytest

from finbot.probe import trace as probe_trace


@pytest.mark.unit
def test_writes_one_file_per_workflow(tmp_path):
    with probe_trace.record_to_dir(str(tmp_path), "wf_1", task_data={"invoice_id": 3}):
        probe_trace.record("delegation", target="invoice")
    data = json.loads((tmp_path / "wf_1.json").read_text())
    assert data["task_data"] == {"invoice_id": 3}
    assert [s["kind"] for s in data["steps"]] == ["delegation"]
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.unit
def test_writes_file_even_when_the_run_fails(tmp_path):
    with pytest.raises(RuntimeError):
        with probe_trace.record_to_dir(str(tmp_path), "wf_2"):
            probe_trace.record("summary", agent="invoice_agent")
            raise RuntimeError("boom")
    assert (tmp_path / "wf_2.json").exists()


@pytest.mark.unit
def test_noop_without_dir_or_with_outer_recorder(tmp_path):
    with probe_trace.record_to_dir(None, "wf_3"):
        assert probe_trace.active_recorder() is None
    with probe_trace.open_recorder() as outer:
        with probe_trace.record_to_dir(str(tmp_path), "wf_4"):
            probe_trace.record("delegation", target="fraud")
    assert len(outer.steps) == 1
    assert not (tmp_path / "wf_4.json").exists()
