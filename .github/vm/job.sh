# stop: idle
# pull: research/runs.jsonl research/run-details
# Rung 1 v4 (v3 + ifcopenshell unavailable to the agent) and rung 2 v2 (v1 + ifcopenshell unavailable + batching + scratch logging),
# both models, one task, effort low. Two tmux sessions in parallel, each with its own process group.
cd ~/ple-submission && git log -1 --oneline
for R in 1 2; do
  if tmux has-session -t rung$R 2>/dev/null; then echo "rung$R already running"; else
    tmux new -d -s rung$R "TASKS=data-hall-mep-routing EFFORT=low bash ~/ple-submission/infra/gcp-vm/rung$R.sh 2>&1 | tee ~/rung$R.log"
  fi
done
sleep 30
for i in $(seq 280); do tmux has-session -t rung1 2>/dev/null || tmux has-session -t rung2 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung1 2>/dev/null || tmux has-session -t rung2 2>/dev/null; then echo "STILL RUNNING after 70 min: left running, VM stays on"; exit 0; fi
for R in 1 2; do echo "== rung$R log"; tr '\r' '\n' < ~/rung$R.log | grep -v '^Fetching' | tail -6 | cut -c1-200; done
IDS=$(python3 -c "
import json
rs=[json.loads(l) for l in open('research/runs.jsonl') if l.strip()]
print(' '.join(r['run_id'] for r in rs if r['label'].startswith(('rung 1 v4','rung 2 v2'))))")
echo "new runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
