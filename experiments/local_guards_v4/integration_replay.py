"""API-free scripted native replay; isolated test DB is set before FinBot imports.

Run from repository root with the existing native Python environment:
  python -m experiments.local_guards_v4.integration_replay [--output /tmp/result.json]
This is a local native-path integration suite, not archive or held-out accuracy.
"""
import argparse
import json
from pathlib import Path
import socket
import math
from statistics import median
import sys
from time import perf_counter
import tracemalloc
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    started = perf_counter()
    tracemalloc.start()
    original_connect = socket.socket.connect
    def no_external(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            raise AssertionError('external sockets forbidden in v4 replay')
        return original_connect(sock, address)
    with patch.object(socket.socket, 'connect', no_external), patch.object(
        socket, 'create_connection', side_effect=AssertionError('external sockets forbidden')):
        suite = unittest.defaultTestLoader.loadTestsFromName(
            'experiments.local_guards_v4.tests.test_runtime')
        from .runtime import Runtime
        original_check = Runtime.check
        check_times = []
        def measured_check(runtime, *check_args, **check_kwargs):
            start = perf_counter()
            try:
                return original_check(runtime, *check_args, **check_kwargs)
            finally:
                check_times.append((perf_counter() - start) * 1000)
        with patch.object(Runtime, 'check', measured_check):
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stderr).run(suite)
    elapsed = perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {'suite': 'native_scripted_integration', 'tests': result.testsRun,
        'failures': len(result.failures), 'errors': len(result.errors),
        'successful': result.wasSuccessful(), 'new_inference_api_requests': 0,
        'external_sockets': 'rejected', 'elapsed_seconds_including_imports': elapsed,
        'python_tracemalloc_peak_bytes_including_imports': peak,
        'full_checkpoint_check_count': len(check_times),
        'full_checkpoint_check_median_ms_with_tracemalloc': median(check_times) if check_times else None,
        'full_checkpoint_check_p95_ms_with_tracemalloc': sorted(check_times)[math.ceil(.95 * len(check_times)) - 1] if check_times else None,
        'limitations': ['synthetic scripted executors, not model performance',
            'sidecar and source DB writes are independent',
            'current-read freshness only; unobserved external ABA is not detected']}
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n')
    print(rendered)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
