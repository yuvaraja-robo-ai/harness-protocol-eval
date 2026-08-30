#!/usr/bin/env bash
# Make progress on a grid whenever the endpoint happens to be awake.
#
# The model host is a laptop on wifi that sleeps. A grid that must run in one unbroken
# session cannot finish against it, so this loop takes whatever cells it can get: when
# the host answers it resumes the grid, when the host vanishes it waits.
#
# `--resume` keeps completed cells and redoes the ones the endpoint broke. An
# llm_error is not a result and must not permanently occupy a cell, where it would
# later be counted as though the agent had been asked the question.
#
#   ./keep_running.sh [MANIFEST] [RUNS_DIR] [TARGET_RUNS] [LOG]
set -u
cd "$(dirname "$0")"

MANIFEST="${1:-MANIFEST.json}"
RUNS_DIR="${2:-runs}"
TARGET="${3:-27}"
LOG="${4:-grid.log}"
HOST_URL="${S18_OLLAMA_URL:-http://192.168.32.2:11434}"
POLL=60
STATUS="keep_running.log"

echo "[$(date -Is)] supervising $MANIFEST -> $RUNS_DIR (target $TARGET)" >> "$STATUS"

while true; do
  if curl -s --max-time 5 "$HOST_URL/api/tags" -o /dev/null; then
    echo "[$(date -Is)] endpoint up; resuming" >> "$STATUS"
    S18_COOLDOWN="${S18_COOLDOWN:-10}" python3 -u run_grid.py \
      --manifest "$MANIFEST" --runs-dir "$RUNS_DIR" --resume >> "$LOG" 2>&1
    evaluable=$(RUNS_DIR="$RUNS_DIR" python3 - <<'PY'
import glob, json, os
n = 0
for f in glob.glob(os.path.join(os.environ["RUNS_DIR"], "*.json")):
    d = json.load(open(f))
    if d.get("ended") not in {"llm_error", "adapter_error"}:
        n += 1
print(n)
PY
)
    echo "[$(date -Is)] pass finished: $evaluable evaluable of $TARGET" >> "$STATUS"
    if [ "$evaluable" -ge "$TARGET" ]; then
      echo "[$(date -Is)] grid complete" >> "$STATUS"
      exit 0
    fi
  else
    echo "[$(date -Is)] endpoint down; waiting ${POLL}s" >> "$STATUS"
  fi
  sleep "$POLL"
done
