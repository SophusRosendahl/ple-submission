# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pi coding agent harness (`@earendil-works/pi-coding-agent`).

Runs one headless Pi session per task. Pi runs in the serve container while the
task's files live in the task container. `task-tools.ts` replaces Pi's built-in
`read`, `write`, `edit`, and `bash` tools with versions that operate on the task
container through `taskbridge.Relay`, and the task's MCP servers are proxied
through the same relay. Pi's agent loop handles model calls, tool execution,
retries, and conversation compaction, returning its last response as the final
message.

The model is configured from the environment variables set by the evaluator in
`models.json` for each task. Claude and Gemini models use their native APIs
under Pi's built-in provider names (`anthropic` and `google`) so Pi's catalog
supplies their limits, thinking support, and image input capabilities. Any other
model uses the OpenAI-compatible `MODEL_BASE_URL` and `MODEL_API_KEY` under a
custom `model` provider with `UNKNOWN_MODEL` limits.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

import inputs
import taskbridge

HERE = pathlib.Path(__file__).resolve().parent
# npm ci, from package-lock.json
PI = shutil.which("pi") or str(HERE / "node_modules" / ".bin" / "pi")
# pi's --thinking level: off, minimal, low, medium, high, xhigh or max
# rung 1 runs at low effort, like rung 0 v5, so the loop is the only change; run_dev --effort sets REASONING_EFFORT
THINKING = os.environ.get("REASONING_EFFORT") or "low"
# stop pi this long before the deadline (less on short tasks) so its answer
# arrives
STOP_BEFORE_SEC = 90
CATALOG_TIMEOUT_SEC = 30
# Request features the Google Cloud route for Claude refuses. pi leaves them
# out, and the Anthropic API works without them too.
COMPAT = {
    "supportsStrictTools": False,
    "supportsMidConvoEffort": False,
    "supportsMidConvoSystemMessages": False,
    "supportsMidConvoToolChanges": False,
}
# A model pi's catalog does not know gets these limits; tune them for yours.
# Pi's catalogue knows gemini-3.8-flash (images, 65.5K output) but NOT gemini-4-neon: left to the template default it
# would be text only with 16,384 output tokens and could not see the drawings. Both Gemini models stop at 65,536.
# Budget guard: the most model calls (replies) one task may use. Every reply, with or without a tool call, is one
# call. After the last allowed reply its tool calls finish, then Pi is stopped; what is on disk is graded.
MAX_CALLS = int(os.environ.get("PI_MAX_CALLS") or 40)  # rung 2 reads, checks and re-checks: 20 is too few
UNKNOWN_MODEL = {"input": ["text", "image"], "contextWindow": 1000000, "maxTokens": 65536, "reasoning": True}
NOTE = (
    "You are working on an engineering task. Your tools read, write, edit and bash act on the task's Linux container,"
    " whose working directory is {workdir}; it has no internet access. The task's input files are in that container:"
    " the first message says where. Nothing from them is in the conversation yet, so read what you need with the read"
    " tool (it shows images). Put every deliverable exactly where and in the format the instruction asks. Keep notes"
    " and partial results in /tmp/scratch, never in a deliverable folder.\n\n"
    "Work in this order.\n"
    "1. Requirements. Read the whole instruction. Write the requirements as a numbered list in"
    " /tmp/scratch/requirements.md, quoting the instruction's own words and numbers. Do not narrow, soften or"
    " reinterpret a requirement; anything you assume goes in a separate list, marked as an assumption.\n"
    "2. Data. Read every input file you need, several at once if you like. In /tmp/scratch/data.md write down what you took from each."
    " Check that you ingested each one correctly: look at it again and compare it with your notes, and re-read"
    " whatever you are unsure of.\n"
    "3. Checks. Before you build, define a check for each requirement, derived from the requirement text and not from"
    " your own design, and write the checks as something you can run (for example /tmp/scratch/checks.py).\n"
    "4. Build a first version of every deliverable early, then improve it.\n"
    "5. Run your checks on the deliverable and fix what fails. A check that cannot fail proves nothing: make sure each"
    " one tests what its requirement says.\n"
    "6. Double-check before you finish: re-read the instruction and requirements.md against what you delivered, rerun"
    " the checks, and confirm that every deliverable exists where the instruction says.\n\n"
    "Batch your tool calls. When several tool calls do not depend on each other, make them together in one reply"
    " instead of one per reply: read all the files you need at once, and put several commands into one bash call."
    " Every reply counts against your budget.\n\n"
    "When you are done, reply with a short summary: what you delivered and where, which checks you ran and what each"
    " one covered, your assumptions, and anything you did not verify. Do not claim more than you tested. You have a"
    " budget of {max_calls} model calls in all: every reply you send, with or without a tool call, is one call, and"
    " when the budget is used up the run is stopped and whatever is on disk is graded."
)


