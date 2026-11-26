# sync: no
# Status of rung 0 (read only), and the layout of a run folder.
tmux ls 2>&1 | head -3
echo "uptime: $(uptime -p) | containers: $(docker ps -q | wc -l) | disk: $(df -h / | tail -1 | awk '{print $3" used, "$5}')"
echo "--- rung0.log (tail):"; tail -c 4000 ~/rung0.log | tr '\r' '\n' | tail -22
R=$(ls -dt ~/ple-submission/runs/*/ 2>/dev/null | head -1); echo "--- newest run folder: $R"
ls "$R" 2>/dev/null | head -20
echo "--- results.json:"; [ -f "$R/results.json" ] && head -c 1500 "$R/results.json"
echo "--- one trial dir:"; T=$(find "$R" -maxdepth 3 -type d -name '*__*' 2>/dev/null | head -1); echo "$T"; find "$T" -maxdepth 2 -type f 2>/dev/null | head -25
echo "--- research/runs.jsonl lines: $(wc -l < ~/ple-submission/research/runs.jsonl)"
