# Stop the 15-task rung-0 v2 run (on request) and start it on one task only: data-hall-mep-routing, both models.
echo "stopping the 15-task run"
tmux kill-session -t rung0 2>/dev/null
pkill -f 'research/run_dev.py'; pkill -f 'eval/run.py'; pkill -f 'harbor'
sleep 8; docker ps -q | xargs -r docker rm -f >/dev/null 2>&1; sleep 2
echo "left running: processes=$(pgrep -fc 'run_dev.py|eval/run.py|harbor') containers=$(docker ps -q | wc -l)"
cd ~/ple-submission && git log -1 --oneline
tmux new -d -s rung0 "TASKS=data-hall-mep-routing bash ~/ple-submission/infra/gcp-vm/rung0.sh 2>&1 | tee ~/rung0.log"
sleep 90
echo "--- rung0.log:"; tr '\r' '\n' < ~/rung0.log | grep -v '^Fetching' | tail -10 | cut -c1-230
