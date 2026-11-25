# Handoff: where the work stands

Written when moving development from a cloud session to a local Mac. Read this first, then
`docs/design-decisions.md` and `docs/architecture.md`.

## The goal

An entry for the PLE competition (Kaggle, 9 Nov 2026 – 5 Jan 2027): a harness that drives a
Google-sponsored model through real engineering tasks. Reference points: the best stock setup on
the leaderboard scores 0.507 on the hidden tasks; the official template (Pi + Claude Opus 5.5)
scores 0.543 on our dev half A.

## How we work

- **Measure first, build up from first principles.** Start from the simplest harness and add one
  capability at a time, each motivated by a failure observed in a run (the "ladder").
- **Dev split** (`research/dev_split.json`): develop on half A (15 tasks) only; half B (14) is held
  out. The tracker refuses half-B records without a stated reason.
- **Scoring** exactly as a submission is scored: competition graders via `eval/run.py`, Opus 5.5
  judge, missing tasks count 0, mean over the half.
- **Lab journal** (`research/journal.ipynb`, built by `research/build_journal.py`): the narrative
  for the write-up; tables and charts read the tracker.
- Running on an 8 GB MacBook Air for now, one task at a time; app-based tasks later on a bigger
  machine (`infra/gcp-vm/` has optional VM scripts).

## Repository map

| Path | What |
|---|---|
| `harnesses/naive/` | rung 0: one model call; the harness pastes the task's files in as plain text first |
| root (`serve.py`, `harness.py`, `task-tools.ts`, …) | the official template (Pi), unchanged; not our entry yet |
| `research/` | split, tracker, `run_dev.py`, journal (see `research/README.md`) |
| `infra/local/` | Mac setup, model proxy start script, model check |
| `docs/` | design decisions, architecture, this note |

## Status (2026-11-25, end of the local-setup session)

Done:
- Mac: repos side by side in `coding_projects/ple/` (`ple/`, `ple-submission/`), `.venv` with the
  research deps, uv, gcloud and Harbor installed. Docker Desktop has only 3.8 GB; runs now go to the VM.
- Google Cloud project `ple-submission` (billing in DKK): budget 600 DKK/month, email alerts at
  50/90/100/110% and 100% forecast, and a **hard cap** that turns off billing at 100%
  (`infra/gcp-budget/`). Vertex AI, Compute Engine and the budget/function APIs enabled.
- Run VM `ple-runner` (spot n2-standard-32, 250 GB, us-central1-a) created and set up: Docker,
  Harbor, both repos, `~/ple/local.env`, proxy start script. Powers off after 30 idle minutes and
  after 24 h running. It is **stopped**; start with
  `gcloud compute instances start ple-runner --zone us-central1-a`.
- Models through the proxy: Gemini 4 Neon works (text and images). **Claude Opus 5.5 has zero
  quota**: three increase requests were auto-denied (new billing account). Retry smaller amounts
  in the console later.
- `run_dev.py --judge {cheap,dev,official}` (default `dev` = Gemini 4 Neon; `PLE_JUDGE` env) and
  `--model <id>` (runs the entry with another model, entry unchanged). The tracker records and lists
  the judge; `combine` refuses to mix judges.

Blocked: the Hugging Face token in `ple/local.env` is rejected ("Invalid username or password"),
so the dataset download failed. Fix: make a new Read token on the account that has dataset access,
then in your own Terminal:
`read -rs "HF?Hugging Face token: " && sed -i '' "s|^HF_TOKEN=.*|HF_TOKEN=$HF|" ~/Documents/coding_projects/ple/ple/local.env && unset HF`

## Next steps

1. Fix the HF token (above), copy it to the VM
   (`gcloud compute scp ple/local.env ple-runner:ple/local.env --zone us-central1-a`), start the VM.
2. On the VM: `bash ple-submission/infra/local/start_proxy.sh`, then `tmux new -s rung0 "bash ~/rung0.sh 2>&1 | tee ~/rung0.log"`.
   `~/rung0.sh` runs rung 0 on all 15 half-A tasks (5 at a time, judge Gemini 4 Neon), first with
   Gemini 3.8 Flash (the "bad" model), then Gemini 4 Neon (the "better" one). App-task images are
   built in the first run (an hour or more).
3. Copy `research/runs.jsonl` and the run folders back from the VM, then write the comparison
   report: what each model does well and where it fails, per task and grader detail.
4. Record results in the journal; decide rung 1 from what rung 0 got wrong.

## Open questions

- Is the task-1 grader analysis (journal section 5) fine for the write-up, given the template's
  AGENTS.md lists "inspect grading scripts" under fair play? Alternative: cite only what
  `eval/run.py --artifacts` reports.
- The repo has no `main` branch yet; work is on `claude/loving-rubin-jc0fnt`.
- The staged workflow architecture (`docs/architecture.md`) is agreed but deliberately not built
  yet: it comes back once the ladder shows where it is needed.
