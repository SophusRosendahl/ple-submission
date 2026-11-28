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
# Run the competition's proxy unchanged, plus one observing callback (request_log.py) that writes one
# JSON line per model request, harness and judge alike, to ~/ple-proxy-requests.jsonl. The competition's
# own callbacks are linked, not copied, so they stay exactly as shipped. If anything below fails we
# fall back to the stock proxy: a run matters more than its log.
SRC="$PLE/kit/model_proxy"; CONF="$HOME/ple-proxy-config"; START="$SRC/start.sh"
mkdir -p "$CONF"
if ln -sf "$SRC/effort_default.py" "$CONF/effort_default.py" && ln -sf "$SRC/judge_fallback.py" "$CONF/judge_fallback.py" \
   && cp "$(dirname "$0")/request_log.py" "$CONF/request_log.py" && cp "$SRC/start.sh" "$CONF/start.sh" \
   && sed -E 's/^(  callbacks: \[.*)\]/\1, request_log.instance]/' "$SRC/config.yaml" > "$CONF/config.yaml" \
   && grep -q 'request_log.instance' "$CONF/config.yaml"; then
  START="$CONF/start.sh"; echo "request log on: ~/ple-proxy-requests.jsonl"
else
  echo "WARNING: could not set up the request log: starting the stock proxy without it"
fi
VERTEXAI_PROJECT="$PROJECT" MODEL_PROXY_KEY="$KEY" nohup "$START" >> "$HOME/ple-proxy.log" 2>&1 &
echo $! > "$HOME/ple-proxy.pid"
echo "model proxy starting for project $PROJECT (pid $(cat "$HOME/ple-proxy.pid"), log ~/ple-proxy.log)"
echo "in about a minute, check it:  python3 infra/local/check_models.py"
