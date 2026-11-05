"""Exercise a native FinBot guard runtime and in-process FinStripe MCP on SQLite."""
import importlib.util
import tempfile
from pathlib import Path


def test_native_runtime_rechecks_state_and_latches_stop():
    path = Path(__file__).resolve().parents[1] / "integration_replay.py"
    assert path.exists(), "API-free native enforcement replay is not implemented"
    spec = importlib.util.spec_from_file_location("integration_replay", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as directory:
        report = module.run_suite(Path(directory))
    assert report["external_connection_attempts"] == 0
    cases = {case["case"]: case for case in report["cases"]}
    assert cases["safe_then_duplicate"]["completed_transfers"] == 1
    for name in ("binding_hold", "missing_review", "stale_proposal", "wrong_recipient"):
        assert cases[name]["completed_transfers"] == 0
    assert cases["missing_review"]["guard_decisions"][0] == "UNKNOWN"
    assert all(case["stopped"] and case["later_tools_blocked"] for case in cases.values())
    assert len({case["database"] for case in cases.values()}) == len(cases)
