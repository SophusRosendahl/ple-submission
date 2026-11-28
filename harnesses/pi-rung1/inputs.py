"""Stages the task's input files as context for Pi (rung 1: files are fed, not read by a tool).

Text files are converted to plain text in the task container (extract_inputs.py) and become part of the
prompt; image files are fetched with read_file and written next to Pi, which attaches them to the first
message through its `@file` arguments (unresized: Pi's main.js passes autoResizeImages=false for those).
Limits are logged, never silent.
"""
from __future__ import annotations

import json
import os
import pathlib

import taskbridge

HERE = pathlib.Path(__file__).resolve().parent
EXTRACTOR = (HERE / "extract_inputs.py").read_text(encoding="utf-8")
REMOTE_DIR = "/tmp/pi-inputs"  # in the task container, outside every graded path
PER_FILE_CHARS = int(os.environ.get("PI_PER_FILE_CHARS", "60000"))
TOTAL_CHARS = int(os.environ.get("PI_TOTAL_CHARS", "500000"))
MAX_IMAGES = int(os.environ.get("PI_MAX_IMAGES", "40"))
MAX_IMAGE_BYTES = int(os.environ.get("PI_MAX_IMAGE_BYTES", "8000000"))
TOTAL_IMAGE_BYTES = int(os.environ.get("PI_TOTAL_IMAGE_BYTES", "18000000"))
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def input_roots(workdir: str) -> list[str]:
  """Where a task keeps its files: the working directory, plus the world folders."""
  roots = [] if workdir in ("", "/") else [workdir]
  return roots + [r for r in ("/filesystem", "/app/files") if r not in roots]


DELIVERABLE_DIRS = {"output", "outputs"}  # the agent must be able to open its own deliverables


def guard_list(files: list[dict], workdir: str) -> list[str]:
  """Substrings that identify the task's input files: names, folders, and the folder relative to workdir.

  Files inside an output folder are not inputs (the agent edits its own deliverable stub there).
  """
  names, dirs = set(), set()
  for f in files:
    parts = pathlib.PurePosixPath(f["path"])
    if DELIVERABLE_DIRS & set(parts.parent.parts):
      continue
    if len(parts.name) >= 4:
      names.add(parts.name)
    dirs.add(str(parts.parent))
    if workdir not in ("", "/") and str(parts.parent).startswith(workdir.rstrip("/") + "/"):
      dirs.add(str(parts.parent)[len(workdir.rstrip("/")) + 1:] + "/")
  return sorted(names) + sorted(d for d in dirs if len(d) > 4)


async def stage(session: taskbridge.Session, folder: pathlib.Path) -> tuple[str, list[str], list[str]]:
  """Returns (the text block for the prompt, the image paths to pass to Pi as @files, the input guard list)."""
  folder.mkdir(parents=True, exist_ok=True)
  script, out = f"{REMOTE_DIR}/extract_inputs.py", f"{REMOTE_DIR}/inputs.json"
  try:
    await session.write_file(script, EXTRACTOR)
    roots = " ".join(f"'{r}'" for r in input_roots(session.workdir))
    res = await session.exec(
        f"python3 {script} --out {out} --per-file {PER_FILE_CHARS} --total {TOTAL_CHARS} {roots}",
        timeout_sec=600)
    await session.log(f"pi: extractor exit {res.get('exit_code')}: {(res.get('output') or '')[-300:]}")
    if res.get("exit_code") != 0:
      return "(The harness could not convert the project files to text.)", [], []
    data = json.loads(await session.read_file(out))
  except (taskbridge.TaskError, ValueError) as exc:
    await session.log(f"pi: input extraction failed: {type(exc).__name__}: {exc}")
    return "(The harness could not convert the project files to text.)", [], []
  seen, files = set(), []
  for f in data["files"]:  # the roots overlap (workdir sits inside /app/files): each file was listed twice
    if f["path"] not in seen:
      seen.add(f["path"])
      files.append(f)
  attached, skipped, total, args = {}, [], 0, []
  images = [f for f in files if f["kind"] == "image"]
  for i, f in enumerate(images[:MAX_IMAGES]):
    ext = pathlib.PurePosixPath(f["path"]).suffix.lower()
    if f["bytes"] > MAX_IMAGE_BYTES or total + f["bytes"] > TOTAL_IMAGE_BYTES or ext not in IMAGE_EXT:
      skipped.append({"path": f["path"], "bytes": f["bytes"], "why": "size limit or type"})
      continue
    try:
      raw = await session.read_file(f["path"])
    except taskbridge.TaskError as exc:
      skipped.append({"path": f["path"], "bytes": f["bytes"], "why": f"read failed: {exc}"})
      continue
    name = f"{i:02d}_{pathlib.PurePosixPath(f['path']).name}"
    (folder / name).write_bytes(raw)
    total += len(raw)
    attached[f["path"]] = name
    args.append("@" + str(folder / name))
  skipped += [{"path": f["path"], "bytes": f["bytes"], "why": "over the image count limit"} for f in images[MAX_IMAGES:]]
  await session.log("pi: IMAGES " + json.dumps({"attached": attached, "bytes": total, "skipped": skipped}))
  parts = [f"=== PROJECT FILES ({len(files)} files; text converted, images attached in this message) ==="]
  for f in files:
    flags = [f["kind"], f"{f['bytes']} bytes"] + (["cut short"] if f["truncated"] else [])
    parts.append(f"\n--- {f['path']} [{', '.join(flags)}] ---")
    if f["text"]:
      parts.append(f["text"])
    if f["path"] in attached:
      parts.append(f"(image: attached as {attached[f['path']]})")
    elif f["note"]:
      parts.append(f"({f['note']})")
  for s in data.get("skipped", []):
    parts.append(f"\n--- {s['path']} --- ({s['note']})")
  guard = guard_list(files, session.workdir)
  await session.log("pi: GUARD " + json.dumps(guard))
  return "\n".join(parts), args, guard
