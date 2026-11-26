# What every run records

The write-up is judged on how closely we analyse failures, so a run must leave enough behind to
reconstruct *what went wrong, task by task, check by check*. Four layers; nothing is deleted.

| Layer | Where | Holds |
|---|---|---|
| Record | `research/runs.jsonl` (git) | per run: label, harness + model + commit, judge, half, `env`; per task: score, status, seconds, tokens, **every grader file**, a listing of the trial folder |
| Run folder | `runs/<run>/` on the VM, copied to `gs://ple-runs-<project number>/runs/` after each run | everything the evaluator wrote: `results.json`, each trial's logs, final message, produced files, the verifier's full output |
| Harness log lines | in each trial's log, parsed into the record | `CALL`, `CALLS`, `CHECK` (below) |
| Proxy request log | on the VM (to be set up: see "Open") | every model request, harness and judge alike |

## Harness log lines (one JSON object after the tag)

* `CALL {...}`: one per successful model call. `t`, `model`, `chars`, `step`, `fp` (prompt-prefix
  hashes, for `research/kvcache.py`), `prompt_tokens`, `cached_reported`, `completion_tokens`,
  `reasoning_reported`, `usage_raw` (the endpoint's own object).
* `CALLS {...}`: one per task. Calls ok / failed (retries are separate calls), input, cached
  input, output and reasoning tokens.
* `CHECK {...}`: **one per self-check the harness runs on its own work**, as it runs it:
  `{"name": str, "kind": "self-check", "passed": bool, "detail": str, "step": int, "t": float}`.
  A check that is skipped or errors is logged too (`passed: null`). Harnesses from rung 1 on
  must log every check through this line, including the ones that pass and the fixes that follow
  a failure (`"action": "fixed" | "ignored"`), so we can compare self-checks with the grader's.

## Run environment (`env` in the record)

Start and finish time, wall seconds, parallel trials, machine (host, CPUs, memory), judge, and
the model override if any. VM hours are the sum of wall seconds of runs plus idle time, from the
VM's own start and stop times.

## Analysis this has to support

* **Per task, per check:** which grader checks or rubric items failed, with the grader's reasoning
  (`grader_files`), next to what the harness's own checks said (`CHECK`): did it know?
* **Self-check calibration:** how often a self-check passed while the grader failed the same thing,
  and the reverse.
* **Cost of a result:** calls, tokens (cached / uncached / reasoning) and seconds per task.
* **Judge:** how many judge calls a run caused, from the proxy log (judge and harness calls are
  told apart by model name).

## Open

* How the grader's files are laid out is read from a real run folder once one exists; until then
  `trial_files` lists everything so nothing is lost and the parser can be written from the data.
* The proxy request log (needs the proxy's callback hook): being looked at.
* The tracker does not yet parse `CALL`, `CALLS` and `CHECK` lines out of trial logs.
