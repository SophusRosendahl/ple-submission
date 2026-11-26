# sync: no
# pull: research/runs.jsonl
# Read the single-task rung-0 v2 runs (read only).
tmux ls 2>&1 | head -2
echo "recorded runs: $(wc -l < ~/ple-submission/research/runs.jsonl)"
for R in $(ls -dt ~/ple-submission/runs/naive-A-20261126-18*/ 2>/dev/null | tac); do
  echo "=== $R"; python3 - "$R" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]) / "results.json"
if not p.is_file(): print("no results.json yet"); sys.exit()
d = json.load(open(p)); print({k: d.get(k) for k in ("model", "score", "complete", "date")})
for t in d["tasks"]: print(t["id"], "score", t["score"], t["status"], t.get("seconds"), "s", t.get("tokens"), "trial", t.get("trial"))
PY
done
R=$(ls -dt ~/ple-submission/runs/naive-A-20261126-18*/ | tac | head -1); T=$(find "$R" -maxdepth 4 -type d -name '*__*' | head -1)
echo "=== trial dir: $T"; (cd "$T" && find . -maxdepth 2 | head -30)
echo "=== harness log lines (naive:)"; grep -rhs "naive:" "$T" 2>/dev/null | cut -c1-700 | head -12
echo "=== proxy request log by model/judge:"
python3 - <<'PY'
import json, collections
rows = [json.loads(l) for l in open("/home/sophusrosendahl/ple-proxy-requests.jsonl")]
agg = collections.defaultdict(lambda: [0, 0, 0, 0, 0.0])
for r in rows:
    k = (r["requested_model"], "judge" if r["is_judge"] else "harness", r["status"], r.get("finish_reason"))
    a = agg[k]; a[0] += 1; a[1] += r.get("prompt_tokens") or 0; a[2] += r.get("completion_tokens") or 0; a[3] += r.get("reasoning_tokens") or 0; a[4] += r.get("latency_s") or 0
for k, a in sorted(agg.items(), key=str): print(k, "n=%d prompt=%d completion=%d reasoning=%d latency=%.0fs" % tuple(a))
PY
