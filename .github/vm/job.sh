# stop: yes
# pull: research/runs.jsonl research/run-details
# Only fetch the rung 0 v3 results (the VM powered itself off before the previous job could pull them).
cd ~/ple-submission
python3 research/tracker.py list | cut -c1-130 | tail -3
find research/run-details/run-005 research/run-details/run-006 -type f | wc -l
true
