#!/usr/bin/env bash
# Starts the competition's model proxy (kit/model_proxy) on this VM in a tmux session, and
# writes ~/ple/local.env for research/run_dev.py. The proxy reaches Vertex AI as the VM's
# service account: no keys involved.
#
#   bash start_proxy.sh            # prompts for your Hugging Face read token on first run
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
PLE="${PLE:-$HOME/ple}"
ENV_FILE="$PLE/local.env"
PROJECT="$(curl -s -H 'Metadata-Flavor: Google' http://metadata.google.internal/computeMetadata/v1/project/project-id)"

if [[ ! -f "$ENV_FILE" ]]; then
  read -rsp "Hugging Face read token (for the gated dev-set dataset): " HF
  echo
  umask 077
  cat > "$ENV_FILE" <<ENV
MODEL_PROXY_URL=http://localhost:4000
MODEL_PROXY_KEY=$(openssl rand -hex 24)
HF_TOKEN=$HF
ENV
  echo "wrote $ENV_FILE (readable only by you)"
fi
KEY="$(grep '^MODEL_PROXY_KEY=' "$ENV_FILE" | cut -d= -f2)"

tmux kill-session -t proxy 2>/dev/null || true
tmux new-session -d -s proxy \
  "cd '$PLE' && VERTEXAI_PROJECT='$PROJECT' MODEL_PROXY_KEY='$KEY' kit/model_proxy/start.sh 2>&1 | tee -a ~/proxy.log"
echo "model proxy starting in tmux session 'proxy' for project $PROJECT (log: ~/proxy.log)"
echo "check it in about a minute:  python3 $(dirname "$0")/check_models.py"
