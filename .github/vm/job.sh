# stop: yes
# pull: research/runs.jsonl research/run-details
# Fetch the rung 0 v3 results (retry: the first attempt raced the VM's own shutdown).
cd ~/ple-submission
python3 research/tracker.py list | cut -c1-130 | tail -3
find research/run-details/run-005 research/run-details/run-006 -type f | wc -l
true
