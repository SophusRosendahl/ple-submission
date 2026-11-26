# sync: no
# Rung 0 status (read only). Never touches the run.
echo "uptime: $(uptime -p) | containers: $(docker ps -q | wc -l) | disk: $(df -h / | tail -1 | awk '{print $3" used, "$5}')"
tmux ls 2>&1 | head -2
echo "--- rung0.log (progress lines, tail):"
tr '\r' '\n' < ~/rung0.log | grep -v '^Fetching' | tail -40 | cut -c1-260
echo "--- runs:"; ls -d ~/ple-submission/runs/*/ 2>/dev/null; echo "recorded runs: $(wc -l < ~/ple-submission/research/runs.jsonl)"
for R in $(ls -d ~/ple-submission/runs/*/ 2>/dev/null); do echo "== $R"; ls "$R" | head -12; [ -f "$R/results.json" ] && head -c 1200 "$R/results.json"; echo; done
