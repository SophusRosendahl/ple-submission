"""Rung 0: a single model call.

No tools and no agent loop. Before the call, the harness (not the model) turns the task's
files into plain text and pastes them after the task text, and attaches the images to the same
request so the model can look at them (NAIVE_IMAGES=0 turns that off). The model answers once. Files it writes as marked blocks in its answer are saved in the task
container; the rest of the answer is the final message. The model cannot open files or run
anything itself.

This is the floor every later rung is measured against.
"""
import asyncio
import base64
import hashlib
import json
import os
import pathlib
import re
import time

import openai
import prompt_fingerprint
import taskbridge

HERE = pathlib.Path(__file__).resolve().parent
EXTRACTOR = (HERE / "extract_inputs.py").read_text(encoding="utf-8")
REMOTE_DIR = "/tmp/naive"  # in the task container, outside every graded path
PER_FILE_CHARS = int(os.environ.get("NAIVE_PER_FILE_CHARS", "60000"))
TOTAL_CHARS = int(os.environ.get("NAIVE_TOTAL_CHARS", "500000"))
# Images are attached to the request itself so the model can look at them. NAIVE_IMAGES=0 turns that off
# (for comparison runs). The task container's read limit is 10 MB per file.
ATTACH_IMAGES = os.environ.get("NAIVE_IMAGES", "1") != "0"
MAX_IMAGES = int(os.environ.get("NAIVE_MAX_IMAGES", "40"))
MAX_IMAGE_BYTES = int(os.environ.get("NAIVE_MAX_IMAGE_BYTES", "8000000"))
TOTAL_IMAGE_BYTES = int(os.environ.get("NAIVE_TOTAL_IMAGE_BYTES", "18000000"))
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff"}

MODEL = os.environ["MODEL_NAME"]
MAX_EFFORT_MODELS = ("claude", "glm")
EFFORT = os.environ.get("REASONING_EFFORT") or (
    "max" if any(m in MODEL.lower() for m in MAX_EFFORT_MODELS) else "high"
)
# Reasoning tokens count against this cap. Measured 2026-11-26: Gemini 3.8 Flash rejects anything above 65,536
# (HTTP 400), and Gemini 4 Neon accepts larger values but stops at exactly 65,536 (all of it thinking), so the
# effective ceiling is 65,536 for both. A reply that reaches it is treated as cut off and restarted (below).
MODEL_CAPS = (("gemini", 65536),)
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS") or next(
    (cap for key, cap in MODEL_CAPS if key in MODEL.lower()), 32000))
# Restart on interruption: when a reply is cut off, call again with the input AND the output so far.
MAX_RESTARTS = int(os.environ.get("NAIVE_MAX_RESTARTS", "5"))
RESTART_EFFORT_STEP = os.environ.get("NAIVE_RESTART_EFFORT_STEP", "1") != "0"   # think less on each restart
EFFORT_LADDER = ("max", "high", "medium", "low")
CUT_OFF_FRACTION = 0.97   # the proxy reports `stop` for some calls that used the whole budget: count tokens too
CONTINUE_NOTE = ("Your reply was cut off at the output limit. Continue exactly where it stopped: do not repeat "
                 "anything already written, and finish every required file. If you were inside a file block, "
                 "carry on with that file's content (do not start the block again).")
EMPTY_NOTE = ("Your previous attempt used its entire output allowance on thinking and wrote nothing. Do not think "
              "at length this time: write the required files now, in the <<<FILE ...>>> format, then the summary.")
RETRY_WAITS = (5, 15, 30, 60, 120)
FILE_BLOCK = re.compile(r"^<<<FILE (?P<path>[^\n>]+)>>>\n(?P<body>.*?)\n<<<END>>>$", re.S | re.M)
# A reply cut off mid-file has an opening marker and no <<<END>>>: keep what was written.
OPEN_BLOCK = re.compile(r"^<<<FILE (?P<path>[^\n>]+)>>>\n(?P<body>(?:(?!^<<<FILE ).)*)\Z", re.S | re.M)

SYSTEM = """You are an experienced engineer completing a task for a client.

You get one reply and nothing else: you cannot open files, run code, or ask questions.
The task's project files follow the task text, converted to plain text for you (spreadsheets
as comma-separated rows, PDFs page by page). Images are attached after the text, each one
preceded by its path: look at them, they usually carry information the text does not. Other
non-text files are listed by name only, and very long files are cut where marked. Work from
what is given.

Write every file the task asks for in your reply, each as a block exactly like this,
with the path the task gives (absolute, or relative to {workdir}):

<<<FILE path/to/file.ext>>>
file contents
<<<END>>>

Only text files can be written this way. After the file blocks, write a short summary of
what you delivered and where; it is sent as your final message."""

client = openai.AsyncOpenAI(timeout=1800, max_retries=0)  # no hidden SDK retries: every request is counted below