def provider() -> tuple[str, dict[str, Any]]:
  """Returns the Pi provider name and its `models.json` entry.

  Returns:
    A tuple of `(provider_name, provider_config)`.
  """
  if os.environ.get("ANTHROPIC_BASE_URL"):
    return "anthropic", {
        "baseUrl": os.environ["ANTHROPIC_BASE_URL"],
        "api": "anthropic-messages",
        "apiKey": "$ANTHROPIC_API_KEY",
        "compat": COMPAT,
    }
  if os.environ.get("GOOGLE_GEMINI_BASE_URL"):
    return "google", {
        "baseUrl": os.environ["GOOGLE_GEMINI_BASE_URL"] + "/v1beta",
        "api": "google-generative-ai",
        "apiKey": "$GEMINI_API_KEY",
    }
  return "model", {
      "baseUrl": os.environ["MODEL_BASE_URL"],
      "api": "openai-completions",
      "apiKey": "$MODEL_API_KEY",
  }


def in_catalog(name: str, model: str, env: dict[str, str]) -> bool:
  """Checks whether Pi's built-in model catalog recognizes `model`.

  If the probe hangs beyond `CATALOG_TIMEOUT_SEC` or fails, returns `False` so
  the model is configured explicitly with `UNKNOWN_MODEL` limits.

  Args:
    name: Provider name (`anthropic`, `google`, or `model`).
    model: Model identifier string.
    env: Subprocess environment variables for the Pi CLI probe.

  Returns:
    `True` if `(name, model)` appears in `pi --list-models`, else `False`.
  """
  try:
    out = subprocess.run(
        [PI, "--offline", "--list-models", model],
        env=env,
        capture_output=True,
        text=True,
        timeout=CATALOG_TIMEOUT_SEC,
        check=False,
    ).stdout
  except (subprocess.TimeoutExpired, OSError):
    return False
  return any(line.split()[:2] == [name, model] for line in out.splitlines())


def configure(
    agent_dir: pathlib.Path,
    relay: taskbridge.Relay,
    session: taskbridge.Session,
    env: dict[str, str],
) -> tuple[str, str]:
  """Writes Pi's model, settings, and MCP configuration files for a task.

  Args:
    agent_dir: Directory where Pi reads its configuration files.
    relay: Local HTTP relay for the task container and its MCP servers.
    session: Active task session.
    env: Environment dictionary passed to Pi subprocesses.

  Returns:
    A tuple of `(provider_name, model_name)`.
  """
  model = os.environ["MODEL_NAME"]
  name, config = provider()
  models = agent_dir / "models.json"
  # `pi --list-models` reads the provider here
  models.write_text(json.dumps({"providers": {name: config}}))
  if not in_catalog(name, model, env):
    config["models"] = [{"id": model, "name": model, **UNKNOWN_MODEL}]
    models.write_text(json.dumps({"providers": {name: config}}))
  settings = {
      "defaultProjectTrust": "never",
      "quietStartup": True,
      "cacheWarming": "off",
      # Pi shrinks images to at most 2000 x 2000 pixels by default; rung 0 sent the originals, so keep them
      "images": {"autoResize": False},
      "retry": {"maxRetries": 6, "maxAgentDelayMs": 60000},
  }
  (agent_dir / "settings.json").write_text(json.dumps(settings))
  servers = {
      s["name"]: {"url": relay.mcp_url(s["name"]), "timeout": 300}
      for s in session.mcp_servers
  }
  (agent_dir / "mcp.json").write_text(json.dumps({"mcpServers": servers}))
  return name, model


