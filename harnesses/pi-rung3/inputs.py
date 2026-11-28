"""Rung 2: tell the agent where the task's input files are; do not feed their contents.

The first message is the task instruction plus a plain listing (paths, sizes) of the files under the task's input
roots. The agent reads what it needs with its `read` tool.
"""
from __future__ import annotations

import taskbridge

MAX_LISTED = 200


def input_roots(workdir: str) -> list[str]:
  """Where a task keeps its files: the working directory, plus the world folders."""
  roots = [] if workdir in ("", "/") else [workdir]
  return roots + [r for r in ("/filesystem", "/app/files") if r not in roots]


async def listing(session: taskbridge.Session) -> str:
  """The text appended to the instruction: where the files are, as a path and size list (no contents)."""
  roots = " ".join(f"'{r}'" for r in input_roots(session.workdir))
  try:
    res = await session.exec(
        f"for r in {roots}; do [ -d \"$r\" ] && find \"$r\" -type f -printf '%p  %s bytes\\n' 2>/dev/null; done"
        f" | sort -u | head -n {MAX_LISTED}", timeout_sec=120)
    files = (res.get("output") or "").strip()
  except taskbridge.TaskError as exc:
    await session.log(f"pi: listing the input files failed: {type(exc).__name__}: {exc}")
    files = ""
  await session.log(f"pi: LISTING {len(files.splitlines())} paths")
  return (f"## Where the input files are\n\nWorking directory: {session.workdir}\n"
          "The files below are in the task container. Their contents are not in this message: read what you need.\n\n"
          + (files or "(the listing came back empty: look around with bash)"))
