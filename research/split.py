"""Split the 29 public dev tasks into a working half (A) and a held-out half (B).

Only half A is used while developing the harness. Half B is run rarely, to check that
improvements on A carry over to tasks we never looked at.

Tasks we had already studied in detail before the split (prompts, inputs, and for one
task its grader) cannot serve as held-out tasks, so they go into A by construction.
The remaining tasks are assigned at random with a fixed seed, balanced by grading type
so both halves have a similar mix of checks, rubric and checks-judge tasks.

Usage: python research/split.py <path to ple/eval/dev_set.yaml>
Writes research/dev_split.json.
"""
import json
import pathlib
import random
import re
import sys

SEED = 20261124
ALREADY_STUDIED = [
    "data-hall-mep-routing",       # prompt, drawings and grader read in full
    "data-center-site-model",      # prompt and constraints read
    "backfeed-energization-reply", # prompt read
    "fill-compaction-acceptance",  # prompt read
    "fire-test-validation-memo",   # prompt and rubric criteria read
]


def read_dev_set(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    tasks = []
    for block in text.split("\n- id: ")[1:]:
        task_id = block.split("\n", 1)[0].strip()
        fields = dict(re.findall(r"^\s+(title|domain|grading): (.+)$", block, re.M))
        tasks.append({"id": task_id, **fields})
    return tasks


def split(tasks):
    rng = random.Random(SEED)
    half_a = set(ALREADY_STUDIED)
    by_grading = {}
    for t in tasks:
        by_grading.setdefault(t["grading"], []).append(t["id"])
    for grading, ids in sorted(by_grading.items()):
        target = round(len(ids) / 2 + 0.01)  # ties go to A, which holds 15 of 29
        fixed = [i for i in ids if i in half_a]
        pool = sorted(i for i in ids if i not in half_a)
        rng.shuffle(pool)
        half_a.update(pool[: max(0, target - len(fixed))])
    order = [t["id"] for t in tasks]
    return [i for i in order if i in half_a], [i for i in order if i not in half_a]


def main():
    tasks = read_dev_set(sys.argv[1])
    a, b = split(tasks)
    info = {t["id"]: {k: t.get(k) for k in ("title", "domain", "grading")} for t in tasks}
    out = {
        "seed": SEED,
        "method": "already-studied tasks fixed in A; the rest assigned at random per grading type",
        "already_studied": ALREADY_STUDIED,
        "A": a,
        "B": b,
        "tasks": info,
    }
    path = pathlib.Path(__file__).with_name("dev_split.json")
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    for name, ids in (("A", a), ("B", b)):
        mix = {}
        for i in ids:
            mix[info[i]["grading"]] = mix.get(info[i]["grading"], 0) + 1
        print(f"{name}: {len(ids)} tasks {mix}")
        for i in ids:
            print(f"   {i:38s} {info[i]['grading']:13s} {info[i]['domain']}")


if __name__ == "__main__":
    main()
