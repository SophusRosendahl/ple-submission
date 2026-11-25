#!/usr/bin/env bash
# Rung 0 model comparison, run on the VM (in tmux, so it survives a dropped SSH session):
#   tmux new -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
# Runs the naive harness on all 15 half-A tasks, 5 at a time, judged by the dev judge
# (Gemini 4 Neon): first with Gemini 3.8 Flash, then with Gemini 4 Neon.
# The first run builds the app-task images (an hour or more).
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/ple-submission"
ENV_FILE="$HOME/ple/local.env"
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE: run infra/local/start_proxy.sh first"; exit 1; }

for MODEL in gemini-3.8-flash gemini-4-neon; do
  echo "=== rung 0 with $MODEL ($(date -u +%FT%TZ)) ==="
  python3 research/run_dev.py --ple "$HOME/ple" --entry harnesses/naive \
      --model "$MODEL" --judge dev --trials 5 --env-file "$ENV_FILE" \
      --label "rung 0: single model call, files as text ($MODEL)"
done
echo "=== done ($(date -u +%FT%TZ)) ==="
