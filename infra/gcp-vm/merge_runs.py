"""Appends to NEW the records of OLD whose run_id NEW does not have. Usage: merge_runs.py OLD NEW

Used when the VM's checkout is replaced: runs recorded on the VM but not yet committed must survive.
Never changes or removes a record already in NEW."""
import json
import pathlib
import sys


def merge(old_path, new_path):
    new = pathlib.Path(new_path)
    have = set()
    lines = new.read_text(encoding="utf-8").splitlines() if new.is_file() else []
    for line in lines:
        if line.strip():
            have.add(json.loads(line)["run_id"])
    added = []
    old = pathlib.Path(old_path)
    for line in (old.read_text(encoding="utf-8").splitlines() if old.is_file() else []):
        if not line.strip():
            continue
        try:
            rid = json.loads(line)["run_id"]
        except (ValueError, KeyError):
            continue
        if rid not in have:
            added.append(line)
            have.add(rid)
    if added:
        new.write_text("".join(l + "\n" for l in lines + added), encoding="utf-8")
    return [json.loads(l)["run_id"] for l in added]


if __name__ == "__main__":
    print("merge_runs: added", merge(sys.argv[1], sys.argv[2]) or "nothing")
