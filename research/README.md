# Research: measurement and the lab journal

| File | What it is |
|---|---|
| `dev_split.json` | the dev-set split: half **A** for development, half **B** held out (made by `split.py`) |
| `tracker.py` | run tracker: records scored runs in `runs.jsonl` and prints a full score report per run |
| `run_dev.py` | runs a harness on half A with the competition's own `eval/run.py`, then records and reports it |
| `runs.jsonl` | every recorded run (committed) |
| `journal.ipynb` | the lab journal: narrative + live tables and charts from the tracker (built by `build_journal.py`) |

Scoring is the competition's: each task 0–1 from its own grader (rubric tasks judged by Claude
Opus 5.5), a task with no result counts as 0, the run's score is the mean over the half.
Half-B results are only recorded with an explicit `--holdout` reason.

## Run a harness on half A

Setup and batch commands for a laptop: `infra/local/README.md`. In short:

```bash
python3 research/run_dev.py --ple ../ple --entry harnesses/naive --label "rung 0: single model call, files as text" \
    --env-file ../ple/local.env --max-memory-gb 12.5 --trials 1
```

Raw run folders go to `runs/` (git-ignored); the record goes to `research/runs.jsonl`.

## Other commands

```bash
python research/tracker.py list
python research/tracker.py combine run-001 run-002 --label "…"   # merge batch runs
python research/tracker.py report run-000
python research/build_journal.py && jupyter nbconvert --execute --inplace research/journal.ipynb
```
