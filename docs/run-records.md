# What every run records

The write-up is judged on how closely we analyse failures, so a run must leave enough behind to
reconstruct *what went wrong, task by task, check by check*. Four layers; nothing is deleted.

| Layer | Where | Holds |
|---|---|---|
| Record | `research/runs.jsonl` (git) | per run: label, harness + model + commit, judge, half, `env`; per task: score, status, seconds, tokens, **every grader file**, a listing of the trial folder |
| Run folder | `runs/<run>/` on the VM, copied to `gs://ple-runs-<project number>/runs/` after each run | everything the evaluator wrote: `results.json`, each trial's logs, final message, produced files, the verifier's full output |
| Harness log lines | in each trial's log, parsed into the record | `CALL`, `CALLS`, `CHECK` (below) |
| Proxy request log | `~/ple-proxy-requests.jsonl` on the VM, copied to the bucket (`infra/local/request_log.py`) | one line per model request, harness and judge alike: times, latency, status, requested and served model, `is_judge`, prompt / completion / **cached** / reasoning tokens, finish reason, error |

## Harness log lines (one JSON object after the tag)

* `CALL {...}`: one per successful model call. `t`, `model`, `chars`, `step`, `fp` (prompt-prefix
  hashes, for `research/kvcache.py`), `prompt_tokens`, `cached_reported`, `completion_tokens`,
  `reasoning_reported`, `usage_raw` (the endpoint's own object).
* `CALLS {...}`: one per task. Calls ok / failed (retries are separate calls), input, cached
  input, output and reasoning tokens.
* `CHECK {...}`: **one per self-check the harness runs on its own work**, as it runs it:
  `{"name": str, "kind": "self-check", "passed": bool, "detail": str, "step": int, "t": float}`.
  A check that is skipped, errors, or found nothing to check is logged too (`passed: null`) and counts as **not passed**. Harnesses from rung 1 on
  must log every check through this line, including the ones that pass and the fixes that follow
  a failure (`"action": "fixed" | "ignored"`), so we can compare self-checks with the grader's.

## Run environment (`env` in the record)

Start and finish time, wall seconds, parallel trials, machine (host, CPUs, memory), judge, and
the model override if any. VM hours are the sum of wall seconds of runs plus idle time, from the
VM's own start and stop times.

## What the counts can and cannot say

* The harness counts the requests it sends to the proxy. The proxy (competition config:
  `num_retries: 3`) retries failed upstream requests itself and logs only each request's final
  outcome, so **the provider may have served more requests than either count shows**; the
  harness count is a lower bound on provider calls, and the proxy log is the better one.
* A judge request the provider refuses is re-sent once to a fallback model by the competition's
  `judge_fallback`; it can appear as an extra judge record.
* Failed calls' tokens are unknown to us; successful calls' tokens come from the endpoint.

## Reading a trial check by check

`python3 research/check_table.py run-010` prints every check the grader ran (gates, each compliance rule, the
clashes grouped by kind, efficiency) next to the score, from the grader files in `research/run-details/`.
It is written for `data-hall-mep-routing`; each task type's grader needs its own rows.

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
* The proxy request log is written and tested against fake events, not yet against the real proxy
  (LiteLLM 1.90.0). It starts with the next proxy start, after the current rung-0 run, and its
  first output gets checked against a few test requests.
* The tracker does not yet parse `CALL`, `CALLS` and `CHECK` lines out of trial logs.
