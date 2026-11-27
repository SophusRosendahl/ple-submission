# stop: idle
# pull: research/runs.jsonl research/run-details
# Rung 0 v5 repeated 3 times (more observations of the same setup): one task, both models, single call, images attached, effort low.
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rung0 2>/dev/null; then echo "rung0 already running: waiting for it"; else
  tmux new -d -s rung0 "for REP in 1 2 3; do TASKS=data-hall-mep-routing EFFORT=low REP=\$REP bash ~/ple-submission/infra/gcp-vm/rung0.sh; done 2>&1 | tee ~/rung0.log"
fi
sleep 30
for i in $(seq 280); do tmux has-session -t rung0 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung0 2>/dev/null; then echo "STILL RUNNING after 70 min: left running, VM stays on"; tr '\r' '\n' < ~/rung0.log | grep -v '^Fetching' | tail -6 | cut -c1-200; exit 0; fi
echo "runs ended"
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if 'repeat' in r['label']))")
echo "repeat runs: $IDS"; python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
