# stop: idle
# pull: research/runs.jsonl research/run-details
# Rung 3 v2 (one agent: set_checks + evaluate, may rewrite its own checker). Neon only, repeats 2 and 3 (repeat 1 is run-048), one task, effort low.
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rung3 2>/dev/null; then echo "rung3 already running"; else
  tmux new -d -s rung3 "for REP in 2 3; do MODELS=gemini-4-neon TASKS=data-hall-mep-routing EFFORT=low REP=\$REP bash ~/ple-submission/infra/gcp-vm/rung3.sh; done 2>&1 | tee ~/rung3-v2b.log"
fi
sleep 30
for i in $(seq 480); do tmux has-session -t rung3 2>/dev/null || break; sleep 15; done
if tmux has-session -t rung3 2>/dev/null; then echo "STILL RUNNING after 120 min: left running, VM stays on"; exit 0; fi
grep -n "^===\|failed\|Traceback\|Error" ~/rung3-v2b.log | tail -30; echo ---; tail -15 ~/rung3-v2b.log
IDS=$(python3 -c "
import json
rs=[json.loads(l) for l in open('research/runs.jsonl') if l.strip()]
print(' '.join(r['run_id'] for r in rs if r['label'].startswith('rung 3 v2')))")
echo "rung 3 v2 runs: $IDS"; [ -n "$IDS" ] && python3 research/collect_details.py $IDS
N=$(gcloud projects describe ple-submission --format='value(projectNumber)' 2>/dev/null | tail -1); B="gs://ple-runs-$N"
gcloud storage rsync --recursive runs "$B/runs" 2>&1 | tail -1
gcloud storage cp ~/ple-proxy-requests.jsonl "$B/ple-proxy-requests.jsonl" 2>&1 | tail -1
true
