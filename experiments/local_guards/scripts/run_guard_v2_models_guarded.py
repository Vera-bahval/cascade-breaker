#!/usr/bin/env python3
"""External ownership guard for the unchanged frozen v5 inference runner.

This wrapper is not the active 05 runner and must not be launched against its
output while it is running. Future executions should enter through this guard.
"""
from __future__ import annotations
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


class OutputBusy(RuntimeError):
 pass


def pid_exists(pid):
 if isinstance(pid,bool) or not isinstance(pid,int) or pid<=0:return False
 try:os.kill(pid,0)
 except ProcessLookupError:return False
 except PermissionError:return True
 return True


def reject_active_owner(output):
 state_path=Path(output)/'runtime-run.json'
 if not state_path.exists():return
 try:state=json.loads(state_path.read_text())
 except (ValueError,OSError) as exc:raise OutputBusy('Cannot validate existing runner ownership; refusing to start') from exc
 child_pid=(state.get('active_child') or {}).get('pid')
 if pid_exists(child_pid):raise OutputBusy(f'Output still has a live model child PID {child_pid}')
 if state.get('status')=='RUNNING':
  pid=state.get('pid')
  if isinstance(pid,bool) or not isinstance(pid,int) or pid<=0:raise OutputBusy('RUNNING owner PID cannot be validated')
  if pid_exists(pid):raise OutputBusy(f'Output already has a live RUNNING owner PID {pid}')


@contextlib.contextmanager
def output_ownership(output):
 output=Path(output);output.mkdir(parents=True,exist_ok=True)
 # Never truncate this lock or the scientific runtime state on a rejected start.
 with (output/'.orchestrator-entrypoint.lock').open('a+') as handle:
  try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError as exc:raise OutputBusy('Another guarded entrypoint owns this output directory') from exc
  try:
   reject_active_owner(output)
   yield
  finally:fcntl.flock(handle,fcntl.LOCK_UN)


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--workspace',type=Path,default=Path.cwd())
 parser.add_argument('--inputs',type=Path,required=True)
 parser.add_argument('--output-directory',type=Path,required=True)
 parser.add_argument('--freeze-manifest',type=Path,required=True)
 parser.add_argument('--deadline',required=True)
 parser.add_argument('--model-cutoff',required=True)
 parser.add_argument('--resource-lease',action='store_true')
 args=parser.parse_args()
 if not args.resource_lease:raise PermissionError('Explicit current root resource lease is required')
 workspace=args.workspace.resolve();output=args.output_directory.resolve()
 command=[str(workspace/'.venv-cheap/bin/python'),str(workspace/'experiments/local_guards/scripts/run_guard_v2_models_v5.py'),
   '--workspace',str(workspace),'--inputs',str(args.inputs.resolve()),'--output-directory',str(output),
   '--freeze-manifest',str(args.freeze_manifest.resolve()),'--deadline',args.deadline,'--model-cutoff',args.model_cutoff,'--resource-lease']
 with output_ownership(output):
  child=subprocess.Popen(command,cwd=workspace,start_new_session=True)
  def forward(number,frame):
   if child.poll() is None:child.send_signal(number)
  old_handlers={number:signal.signal(number,forward) for number in (signal.SIGTERM,signal.SIGINT)}
  try:
   # Hold ownership until the frozen runner finishes its own child cleanup and
   # writes models_unloaded, including when this wrapper receives termination.
   return child.wait()
  finally:
   for number,handler in old_handlers.items():signal.signal(number,handler)


if __name__=='__main__':raise SystemExit(main())
