# Job 5: start rung 0 in tmux unless it is already running; then show the first minutes of its log.
if tmux has-session -t rung0 2>/dev/null; then
  echo "rung0 is already running: not touching it"
else
  tmux new -d -s rung0 "bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
fi
sleep 150
echo "--- rung0.log (tail):"; tail -c 5000 ~/rung0.log | tr '\r' '\n' | tail -25
echo "--- proxy answers at 172.17.0.1: $(curl -s -o /dev/null -m 5 -w '%{http_code}' http://172.17.0.1:4000/health/liveliness)"
