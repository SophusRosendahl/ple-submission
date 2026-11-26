#!/usr/bin/env bash
# Copies full run outputs from the VM to the project's bucket (rsync: safe to repeat, never deletes).
# Runs after each rung-0 run, and can be run by hand or from a VM job.
set -uo pipefail
N=$(gcloud projects describe "${VERTEXAI_PROJECT:-ple-submission}" --format='value(projectNumber)' 2>/dev/null) || N=""
BUCKET="${RUNS_BUCKET:-gs://ple-runs-${N:-314857451555}}"
cd "$HOME/ple-submission"
gcloud storage rsync --recursive runs "$BUCKET/runs" && echo "saved runs/ to $BUCKET/runs" || echo "could not save runs/ to $BUCKET (bucket missing? see infra/gcp-vm/storage_cost_setup.sh)"
gcloud storage cp research/runs.jsonl "$BUCKET/runs.jsonl" 2>/dev/null || true
[ -f "$HOME/ple-proxy-requests.jsonl" ] && gcloud storage cp "$HOME/ple-proxy-requests.jsonl" "$BUCKET/ple-proxy-requests.jsonl" 2>/dev/null || true
