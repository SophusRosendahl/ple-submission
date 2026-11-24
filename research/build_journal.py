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

Every number below is read from the run tracker (`research/runs.jsonl`) when the notebook runs."""),

    md("""## 1. The problem

PLE has 85 real engineering tasks: structural, civil, electrical and mechanical. Each runs in an
isolated container with the project's files and up to 6 hours, and asks for a real deliverable: a
calculation package, a coordinated IFC model, a review memo. Tasks are graded `0`–`1` by
programmatic checks, by an LLM judge against an expert rubric, or both.

An entry is a **harness**, the code that drives a model through each task, paired with one of the
Google-sponsored models. The best stock setup on the public leaderboard (Gemini 4 Neon with
Google's own agent) scores **0.507** on the 56 hidden tasks: about half the available points."""),

    md("""## 2. How we measure

**The score.** A run is scored exactly as the competition scores a submission: each task's grader
gives `0`–`1`, rubric tasks are judged by Claude Opus 5.5, a task with no result counts as `0`, and
the run's score is the mean over the set.

**A split we don't cheat on.** The 29 public dev tasks are split in two. We develop only on
**half A**. **Half B** is held out and run rarely, to check that what helps on A carries over to
tasks we have never looked at. Five tasks we had studied in detail before splitting were placed in
A by construction; the rest were assigned at random (fixed seed), balanced by grading type."""),

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

    md("""## 3. Runs recorded so far"""),

    code("""runs = tracker.load_runs()
overview = pd.DataFrame([{
    "run": r["run_id"], "label": r["label"], "model": r["harness"]["model"],
    "half": r["half"], "score": round(tracker.score(r)["score"], 3),
    "measured": f"{tracker.score(r)['n_measured']}/{tracker.score(r)['n_tasks']}",
    "run date": (r["source"].get("run_date") or "")[:10],
} for r in runs])
overview"""),

    md("""## 4. A reference point: the official template on half A

The competition's starter repository ships a complete dev run of the Pi coding agent on Claude
Opus 5.5. We did not build it; we record it as a reference for what a capable general-purpose
coding agent scores on our half A."""),

    code("""INK, MUTED, GRID, SURFACE = "#1f1f1e", "#6b6a64", "#e7e6e1", "#fcfcfb"
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
    return fig

reference = runs[0]
plot_runs([reference["run_id"]], "Reference: official template (Pi + Claude Opus 5.5), score per task on half A");"""),

    code("""f = task_frame(reference)
f.groupby("grading")["score"].agg(["mean", "count"]).round(3)"""),

    md("""**What stands out**

* A wide spread: two tasks score `1.0`, two score `0`.
* The three structural calculation tasks (wind diaphragm, roof deck, and the EOR corrections)
  all sit around `0.3`.
* One of the zeros, `data-hall-mep-routing`, is a near miss, below."""),

    md("""## 5. First observation: a near miss scored zero

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

    md("""## 6. Plan: build up from a single model call

We start from the simplest possible harness and add one capability at a time, each motivated by
a failure we observe, measuring every step on half A.

| Rung | Harness | Question it answers |
|---|---|---|
| 0 | **one model call**: task text in, deliverables written from its reply; it cannot read the inputs or run anything | how much of the score is pure engineering knowledge? |
| 1 | a tool loop: read files, run commands, write files | how much does access to the project add? |
| … | each next capability is chosen from what rung *n* got wrong | |

Rung 0 is implemented in `harnesses/naive/`. Next step: run it on half A."""),
]

nb = nbf.v4.new_notebook(cells=cells, metadata={
    "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
    "language_info": {"name": "python"},
})
path = HERE / "journal.ipynb"
nbf.write(nb, path)
print(f"wrote {path}")
