# stop: idle
# pull: research/runs.jsonl research/run-details research/ple-state.txt
# Pull-only for the rung 1 v3 results (the push of their first pull failed on a merge conflict, fixed in the workflow),
# plus a read-only report of the organizers' repository on the VM: is the grader code the organizers' own, unmodified?
cd ~/ple-submission && git log -1 --oneline
P=$(ls -d ~/ple /home/*/ple 2>/dev/null | head -1)
{
  echo "== organizers' repository at $P"; git -C "$P" remote -v | head -3
  echo "== commit"; git -C "$P" log -1 --format='%H %cI %s'
  echo "== local changes (git status --porcelain, tracked and untracked; empty = none)"; git -C "$P" status --porcelain | head -20
  echo "== diff against the commit (stat)"; git -C "$P" diff --stat | tail -5
  echo "== ignored files that could change behaviour (names only)"; git -C "$P" status --ignored --porcelain | grep '^!!' | head -10
  echo "== cpus / memory of this machine"; nproc; free -g | sed -n 2p
} > research/ple-state.txt 2>&1
cat research/ple-state.txt | cut -c1-200
if tmux has-session -t rung1 2>/dev/null; then echo "rung1 still running: runs not pulled"; exit 0; fi
python3 research/tracker.py list | tail -4 | cut -c1-200
ls research/run-details | tail -4
