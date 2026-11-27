# stop: idle
# pull: research/runs.jsonl research/run-details
# Environment audit: what can a model see and reach inside the task container? Read-only listing, no model calls
# (harnesses/audit). Recorded as a diagnostic run, not a measurement.
cd ~/ple-submission && git log -1 --oneline
MODELS=gemini-3.8-flash TASKS=data-hall-mep-routing EFFORT=low bash infra/gcp-vm/audit.sh 2>&1 | tr '\r' '\n' | grep -v '^Fetching' | tail -12 | cut -c1-200
IDS=$(python3 -c "
import json
print(' '.join(r['run_id'] for r in map(json.loads, open('research/runs.jsonl')) if r['label'].startswith('environment audit')))")
echo "audit runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
