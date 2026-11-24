"""Run tracker: one record per scored run, kept in research/runs.jsonl.

A run is scored the way the competition scores a submission: every task in the set counts,
each task scores 0-1 from its own grader (rubric tasks judged by an LLM judge), a task with
no result counts as 0, and the run's score is the mean over the set.

Development uses half A of the dev split only (research/dev_split.json). Recording a result
for a half-B task needs an explicit --holdout reason, which is stored with the record.

Commands:
  import-results  RUN_DIR      record a run folder written by ple's eval/run.py (results.json)
  import-manifest ARTIFACTS    record the scores in an artifacts/manifest.json (e.g. the
                               official template's committed run)
  combine RUN_ID RUN_ID ...     merge batch runs of the same harness into one record (later runs win)
  list                         one line per recorded run
  report RUN_ID                full scoring of one run, like a live submission
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUNS = pathlib.Path(os.environ.get("PLE_TRACKER_RUNS", HERE / "runs.jsonl"))
SPLIT = HERE / "dev_split.json"
DETAIL_FILES = ("grade.json", "metrics.json", "reward.json")
MAX_DETAIL_CHARS = 20000


def load_split() -> dict:
    return json.loads(SPLIT.read_text(encoding="utf-8"))


def tasks_of(half: str, split: dict | None = None) -> list[str]:
    split = split or load_split()
    if half == "A":
        return list(split["A"])
    if half == "B":
        return list(split["B"])
    if half == "all":
        return list(split["A"]) + list(split["B"])
    raise ValueError(f"unknown half {half!r}; use A, B or all")


def load_runs() -> list[dict]:
    if not RUNS.exists():
        return []
    return [json.loads(line) for line in RUNS.read_text(encoding="utf-8").splitlines() if line.strip()]


def next_run_id(runs: list[dict]) -> str:
    return f"run-{len(runs):03d}"


def append_run(record: dict) -> dict:
    runs = load_runs()
    record = {"run_id": next_run_id(runs), **record}
    with RUNS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=False) + "\n")
    return record


def keep_tasks(tasks: dict, half: str, holdout_reason: str | None) -> tuple[dict, list[str]]:
    """Keeps the tasks of `half`; refuses half-B tasks unless a hold-out reason is given."""
    split = load_split()
    allowed = set(tasks_of(half, split))
    if half in ("B", "all") and not holdout_reason:
        sys.exit("recording half-B results needs --holdout 'why this hold-out use is justified'")
    dropped = sorted(t for t in tasks if t not in allowed)
    return {t: v for t, v in tasks.items() if t in allowed}, dropped


def grader_detail(trial_dir: pathlib.Path) -> dict | None:
    """The grader's own breakdown, where the trial folder holds one."""
    verifier = trial_dir / "verifier"
    if not verifier.is_dir():
        return None
    for name in DETAIL_FILES:
        path = verifier / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            try:
                return {"file": name, "data": json.loads(text)}
            except ValueError:
                return {"file": name, "text": text[:MAX_DETAIL_CHARS]}
    stdout = verifier / "test-stdout.txt"
    if stdout.is_file():
        return {"file": stdout.name, "text": stdout.read_text(encoding="utf-8", errors="replace")[-MAX_DETAIL_CHARS:]}
    failed = verifier / "GRADER_FAILED.txt"
    if failed.is_file():
        return {"file": failed.name, "text": failed.read_text(encoding="utf-8", errors="replace")[:MAX_DETAIL_CHARS]}
    return None


