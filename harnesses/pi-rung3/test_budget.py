"""Tests of the call budget guard: counting, waiting for the last reply's tools, stopping a process."""
import asyncio
import json
import os
import time
import unittest

os.environ.setdefault("MODEL_NAME", "m")
import harness  # noqa: E402
import taskbridge  # noqa: E402


class FakeSession:
  final_message = ""

  def __init__(self):
    self.lines = []

  async def log(self, text):
    self.lines.append(text)

  async def usage(self, *a, **k):
    pass

  def time_left(self):
    return None


def reply(tools):
  blocks = [{"type": "toolCall", "id": str(i), "name": "bash", "arguments": {}} for i in range(tools)] or [{"type": "text", "text": "done"}]
  return {"type": "message_end", "message": {"role": "assistant", "content": blocks, "stopReason": "toolUse" if tools else "stop", "usage": {"input": 10, "output": 2}}}


class BudgetTest(unittest.TestCase):
  def run_events(self, run, events):
    async def go():
      for e in events:
        await run.on_event(e)
    asyncio.run(go())

  def test_stops_after_the_tools_of_the_last_allowed_reply(self):
    run = harness.Run(FakeSession(), "m", max_calls=3)
    end = {"type": "tool_execution_end", "result": {}}
    self.run_events(run, [reply(1), end, reply(1), end, reply(2)])
    self.assertEqual(run.replies, 3)
    self.assertFalse(run.budget_hit.is_set())   # two tool calls of reply 3 still running
    self.run_events(run, [end])
    self.assertFalse(run.budget_hit.is_set())
    self.run_events(run, [end])
    self.assertTrue(run.budget_hit.is_set())

  def test_a_final_answer_at_the_limit_needs_no_stop(self):
    run = harness.Run(FakeSession(), "m", max_calls=2)
    self.run_events(run, [reply(1), {"type": "tool_execution_end", "result": {}}, reply(0)])
    self.assertEqual(run.replies, 2)
    self.assertFalse(run.budget_hit.is_set())

  def test_under_the_limit_nothing_happens(self):
    run = harness.Run(FakeSession(), "m", max_calls=20)
    self.run_events(run, [reply(1), {"type": "tool_execution_end", "result": {}}] * 5)
    self.assertFalse(run.budget_hit.is_set())
    self.assertEqual(run.calls["ok"], 5)

  def test_cancelling_run_process_kills_the_process(self):
    async def go():
      session = FakeSession()
      pid_file = "/tmp/budget_test.pid"
      proc = asyncio.create_task(taskbridge.run_process(
          ["bash", "-c", f"echo $$ > {pid_file}; sleep 100"], session, stop_before_sec=60))
      await asyncio.sleep(1)
      t = time.time()
      proc.cancel()
      try:
        await proc
      except asyncio.CancelledError:
        pass
      pid = int(open(pid_file).read())
      alive = os.path.exists(f"/proc/{pid}")
      return alive, time.time() - t
    alive, took = asyncio.run(go())
    self.assertFalse(alive)
    self.assertLess(took, 12)


if __name__ == "__main__":
  unittest.main()
