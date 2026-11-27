# stop: idle
# pull: research/runs.jsonl research/run-details
# Re-pull the results of the 3 rung 0 repeats (the first pull's push was rejected). No new run is started.
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rung0 2>/dev/null; then echo "rung0 still running: not collecting"; exit 0; fi
echo "runs ended"
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if 'repeat' in r['label']))")
echo "repeat runs: $IDS"; python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