def import_results(run_dir: pathlib.Path, label: str, half: str, notes: str,
                   harness_commit: str | None, holdout: str | None) -> dict:
    saved = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    tasks = {}
    for row in saved.get("tasks", []):
        trial = run_dir / row["trial"] if row.get("trial") else None
        tasks[row["id"]] = {
            "score": row.get("score", 0.0),
            "measured": bool(row.get("measured")),
            "status": row.get("status"),
            "kind": row.get("kind"),
            "seconds": row.get("seconds"),
            "tokens": row.get("tokens"),
            "grader": grader_detail(trial) if trial else None,
        }
    tasks, dropped = keep_tasks(tasks, half, holdout)
    return append_run({
        "label": label,
        "recorded": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"kind": "eval/run.py", "run_dir": str(run_dir), "run_date": saved.get("date")},
        "harness": {"name": saved.get("submission"), "model": saved.get("model"), "commit": harness_commit},
        "judge_model": saved.get("judge_model"),
        "half": half,
        "holdout_reason": holdout,
        "tasks": tasks,
        "dropped_outside_half": dropped,
        "notes": notes,
    })


def import_manifest(artifacts: pathlib.Path, label: str, half: str, notes: str,
                    source: str, model: str | None, holdout: str | None) -> dict:
    manifest = json.loads((artifacts / "manifest.json").read_text(encoding="utf-8"))
    tasks = {
        task: {
            "score": entry.get("reward") if entry.get("reward") is not None else 0.0,
            "measured": entry.get("reward") is not None,
            "status": "recorded in manifest",
            "kind": None, "seconds": None, "tokens": None, "grader": None,
        }
        for task, entry in manifest.get("tasks", {}).items()
    }
    tasks, dropped = keep_tasks(tasks, half, holdout)
    harness = manifest.get("harness", {})
    return append_run({
        "label": label,
        "recorded": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"kind": "artifacts manifest", "where": source, "run_date": manifest.get("created")},
        "harness": {"name": harness.get("name"), "model": model or harness.get("model_api"),
                    "commit": harness.get("commit")},
        "judge_model": None,
        "half": half,
        "holdout_reason": holdout,
        "tasks": tasks,
        "dropped_outside_half": dropped,
        "notes": notes,
    })


def commits(run: dict) -> list[str]:
    c = run["harness"].get("commit")
    return [x or "?" for x in c] if isinstance(c, list) else [c or "?"]


def combine(run_ids: list[str], label: str, notes: str) -> dict:
    """Merges batch runs of one harness and model into one record; later runs win per task."""
    by_id = {r["run_id"]: r for r in load_runs()}
    missing = [i for i in run_ids if i not in by_id]
    if missing:
        sys.exit(f"no such run: {', '.join(missing)}")
    parts = [by_id[i] for i in run_ids]
    kinds = {(p["harness"].get("name"), p["harness"].get("model"), p["half"]) for p in parts}
    if len(kinds) > 1:
        sys.exit(f"these runs differ in harness, model or half, so they cannot be combined: {sorted(kinds, key=str)}")
    tasks = {}
    for p in parts:
        tasks.update(p["tasks"])
    first = parts[0]
    return append_run({
        "label": label,
        "recorded": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"kind": "combined", "runs": run_ids,
                   "run_date": max((p["source"].get("run_date") or "") for p in parts) or None},
        "harness": {**first["harness"], "commit": sorted({c for p in parts for c in commits(p)})},
        "judge_model": first.get("judge_model"),
        "half": first["half"],
        "holdout_reason": first.get("holdout_reason"),
        "tasks": tasks,
        "dropped_outside_half": [],
        "notes": notes,
    })


def score(run: dict) -> dict:
    """Scores a run the way a submission is scored: the mean over every task of its half."""
    expected = tasks_of(run["half"])
    rows = []
    for task in expected:
        t = run["tasks"].get(task)
        s = float(t["score"]) if t and t.get("measured") else 0.0
        rows.append((task, s, t))
    missing = [task for task, _, t in rows if not t or not t.get("measured")]
    return {
        "score": sum(s for _, s, _ in rows) / len(rows) if rows else 0.0,
        "n_tasks": len(rows),
        "n_measured": len(rows) - len(missing),
        "unmeasured_scored_zero": missing,
        "rows": rows,
    }


