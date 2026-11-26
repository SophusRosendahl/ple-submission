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
import re
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RUNS = pathlib.Path(os.environ.get("PLE_TRACKER_RUNS", HERE / "runs.jsonl"))
SPLIT = HERE / "dev_split.json"
DETAIL_FILES = ("grade.json", "metrics.json", "reward.json")
MAX_DETAIL_CHARS = 20000
MAX_FILE_CHARS = 60000     # per grader file kept in the record; the whole folder is also saved to the bucket


OFFICIAL_JUDGE = "claude-opus-5-5"   # the leaderboard's judge


def judge_name(model: str | None) -> str:
    """The judge model without the proxy's `-judge` suffix; '?' when unknown."""
    if not model:
        return "?"
    return model[: -len("-judge")] if model.endswith("-judge") else model


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


def grader_files(trial_dir: pathlib.Path) -> dict | None:
    """Every file the grader left in the trial's verifier folder (all check reports), not just the first.

    JSON files are kept parsed, anything else as text; a file over MAX_FILE_CHARS keeps its head
    and tail. The complete folder is in the run outputs bucket.
    """
    verifier = trial_dir / "verifier"
    if not verifier.is_dir():
        return None
    out = {}
    for path in sorted(p for p in verifier.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_FILE_CHARS:
            text = text[: MAX_FILE_CHARS // 2] + f"\n[... {len(text) - MAX_FILE_CHARS} characters cut ...]\n" + text[-MAX_FILE_CHARS // 2:]
        try:
            out[str(path.relative_to(verifier))] = {"data": json.loads(text)}
        except ValueError:
            out[str(path.relative_to(verifier))] = {"text": text}
    return out


def trial_listing(trial_dir: pathlib.Path) -> list | None:
    """Every file in the trial folder with its size: shows what a run left behind, whatever the layout."""
    if not trial_dir.is_dir():
        return None
    return [[str(p.relative_to(trial_dir)), p.stat().st_size] for p in sorted(trial_dir.rglob("*")) if p.is_file()]


HARNESS_TAGS = ("CALL", "CALLS", "CHECK")


def harness_records(trial_dir: pathlib.Path) -> dict | None:
    """Parses the tagged JSON lines a harness logged (`<name>: CALL {...}`, `CALLS`, `CHECK`) from a trial.

    Looks in the trial's agent logs (the harness's log lines are in agent/*.txt, prefixed `harness:`).
    Returns {"calls": the CALLS summary or None, "call_records": [...], "checks": [...]}, or None
    when the folder holds none of these (an older harness, or a different one).
    """
    out = {"calls": None, "call_records": [], "checks": []}
    found = False
    files = sorted((trial_dir / "agent").glob("*.txt")) + [trial_dir / "trial.log"]
    for path in files:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r": (CALLS|CALL|CHECK) (\{.*\})\s*$", line)
            if not m:
                continue
            try:
                data = json.loads(m.group(2))
            except ValueError:
                continue
            found = True
            if m.group(1) == "CALLS":
                out["calls"] = data
            elif m.group(1) == "CALL":
                out["call_records"].append(data)
            else:
                out["checks"].append(data)
    return out if found else None


def import_results(run_dir: pathlib.Path, label: str, half: str, notes: str,
                   harness_commit: str | None, holdout: str | None, env: dict | None = None) -> dict:
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
            "grader_files": grader_files(trial) if trial else None,
            "trial_files": trial_listing(trial) if trial else None,
            "harness": harness_records(trial) if trial else None,
        }
    tasks, dropped = keep_tasks(tasks, half, holdout)
    return append_run({
        "label": label,
        "recorded": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"kind": "eval/run.py", "run_dir": str(run_dir), "run_date": saved.get("date")},
        "harness": {"name": saved.get("submission"), "model": saved.get("model"), "commit": harness_commit},
        "judge_model": saved.get("judge_model"),
        "env": env,
        "half": half,
        "holdout_reason": holdout,
        "tasks": tasks,
        "dropped_outside_half": dropped,
        "notes": notes,
    })


