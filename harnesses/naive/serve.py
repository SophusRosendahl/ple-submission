"""Rung 0: a single model call.

No tools and no agent loop. Before the call, the harness (not the model) turns the task's
files into plain text and pastes them after the task text; images are listed by name only.
The model answers once. Files it writes as marked blocks in its answer are saved in the task
container; the rest of the answer is the final message. The model cannot open files or run
anything itself.

This is the floor every later rung is measured against.
"""
import asyncio
import json
import os
import pathlib
import re

import openai
import taskbridge

HERE = pathlib.Path(__file__).resolve().parent
EXTRACTOR = (HERE / "extract_inputs.py").read_text(encoding="utf-8")
REMOTE_DIR = "/tmp/naive"  # in the task container, outside every graded path
PER_FILE_CHARS = int(os.environ.get("NAIVE_PER_FILE_CHARS", "60000"))
TOTAL_CHARS = int(os.environ.get("NAIVE_TOTAL_CHARS", "500000"))

MODEL = os.environ["MODEL_NAME"]
MAX_EFFORT_MODELS = ("claude", "glm")
EFFORT = os.environ.get("REASONING_EFFORT") or (
    "max" if any(m in MODEL.lower() for m in MAX_EFFORT_MODELS) else "high"
)
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "32000"))
RETRY_WAITS = (5, 15, 30, 60, 120)
FILE_BLOCK = re.compile(r"^<<<FILE (?P<path>[^\n>]+)>>>\n(?P<body>.*?)\n<<<END>>>$", re.S | re.M)
# A reply cut off mid-file has an opening marker and no <<<END>>>: keep what was written.
OPEN_BLOCK = re.compile(r"^<<<FILE (?P<path>[^\n>]+)>>>\n(?P<body>(?:(?!^<<<FILE ).)*)\Z", re.S | re.M)

SYSTEM = """You are an experienced engineer completing a task for a client.

You get one reply and nothing else: you cannot open files, run code, or ask questions.
The task's project files follow the task text, converted to plain text for you (spreadsheets
as comma-separated rows, PDFs page by page). Images and other non-text files are listed by
name only, and very long files are cut where marked. Work from what is given.

Write every file the task asks for in your reply, each as a block exactly like this,
with the path the task gives (absolute, or relative to {workdir}):

<<<FILE path/to/file.ext>>>
file contents
<<<END>>>

Only text files can be written this way. After the file blocks, write a short summary of
what you delivered and where; it is sent as your final message."""

client = openai.AsyncOpenAI(timeout=1800, max_retries=0)


async def ask(session, messages):
  """One streamed model call with retries for transient errors."""
  for attempt, wait in enumerate((0,) + RETRY_WAITS):
    if wait:
      left = session.time_left()
      if left is not None and left < wait + 120:
        raise RuntimeError("no time left to retry the model call")
      await session.log(f"naive: retrying the model call in {wait}s")
      await asyncio.sleep(wait)
    try:
      stream = await client.chat.completions.create(
          model=MODEL,
          messages=messages,
          max_completion_tokens=MAX_OUTPUT_TOKENS,
          reasoning_effort=EFFORT,
          stream=True,
          stream_options={"include_usage": True},
      )
      text, usage, finished, reason = [], None, False, None
      async for chunk in stream:
        if chunk.usage:
          usage = chunk.usage
        for choice in chunk.choices:
          if choice.delta and choice.delta.content:
            text.append(choice.delta.content)
          if choice.finish_reason:
            finished, reason = True, choice.finish_reason
      if not finished:
        raise RuntimeError("the stream ended without a finish reason")
      if reason == "length":
        await session.log(f"naive: reply cut off at the {MAX_OUTPUT_TOKENS}-token limit (reasoning counts towards it)")
      return "".join(text), usage
    except openai.BadRequestError:
      raise  # a 400 will fail again unchanged
    except Exception as exc:  # pylint: disable=broad-exception-caught
      await session.log(f"naive: model call failed ({type(exc).__name__}: {exc})")
      if attempt == len(RETRY_WAITS):
        raise
  raise RuntimeError("unreachable")


def input_roots(workdir):
  """Where a task keeps its files: the working directory, plus the world folders."""
  roots = [] if workdir in ("", "/") else [workdir]
  return roots + [r for r in ("/filesystem", "/app/files") if r not in roots]


def render_inputs(data):
  """The extracted files as one plain-text block for the prompt."""
  parts = [f"=== PROJECT FILES ({len(data['files'])} files, converted to plain text) ==="]
  for f in data["files"]:
    flags = [f["kind"], f"{f['bytes']} bytes"] + (["cut short"] if f["truncated"] else [])
    parts.append(f"\n--- {f['path']} [{', '.join(flags)}] ---")
    if f["text"]:
      parts.append(f["text"])
    if f["note"]:
      parts.append(f"({f['note']})")
  for s in data.get("skipped", []):
    parts.append(f"\n--- {s['path']} --- ({s['note']})")
  return "\n".join(parts)


async def gather_inputs(session):
  """Runs the extractor in the task container; returns the prompt block, or a note why not."""
  script, out = f"{REMOTE_DIR}/extract_inputs.py", f"{REMOTE_DIR}/inputs.json"
  try:
    await session.write_file(script, EXTRACTOR)
    roots = " ".join(f"'{r}'" for r in input_roots(session.workdir))
    res = await session.exec(
        f"python3 {script} --out {out} --per-file {PER_FILE_CHARS} --total {TOTAL_CHARS} {roots}",
        timeout_sec=600)
    await session.log(f"naive: extractor exit {res.get('exit_code')}: {(res.get('output') or '')[-500:]}")
    if res.get("exit_code") != 0:
      return "(The harness could not convert the project files to text.)"
    return render_inputs(json.loads(await session.read_file(out)))
  except (taskbridge.TaskError, ValueError) as exc:
    await session.log(f"naive: input extraction failed: {type(exc).__name__}: {exc}")
    return "(The harness could not convert the project files to text.)"


async def solve(session):
  inputs = await gather_inputs(session)
  messages = [
      {"role": "system", "content": SYSTEM.format(workdir=session.workdir)},
      {"role": "user", "content": f"{session.instruction}\n\n{inputs}"},
  ]
  answer, usage = await ask(session, messages)
  if usage:
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    await session.usage(MODEL, input_tokens=usage.prompt_tokens or 0,
                        output_tokens=usage.completion_tokens or 0, cache_read_tokens=cached)

  written = []
  blocks = list(FILE_BLOCK.finditer(answer))
  tail = OPEN_BLOCK.search(answer[blocks[-1].end():] if blocks else answer)
  if tail and tail["body"].strip():
    await session.log(f"naive: {tail['path'].strip()} has no <<<END>>>: the reply was cut off; writing the partial file")
    blocks.append(tail)
  for block in blocks:
    path = block["path"].strip()
    try:
      await session.write_file(path, block["body"] + "\n")
      written.append(path)
    except taskbridge.TaskError as exc:
      await session.log(f"naive: could not write {path}: {exc}")
  await session.log(f"naive: wrote {len(written)} file(s): {', '.join(written) or 'none'}")

  summary = re.sub(r"\n{3,}", "\n\n", OPEN_BLOCK.sub("", FILE_BLOCK.sub("", answer))).strip()
  return summary or "(no summary in the model's reply)"


if __name__ == "__main__":
  taskbridge.run(solve)
