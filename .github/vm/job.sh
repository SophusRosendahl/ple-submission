# sync: no
# Summarise the finished rung-0 runs (read only).
tmux ls 2>&1 | head -2
echo "recorded runs in research/runs.jsonl: $(wc -l < ~/ple-submission/research/runs.jsonl)"
for R in $(ls -d ~/ple-submission/runs/*/ 2>/dev/null); do
  echo "=================== $R"
  python3 - "$R" <<'PY'
import json, sys, pathlib
r = pathlib.Path(sys.argv[1]); p = r / "results.json"
if not p.is_file(): print("no results.json"); sys.exit()
d = json.load(open(p))
print({k: d.get(k) for k in ("submission", "model", "judge_model", "score", "complete", "date")}, "unmeasured:", d.get("unmeasured"))
for t in d["tasks"]:
    print(f'{t["id"]:30s} score={t["score"]!s:6} {t["status"]:10s} {t["kind"]!s:10s} {t.get("seconds")!s:>5}s tokens={t.get("tokens")}')
PY
done
echo "=================== one trial's files (first run)"
R=$(ls -d ~/ple-submission/runs/*/ | head -1); T=$(find "$R" -maxdepth 4 -type d -name '*__*' | head -1); echo "$T"
find "$T" -type f | sed "s|$T/||" | head -40
echo "=================== rung0.log (non-progress lines, tail)"
tr '\r' '\n' < ~/rung0.log | grep -v '^Fetching' | tail -45 | cut -c1-240
