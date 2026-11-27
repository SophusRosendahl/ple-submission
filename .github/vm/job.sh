# stop: idle
# pull: research/runs.jsonl research/run-details
# Pull-only: the rung 1 v3 results are on the VM, but the push of their first pull failed on a merge conflict (fixed in the workflow).
cd ~/ple-submission && git log -1 --oneline
if tmux has-session -t rung1 2>/dev/null; then echo "rung1 still running: nothing pulled"; exit 0; fi
python3 research/tracker.py list | tail -4 | cut -c1-200
ls research/run-details | tail -4
