# stop: yes
# pull: research/runs.jsonl
# Recover run-004 (lost from the VM's runs.jsonl by a sync, but saved as a patch), enrich it, stop the VM.
cd ~/ple-submission
ls -la ~/sync-backup 2>/dev/null | tail -6
for p in ~/sync-backup/*.patch; do
  grep '^+{' "$p" | sed 's/^+//' > /tmp/recovered.jsonl
  python3 infra/gcp-vm/merge_runs.py /tmp/recovered.jsonl research/runs.jsonl
done
python3 research/tracker.py enrich run-004 runs/naive-A-20261126-181344
python3 research/tracker.py list | cut -c1-120
python3 - <<'PY'
import json
for l in open("research/runs.jsonl"):
    r = json.loads(l)
    if r["run_id"] in ("run-003", "run-004"):
        t = list(r["tasks"].values())[0]
        print(r["run_id"], "score", t["score"], "env", bool(r.get("env")), "harness", (t.get("harness") or {}).get("calls"))
PY
true