def invalid_reason(run: dict) -> str | None:
    """Why a run is marked invalid, or None if it is not."""
    v = run.get("validity") or {}
    return v.get("reason") if v.get("valid") is False else None


def mark_invalid(run_ids: list[str], reason: str) -> list[str]:
    """Marks runs invalid (kept, never deleted): the record stays, with the reason and the date."""
    runs = load_runs()
    known = {r["run_id"] for r in runs}
    missing = [r for r in run_ids if r not in known]
    if missing:
        sys.exit(f"no such run: {', '.join(missing)}")
    for r in runs:
        if r["run_id"] in run_ids:
            r["validity"] = {"valid": False, "reason": reason, "marked": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")}
    RUNS.write_text("".join(json.dumps(r, sort_keys=False) + "\n" for r in runs), encoding="utf-8")
    return run_ids


def enrich(run_id: str, run_dir: pathlib.Path) -> dict:
    """Adds the detail fields (grader files, trial listing, harness records) to an existing record from its
    run folder. Only adds or refreshes those fields; scores and everything else stay as recorded."""
    runs = load_runs()
    hit = [r for r in runs if r["run_id"] == run_id]
    if not hit:
        sys.exit(f"no run {run_id}")
    saved = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    trials = {row["id"]: run_dir / row["trial"] for row in saved.get("tasks", []) if row.get("trial")}
    for task, rec in hit[0]["tasks"].items():
        trial = trials.get(task)
        if trial and trial.is_dir():
            rec["grader_files"], rec["trial_files"], rec["harness"] = grader_files(trial), trial_listing(trial), harness_records(trial)
    RUNS.write_text("".join(json.dumps(r, sort_keys=False) + "\n" for r in runs), encoding="utf-8")
    return hit[0]


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
    kinds = {(p["harness"].get("name"), p["harness"].get("model"), p["half"], judge_name(p.get("judge_model"))) for p in parts}
    if len(kinds) > 1:
        sys.exit("these runs differ in harness, model, half or judge, so they cannot be combined:"
                 f" {sorted(kinds, key=str)}")
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
        *([f"*** INVALID: {invalid_reason(run)}"] if invalid_reason(run) else []),
        f"harness {h.get('name')} · model {h.get('model')} · commit {h.get('commit')}",
        f"source {run['source'].get('kind')} · run date {run['source'].get('run_date')} · judge {judge_name(run.get('judge_model'))}"
        + ("" if judge_name(run.get("judge_model")) in (OFFICIAL_JUDGE, "?") else " (not the leaderboard's judge: judged scores approximate)"),
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
    e = sub.add_parser("enrich", help="add detail fields to an existing record from its run folder")
    e.add_argument("run_id")
    e.add_argument("run_dir", type=pathlib.Path)
    iv = sub.add_parser("invalidate", help="mark runs invalid (kept in the tracker, flagged everywhere)")
    iv.add_argument("run_ids", nargs="+")
    iv.add_argument("--reason", required=True)
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
    elif a.cmd == "invalidate":
        print("marked invalid:", ", ".join(mark_invalid(a.run_ids, a.reason)))
    elif a.cmd == "enrich":
        rec = enrich(a.run_id, a.run_dir)
        print(f"{rec['run_id']}: {sum(1 for t in rec['tasks'].values() if t.get('harness'))} of {len(rec['tasks'])} task(s) have harness records")
    elif a.cmd == "combine":
        print(report(combine(a.run_ids, a.label, a.notes)))
    elif a.cmd == "list":
        for run in load_runs():
            s = score(run)
            print(f"{run['run_id']}  {s['score']:.3f}  half {run['half']}  {run['harness'].get('model')}"
                  f"  judge {judge_name(run.get('judge_model'))}  {run['label']}"
                  + (f"  [INVALID: {invalid_reason(run)[:70]}...]" if invalid_reason(run) else ""))
    elif a.cmd == "report":
        runs = {r["run_id"]: r for r in load_runs()}
        if a.run_id not in runs:
            sys.exit(f"no run {a.run_id}; see `tracker.py list`")
        print(report(runs[a.run_id]))


if __name__ == "__main__":
    main()