class Run:
  """Tracks JSON stream events from a single Pi subprocess run."""

  def __init__(self, session: taskbridge.Session, model: str, max_calls: int = MAX_CALLS):
    self.session, self.model, self.replies = session, model, 0
    self.max_calls = max_calls
    self.budget_hit = asyncio.Event()  # set once the last allowed reply's tool calls have finished
    self.pending_tools = None  # tool calls of the last allowed reply that are still running
    # Same shape as rung 0's CALLS summary (research/costs.py reads ok and failed). Pi's usage has a
    # `reasoning` count; the proxy request log is the cross-check.
    self.calls = {"ok": 0, "failed": 0, "input_tokens": 0, "cached_input_tokens": 0,
                  "output_tokens": 0, "reasoning_tokens": 0}
    self.tools = {}
    self.ran_deliverable = False
    self.blocked = 0  # always 0 in rung 2 (no input guard); kept so the log shape matches rung 1
    self.reads = {}   # path -> times the read tool opened it (more than once = a re-read)
    self.written = []  # paths the write and edit tools touched, in order

  async def finish(self) -> None:
    """Logs the per-task summaries the tracker reads."""
    await self.session.log("pi: BUDGET " + json.dumps({"max_calls": self.max_calls, "replies": self.replies,
                                                       "stopped_by_budget": self.budget_hit.is_set()}))
    await self.session.log("pi: CALLS " + json.dumps(self.calls))
    await self.session.log("pi: TOOLS " + json.dumps({"counts": self.tools, "ran_deliverable": self.ran_deliverable, "reads": self.reads, "written": self.written}))

  async def on_event(self, event: dict[str, Any]) -> None:
    """Processes a parsed JSON event from Pi, updating final message and usage.

    Args:
      event: Decoded JSON event dictionary from Pi's stdout stream.
    """
    kind, message = event.get("type"), event.get("message") or {}
    if kind == "message_end" and message.get("role") == "assistant":
      self.replies += 1
      text = "\n".join(
          b.get("text", "")
          for b in message.get("content") or []
          if b.get("type") == "text"
      )
      if text.strip():
        self.session.final_message = text.strip()
      if message.get("stopReason") == "error":
        await self.session.log(
            f"pi: model error: {message.get('errorMessage')}"
        )
      # input_tokens counts cached prompt tokens too
      u = message.get("usage") or {}
      if self.replies >= self.max_calls and self.pending_tools is None:
        tool_calls = sum(1 for b in message.get("content") or [] if b.get("type") == "toolCall")
        if tool_calls:  # a reply without a tool call is the final answer: Pi ends by itself
          self.pending_tools = tool_calls
      failed = message.get("stopReason") == "error"
      self.calls["failed" if failed else "ok"] += 1
      prompt = u.get("input", 0) + u.get("cacheRead", 0) + u.get("cacheWrite", 0)
      self.calls["input_tokens"] += prompt
      self.calls["cached_input_tokens"] += u.get("cacheRead", 0)
      self.calls["output_tokens"] += u.get("output", 0)
      self.calls["reasoning_tokens"] += u.get("reasoning", 0) or 0
      await self.session.log("pi: CALL " + json.dumps({
          "n": self.replies, "model": self.model, "stop_reason": message.get("stopReason"),
          "prompt_tokens": prompt, "cached_reported": u.get("cacheRead", 0),
          "cache_write": u.get("cacheWrite", 0), "completion_tokens": u.get("output", 0),
          "reasoning_reported": u.get("reasoning", 0) or 0, "usage_raw": u}, default=str))
      await self.session.usage(
          self.model,
          input_tokens=u.get("input", 0)
          + u.get("cacheRead", 0)
          + u.get("cacheWrite", 0),
          output_tokens=u.get("output", 0),
          cache_read_tokens=u.get("cacheRead", 0),
      )
    elif kind == "tool_execution_end":
      if self.pending_tools is not None:
        self.pending_tools -= 1
        if self.pending_tools <= 0:
          await self.session.log(f"pi: call budget of {self.max_calls} used up: stopping")
          self.budget_hit.set()
      if "INPUT_GUARD" in json.dumps(event.get("result"), default=str):
        self.blocked += 1
        await self.session.log("pi: input guard refused a command")
    elif kind == "tool_execution_start":
      name, args = event.get("toolName"), event.get("args") or {}
      self.tools[name] = self.tools.get(name, 0) + 1
      if name == "read":
        self.reads[str(args.get("path"))] = self.reads.get(str(args.get("path")), 0) + 1
      elif name in ("write", "edit"):
        self.written.append(str(args.get("path")))
      if name == "bash" and "solution.py" in str(args.get("command", "")) and "python" in str(args.get("command", "")):
        self.ran_deliverable = True  # the agent tried its own deliverable (unprompted: the note does not say to)
      await self.session.log(
          f"pi: {event.get('toolName')} {json.dumps(event.get('args'))[:300]}"
      )
    elif kind in ("auto_retry_start", "compaction_start"):
      await self.session.log(f"pi: {kind} {json.dumps(event)[:300]}")

  async def on_line(self, line: bytes) -> None:
    """Parses a raw stdout line from Pi as JSON and forwards it to `on_event`.

    Args:
      line: Raw line bytes emitted by Pi.
    """
    try:
      event = json.loads(line)
    except ValueError:
      return
    if isinstance(event, dict):
      await self.on_event(event)


