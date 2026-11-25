#!/usr/bin/env bash
# Starts the run VM and gets it ready for a run, from Cloud Shell or your Mac (signed in to gcloud):
#   bash infra/gcp-vm/vm_up.sh                 # start, update repos, start the model proxy, check models
#   RUN=1 bash infra/gcp-vm/vm_up.sh           # ... and start the rung-0 run in tmux
#   ENV_FILE=~/path/local.env bash ...         # also copy a fixed local.env (HF token) to the VM first
# Follow a run:  gcloud compute ssh ple-runner --zone us-central1-a -- tail -f rung0.log
set -euo pipefail
ZONE="${ZONE:-us-central1-a}"
NAME="${NAME:-ple-runner}"
BRANCH="${BRANCH:-$(git -C "$(dirname "$0")" rev-parse --abbrev-ref HEAD)}"   # branch the VM checks out
SSH=(gcloud compute ssh "$NAME" --zone "$ZONE")

gcloud compute instances start "$NAME" --zone "$ZONE"
for i in $(seq 30); do "${SSH[@]}" --command true 2>/dev/null && break; sleep 10; done

if [[ -n "${ENV_FILE:-}" ]]; then
  gcloud compute scp "$ENV_FILE" "$NAME:ple/local.env" --zone "$ZONE"
  "${SSH[@]}" --command 'chmod 600 ~/ple/local.env'
fi

"${SSH[@]}" --command "set -e
  git -C ~/ple pull --ff-only
  git -C ~/ple-submission fetch origin $BRANCH
  git -C ~/ple-submission checkout -B $BRANCH FETCH_HEAD
"'
  grep -q "^HF_TOKEN=." ~/ple/local.env || { echo "HF_TOKEN missing in ~/ple/local.env"; exit 1; }
  bash ~/ple-submission/infra/local/start_proxy.sh
  sleep 60
  python3 ~/ple-submission/infra/local/check_models.py'

if [[ "${RUN:-0}" == "1" ]]; then
  "${SSH[@]}" --command 'tmux new -d -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"'
  echo "rung 0 started in tmux session rung0 on $NAME (log ~/rung0.log)"
fi
echo "Stop the VM when done: gcloud compute instances stop $NAME --zone $ZONE"
