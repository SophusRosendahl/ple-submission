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

# The proxy dies with the VM (nohup, no service), so make sure it answers where task containers
# reach it (Docker's bridge address), starting it if not. Never restart a proxy that is up.
up() { curl -s -o /dev/null -m 5 "http://172.17.0.1:4000/health/liveliness"; }
if ! up; then
  echo "model proxy not answering: starting it"
  VERTEXAI_PROJECT="${VERTEXAI_PROJECT:-ple-submission}" bash "$HOME/ple-submission/infra/local/start_proxy.sh"
  for _ in $(seq 40); do up && break; sleep 5; done
  up || { echo "model proxy still not answering after 200 s: see ~/ple-proxy.log"; exit 1; }
fi

# TASKS=<id,id> limits the run to those tasks (default: all of half A)
TASK_ARGS=(); [[ -n "${TASKS:-}" ]] && TASK_ARGS=(--tasks "$TASKS")
# EFFORT=low|medium|high|max sets the reasoning level of the harness's model calls (default: the proxy's highest)
EFFORT_ARGS=(); [[ -n "${EFFORT:-}" ]] && EFFORT_ARGS=(--effort "$EFFORT")

for MODEL in gemini-3.8-flash gemini-4-neon; do
  echo "=== rung 0 with $MODEL ($(date -u +%FT%TZ)) ==="
  python3 research/run_dev.py --ple "$HOME/ple" --entry harnesses/naive \
      --model "$MODEL" --judge dev --trials 5 --env-file "$ENV_FILE" "${TASK_ARGS[@]}" "${EFFORT_ARGS[@]}" \
      --label "rung 0 v5: single call, images attached, reasoning effort ${EFFORT:-default} ($MODEL)" || echo "=== run for $MODEL failed ==="
  bash "$HOME/ple-submission/infra/gcp-vm/save_runs.sh" || true   # keep the full outputs off the VM disk
done
echo "=== done ($(date -u +%FT%TZ)) ==="
