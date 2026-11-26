# stop: yes
# pull: research/runs.jsonl
# Finish the single-task runs: add the detail fields to their records, copy the raw outputs to the bucket, stop the VM.
cd ~/ple-submission
python3 research/tracker.py enrich run-003 runs/naive-A-20261126-180514
python3 research/tracker.py enrich run-004 runs/naive-A-20261126-181344
python3 research/tracker.py list
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -2
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
