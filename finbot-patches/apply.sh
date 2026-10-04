#!/usr/bin/env bash
# Apply the pilot's FinBot changes on top of the pinned submodule commit (a7f6964).
# Creates local branch cascade-control-probe inside finbot/; does not touch any remote.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
git submodule update --init finbot
cd finbot
if git show-ref --quiet refs/heads/cascade-control-probe; then
  echo "finbot: branch cascade-control-probe already exists, nothing to do"
  exit 0
fi
git switch -c cascade-control-probe a7f6964fbc60da807e2544d826a5b4e20eb0c5dc
git am "$ROOT"/finbot-patches/*.patch
echo "finbot: cascade-control-probe ready ($(git rev-list --count a7f6964..HEAD) commits on top of a7f6964)"
