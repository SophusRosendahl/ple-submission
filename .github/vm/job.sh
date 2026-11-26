# sync: no
# Can the VM write to the run-outputs bucket? And where is rung 0?
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>&1 | tail -1); B="gs://ple-runs-$N"
echo "bucket: $B"
echo "write test: $(echo "vm check $(date -u +%FT%TZ)" | gcloud storage cp - "$B/_check.txt" 2>&1 | tail -1)"
echo "list: $(gcloud storage ls "$B" 2>&1 | head -5 | tr '\n' ' ')"
echo "--- rung 0:"; tmux ls 2>&1 | head -2; echo "containers: $(docker ps -q | wc -l)"
tail -c 2500 ~/rung0.log | tr '\r' '\n' | tail -10
ls ~/ple-submission/runs/*/ 2>/dev/null | head -8