# Efficiency accounting. A "call" is one request sent to the model endpoint by this harness.
# `ok` finished with a finish reason, `failed` raised or ended early. Retries are separate calls.
# Tokens, as the endpoint reports them: `input` is all prompt tokens, of which `cached_input` were
# served from the provider's prompt (KV) cache; `output` is all completion tokens, of which
# `reasoning` were thinking tokens. Cached and reasoning tokens are parts of the totals, not extras.
CALLS = {"ok": 0, "failed": 0, "input_tokens": 0, "cached_input_tokens": 0,
         "output_tokens": 0, "reasoning_tokens": 0}


async def ask(session, messages, effort=None):
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
          reasoning_effort=effort or EFFORT,
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
      CALLS["ok"] += 1
      if reason == "length":
        await session.log(f"naive: reply cut off at the {MAX_OUTPUT_TOKENS}-token limit (reasoning counts towards it)")
      return "".join(text), usage, reason
    except openai.BadRequestError:
      CALLS["failed"] += 1
      raise  # a 400 will fail again unchanged
    except Exception as exc:  # pylint: disable=broad-exception-caught
      CALLS["failed"] += 1
      await session.log(f"naive: model call failed ({type(exc).__name__}: {exc})")
      if attempt == len(RETRY_WAITS):
        raise
  raise RuntimeError("unreachable")


def input_roots(workdir):
  """Where a task keeps its files: the working directory, plus the world folders."""
  roots = [] if workdir in ("", "/") else [workdir]
  return roots + [r for r in ("/filesystem", "/app/files") if r not in roots]


def render_inputs(data, attached=()):
  """The extracted files as one plain-text block for the prompt. `attached` are paths sent as images."""
  parts = [f"=== PROJECT FILES ({len(data['files'])} files, converted to plain text) ==="]
  for f in data["files"]:
    flags = [f["kind"], f"{f['bytes']} bytes"] + (["cut short"] if f["truncated"] else [])
    parts.append(f"\n--- {f['path']} [{', '.join(flags)}] ---")
    if f["text"]:
      parts.append(f["text"])
    if f["path"] in attached:
      parts.append("(image: attached below)")
    elif f["note"]:
      parts.append(f"({f['note']})")
  for s in data.get("skipped", []):
    parts.append(f"\n--- {s['path']} --- ({s['note']})")
  return "\n".join(parts)


async def gather_inputs(session):
  """Runs the extractor in the task container. Returns (the text block, the image files found)."""
  script, out = f"{REMOTE_DIR}/extract_inputs.py", f"{REMOTE_DIR}/inputs.json"
  try:
    await session.write_file(script, EXTRACTOR)
    roots = " ".join(f"'{r}'" for r in input_roots(session.workdir))
    res = await session.exec(
        f"python3 {script} --out {out} --per-file {PER_FILE_CHARS} --total {TOTAL_CHARS} {roots}",
        timeout_sec=600)
    await session.log(f"naive: extractor exit {res.get('exit_code')}: {(res.get('output') or '')[-500:]}")
    if res.get("exit_code") != 0:
      return "(The harness could not convert the project files to text.)", []
    data = json.loads(await session.read_file(out))
    seen, unique = set(), []
    for f in data["files"]:  # the roots overlap (workdir sits inside /app/files): each file was listed twice
      if f["path"] not in seen:
        seen.add(f["path"])
        unique.append(f)
    data["files"] = unique
    return data, [f for f in unique if f["kind"] == "image"]
  except (taskbridge.TaskError, ValueError) as exc:
    await session.log(f"naive: input extraction failed: {type(exc).__name__}: {exc}")
    return "(The harness could not convert the project files to text.)", []


async def load_images(session, files):
  """Reads the task's image files; returns (content parts, attached paths). Limits are logged, never silent."""
  parts, attached, skipped, total = [], [], [], 0
  for f in files[:MAX_IMAGES]:
    ext = pathlib.PurePosixPath(f["path"]).suffix.lower()
    if f["bytes"] > MAX_IMAGE_BYTES or total + f["bytes"] > TOTAL_IMAGE_BYTES or ext not in MIME:
      skipped.append({"path": f["path"], "bytes": f["bytes"], "why": "size limit or type"})
      continue
    try:
      raw = await session.read_file(f["path"])
    except taskbridge.TaskError as exc:
      skipped.append({"path": f["path"], "bytes": f["bytes"], "why": f"read failed: {exc}"})
      continue
    total += len(raw)
    attached.append(f["path"])
    parts.append({"type": "text", "text": f"[image: {f['path']}]"})
    parts.append({"type": "image_url", "image_url": {"url": f"data:{MIME[ext]};base64,{base64.b64encode(raw).decode()}"}})
  skipped += [{"path": f["path"], "bytes": f["bytes"], "why": "over the image count limit"} for f in files[MAX_IMAGES:]]
  await session.log("naive: IMAGES " + json.dumps({"attached": attached, "bytes": total, "skipped": skipped}))
  return parts, attached


