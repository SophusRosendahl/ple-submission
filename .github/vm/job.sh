# sync: no
# pull: research/runs.jsonl
# Save the finished rung-0 runs: raw folders to the bucket, records back into git (read-only on the run).
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
echo "saving runs/ to $B"
cd ~/ple-submission && gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -3
gcloud storage cp research/runs.jsonl "$B/runs.jsonl" 2>&1 | tail -1
echo "bucket now holds: $(gcloud storage du -s "$B" 2>&1 | tail -1)"
echo "records on the VM: $(wc -l < research/runs.jsonl)"; cut -c1-110 research/runs.jsonl | sed 's/^/  /'
