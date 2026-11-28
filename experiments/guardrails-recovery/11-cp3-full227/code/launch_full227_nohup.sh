#!/bin/zsh
# CP3-FULL227: resume the series detached from the controlling session (own session via setsid + nohup), with PID file and log.
#   zsh launch_full227_nohup.sh <approval-hash>     start (refuses if any runner is alive)
#   zsh launch_full227_nohup.sh status              is it running, last lines of the log
# The runner itself re-checks the approval hash, the provider route and resumability before any paid call.
set -eu
CP3="${PROJECT_ROOT:?set PROJECT_ROOT}/CascadeLab/iv_lab/finbot-cp3"
OUT="$PROJECT_ROOT/CascadeLab/iv_lab/analysis/CHECKPOINT3/tests/CP3_FULL227"
PY="$PROJECT_ROOT/finbot-pr477/.venv/bin/python"
PIDFILE=$OUT/full227-v1.runner.pid
LOG=$OUT/FULL227_V1_CONSOLE.txt
# free stub test of this launcher: same code path, stub process instead of the runner, pid/log in a temp dir
STUB=${CP3_LAUNCH_STUB_DIR:-}
if [[ -n $STUB ]]; then PIDFILE=$STUB/stub.pid; LOG=$STUB/stub.log; fi

if [[ "${1:-}" == "status" ]]; then
  if [[ -f $PIDFILE ]] && kill -0 "$(head -1 $PIDFILE)" 2>/dev/null; then
    echo "RUNNING pid=$(head -1 $PIDFILE) since $(sed -n 2p $PIDFILE)"
  else
    echo "NOT RUNNING (pidfile: $( [[ -f $PIDFILE ]] && cat $PIDFILE | tr '\n' ' ' || echo none))"
  fi
  echo "rows: $(grep -c . $OUT/full227-v1/rows.jsonl) of 681"
  tail -8 $LOG
  exit 0
fi

HASH=${1:?approval hash required}
[[ $HASH =~ '^[0-9a-f]{64}$' ]] || { echo "bad hash"; exit 2; }

# 1. no second runner (any process, also one started outside this script)
if pgrep -f runner_cp3_full >/dev/null; then
  echo "REFUSED: a runner is already alive:"; pgrep -fl runner_cp3_full; exit 3
fi
if [[ -f $PIDFILE ]] && kill -0 "$(head -1 $PIDFILE)" 2>/dev/null; then
  echo "REFUSED: pid $(head -1 $PIDFILE) from $PIDFILE is alive"; exit 3
fi

# 2. series must be resumable (free, read-only)
cd $CP3
if [[ -z $STUB ]]; then
  RC=$(PYTHONPATH=. $PY -B scripts/runner_cp3_full.py resume-check 2>/dev/null)
  echo "$RC" | grep -q '"resumable": true' || { echo "REFUSED: $RC"; exit 4; }
fi

# 3. start in its own session: survives the end of the controlling / terminal session
echo "=== segment resume via nohup $(date -u +%FT%TZ) hash=${HASH[1,8]}… ===" >> $LOG
PYTHONPATH=. $PY -B - "$PY" "$HASH" "$LOG" "$PIDFILE" "$STUB" <<'EOF'
import os, subprocess, sys, datetime
py, h, log, pidfile, stub = sys.argv[1:6]
cmd = ([py, "-c", "import time; print('stub runner_cp3_full alive', flush=True); time.sleep(90)", "runner_cp3_full_stub"]
       if stub else [py, "-B", "scripts/runner_cp3_full.py", "full227-resume", h])
with open(log, "ab") as fh:
    p = subprocess.Popen(["/usr/bin/nohup", *cmd],
                         stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True,
                         env=dict(os.environ, PYTHONPATH="."))
open(pidfile, "w").write(f"{p.pid}\n{datetime.datetime.now(datetime.timezone.utc):%Y-%m-%dT%H:%M:%SZ}\n{h}\n")
print(f"STARTED pid={p.pid} log={log}")
EOF
sleep 5
kill -0 "$(head -1 $PIDFILE)" 2>/dev/null && echo "alive after 5 s" || { echo "EXITED early:"; tail -15 $LOG; exit 5; }