def loggable(messages):
  """The messages with image data replaced by a short stand-in (hash and size), for the prompt fingerprint:
  the prefix property holds and a fingerprint does not carry megabytes of base64."""
  out = []
  for m in messages:
    content = m["content"]
    if isinstance(content, list):
      content = [
          {"type": "image_url", "image_url": {"url": "<image sha1=%s bytes=%d>" % (
              hashlib.sha1(p["image_url"]["url"].encode()).hexdigest()[:12], len(p["image_url"]["url"]))}}
          if p.get("type") == "image_url" else p for p in content]
    out.append({**m, "content": content})
  return out


async def solve(session):
  try:
    return await _solve(session)
  finally:  # one machine-readable line per task; research/ reads it back
    await session.log("naive: CALLS " + json.dumps({"model": MODEL, **CALLS}))


def cut_off(usage, reason):
  """True when a reply was interrupted: the provider said `length`, or it used (nearly) the whole budget."""
  used = (usage.completion_tokens or 0) if usage else 0
  return reason == "length" or used >= CUT_OFF_FRACTION * MAX_OUTPUT_TOKENS


def assemble(pieces):
  """Joins a reply and its continuation. If the continuation starts a new file block while the reply ended
  inside an unfinished one, the unfinished block is dropped (the model restarted that file)."""
  answer = pieces[0]
  for piece in pieces[1:]:
    open_block = OPEN_BLOCK.search(answer)
    if open_block and piece.lstrip().startswith("<<<FILE"):
      answer = answer[:open_block.start()]
    answer += piece
  return answer


async def record_call(session, messages, usage, reason, started, n_images, effort, n):
  """Counters, the CALL log line and the usage report for one finished model call."""
  if reason == "length" or cut_off(usage, reason):
    await session.log(f"naive: call {n + 1} used the whole output budget ({MAX_OUTPUT_TOKENS} tokens, finish={reason})")
  if not usage:
    return
  cached = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
  reasoning = getattr(getattr(usage, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
  CALLS["input_tokens"] += usage.prompt_tokens or 0
  CALLS["cached_input_tokens"] += cached
  CALLS["output_tokens"] += usage.completion_tokens or 0
  CALLS["reasoning_tokens"] += reasoning
  chars, fp = prompt_fingerprint.fingerprint(loggable(messages))
  raw = usage.model_dump() if hasattr(usage, "model_dump") else repr(usage)
  # One record per successful call: what research/kvcache.py needs to estimate cache use (hashes of the
  # prompt, never its text) next to the endpoint's own, unprocessed usage figures.
  await session.log("naive: CALL " + json.dumps({
      "t": round(started, 1), "model": MODEL, "n": n, "effort": effort, "chars": chars,
      "step": prompt_fingerprint.STEP, "fp": fp, "finish_reason": reason, "max_output_tokens": MAX_OUTPUT_TOKENS,
      "images_attached": n_images, "prompt_tokens": usage.prompt_tokens or 0, "cached_reported": cached,
      "completion_tokens": usage.completion_tokens or 0, "reasoning_reported": reasoning, "usage_raw": raw},
      default=str))
  await session.usage(MODEL, input_tokens=usage.prompt_tokens or 0,
                      output_tokens=usage.completion_tokens or 0, cache_read_tokens=cached)


async def _solve(session):
  data, image_files = await gather_inputs(session)
  image_parts, attached = await load_images(session, image_files) if (ATTACH_IMAGES and image_files) else ([], [])
  inputs = render_inputs(data, attached) if isinstance(data, dict) else data
  text = f"{session.instruction}\n\n{inputs}"
  messages = [
      {"role": "system", "content": SYSTEM.format(workdir=session.workdir)},
      {"role": "user", "content": [{"type": "text", "text": text}] + image_parts if image_parts else text},
  ]
  base, answer, effort = messages, "", EFFORT
  for n in range(MAX_RESTARTS + 1):
    convo = base if n == 0 else base + (
        [{"role": "assistant", "content": answer}, {"role": "user", "content": CONTINUE_NOTE}] if answer.strip()
        else [{"role": "user", "content": EMPTY_NOTE}])
    started = time.time()
    text, usage, reason = await ask(session, convo, effort)
    await record_call(session, convo, usage, reason, started, len(attached), effort, n)
    answer = assemble([answer, text]) if answer else text
    if not cut_off(usage, reason) or n == MAX_RESTARTS:
      break
    left = session.time_left()
    if left is not None and left < 900:
      await session.log("naive: no time left to restart")
      break
    if RESTART_EFFORT_STEP:
      i = EFFORT_LADDER.index(effort) if effort in EFFORT_LADDER else 1
      effort = EFFORT_LADDER[min(i + 1, len(EFFORT_LADDER) - 1)]
    await session.log("naive: RESTART " + json.dumps({"n": n + 1, "after": reason, "kept_chars": len(answer), "next_effort": effort}))

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
