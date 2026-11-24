"""Rung 0: a single model call.

No tools and no agent loop. The model receives the task text and answers once. Files it
writes as marked blocks in its answer are saved in the task container; the rest of the
answer is the final message. The model cannot read the task's input files or run anything.

This is the floor every later rung is measured against.
"""
import asyncio
import os
import re

import openai
import taskbridge

MODEL = os.environ["MODEL_NAME"]
MAX_EFFORT_MODELS = ("claude", "glm")
EFFORT = os.environ.get("REASONING_EFFORT") or (
    "max" if any(m in MODEL.lower() for m in MAX_EFFORT_MODELS) else "high"
)
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "32000"))
RETRY_WAITS = (5, 15, 30, 60, 120)
FILE_BLOCK = re.compile(r"^<<<FILE (?P<path>[^\n>]+)>>>\n(?P<body>.*?)\n<<<END>>>$", re.S | re.M)

SYSTEM = """You are an experienced engineer completing a task for a client.

You get one reply and nothing else: you cannot open the task's files, run code, or ask
questions. Work from the task text alone.

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
      text, usage, finished = [], None, False
      async for chunk in stream:
        if chunk.usage:
          usage = chunk.usage
        for choice in chunk.choices:
          if choice.delta and choice.delta.content:
            text.append(choice.delta.content)
          if choice.finish_reason:
            finished = True
      if not finished:
        raise RuntimeError("the stream ended without a finish reason")
      return "".join(text), usage
    except openai.BadRequestError:
      raise  # a 400 will fail again unchanged
    except Exception as exc:  # pylint: disable=broad-exception-caught
      await session.log(f"naive: model call failed ({type(exc).__name__}: {exc})")
      if attempt == len(RETRY_WAITS):
        raise
  raise RuntimeError("unreachable")


async def solve(session):
  messages = [
      {"role": "system", "content": SYSTEM.format(workdir=session.workdir)},
      {"role": "user", "content": session.instruction},
  ]
  answer, usage = await ask(session, messages)
  if usage:
    cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    await session.usage(MODEL, input_tokens=usage.prompt_tokens or 0,
                        output_tokens=usage.completion_tokens or 0, cache_read_tokens=cached)

  written = []
  for block in FILE_BLOCK.finditer(answer):
    path = block["path"].strip()
    try:
      await session.write_file(path, block["body"] + "\n")
      written.append(path)
    except taskbridge.TaskError as exc:
      await session.log(f"naive: could not write {path}: {exc}")
  await session.log(f"naive: wrote {len(written)} file(s): {', '.join(written) or 'none'}")

  summary = re.sub(r"\n{3,}", "\n\n", FILE_BLOCK.sub("", answer)).strip()
  return summary or "(no summary in the model's reply)"


if __name__ == "__main__":
  taskbridge.run(solve)
