# stop: idle
# pull: research/runs.jsonl research/run-details research/gcp-budget-check.txt
# 1) stop what the cancelled rung 1 v2 job left running (it had no call budget), 2) read-only budget/quota check,
# 3) rung 1 v3: input guard + 20-call budget, both models, one task, effort low.
cd ~/ple-submission && git log -1 --oneline
tmux kill-session -t rung1 2>/dev/null; pkill -f research/run_dev.py; pkill -f eval/run.py; pkill -f harbor; sleep 5
echo "containers before kill:"; docker ps --format '{{.Names}} {{.Image}}' | cut -c1-120 | head
docker ps -q | xargs -r docker kill >/dev/null 2>&1; sleep 2; echo "containers after: $(docker ps -q | wc -l)"
OUT=research/gcp-budget-check.txt
{
  echo "== checked $(date -u +%FT%TZ) by the VM's own service account: $(gcloud config get-value account 2>/dev/null)"
  echo; echo "== billing link of the project"
  gcloud billing projects describe ple-submission 2>&1 | head -12
  BA=$(gcloud billing projects describe ple-submission --format='value(billingAccountName)' 2>/dev/null | sed 's#billingAccounts/##')
  echo; echo "== budgets on billing account '${BA:-unknown}'"
  [ -n "$BA" ] && gcloud billing budgets list --billing-account="$BA" 2>&1 | head -40 || echo "(no billing account id: skipped)"
  echo; echo "== Vertex AI quota overrides on the project (consumer quota)"
  gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/ple-submission --filter="metric~gemini" 2>&1 | head -40
} > "$OUT" 2>&1
head -14 "$OUT" | cut -c1-180
tmux new -d -s rung1 "TASKS=data-hall-mep-routing EFFORT=low bash ~/ple-submission/infra/gcp-vm/rung1.sh 2>&1 | tee ~/rung1.log"
sleep 30
for i in $(seq 280); do tmux has-session -t rung1 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung1 2>/dev/null; then echo "STILL RUNNING after 70 min: left running, VM stays on"; tr '\r' '\n' < ~/rung1.log | grep -v '^Fetching' | tail -6 | cut -c1-200; exit 0; fi
echo "runs ended"; tr '\r' '\n' < ~/rung1.log | grep -v '^Fetching' | tail -12 | cut -c1-200
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if r['label'].startswith('rung 1 v3')))")
echo "rung 1 v3 runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
