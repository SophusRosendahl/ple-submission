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

## Next steps

1. Mac setup per `infra/local/README.md`; `python3 infra/local/check_models.py` (also settles
   whether image input works through the proxy).
2. Rung 0 on one task at a time, starting with `data-center-site-model` (lightest, checks-only),
   then `fire-test-validation-memo` (exercises the judge):
   ```bash
   python3 research/run_dev.py --ple ../ple --entry harnesses/naive \
       --label "rung 0: single model call, files as text" \
       --env-file ../ple/local.env --tasks data-center-site-model --trials 1
   ```
3. Check the first real report against the actual `eval/run.py` output folder (the tracker's
   grader-detail parsing was only tested on a hand-made run folder).
4. Record results in the journal; decide rung 1 from what rung 0 got wrong.

## Open questions

- Is the task-1 grader analysis (journal section 5) fine for the write-up, given the template's
  AGENTS.md lists "inspect grading scripts" under fair play? Alternative: cite only what
  `eval/run.py --artifacts` reports.
- The repo has no `main` branch yet; work is on `claude/loving-rubin-jc0fnt`.
- The staged workflow architecture (`docs/architecture.md`) is agreed but deliberately not built
  yet: it comes back once the ladder shows where it is needed.
