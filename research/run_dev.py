"""Run a harness on one half of the dev split, score it, and record it in the tracker.

Scoring is the competition's own: ple's eval/run.py runs each task with the real task images
and graders, every task in the half counts, and a task with no result scores 0. The tracker
then prints the full report (research/tracker.py report).

Judge: rubric and checks-judge tasks are scored by an LLM judge. The leaderboard uses Claude
Opus 5.5 (`--judge official`); early runs use a cheaper one (`--judge dev`, the default, or
`--judge cheap`), and any proxy model name works too. `PLE_JUDGE` sets the default for a shell
session. The tracker records the judge of every run, and scores are only comparable between
runs with the same judge.

Needs, on the machine that runs it: Docker, uv, Harbor 0.20.0 with websockets, a clone of the
competition repository, and an env file with MODEL_PROXY_URL / MODEL_PROXY_KEY (and HF_TOKEN
on first use). See the competition's eval/README.md.

Example:
  python research/run_dev.py --ple ../ple --entry harnesses/naive \\
      --label "rung 0: single model call" --env-file ../ple/local.env
  PLE_JUDGE=official python research/run_dev.py ...     # judge with Claude Opus 5.5
  python research/run_dev.py ... --model gemini-3.8-flash   # same entry, another harness model
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile

import tracker

REPO = pathlib.Path(__file__).resolve().parent.parent

# Judge presets (proxy model names). Change a preset here to switch every run that uses it.
JUDGES = {
    "cheap": "gemini-3.8-flash",     # plumbing tests: does the pipeline score at all
    "dev": "gemini-4-neon",          # early ladder runs on half A
    "official": "claude-opus-5-5",   # what the leaderboard uses; for runs we compare to the reference
}
DEFAULT_JUDGE = "dev"


def resolve_judge(name: str, env_file: pathlib.Path | None) -> str:
    """Maps a preset or model name to the judge model; refuses a conflicting JUDGE_MODEL in the env file."""
    model = JUDGES.get(name, name)
    if env_file and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "JUDGE_MODEL" and value.strip():
                if tracker.judge_name(value.strip()) != tracker.judge_name(model):
                    sys.exit(f"{env_file} sets JUDGE_MODEL={value.strip()}, which overrides --judge {name} ({model}):"
                             " remove it from the env file and choose the judge with --judge or PLE_JUDGE")
    return model


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


def with_model(entry: pathlib.Path, model: str | None, effort: str | None = None) -> pathlib.Path:
    """A temporary copy of the entry with another model and/or a reasoning level; the entry itself is unchanged.

    The copy lives outside any git work tree, so the kit builds every file in it. `effort` becomes the
    REASONING_EFFORT environment variable the harness reads (submission.yaml `env`).
    """
    variant = pathlib.Path(tempfile.mkdtemp(prefix="ple-variant-")) / entry.name
    shutil.copytree(entry, variant, ignore=shutil.ignore_patterns(".venv", "__pycache__", "node_modules", "artifacts"))
    spec = variant / "submission.yaml"
    text = spec.read_text(encoding="utf-8")
    if model:
        model_api = model if "/" in model else f"google-cloud/{model}"
        text, n = re.subn(r"^model_api:.*$", f"model_api: {model_api}", text, count=1, flags=re.M)
        if n != 1:
            sys.exit(f"{entry / 'submission.yaml'} has no model_api line to replace")
    if effort:
        if re.search(r"^env:\s*$", text, flags=re.M):
            text = re.sub(r"^env:\s*$", f'env:\n  REASONING_EFFORT: "{effort}"', text, count=1, flags=re.M)
        else:
            text = text.rstrip("\n") + f'\nenv:\n  REASONING_EFFORT: "{effort}"\n'
    spec.write_text(text, encoding="utf-8")
    return variant


def run_environment(started, finished, trials, judge, model_override, effort=None):
    """Where and how long a run took: what the efficiency plots and the VM-hours count need."""
    try:
        mem_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except (ValueError, OSError, AttributeError):
        mem_gb = None
    return {
        "started": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "finished": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "wall_seconds": round((finished - started).total_seconds()),
        "parallel_trials": trials, "machine": {"host": platform.node(), "cpus": os.cpu_count(), "memory_gb": mem_gb},
        "judge": judge, "model_override": model_override, "reasoning_effort": effort or "default",
    }


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
    ap.add_argument("--judge", default=os.environ.get("PLE_JUDGE", DEFAULT_JUDGE),
                    help=f"judge preset ({', '.join(f'{k}={v}' for k, v in JUDGES.items())}) or a proxy model name;"
                         f" default $PLE_JUDGE or {DEFAULT_JUDGE}")
    ap.add_argument("--model", default=None,
                    help="run the entry with this model instead of its submission.yaml model_api"
                         " (e.g. gemini-3.8-flash; runs a temporary copy, the entry is unchanged)")
    ap.add_argument("--effort", default=None, choices=["low", "medium", "high", "max"],
                    help="reasoning level for the harness's model calls (default: the model's highest, set by the proxy)")
    ap.add_argument("--notes", default="")
    a = ap.parse_args(argv)
    judge = resolve_judge(a.judge, a.env_file)
    print(f"judge: {judge}" + ("" if tracker.judge_name(judge) == tracker.OFFICIAL_JUDGE
                                else " (not the leaderboard's judge: judged scores are approximate)"), flush=True)

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
    run_entry = with_model(entry, a.model, a.effort) if (a.model or a.effort) else entry
    if a.model or a.effort:
        print(f"harness model: {a.model or 'as in the entry'}, reasoning effort: {a.effort or 'default'} "
              f"(temporary copy of {entry.name} at {run_entry})", flush=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = REPO / "runs" / f"{entry.name}-{a.half}-{stamp}"
    cmd = ["uv", "run", "python", "eval/run.py", str(run_entry), "--tasks", ",".join(tasks),
           "--out", str(out), "--no-export"]
    if a.env_file:
        cmd += ["--env-file", str(a.env_file.resolve())]
    if a.trials:
        cmd += ["--trials", str(a.trials)]
    print("running:", " ".join(cmd), flush=True)
    started = dt.datetime.now(dt.timezone.utc)
    code = subprocess.run(cmd, cwd=a.ple, check=False, env={**os.environ, "JUDGE_MODEL": judge}).returncode
    finished = dt.datetime.now(dt.timezone.utc)
    if run_entry != entry:
        shutil.rmtree(run_entry.parent, ignore_errors=True)
    if not (out / "results.json").is_file():
        sys.exit(f"eval/run.py exited {code} and wrote no results.json in {out}")
    partial = len(tasks) < len(half_tasks)
    notes = a.notes + (f" (subset: {len(tasks)} of {len(half_tasks)} tasks)" if partial else "")
    rec = tracker.import_results(out, a.label, a.half, notes.strip(), git_commit(entry), a.holdout,
                                 env=run_environment(started, finished, a.trials, judge, a.model, a.effort))
    print()
    print(tracker.report(rec))
    if partial:
        print("\nnote: tasks of the half that were not run count as 0 in the score above;"
              " merge batches with `tracker.py combine`")


if __name__ == "__main__":
    main()
