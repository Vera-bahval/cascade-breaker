"""Untraced native-path measurements on the already open scripted suite.

Fresh-process startup includes imports and temporary fixture DB preparation;
it is not a production app-start benchmark. No inference client is contacted.
"""
import argparse
import json
from pathlib import Path
import resource
import socket
import sys
from time import perf_counter
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    start = perf_counter()
    connect = socket.socket.connect
    def no_internet(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError("external connection forbidden")
        return connect(sock, address)
    times, first_complete, traces, current_test = [], [], [], [None]
    with patch.object(socket.socket, "connect", no_internet):
        suite = unittest.defaultTestLoader.loadTestsFromName("experiments.local_guards_v4.tests.test_runtime")
        from .runtime import Runtime
        check = Runtime.check
        snapshot = Runtime.snapshot
        snapshots = {}
        class CaseResult(unittest.TextTestResult):
            def startTest(self, test):
                current_test[0] = test.id()
                super().startTest(test)
        def capture_snapshot(runtime, *a, **kw):
            obj = snapshot(runtime, *a, **kw)
            snapshots[id(runtime)] = obj
            return obj
        def measure(runtime, *a, **kw):
            then = perf_counter()
            snapshots.pop(id(runtime), None)
            try:
                result = check(runtime, *a, **kw)
                if not first_complete:
                    first_complete.append(perf_counter() - start)
                return result
            finally:
                times.append((perf_counter() - then) * 1000)
                traces.append({"test": current_test[0], "profile": runtime.profile,
                    "checkpoint": a[0] if a else kw.get("checkpoint"),
                    "observation": snapshots.get(id(runtime)),
                    "result": runtime.local_stop or (runtime.decisions[-1] if runtime.decisions else None)})
        with patch.object(Runtime, "check", measure), patch.object(Runtime, "snapshot", capture_snapshot):
            outcome = unittest.TextTestRunner(verbosity=1, stream=sys.stderr, resultclass=CaseResult).run(suite)
    ordered = sorted(times)
    report = {"kind": "fresh-process untraced existing native scripted workload",
        "tests": outcome.testsRun, "successful": outcome.wasSuccessful(), "checks": len(times),
        "p50_ms": ordered[(len(ordered) - 1) // 2], "p95_ms": ordered[__import__("math").ceil(.95 * len(ordered)) - 1],
        "first_completed_checkpoint_seconds_including_imports_and_fixture_setup": first_complete[0],
        "whole_workload_seconds": perf_counter() - start,
        "peak_process_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "new_inference_api_calls": 0,
        "native_checkpoint_traces": traces,
        "limitations": ["Local mixed positive/negative checkpoints, not production traffic latency.",
            "Full Runtime.check includes source reads and sidecar operations; guard-only timing is separate.",
            "Startup includes test fixture database creation; RSS includes native dependencies.",
            "Local compute/development USD cost is not measured."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "native_checkpoint_traces"}, indent=2))
    return 0 if outcome.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
