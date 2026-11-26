# Rung 0 v2: new harness code (64k output cap, call counting, fingerprints, finish reasons) and the request-logging proxy.
if tmux has-session -t rung0 2>/dev/null; then echo "rung0 already running: not touching it"; exit 0; fi
cd ~/ple-submission && git log -1 --oneline
[ -f ~/ple-proxy.pid ] && kill "$(cat ~/ple-proxy.pid)" 2>/dev/null; sleep 3   # restart it, so the request log is on
tmux new -d -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
sleep 150
echo "--- rung0.log:"; tr '\r' '\n' < ~/rung0.log | grep -v '^Fetching' | tail -14 | cut -c1-220
echo "--- proxy: $(curl -s -o /dev/null -m 5 -w '%{http_code}' http://172.17.0.1:4000/health/liveliness) | request log: $(ls -la ~/ple-proxy-requests.jsonl 2>&1 | awk '{print $5" bytes"}')"
grep -c . ~/ple-proxy-config/config.yaml >/dev/null 2>&1 && grep -n 'callbacks' ~/ple-proxy-config/config.yaml