async def dump_scratch(session: taskbridge.Session) -> None:
  """Logs the text files the agent kept in /tmp/scratch (requirements, data notes, its checks).

  The task container is thrown away after grading and only the deliverable folders are captured, so without this the
  agent's own checks cannot be read afterwards. Text only, in chunks; a failure here never affects the run.
  """
  try:
    res = await session.exec("find /tmp/scratch -maxdepth 2 -type f -size -300k 2>/dev/null | sort | head -40", timeout_sec=60)
    for path in (res.get("output") or "").split():
      raw = await session.read_file(path)
      if b"\0" in raw[:2000]:
        await session.log(f"pi: SCRATCH[{path}] 1/1: " + json.dumps(f"(binary file, {len(raw)} bytes)"))
        continue
      text = raw.decode("utf-8", "replace")
      parts = [text[i:i + 1500] for i in range(0, len(text), 1500)] or [""]
      for i, part in enumerate(parts, 1):
        await session.log(f"pi: SCRATCH[{path}] {i}/{len(parts)}: " + json.dumps(part))
  except Exception as exc:  # recording only
    await session.log(f"pi: could not dump the scratch folder: {type(exc).__name__}: {exc}")


async def solve(session: taskbridge.Session) -> str:
  """Runs Pi on a single task and returns the final response.

  Creates an isolated temporary agent home, configures tools and MCP servers to
  communicate through `taskbridge.Relay`, and feeds the task instruction on
  standard input.

  Args:
    session: Active task session.

  Returns:
    The final message produced by Pi.

  Raises:
    RuntimeError: If Pi exits before the model produces any assistant reply.
  """
  with tempfile.TemporaryDirectory(
      prefix="pi-",
      dir=os.environ.get("HOME") or None,
      ignore_cleanup_errors=True,
  ) as scratch:
    agent_dir, work = (
        pathlib.Path(scratch) / "agent",
        pathlib.Path(scratch) / "work",
    )
    agent_dir.mkdir()
    work.mkdir()
    async with taskbridge.Relay(session) as relay:
      env = relay.env()
      env.update(
          PI_CODING_AGENT_DIR=str(agent_dir),
          PI_OFFLINE="1",
          PI_SKIP_VERSION_CHECK="1",
          PI_TELEMETRY="0",
          NODE_NO_WARNINGS="1",
          TASK_WORKDIR=session.workdir,
      )
      name, model = await asyncio.to_thread(
          configure, agent_dir, relay, session, env
      )
      # Rung 2: the contents are not fed. The first message is the instruction plus a listing of where the files are.
      prompt = session.instruction + "\n\n" + await inputs.listing(session)
      argv = [
          PI,
          "--print",
          "--mode",
          "json",
          "--no-session",
          "-nc",
          "-ns",
          "-np",
          "-na",
          "-e",
          str(HERE / "task-tools.ts"),
          "--provider",
          name,
          "--model",
          model,
          "--thinking",
          THINKING,
          "--append-system-prompt",
          NOTE.format(workdir=session.workdir, max_calls=MAX_CALLS),
          "--tools",
          "read,write,edit,bash",
      ]
      version = (HERE / "VERSION").read_text(encoding="utf-8").strip() if (HERE / "VERSION").is_file() else None
      await session.log("pi: VERSION " + json.dumps({"harness": version, "model": model, "thinking": THINKING,
                                                     "max_calls": MAX_CALLS}))
      run = Run(session, model)
      proc = asyncio.create_task(taskbridge.run_process(
          argv,
          session,
          env=env,
          cwd=str(work),
          on_line=run.on_line,
          stdin=prompt.encode(),
          stop_before_sec=STOP_BEFORE_SEC,
          log_prefix="pi: ",
      ))
      budget = asyncio.create_task(run.budget_hit.wait())
      await asyncio.wait({proc, budget}, return_when=asyncio.FIRST_COMPLETED)
      if proc.done():
        done = proc.result()
        budget.cancel()
      else:  # the call budget is used up: stop Pi (run_process kills its process group when cancelled)
        proc.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
          await proc
        done = taskbridge.Finished(-1, "", True)
        note = (f"Stopped by the harness: the budget of {MAX_CALLS} model calls was used up. Whatever the"
                " deliverables held at that moment is what was delivered; it was not reviewed afterwards.")
        session.final_message = note + (f"\n\nLast message from the agent: {session.final_message}"
                                        if session.final_message else "")
  await dump_scratch(session)
  await run.finish()
  if not run.replies:
    raise RuntimeError(
        f"pi exited with {done.code} before the model answered:"
        f" {done.stderr[-2000:]}"
    )
  return session.final_message or "(pi stopped without a final message)"
