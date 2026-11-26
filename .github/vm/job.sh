# sync: no
# pull: research/runs.jsonl
# Look inside the single-task trials (read only). Waits up to 12 min for the Neon run to finish.
for i in $(seq 48); do tmux has-session -t rung0 2>/dev/null || break; sleep 15; done
tmux ls 2>&1 | head -1
echo "recorded runs: $(wc -l < ~/ple-submission/research/runs.jsonl)"
for T in $(ls -d ~/ple-submission/runs/naive-A-20261126-1805*/attempt1/jobs/dev/data-hall*/ ~/ple-submission/runs/naive-A-20261126-1813*/attempt1/jobs/dev/data-hall*/ 2>/dev/null); do
  echo; echo "################ $T"
  python3 - "$T/../../../results.json" <<'PY'
import json, sys, os
p = sys.argv[1]
if os.path.isfile(p):
    d = json.load(open(p)); print({k: d.get(k) for k in ("model", "score", "complete")}); [print(t["id"], t["score"], t["status"], t.get("seconds"), t.get("tokens")) for t in d["tasks"]]
PY
  echo "--- files (size):"; (cd "$T" && find . -type f -printf '%s %p\n' | sort -k2 | head -40)
  echo "--- harness lines:"; grep -rhs "naive:" "$T" 2>/dev/null | cut -c1-900 | head -12
  echo "--- verifier:"; for f in "$T"/verifier/*; do [ -f "$f" ] && { echo "[$f]"; head -c 1500 "$f"; echo; }; done
  echo "--- exception:"; head -c 600 "$T/exception.txt" 2>/dev/null
done
