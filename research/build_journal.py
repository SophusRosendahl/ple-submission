"""Builds research/journal.ipynb, the living lab journal for our PLE entry.

The narrative lives here as markdown cells; the numbers come from the run tracker when the
notebook runs, so re-running it after a new run updates every table and chart.

  python research/build_journal.py            # write the notebook
  jupyter nbconvert --execute --inplace research/journal.ipynb   # run it
"""
import pathlib

import nbformat as nbf

HERE = pathlib.Path(__file__).resolve().parent
md, code = nbf.v4.new_markdown_cell, nbf.v4.new_code_cell

cells = [
    md("""# Building an engineering agent for PLE: lab journal

A living record of how our entry to the *Physical-Engineering's Last Exam* competition is built:
what we measured, what we observed, and why each part of the harness exists. It is the source for
the competition write-up.

Every number below is read from the run tracker (`research/runs.jsonl`) when the notebook runs.
The story so far, in order: **(1)** a cloud VM so we can judge exactly, **(2)** a split of the
dev set in two, **(3)** a very simple naive test with just a model."""),

    md("""## Write-up tracker

The final upload is written from this notebook, against the competition's judging criteria
(from the Kaggle page; 100 points in all).
Status: `todo` / `draft` / `done`. Update the table in `research/build_journal.py`, then rebuild.

| # | Criterion (points) | What judges look for | What we have / still need | Status |
|---|---|---|---|---|
| 1 | **Insight & failure analysis** (25) | Something non-obvious; real dev-set failures; controlled ablations ("we added X, score went A to B"); ideas that failed | Near miss in section 5; lab log. Need: one-change-at-a-time ladder runs, failures read task by task, failed ideas written down | draft |
| 2 | **Engineering reasoning** (25) | One concrete dev task walked through, our agent's trajectory against a licensed engineer's workflow: where it held up, where it took shortcuts, which domain skills separated pass from fail | Need: keep the full trajectory of each run (not just scores) and pick one task | todo |
| 3 | **Cross-model generalizability** (15) | All 29 dev tasks with at least two models, ideally across families; which changes help every model, which only one; how model choice shifts accuracy and token cost; comparison table in the write-up; one target `google-cloud/<id>` committed in `submission.yaml` for Stage 2 | Rung 0 runs two models on half A only. Need: every rung on 2+ models, a final pass over all 29 (half B needs a stated reason), and the single target model chosen | todo |
| 4 | **Efficiency & scaling** (20) | Dev score against compute budget (calls, tokens, runtime or parallel verification attempts); where accuracy plateaus; remaining headroom | The harness now counts model calls exactly (section 4); tracker stores tokens and seconds per task. Need: read the call counts into the tracker, a score-vs-budget chart per rung, and one budget knob to vary (for example verification attempts) | draft |
| 5 | **Clarity & visuals** (15) | Written for an ML researcher with no civil, mechanical or electrical background; headline finding near the top; the 3 required figures; under 2,000 words | Need: which 3 figures are required (not yet read), and a short plain-language glossary. Word count is checked at the end | todo |

Gate: the top 100 submissions from Stage 1 advance to Stage 2, and an entry must first pass the
automated `kit check` and artifacts verification before its write-up is scored.

Also needed, from our own plan: the evaluation setup (section 2), the split and hold-out
discipline (section 3), the final architecture (`docs/architecture.md`,
`docs/design-decisions.md`) and how to reproduce (`infra/`)."""),

    md("""## 1. The problem

PLE has 85 real engineering tasks: structural, civil, electrical and mechanical. Each runs in an
isolated container with the project's files and up to 6 hours, and asks for a real deliverable: a
calculation package, a coordinated IFC model, a review memo. Tasks are graded `0`-`1` by
programmatic checks, by an LLM judge against an expert rubric, or both.

An entry is a **harness**, the code that drives a model through each task, paired with one of the
Google-sponsored models. The best stock setup on the public leaderboard (Gemini 4 Neon with
Google's own agent) scores **0.507** on the 56 hidden tasks: about half the available points."""),

    md("""## 2. An evaluation environment in a cloud VM

**Why.** We want to judge our harness *exactly* as the competition does: its own task images,
its own graders, the same protocol. That needs Docker with real memory (some tasks run app
servers and need up to 16 GB), and a model endpoint for both the harness and the judge.

**What we set up**

* One VM (`ple-runner`, spot `n2-standard-32`, 250 GB, Docker + Harbor) in our own Google Cloud
  project, running the competition's `eval/run.py` unchanged. It powers itself off after 30 idle
  minutes and after 24 h, so a forgotten VM cannot run up a bill.
* The competition's model proxy on the VM, calling Vertex AI as the VM's own service account (no
  keys stored).
* A budget of 600 DKK a month with alerts, and a **hard cap** that switches billing off at 100 %.
* Control from a cloud session, with no laptop: a GitHub Actions workflow starts the VM, runs a
  job script on it and reads the log back. Google trusts GitHub's identity for this one
  repository (workload identity federation), so no keys are stored.

**Why not the laptop.** Docker Desktop on the 8 GB Mac had 3.8 GB, too little for the larger
tasks, and the laptop later broke.

**Caveat on the judge.** The leaderboard judges rubric tasks with Claude Opus 5.5. Our project
has no Vertex quota for it (three increase requests were auto-denied), so development runs use
Gemini 4 Neon as judge. Judged scores are therefore *approximate*; we only compare runs that
share a judge, and the tracker refuses to merge runs with different judges."""),

    md("""## 3. Splitting the dev set in two

**A split we don't cheat on.** The 29 public dev tasks are split in two. We develop only on
**half A** (15 tasks). **Half B** (14 tasks) is held out and run rarely, to check that what helps
on A carries over to tasks we have never looked at; the tracker refuses to record a half-B run
without a stated reason. Five tasks we had studied in detail before splitting were placed in A by
construction; the rest were assigned at random (fixed seed), balanced by grading type."""),

    code("""import json, pathlib, sys
import pandas as pd
import matplotlib.pyplot as plt

HERE = pathlib.Path.cwd()
sys.path.insert(0, str(HERE))
import tracker

split = tracker.load_split()
rows = [{"half": h, "task": t, **{k: split["tasks"][t][k] for k in ("grading", "domain")}}
        for h in ("A", "B") for t in split[h]]
tasks = pd.DataFrame(rows)
print(f"seed {split['seed']} · {split['method']}")
pd.crosstab(tasks["grading"], tasks["half"], margins=True, margins_name="total")"""),

    code("""tasks[tasks.half == "A"][["task", "grading", "domain"]].reset_index(drop=True)"""),

    md("""> **Status (2026-11-26): rung 0 is invalid so far.** Every rung-0 run to date (run-001 to run-004) was
> blind to images: the harness listed them by name only, and the model never saw the drawings.
> Those runs stay in the tracker, flagged `INVALID` with the reason (`tracker.py invalidate`), and
> say nothing about the models on image-based tasks. **Rung 0 v3**, with images attached, replaces
> them. See the lab log."""),

    md("""## 4. Rung 0: a naive test with just a model

**Design.** One model call, no tools, no agent loop. Before the call the harness (not the model)
turns the task's files into plain text and pastes them after the task text; images are listed by
name only. The model answers once; files it writes as marked blocks in its answer are saved in
the task container, and the rest of the answer is the final message. It cannot open files or run
anything. It lives in `harnesses/naive/`.

**Why start here.** It is the floor every later rung is measured against. If a tool loop does not
beat it, the loop is not earning its cost.

**Known limits, by design.** It can only write text files (no xlsx, docx or images), and it never
checks its own work. We expect it to fail on those tasks, and *which* tasks it fails is the point.

**The comparison.** The same harness with two models: Gemini 3.8 Flash (the "bad" model) and
Gemini 4 Neon (the "better" one), over all of half A, judged by Gemini 4 Neon."""),

    code("""runs = tracker.load_runs()
overview = pd.DataFrame([{
    "run": r["run_id"], "label": r["label"], "model": r["harness"]["model"],
    "half": r["half"], "judge": tracker.judge_name(r.get("judge_model")), "score": round(tracker.score(r)["score"], 3),
    "valid": "NO" if tracker.invalid_reason(r) else "yes",
    "measured": f"{tracker.score(r)['n_measured']}/{tracker.score(r)['n_tasks']}",
    "run date": (r["source"].get("run_date") or "")[:10],
} for r in runs])
overview"""),

    code("""from IPython.display import display
INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e7e6e1", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834"]  # categorical slots 1-2, validated (CVD and contrast)

def task_frame(run):
    s = tracker.score(run)
    return pd.DataFrame([{"task": t, "grading": split["tasks"][t]["grading"], "score": sc}
                         for t, sc, _ in s["rows"]])

def plot_runs(run_ids, title):
    chosen = [r for r in runs if r["run_id"] in run_ids]
    base = task_frame(chosen[0]).sort_values("score")
    order = list(base["task"])
    fig, ax = plt.subplots(figsize=(8.5, 0.36 * len(order) + 1.4), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    y = range(len(order))
    for i, run in enumerate(chosen):
        f = task_frame(run).set_index("task").loc[order]
        label = f"{run['run_id']} · {tracker.score(run)['score']:.3f}"
        if len(chosen) == 1:
            ax.barh(list(y), f["score"], height=0.55, color=SERIES[0], label=label)
            for yi, sc in zip(y, f["score"]):
                if sc == 0:
                    ax.text(0.005, yi, "0", color=MUTED, fontsize=9, va="center")
        else:
            ax.scatter(f["score"], list(y), s=46, color=SERIES[i], zorder=3, label=label,
                       edgecolors=SURFACE, linewidths=2)
    mean = tracker.score(chosen[0])["score"]
    ax.axvline(mean, color=MUTED, lw=1, ls=(0, (3, 3)))
    ax.text(mean, len(order) - 0.4, f" mean {mean:.3f}", color=MUTED, fontsize=9, va="bottom")
    ax.set_yticks(list(y), [f"{t}  ({split['tasks'][t]['grading']})" for t in order], color=INK, fontsize=9)
    ax.set_xlim(0, 1.0); ax.set_xlabel("task score", color=MUTED, fontsize=9)
    ax.tick_params(axis="x", colors=MUTED, labelsize=9); ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    for side in ("top", "right", "left"): ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_title(title, loc="left", color=INK, fontsize=11, pad=10)
    if len(chosen) > 1:
        ax.legend(frameon=False, fontsize=9, loc="lower right")
    fig.tight_layout()
    return fig"""),

    md("""### Rung 0 results

**v1 (invalid as a floor).** Both models scored about zero (Gemini 3.8 Flash 0.007, Gemini 4 Neon
0.000). The cause is our setup, not the models: the harness capped the reply at 32,000 tokens, and
the model's thinking tokens count against that cap. Output was at the cap in 15 of 15 (Flash) and
14 of 15 (Neon) tasks, and several tasks wrote no file at all (the grader reports
`ERR_NO_SUBMISSION`). We did not log why each reply stopped, so the cut-off is inferred.

**v2.** The cap is 64,000 for Gemini and every call now records its finish reason, so a cut-off
shows up as one. Filled in from the tracker below (`rung 0` in the run label)."""),

    code("""rung0 = [r for r in runs if r["label"].lower().startswith("rung 0")]
if rung0:
    display(plot_runs([r["run_id"] for r in rung0], "Rung 0: one model call, score per task on half A"))
    print(overview[overview["label"].str.lower().str.startswith("rung 0")].to_string(index=False))
else:
    print("No rung-0 run is recorded yet.")"""),

    md("""### Where the full outputs live, and how we count effort

* **Summary** of every run (scores, per-task seconds and tokens, grader notes): `research/runs.jsonl`,
  in git, small.
* **Everything else** (agent trajectories, serve logs, grader output, produced files): the
  Cloud Storage bucket `gs://ple-runs-<project number>/runs/`, synced from the VM after each run
  by `infra/gcp-vm/save_runs.sh`. The "engineering reasoning" walk-through is written from these.
* **Effort is counted in model calls, tokens and runtime, not dollars.** A *call* is one request
  the harness sends to the model endpoint. The harness counts them itself and writes one
  `CALLS {...}` line per task: successful calls, failed calls (errors and streams that ended
  early), and tokens as the endpoint reports them: input (of which **cached**, served from the
  provider's prompt/KV cache) and output (of which **reasoning**). Every retry is its own call
  and the SDK's hidden retries are switched off. The raw `usage` object of each call is logged
  too (`USAGE {...}`), so the figures can be checked against what the endpoint said. Two limits:
  a failed call's tokens are invisible to us, and whether the evaluator's own `tokens` figure
  counts cached tokens inside input or beside it is still to be verified against these lines.
  Our own cache estimate: each call also logs hashes of its prompt prefix (never the text), and
  `research/kvcache.py` replays the calls through a simulated prefix cache (longest shared prefix
  with an earlier call of the same model within a time window, above a minimum size) to split
  input tokens into cached and uncached. The window and minimum are provider-specific and not
  known to us: they are placeholders until calibrated against the endpoint's reported cached
  tokens, and `kvcache.compare` shows how far off the estimate is.
  Judge calls are made by the grader and are never added in.
  The efficiency plots (score against calls, tokens and runtime) read these numbers."""),

    code("""import costs
usage = pd.DataFrame([{"run": r["run_id"], "model": r["harness"]["model"], **costs.run_usage(r)} for r in runs])
usage"""),

    md("""### Rung 0 v2, one task: `data-hall-mep-routing`

To start simple we ran both models on a single task, a checks-graded one (no LLM judge involved).
Both scored **0.0**, for different reasons, and the grader's own report says exactly why.

| | Gemini 3.8 Flash | Gemini 4 Neon |
|---|---|---|
| output tokens (of which thinking) | 63,996 (60,587) | 49,290 (29,597) |
| why the call ended | hit the 64,000-token cap | finished |
| what was written | a script cut off mid-file | a 48 KB script and a reconciliation file |
| grader verdict | `ERR_NO_OUTPUT`: the script wrote no file | `ERR_CLASH`: valid design, but two hard gates failed |

**What the trial folders show once read in full.** This task's only inputs are **seven PNG drawing
sheets**, and rung 0 lists images by name only (`image: not included as text`). Neither model
saw a drawing. Neon said so in its final message ("all seven required drawing sheets were omitted
in this text-only environment") and wrote a template with provisional placeholders for everything
that comes from the drawings: hall dimensions, column grid, entry points, sprinkler positions. The
grader's two failed gates are consequences of that: the service entry at (200, 3360) exists only
on sheets M-101/E-101, and a guessed layout cannot connect to it or clear unseen clashes.

So the 0.0 on this task measures **missing inputs, not engineering ability**. Flash's cut-off
(thinking used 60,587 of 63,996 tokens) is a second, separate fault. Two lessons for the ladder:
rung 0 as built is blind on every task whose inputs are images, so it cannot serve as a floor
for those; and the first capability to add is *seeing the inputs*, before any run-and-check
loop. (Our first note here said the missing piece was a run-and-check loop; reading the
trajectory showed that was premature, and it is kept in the lab log as a correction.)"""),

    md("""## 5. A reference point, and what it taught us

### The official template on half A

The competition's starter repository ships a complete dev run of the Pi coding agent on Claude
Opus 5.5. We did not build it; we record it as a reference for what a capable general-purpose
coding agent scores on our half A."""),

    code("""reference = runs[0]
plot_runs([reference["run_id"]], "Reference: official template (Pi + Claude Opus 5.5), score per task on half A");"""),

    code("""f = task_frame(reference)
f.groupby("grading")["score"].agg(["mean", "count"]).round(3)"""),

    md("""**What stands out**

* A wide spread: two tasks score `1.0`, two score `0`.
* The three structural calculation tasks (wind diaphragm, roof deck, and the EOR corrections)
  all sit around `0.3`.
* One of the zeros, `data-hall-mep-routing`, is a near miss, below."""),

    md("""### A near miss that scored zero

`data-hall-mep-routing` asks for a Python script that builds a clash-free 3D model (IFC) of a data
hall from seven drawing sheets and routes cable tray, busway and chilled-water pipe through it.

We re-graded the template's own deliverable with the task's public grader:

| | template's design | reference route |
|---|---|---|
| connectivity (every row served, every cooling unit reached) | passed | passed |
| total route length | 186.9 m | 260.6 m |
| code-rule violation rate | 8 % | 0 % |
| clashes over 2 mm | **23** | 0 |
| **score** | **0** | 1 |

Every one of the 23 clashes is between two segments **of the same service** overlapping where
they join. Without them the design would have scored about **0.92**. One generic check (no two
solids overlap by more than 2 mm, including pieces of the same route), run before finishing, would
have caught it.

This is the pattern our harness is built around: **the agent defines how its work will be
judged, checks its work against that before finishing, and fixes what fails.**"""),

    md("""## 6. The ladder: build up from the floor

We add one capability at a time, each motivated by a failure we observe, measuring every step on
half A.

| Rung | Harness | Question it answers |
|---|---|---|
| 0 | **one model call**: files pasted in as plain text, deliverables written from the reply | how far does one careful read of the project get? |
| 1 | a tool loop: read files, run commands, write files | how much does access to the project add? |
| ... | each next capability is chosen from what rung *n* got wrong | |

Rung 1 is chosen after we have read rung 0's failures task by task."""),

    md("""## Lab log

Dated, honest notes, including what went wrong. Newest last.

* **2026-11-25.** Docker on the Mac is too small, so runs move to a cloud VM. Budget and hard cap
  set up. Claude Opus 5.5 has zero Vertex quota (three increase requests auto-denied), so the dev
  judge is Gemini 4 Neon.
* **2026-11-25.** The Mac broke. A GitHub Actions workflow now drives the VM from a cloud session.
  First attempts failed on small things (a service-account name too short, a lookup that needed
  admin rights).
* **2026-11-26.** The Hugging Face token never reached the VM (it was empty), and two of our own
  checks reported "access OK" when it was not. Replaced with a repository secret and a check that
  tests real access.
* **2026-11-26.** First rung-0 start: the 29-task dataset (16,425 files) downloaded in 28 minutes
  through Hugging Face's rate limit, then the run stopped because the model proxy was not running
  after the VM's reboot. The run script now starts the proxy if it is down.
* **2026-11-26.** Read the judging criteria. Added: a bucket for full run outputs, exact model-call
  counting in the harness (efficiency is judged on calls, tokens and runtime, so no billing
  export), and a write-up tracker keyed to the five criteria.
* **2026-11-26.** Wrote down what every run must record (`docs/run-records.md`) so failures can be
  analysed check by check. Found that the tracker kept only the first grader file per task; it now
  keeps all of them. Found that the competition's proxy retries failed requests itself (3 times),
  so our own call counts are lower bounds; added a request log at the proxy to count what the
  provider actually served, judge calls included.
* **2026-11-26.** Rung 0 v1 finished: Flash 0.007, Neon 0.000. Not a result about the models: the
  32,000-token output cap was reached in nearly every task (thinking tokens count against it) and
  most tasks wrote no file. Kept in the tracker, annotated invalid; reran as v2 with a 64,000 cap
  and finish reasons logged. A lesson for every later rung: **check that the harness's own limits are
  not the thing being measured.**
* **2026-11-26.** Ran rung 0 v2 on one task, both models: 0.0 each. Flash's thinking used 60,587 of
  its 63,996 output tokens and the script was cut off; Neon finished a runnable script that fails
  the clash gate (5 clashes) and the connectivity gate (not connected to the service entry). The
  request log works against the real proxy, and showed that the proxy reports `finish_reason: stop`
  on some calls that spent their whole budget thinking: our cut-off check is only reliable when the
  provider reports `length`, so the harness also needs a token-count check.
* **2026-11-26.** Correction after reading the full trial folders: both models were blind to the
  seven drawing PNGs (images are listed by name only). Neon said so itself and wrote placeholders.
  The "needs run-and-check" conclusion above was premature; rung 0 cannot be a floor on image tasks.
* **2026-11-26.** Decision: **rung 0 is invalid so far.** All four runs (run-001 to run-004) are marked
  invalid in the tracker with the reason; they are kept, not deleted. Rung 0 v3 changes exactly one
  thing: images are attached to the request (the harness reads them and sends them as image parts;
  `NAIVE_IMAGES=0` switches it off for later comparison). Same 64,000-token cap, same reasoning
  effort, same single call.
* **2026-11-26.** Near-loss: syncing the VM's code overwrote its `runs.jsonl`, which held the Neon
  run's record uncommitted. A saved patch let us recover it; the sync now merges records instead
  (`infra/gcp-vm/merge_runs.py`). Lesson: a record that lives only on a machine is not recorded.
* **2026-11-26.** Review of `harnesses/naive` found that a reply cut off at the token limit
  silently lost its last file. Fixed in the harness (the partial file is now written and the cut-off
  is logged); rung 0's first runs predate that fix, which matters only for tasks where the reply
  was cut off."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
})
path = HERE / "journal.ipynb"
nbf.write(nb, path)
print(f"wrote {path}")
