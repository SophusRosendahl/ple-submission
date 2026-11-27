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
| 1 | **Insight & failure analysis** (25) | Something non-obvious; real dev-set failures; controlled ablations ("we added X, score went A to B"); ideas that failed | Near miss in section 5; lab log; **rung 1: the model writes its own checks unprompted and gets one wrong (section 6a)**. Need: one-change-at-a-time ladder runs, repeats, failures read task by task, failed ideas written down | draft |
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

**The idea in one sentence.** Every run happens in a cloud environment we built to look like the evaluation
environment as closely as we could, so that what we measure on the development tasks is what the evaluation would
measure.

**Where it matches** (checked against the organizers' own files and our run records):

* The runner, graders and task images are the organizers' own, from their repository at one recorded commit with no
  local changes. Each run record stores that commit.
* Each task runs in its own container with the CPUs and memory the task declares, no network, and our harness in a
  separate container, talking to it over the competition's protocol.
* The models are reached through the organizers' own proxy configuration, with the same model names, backed by
  Vertex AI, and the default reasoning level is the models' highest, as in the evaluation.

**Where it does not match** (stated so the numbers are read correctly):

* Judged tasks use Gemini 4 Neon as judge, the leaderboard uses Claude Opus 5.5 (below). The task this write-up
  studies is graded by plain code, so its scores are not affected.
* Our machine is far larger (32 CPUs); it only decides how many trials run side by side.
* The backend behind the real sponsored model endpoint is not documented; ours is Vertex AI in our own project.
* We have only the 29 development tasks, not the hidden test set.

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

    md("""> **Status (2026-11-26): rung 0 has its first valid result: v5 (single call, images attached, low
> reasoning effort).** Runs run-001 to run-008 stay in the tracker flagged `INVALID` with their reasons
> (blind to images, then a thinking budget that left no room to answer). See the lab log."""),

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

    md("""### Rung 0 v3: the model can see the drawings (run-005, run-006)

Same single call as v2, with the seven PNG sheets attached. **Both still score 0.0, now for a third
reason: the thinking budget.** With the drawings in front of it, the model thinks far longer.

| | Gemini 3.8 Flash | Gemini 4 Neon |
|---|---|---|
| output tokens (thinking) | 63,996 (61,438) | 64,000 (**64,000**) |
| visible answer | thinking text leaking out, no files | none at all |
| files written | 0 | 0 |
| grader | `ERR_NO_SUBMISSION` | `ERR_NO_SUBMISSION` |

Neon spent its entire 64,000-token budget on thinking, so the reply is empty. Flash's reply is its
own working ("Row A: Y = 3000, Row B: Y = 6000, ...": it did read the row positions off the
sheets) cut off before any file. The v2 runs without images thought for 30k tokens; seeing the
drawings roughly doubles it.

Also found: every image was attached **twice** (the extractor scans two overlapping folders), which
doubled the image tokens (18.5k prompt tokens for seven sheets). Fixed in the harness; the v3
token figures are inflated by it.

**Verdict (user decision): v3 is invalid too.** The budget was too small for what the task needs, so
the run measures nothing about the model. v3 is flagged `INVALID` in the tracker.

**The output limit, measured, not assumed.** We probed each endpoint with a trivial request at
increasing `max_completion_tokens` (2026-11-26): **Gemini 3.8 Flash rejects anything above 65,536**
(HTTP 400), while **Gemini 4 Neon accepted every value up to 1,000,000.** So the budget is now per
model (Flash 65,536, its ceiling; Neon 200,000; Gemini 4 Argon stays at 65,536 as the competition
notes say). The duplicate-image bug is fixed too. This is rung 0 v4.

**v4 (run-007, run-008): the budget cannot be raised.** Flash was cut off again (62,914 of 65,532 tokens
spent thinking). Neon was asked for 200,000 tokens and stopped at **exactly 65,536, all of it thinking,
zero text tokens**, with `finish_reason: stop`. The probe only showed that the API *accepts* larger
values for a trivial request, not that the model generates beyond 65,536 (accepted is not honoured).
The effective output ceiling is 65,536 tokens for both models. Both runs are flagged `INVALID`: at the
default reasoning level one call cannot read the drawings and write the script. Seven drawings cost
7,560 image tokens (1,080 each) and the images are now attached once.

**Restart on interruption: built, then scrapped (user decision).** The idea was to call again with the
input and the output so far when a reply is cut off. It does not fit: the model's hidden thinking cannot be
fed back, so for Neon (65,536 tokens of hidden thinking, nothing visible) a restart is just a retry. The
real answer to a fixed output budget is an agent loop, with state in files and a fresh budget per step.
For rung 0 the next try is simpler: **a low reasoning effort** (v5, single call, nothing else changed).

### Rung 0 v5: low reasoning effort, the first valid result (run-009, run-010)

Same single call, images attached once, reasoning effort **low**. Both models now write a script and
the grader runs it.

| | Gemini 3.8 Flash | Gemini 4 Neon |
|---|---|---|
| output tokens (thinking) | 11,506 (0) | 25,954 (14,730) |
| files written | `solution.py`, `reconciliation.json` | `solution.py`, `reconciliation.json` |
| grader | `ERR_EXEC`: the delivered script failed when the grader ran it | valid model; **connectivity gate passed**, **clash gate failed** |
| the failure | `pset.edit_pset(product=...)`: no such argument (an ifcopenshell API mistake) | 30 hard clashes, 8.5 % rule violations, route 402 m against an optimum of 261 m |
| score | 0.0 | 0.0 |

Reading the drawings worked: Neon's design connects every service to the entry that its first,
blind attempt missed. What is left are the failures a person finds by *running* the work: Flash's
script dies on its first execution, and Neon's clashes show up as soon as a clash check is run on its
own model. Neither model could run anything in this design. That is the evidence for rung 1: a loop in
which the model runs its script and the checks the grader will apply, and fixes what they show.

**What this says.** In one call, at the default (highest) reasoning level, a task that needs
seven drawings read and a 400-line script written does not fit in a 64,000-token output budget.
The reasoning level is therefore a design knob to measure (low / medium / high), not a constant."""),

    md("""### The score is not enough: every check, one by one

The grader runs many checks and a single failed *gate* zeroes the score, so the score hides the rest.
`research/check_table.py` lists every check of a trial next to the score. Below: the blind v2 attempt
(run-004), Flash at low effort (run-009, its delivered script failed when run, so no check ran) and Neon at low effort (run-010)."""),

    code("""import check_table
from IPython.display import Markdown, display
for rid in ("run-004", "run-009", "run-010"):
    display(Markdown(check_table.table(rid)))"""),

    md("""**Reading run-010 (Neon, low effort, images), check by check**

* **Passed:** the script runs, the IFC4 contract (gate 0), and **connectivity (gate 2)**: all 6 rows
  served at 98 % or better and all 22 cooling units reached. This is the effect of seeing the drawings:
  the blind run (run-004) was not connected to the entry at all.
* **Failed gate 1, 30 clashes, in two groups.** **22 are segments of the same service overlapping where
  they join** (8 chilled water, 7 busway, 7 cable tray): the same defect the official template's near
  miss had. **8 are the model's own background rebuild** clashing with itself (for example the
  containment roof against its door). One generic check, "no two pieces of a route overlap by more than
  2 mm", would remove 22 of the 30.
* **Failed two compliance rules, both from the rebuild, not the routing.** 16 sprinkler heads sit at
  1,890 mm above the floor where 2,600 mm is needed (an elevation misread), and 8 cable-tray runs leave
  only 166 mm of access underneath where 300 mm is needed.
* **Efficiency:** the route is 402 m against a 261 m reference (factor 0.648, 54 % too long).
* **Two rules checked nothing, and count as NOT PASSED** (`wide_obstruction_needs_sprinkler`,
  `tray_below_tile`: 0 items checked, in this run and in the blind one). The grader lets a rule through when
  the submitted model has nothing it applies to, but a compliance check that tested nothing does not show
  compliance, so we count it as not passed. Run-010's tally is **6 of 11 passed, 3 failed, 2 not passed**.
  **Why they checked nothing (from the task's own drawings, 2026-11-27).** Both rules are defined on the
  sheets, and the model built both elements to those definitions. Sheet A-301 says the top of any under-floor
  tray must be 20 mm or more below the underside of the floor panel, and that the access floor is one 35 mm
  panel following the room outline (not tiles): the script's floor is exactly that, and its tray top sits 88
  mm below the panel. Sheets F-101 and A-602 say the 1,400 mm cold-aisle containment roof is a fixed
  obstruction wider than 1,200 mm that needs heads beneath it: the script's four roofs are 1,400 mm wide and
  it has the 16 in-aisle heads. Yet the grader found nothing to check for either rule, although it did see
  the roofs for the clash gate. **None of the seven sheets, and not the task text, names the IFC class,
  type or property that identifies a floor panel or a containment roof** (every sheet answered "none" when
  asked for IFC class, ObjectType or property-set names; the task text only says "exact element classes" and
  gives one example, racks). So the likely cause is a hidden naming convention: the grader recognises these two
  elements by names the task never states. This is a likelihood, not proven; the grader's own files would
  show it and we do not open them.
* **If every gate had passed, the score would have been 0.593** (compliance 0.915 x efficiency 0.648).
  That is the real distance to a usable answer.

Neither the 22 same-service overlaps nor the sprinkler height needed engineering judgement to find: a
script that checks its own model finds them."""),

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

    md("""### Rung 0 findings (run-009 to run-016: 8 observations, 4 per model, one task)

**Headline: a single call never produced a model that passes the gates. All 8 observations scored 0.0, and
four different things stopped them.** One task (`data-hall-mep-routing`), one call, files and the seven drawing
sheets attached, reasoning effort low, judge Gemini 4 Neon. Each run is one trial; the label says repeat n.

| Model | Calls | Input tokens | Output tokens | Time | What the grader found, per observation |
|---|---|---|---|---|---|
| Gemini 3.8 Flash | 1 | 10,043 | 11,404 to 13,809 | about 1.3 min | script failed to run (3), clash gate failed (1) |
| Gemini 4 Neon | 1 | 10,076 | 25,066 to 50,422 | 3.6 to 5.2 min | clash gate failed (2), invalid IFC (2) |

**What the failures are**

1. **The delivered script does not run (3 of 8, all Flash).** The agent did not crash: it finished and
   delivered `output/solution.py`, and the grader's run of that file failed within one second on a wrong
   ifcopenshell call: `pset.edit_pset(product=...)` (no such argument), `aggregate.assign_object(product=...)`
   (the argument is `products`), and `col_shape.Representations[0]` (no such attribute). For two of these,
   ifcopenshell's own message prints the correct signature: one run of the script would have shown it.
2. **The script runs but writes an invalid IFC file (2 of 8, both Neon).** The grader reports 7 to 8 schema
   violations (for example 6 shape representations where exactly 1 is allowed).
3. **Valid model, clash gate fails (3 of 8).** Only here do the compliance rules run. Two of the rules checked
   nothing in any of these runs (`wide_obstruction_needs_sprinkler`, `tray_below_tile`), so we count them not
   passed. Of the rules that did run, `clear_height` and `tray_stack_headroom` failed every time. Had the gates
   passed, the two runs we read would have scored 0.538 (Flash) and 0.612 (Neon), mostly route length:
   425 m and 389 m against 261 m.
4. **Nothing in the run can tell the model any of this.** One call has no way to execute what it wrote.

**Reading it.** The weak point is not understanding the task: a model that gets through the gates scores about
0.5 to 0.6 before any rule fix. It is that the deliverable is a program the model wrote blind. Cost is small and
exact: one call, about 10,000 input tokens, 11,000 to 50,000 output tokens. Effort at low cut Neon's output from
65,536 tokens (all spent thinking) to about 25,000.

**What we deliberately did not do.** We did not add a run-and-check step to rung 0; that would no longer be a
single call. Running the delivered file, and validating the model it writes with ifcopenshell, are recorded as
requirements for a later rung (design-decisions: Run the deliverable). Rung 1 does not include them."""),

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
| 1 | Pi agent loop; files fed as context (not read by tool); write, edit, bash; a review-your-work instruction; no structured checks, no ifcopenshell | how much does a loop that can look at its own work add? |
| ... | each next capability is chosen from what rung *n* got wrong | |

Rung 1 is chosen after we have read rung 0's failures task by task."""),

    md("""### 6a. Rung 1: the model starts writing its own checks, and gets one wrong

**We never asked for self-checks. Rung 1 only gave the model tools and a note to review its work. Both models
wrote their own checks anyway, and the check that mattered used the wrong definition.** (One run per model, task
`data-hall-mep-routing`, rung 1 v1; keyword counts over the agents' commands.)

| | Gemini 3.8 Flash (run-017) | Gemini 4 Neon (run-019) |
|---|---|---|
| commands the agent ran | 295 | 21 |
| schema validation of its own model (`ifcopenshell.validate`) | 6 | 3 |
| pairwise geometry clash checks | 10 | 2 |
| of those, checks that skip pairs of the same service | 4 | 2 |
| first clash check (step of its run) | 245 of 295 | 19 of 21 |

What it got right: schema validation (the grader's schema gate passed in both runs), and Neon's first clash check
found 8 overlaps in its own room rebuild, which the final model does not have (rung 0 had 2 to 10 such overlaps in
every run).

What it got wrong: both clash checks skipped same-service pairs, with a comment saying why (Neon: *they meet at
tees/elbows*; Flash: *don't check elements of same service network*). The task defines a hard clash as one solid
overlapping another by more than 2 mm **anywhere**, and the grader reports 22 same-service overlaps in both runs,
the only gate that failed. The check agreed with the model's belief, not with the task.

**Why this matters for the write-up.**
1. **The behaviour is real and appears with the loop, not before.** Rung 0 (one call, no tools) had no chance to
   check anything; with tools both models started verifying their output without being told.
2. **A self-check is only as good as the definition it encodes.** A check built from the model's own reading of
   the requirement can pass while the requirement fails. More checking is not enough; the check has to come from
   the requirement as written.
3. **It motivates the next rung** (structured self-check against the task's own words) with a failure we
   observed, rather than a guess. Whether it works is for the next measurement; one run per model so far."""),

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
* **2026-11-26.** Rung 0 v3 (images attached), run-005 and run-006: both 0.0 again. With the
  drawings visible, both models spent the whole 64,000-token budget thinking (Neon: all 64,000 as
  reasoning, empty reply) and wrote no file. Also found that images were attached twice; fixed.
  Next knob to measure: reasoning effort.
* **2026-11-26.** Decision: v3 (run-005, run-006) is **invalid**: the output budget was too small, so
  nothing was written. Probed the endpoints: Flash's hard output limit is 65,536, Neon accepts up to
  1,000,000. Rung 0 v4 uses a per-model budget (Flash 65,536, Neon 200,000) and the image-dedupe fix.
* **2026-11-26.** Rung 0 v4 (run-007, run-008) invalid: the effective output ceiling is 65,536 for
  both models, even though the API accepted 200,000 for Neon (it stopped at exactly 65,536, all
  thinking, no text). The budget cannot be raised; the reasoning level is the remaining lever.
* **2026-11-26.** Decision: do not split into two calls; tried **restart on interruption** (feed the model its
  input and its output so far), implemented it with seven tests, then **scrapped it** the same day: hidden
  thinking can't be fed back, so for Neon it degenerates into a retry. The output ceiling is simply 65,536
  for both Gemini models. Rung 0 v5 = the single call at **low reasoning effort** instead.
* **2026-11-26.** Rung 0 v5 (low effort), run-009 and run-010: **the first valid rung-0 result.** Both
  wrote a script. Flash's delivered script failed when the grader ran it (a wrong ifcopenshell argument); Neon's ran, passed the schema and
  connectivity gates and failed the clash gate (30 clashes). Score 0.0 each, for reasons a run-and-check
  loop would catch. Lowering the effort cut Neon's output from 65,536 hidden-thinking tokens to 25,954.
* **2026-11-27.** Rung 0 v5 repeated three times (run-011 to run-016): all six scored 0.0; with run-009/010, eight observations. Three deliveries (all Flash) failed when the grader ran the script (wrong ifcopenshell arguments, an attribute that does not exist), two were invalid IFC, three had clashes. **The agent did not crash: it finished and delivered a file that does not run.** Trying the file is the first thing an agent must do; the harness must do it too (design-decisions, 'Run the deliverable').
* **2026-11-27.** Rung 1 v1, run-017 (Flash, 287 calls) and run-019 (Neon, 10 calls): both deliver a script that runs and a valid model; both fail the clash gate on the same 22 same-service overlaps. **Both models wrote their own checks unprompted, and both clash checks skipped same-service pairs** (section 6a). Input re-reads by Flash: 10 commands (baseline for the input guard); the v2 job was cancelled when the 20-call budget was decided; v3 runs.
* **2026-11-26.** Looked at the grader's checks one by one (`research/check_table.py`). Neon at low effort:
  schema and connectivity pass; 30 clashes (22 are consecutive segments of the same service overlapping at
  their joints, 8 are the model's own background); 16 sprinkler heads at 1,890 mm (needs 2,600) and 8
  tray runs with 166 mm of access (needs 300); route 54 % too long. Would score 0.593 if the gates passed.
* **2026-11-26.** Process: a job that powers the VM off by itself raced the workflow's own pull and
  lost its results for a while (they were safe on the VM disk and in the bucket). The VM is now
  stopped by the workflow, after the pull.
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
