# stop: idle
# pull: research/runs.jsonl research/run-details
# Rung 1 v1, Neon again: the first Neon run (run-018) failed on its first call (Pi sent a thinking budget; patch_pi.py fixes it).
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rung1 2>/dev/null; then echo "rung1 already running: waiting for it"; else
  tmux new -d -s rung1 "MODELS=gemini-4-neon TASKS=data-hall-mep-routing EFFORT=low bash ~/ple-submission/infra/gcp-vm/rung1.sh 2>&1 | tee ~/rung1.log"
fi
sleep 30
for i in $(seq 280); do tmux has-session -t rung1 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung1 2>/dev/null; then echo "STILL RUNNING after 70 min: left running, VM stays on"; tr '\r' '\n' < ~/rung1.log | grep -v '^Fetching' | tail -6 | cut -c1-200; exit 0; fi
echo "runs ended"; tr '\r' '\n' < ~/rung1.log | grep -v '^Fetching' | tail -12 | cut -c1-200
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if r['label'].startswith('rung 1')))")
echo "rung 1 runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