def summarise_grader(detail: dict | None) -> str:
    if not detail:
        return ""
    data = detail.get("data")
    if isinstance(data, dict):
        keys = [k for k in ("combined_score", "score", "exec_status", "reason", "passed", "failed") if k in data]
        return ", ".join(f"{k}={data[k]}" for k in keys)[:160] or detail["file"]
    return (detail.get("text") or "").strip().splitlines()[-1][:160] if detail.get("text") else detail["file"]


def report(run: dict) -> str:
    split = load_split()
    s = score(run)
    h = run["harness"]
    lines = [
        f"{run['run_id']}  {run['label']}",
        f"harness {h.get('name')} · model {h.get('model')} · commit {h.get('commit')}",
        f"source {run['source'].get('kind')} · run date {run['source'].get('run_date')} · judge {run.get('judge_model')}",
        f"half {run['half']} ({s['n_tasks']} tasks)" + (f" · hold-out use: {run['holdout_reason']}" if run.get("holdout_reason") else ""),
        "",
        f"SCORE {s['score']:.3f}   measured {s['n_measured']}/{s['n_tasks']}"
        + (f"   scored 0 for no result: {', '.join(s['unmeasured_scored_zero'])}" if s["unmeasured_scored_zero"] else ""),
        "",
        f"{'task':38s} {'grading':13s} {'score':>6s}  {'minutes':>7s}  status / grader",
    ]
    for task, sc, t in sorted(s["rows"], key=lambda r: -r[1]):
        grading = split["tasks"][task]["grading"]
        minutes = f"{t['seconds'] / 60:7.1f}" if t and t.get("seconds") else "      -"
        status = (t.get("status") or "") if t else "no result"
        extra = summarise_grader(t.get("grader")) if t else ""
        lines.append(f"{task:38s} {grading:13s} {sc:6.3f}  {minutes}  {status}{' · ' + extra if extra else ''}")
    by_grading = {}
    for task, sc, _ in s["rows"]:
        by_grading.setdefault(split["tasks"][task]["grading"], []).append(sc)
    lines += ["", "by grading type: " + " · ".join(
        f"{g} {sum(v) / len(v):.3f} (n={len(v)})" for g, v in sorted(by_grading.items()))]
    if run.get("notes"):
        lines += ["", f"notes: {run['notes']}"]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("import-results")
    r.add_argument("run_dir", type=pathlib.Path)
    m = sub.add_parser("import-manifest")
    m.add_argument("artifacts", type=pathlib.Path)
    m.add_argument("--source", required=True, help="where these artifacts came from")
    m.add_argument("--model", default=None)
    for p in (r, m):
        p.add_argument("--label", required=True)
        p.add_argument("--half", default="A", choices=["A", "B", "all"])
        p.add_argument("--holdout", default=None, help="reason, required for half B or all")
        p.add_argument("--notes", default="")
    r.add_argument("--commit", default=None, help="harness git commit that produced the run")
    c = sub.add_parser("combine")
    c.add_argument("run_ids", nargs="+")
    c.add_argument("--label", required=True)
    c.add_argument("--notes", default="")
    sub.add_parser("list")
    rep = sub.add_parser("report")
    rep.add_argument("run_id")
    a = ap.parse_args(argv)

    if a.cmd == "import-results":
        rec = import_results(a.run_dir, a.label, a.half, a.notes, a.commit, a.holdout)
        print(report(rec))
    elif a.cmd == "import-manifest":
        rec = import_manifest(a.artifacts, a.label, a.half, a.notes, a.source, a.model, a.holdout)
        print(report(rec))
    elif a.cmd == "combine":
        print(report(combine(a.run_ids, a.label, a.notes)))
    elif a.cmd == "list":
        for run in load_runs():
            s = score(run)
            print(f"{run['run_id']}  {s['score']:.3f}  half {run['half']}  {run['harness'].get('model')}  {run['label']}")
    elif a.cmd == "report":
        runs = {r["run_id"]: r for r in load_runs()}
        if a.run_id not in runs:
            sys.exit(f"no run {a.run_id}; see `tracker.py list`")
        print(report(runs[a.run_id]))


if __name__ == "__main__":
    main()
