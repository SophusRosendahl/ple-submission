"""verify_facts: comparing two readings, and the tool with a fake second reader."""
import asyncio
import json
import unittest

import evaluator
import verifier


class Compare(unittest.TestCase):
  def test_text_numbers_points_and_lists(self):
    self.assertTrue(verifier.agree("IfcCableSegment", "ifccablesegment"))
    self.assertFalse(verifier.agree("IfcCableSegment", "IfcCableCarrierSegment"))
    self.assertTrue(verifier.agree(2600, 2600.4))
    self.assertFalse(verifier.agree(2600, 1890))
    self.assertTrue(verifier.agree([0, 9900], [10, 9895]))
    self.assertFalse(verifier.agree([0, 9900], [200, 3360]))
    self.assertTrue(verifier.agree([0, 9900], [0, 9950], tol=100))
    self.assertTrue(verifier.agree(["a b", "c"], ["c", "A B"]))

  def test_parse_answers(self):
    self.assertEqual(verifier.parse_answers('here:\n[{"id": "x", "answer": 1}]')[0]["id"], "x")
    self.assertIsNone(verifier.parse_answers("no json"))


class FakeSession:
  instruction = "Design the hall."

  def __init__(self):
    self.logs = []

  async def log(self, t):
    self.logs.append(t)


def run(coro):
  return asyncio.new_event_loop().run_until_complete(coro)


class Tool(unittest.TestCase):
  FACTS = [{"id": "entry", "question": "Where is the service entry (x, y)?", "answer": [0, 9900]},
           {"id": "cls", "question": "IFC class of the busway?", "answer": "IfcCableSegment"},
           {"id": "lim", "question": "Minimum headroom?", "answer": 2600},
           {"id": "gone", "question": "Fire rating?", "answer": "2 h"}]

  def ask_with(self, answers):
    seen = {}
    async def ask(prompt):
      seen["prompt"] = prompt
      return "Here you go:\n" + json.dumps(answers)
    return ask, seen

  def test_agreement_disagreement_and_not_found_are_reported_and_answers_are_withheld(self):
    ask, seen = self.ask_with([{"id": "entry", "answer": [200, 3360], "source": "M-101 note 2"}, {"id": "cls", "answer": "IfcCableSegment", "source": "A-601"},
                               {"id": "lim", "answer": 2600, "source": "A-602"}, {"id": "gone", "answer": "not stated", "source": ""}])
    s, st = FakeSession(), evaluator.DesignState()
    out = run(verifier.verify_tool(s, st, {"facts": self.FACTS}, ask, listing="files..."))["output"]
    self.assertIn("2 agree, 1 disagree, 1 not found", out)
    self.assertIn("[DISAGREE] entry", out)
    self.assertIn("second reading: [200, 3360], from M-101 note 2", out)
    self.assertIn("[NOT FOUND] gone", out)
    self.assertNotIn("[0, 9900]", seen["prompt"])  # the reader never sees the agent's answers
    self.assertNotIn("IfcCableSegment", seen["prompt"])
    self.assertIn("Design the hall.", seen["prompt"])
    self.assertTrue(any("pi: VERIFY" in l for l in s.logs))

  def test_bad_input_and_call_limit(self):
    s, st = FakeSession(), evaluator.DesignState()
    ask, _ = self.ask_with([])
    self.assertIn("non-empty list", run(verifier.verify_tool(s, st, {"facts": []}, ask))["output"])
    self.assertIn("Every fact needs", run(verifier.verify_tool(s, st, {"facts": [{"id": "a"}]}, ask))["output"])
    st.verify_calls = verifier.MAX_CALLS
    self.assertIn("limit", run(verifier.verify_tool(s, st, {"facts": self.FACTS}, ask))["output"])

  def test_unparseable_second_reading_compares_nothing(self):
    async def ask(prompt):
      return "I could not read the files."
    out = run(verifier.verify_tool(FakeSession(), evaluator.DesignState(), {"facts": self.FACTS}, ask))["output"]
    self.assertIn("nothing was compared", out)


if __name__ == "__main__":
  unittest.main()
