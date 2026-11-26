"""Copies what a recorded run left behind (agent logs, deliverables, grader files) into
research/run-details/<run_id>/<task>/ so it can be read in git. Small files only: no config or lock files
(they can hold keys), no egress logs, and never the grader's own code.

  python3 research/collect_details.py run-005 [run-006 ...]
"""
import json
import pathlib
import shutil
import sys

import tracker

HERE = pathlib.Path(__file__).resolve().parent
KEEP = ("agent", "deliverables", "verifier")
SKIP_NAMES = {"egress.log"}


def collect(run_id):
    run = next((r for r in tracker.load_runs() if r["run_id"] == run_id), None)
    if run is None:
        sys.exit(f"no run {run_id}")
    run_dir = pathlib.Path(run["source"]["run_dir"])
    saved = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    n = 0
    for row in saved.get("tasks", []):
        trial = run_dir / row["trial"] if row.get("trial") else None
        if not trial or not trial.is_dir():
            continue
        dest = HERE / "run-details" / run_id / row["id"]
        for sub in KEEP:
            if (trial / sub).is_dir():
                shutil.copytree(trial / sub, dest / sub, dirs_exist_ok=True,
                                ignore=lambda d, names: [x for x in names if x in SKIP_NAMES])
        n += 1
    return n


if __name__ == "__main__":
    for rid in sys.argv[1:]:
        print(rid, "->", collect(rid), "task folder(s)")
