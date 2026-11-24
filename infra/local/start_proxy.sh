#!/usr/bin/env bash
# Starts the competition's model proxy (kit/model_proxy) on this machine, calling models on
# Vertex AI in your Google Cloud project with your own gcloud login, and writes the env file
# research/run_dev.py reads. Works on macOS and Linux.
#
# One-time:  gcloud auth application-default login
#            gcloud config set project <your-project-id>
# Then:      bash infra/local/start_proxy.sh      (from ple-submission; asks for your Hugging Face token once)
#
# The proxy keeps running in the background; its log is ~/ple-proxy.log.
# Stop it with:  kill "$(cat ~/ple-proxy.pid)"
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
PLE="${PLE:-$(cd "$(dirname "$0")/../../../ple" && pwd)}"   # the competition repo, next to ple-submission
ENV_FILE="${ENV_FILE:-$PLE/local.env}"
PROJECT="${VERTEXAI_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
: "${PROJECT:?no Google Cloud project: run gcloud config set project <id>, or set VERTEXAI_PROJECT}"

if [[ ! -f "$ENV_FILE" ]]; then
  read -rsp "Hugging Face read token (for the gated dev-set dataset): " HF
  echo
  umask 077
  cat > "$ENV_FILE" <<ENV
MODEL_PROXY_URL=http://localhost:4000
MODEL_PROXY_KEY=$(openssl rand -hex 24)
HF_TOKEN=$HF
ENV
  echo "wrote $ENV_FILE (readable only by you; *.env is git-ignored in the competition repo)"
fi
KEY="$(grep '^MODEL_PROXY_KEY=' "$ENV_FILE" | cut -d= -f2)"

if [[ -f "$HOME/ple-proxy.pid" ]] && kill -0 "$(cat "$HOME/ple-proxy.pid")" 2>/dev/null; then
  kill "$(cat "$HOME/ple-proxy.pid")" && sleep 2
fi
cd "$PLE"
VERTEXAI_PROJECT="$PROJECT" MODEL_PROXY_KEY="$KEY" nohup kit/model_proxy/start.sh >> "$HOME/ple-proxy.log" 2>&1 &
echo $! > "$HOME/ple-proxy.pid"
echo "model proxy starting for project $PROJECT (pid $(cat "$HOME/ple-proxy.pid"), log ~/ple-proxy.log)"
echo "in about a minute, check it:  python3 infra/local/check_models.py"
