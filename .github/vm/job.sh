# stop: idle
# pull: research/runs.jsonl research/run-details
# 1) bring back the environment audit run (its first job was killed in the foreground before it could pull: run in tmux, which has its own process group);
# 2) rung 2 v1 on both models, one task, effort low, 40-call budget.
cd ~/ple-submission && git log -1 --oneline
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if r['label'].startswith('environment audit')))")
echo "audit runs on the VM: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
if tmux has-session -t rung2 2>/dev/null; then echo "rung2 already running: waiting for it"; else
  tmux new -d -s rung2 "TASKS=data-hall-mep-routing EFFORT=low bash ~/ple-submission/infra/gcp-vm/rung2.sh 2>&1 | tee ~/rung2.log"
fi
sleep 30
for i in $(seq 280); do tmux has-session -t rung2 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung2 2>/dev/null; then echo "STILL RUNNING after 70 min: left running, VM stays on"; tr '\r' '\n' < ~/rung2.log | grep -v '^Fetching' | tail -6 | cut -c1-200; exit 0; fi
echo "runs ended"; tr '\r' '\n' < ~/rung2.log | grep -v '^Fetching' | tail -12 | cut -c1-200
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if r['label'].startswith('rung 2 v1')))")
echo "rung 2 v1 runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
