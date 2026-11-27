# stop: idle
# pull: research/runs.jsonl research/run-details
# Environment audit v2: the network test now makes real requests (DNS, HTTP, a TCP request and reply, an unroutable address), because a plain
# TCP connect can succeed through a transparent proxy even when nothing gets out. Read-only, no model calls. Run in tmux (own process group).
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rungaudit 2>/dev/null; then echo "audit already running: waiting"; else
  tmux new -d -s rungaudit "MODELS=gemini-3.8-flash TASKS=data-hall-mep-routing EFFORT=low bash ~/ple-submission/infra/gcp-vm/audit.sh 2>&1 | tee ~/audit.log"
fi
sleep 20
for i in $(seq 120); do tmux has-session -t rungaudit 2>/dev/null || break; sleep 10; done
tr '\r' '\n' < ~/audit.log | grep -v '^Fetching' | tail -5 | cut -c1-200
IDS=$(python3 -c "
import json
rs=[json.loads(l) for l in open('research/runs.jsonl') if l.strip()]
print(' '.join(r['run_id'] for r in rs if r['label'].startswith('environment audit'))[-30:])")
echo "latest audit runs: $IDS"; for r in $IDS; do python3 research/collect_details.py $r; done
