#!/usr/bin/env python3
"""Bind the frozen generation-05 Jev watcher to its prospective clock limits."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import runpy
import sys

METHOD_SHA256='905199e01d99950fe905cb741d27bee56df5be745819d62d64820fb119747d44'


def timestamp(value):
 parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
 if parsed.utcoffset() is None:raise ValueError('An explicit timezone is required')
 return parsed.timestamp()


def validate_clock(method, deadline, cutoff):
 method=Path(method)
 if hashlib.sha256(method.read_bytes()).hexdigest()!=METHOD_SHA256:
  raise ValueError('Expected the pinned generation-05 method freeze')
 spec=json.loads(method.read_text())
 requested_deadline=timestamp(deadline);requested_cutoff=timestamp(cutoff)
 if requested_deadline>timestamp(spec['technical_runner_deadline_utc']):
  raise ValueError('CLI deadline exceeds the frozen absolute deadline')
 if requested_cutoff!=timestamp(spec['inference_cutoff_utc']):
  raise ValueError('CLI model cutoff differs from the frozen prospective cutoff')
 if requested_cutoff>requested_deadline:
  raise ValueError('Model cutoff exceeds CLI deadline')
 return spec


def main():
 parser=argparse.ArgumentParser(add_help=False)
 parser.add_argument('--method-freeze',type=Path,required=True)
 parser.add_argument('--deadline',required=True);parser.add_argument('--model-cutoff',required=True)
 args,_=parser.parse_known_args()
 validate_clock(args.method_freeze,args.deadline,args.model_cutoff)
 base=Path(__file__).with_name('run_guard_v2_jev_serial_v5.py')
 # The base watcher verifies every frozen source/input file before any work.
 sys.argv=[str(base),*sys.argv[1:]]
 runpy.run_path(str(base),run_name='__main__')


if __name__=='__main__':main()
