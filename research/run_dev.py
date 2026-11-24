"""Run a harness on one half of the dev split, score it, and record it in the tracker.

Scoring is the competition's own: ple's eval/run.py runs each task with the real task images
and graders (rubric tasks judged by the judge model, Claude Opus 5.5 by default), every task
in the half counts, and a task with no result scores 0. The tracker then prints the full
report (research/tracker.py report).

Needs, on the machine that runs it: Docker, uv, Harbor 0.20.0 with websockets, a clone of the
competition repository, and an env file with MODEL_PROXY_URL / MODEL_PROXY_KEY (and HF_TOKEN
on first use). See the competition's eval/README.md.

Example:
  python research/run_dev.py --ple ../ple --entry harnesses/naive \\
      --label "rung 0: single model call" --env-file ../ple/local.env
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

import tracker

REPO = pathlib.Path(__file__).resolve().parent.parent


def git_commit(path: pathlib.Path) -> str | None:
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True, check=False)
    dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--", "."],
                           capture_output=True, text=True, check=False).stdout.strip()
    return (out.stdout.strip() + ("+dirty" if dirty else "")) if out.returncode == 0 else None


def app_tasks():
    """Half-A tasks that run app servers (from research/task_resources.json)."""
    res = json.loads((REPO / "research" / "task_resources.json").read_text(encoding="utf-8"))
    return {t for t, r in res["tasks"].items() if r.get("apps")}


def split_by_memory(tasks, max_gb):
    """Splits tasks into those whose task + harness containers fit in max_gb of Docker memory."""
    res = json.loads((REPO / "research" / "task_resources.json").read_text(encoding="utf-8"))
    overhead = res["harness_overhead"]["memory_mb"]
    fits, too_big = [], []
    for t in tasks:
        need = res["tasks"].get(t, {}).get("memory_mb")
        (fits if need is not None and (need + overhead) / 1024 <= max_gb else too_big).append(t)
    return fits, too_big


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ple", type=pathlib.Path, required=True, help="clone of the competition repository")
    ap.add_argument("--entry", type=pathlib.Path, required=True, help="harness folder holding submission.yaml")
    ap.add_argument("--label", required=True, help="what this run is, for the tracker")
    ap.add_argument("--half", default="A", choices=["A", "B", "all"])
    ap.add_argument("--holdout", default=None, help="reason, required for half B or all")
    ap.add_argument("--tasks", default=None, help="comma-separated subset of the half (default: the whole half)")
    ap.add_argument("--max-memory-gb", type=float, default=None,
                    help="only tasks whose task + harness containers fit in this much Docker memory")
    ap.add_argument("--skip-apps", action="store_true",
                    help="leave out tasks that run app servers (large images, more memory)")
    ap.add_argument("--env-file", type=pathlib.Path, default=None)
    ap.add_argument("--trials", type=int, default=None, help="tasks to run in parallel")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)

    if a.half != "A" and not a.holdout:
        sys.exit("running half B needs --holdout 'why this hold-out use is justified'")
    half_tasks = tracker.tasks_of(a.half)
    tasks = [t.strip() for t in a.tasks.split(",")] if a.tasks else half_tasks
    outside = [t for t in tasks if t not in half_tasks]
    if outside:
        sys.exit(f"not in half {a.half}: {', '.join(outside)}")
    if a.max_memory_gb is not None:
        fits, too_big = split_by_memory(tasks, a.max_memory_gb)
        print(f"fits in {a.max_memory_gb:g} GB: {len(fits)} tasks; left for later: {', '.join(too_big) or 'none'}")
        if not fits:
            sys.exit("no task fits in that much memory")
        tasks = fits

    if a.skip_apps:
        apps = app_tasks()
        left = [t for t in tasks if t in apps]
        tasks = [t for t in tasks if t not in apps]
        print(f"without app servers: {len(tasks)} tasks; left for later: {', '.join(left) or 'none'}")
        if not tasks:
            sys.exit("every selected task runs app servers")

    entry = a.entry.resolve()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = REPO / "runs" / f"{entry.name}-{a.half}-{stamp}"
    cmd = ["uv", "run", "python", "eval/run.py", str(entry), "--tasks", ",".join(tasks),
           "--out", str(out), "--no-export"]
    if a.env_file:
        cmd += ["--env-file", str(a.env_file.resolve())]
    if a.trials:
        cmd += ["--trials", str(a.trials)]
    print("running:", " ".join(cmd), flush=True)
    code = subprocess.run(cmd, cwd=a.ple, check=False).returncode
    if not (out / "results.json").is_file():
        sys.exit(f"eval/run.py exited {code} and wrote no results.json in {out}")
    partial = len(tasks) < len(half_tasks)
    notes = a.notes + (f" (subset: {len(tasks)} of {len(half_tasks)} tasks)" if partial else "")
    rec = tracker.import_results(out, a.label, a.half, notes.strip(), git_commit(entry), a.holdout)
    print()
    print(tracker.report(rec))
    if partial:
        print("\nnote: tasks of the half that were not run count as 0 in the score above;"
              " merge batches with `tracker.py combine`")


if __name__ == "__main__":
    main()
