# sync: no
# Read the single-task rung-0 v2 runs (read only; never touches a run in progress).
tmux ls 2>&1 | head -2
echo "recorded runs: $(wc -l < ~/ple-submission/research/runs.jsonl)"; tail -n 2 ~/ple-submission/research/runs.jsonl | cut -c1-150
for R in $(ls -dt ~/ple-submission/runs/naive-A-2026112618*/ 2>/dev/null); do
  echo "=== $R"; python3 - "$R" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "results.json"
if not p.is_file(): print("no results.json yet"); sys.exit()
d = json.load(open(p)); print({k: d.get(k) for k in ("model", "score", "complete", "date")})
for t in d["tasks"]: print(t["id"], "score", t["score"], t["status"], t.get("seconds"), "s", t.get("tokens"), "trial", t.get("trial"))
PY
done
R=$(ls -dt ~/ple-submission/runs/naive-A-2026112618*/ | tail -1); T=$(find "$R" -maxdepth 4 -type d -name '*__*' | head -1)
echo "=== trial dir (first v2 run): $T"; find "$T" -maxdepth 2 | sed "s|$T||" | head -30
echo "=== harness log lines (naive:)"; grep -rhs "naive:" "$T" --include='*.txt' --include='*.log' | cut -c1-600 | head -14
echo "=== proxy request log: $(wc -l < ~/ple-proxy-requests.jsonl 2>/dev/null) lines"; head -c 1600 ~/ple-proxy-requests.jsonl 2>/dev/null
