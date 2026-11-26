# Job 4: status of the rung-0 run (read only).
tmux ls 2>&1 | head -3
echo "--- VM uptime / disk:"; uptime -p; df -h / | tail -1
echo "--- dataset cache files: $(find ~/.cache/plebench -type f 2>/dev/null | wc -l) / 16425"
echo "--- containers: $(docker ps -q | wc -l)"
echo "--- rung0.log (last 25 lines, progress bars collapsed):"
tail -c 6000 ~/rung0.log | tr '\r' '\n' | tail -25
