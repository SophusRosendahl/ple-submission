"""verify_facts: an independent second reading of the facts the agent's checks and design depend on.

The agent lists the critical facts it took from the input files (IFC class of each element type, coordinates of anchors such as service
entries, numeric limits, counts) as questions with its own answers. A separate fresh-context run of the same model, which sees only the
task text, the files and the questions, never the agent's answers, answers them from the files with a source for each. The harness compares
the two readings. A disagreement is not a verdict: it tells the agent which fact to re-read and which sheet the other reading cites.
"""
from __future__ import annotations

import json
import re

MAX_FACTS = 25
MAX_CALLS = 4

SYSTEM = """You answer factual questions about the input files of an engineering task, by reading the files. You do not design anything and you are not
told what anyone else answered. Read the sheets and documents the questions need, and answer ONLY from them: if the files do not say, answer "not stated".
Give each answer in the units and format the question asks for (millimetres unless it says otherwise; coordinates as [x, y] or [x, y, z]; IFC classes with
their exact spelling). Give the sheet or file and the note or location you took it from.

Reply with a single JSON list and nothing else: [{"id": "<the question's id>", "answer": <your answer>, "source": "<sheet/file and location>"}, ...]"""


def norm_text(v) -> str:
  return re.sub(r"[^a-z0-9.]+", " ", str(v).lower()).strip()


def numbers(v):
  """A list of floats if `v` is a number or a list of numbers, else None."""
  if isinstance(v, bool):
    return None
  if isinstance(v, (int, float)):
    return [float(v)]
  if isinstance(v, (list, tuple)) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v):
    return [float(x) for x in v]
  return None


def agree(mine, theirs, tol=None) -> bool:
  a, b = numbers(mine), numbers(theirs)
  if a is not None and b is not None:
    if len(a) != len(b):
      return False
    t = float(tol) if tol is not None else (25.0 if len(a) > 1 else None)
    return all(abs(x - y) <= (t if t is not None else max(1.0, 0.005 * max(abs(x), abs(y)))) for x, y in zip(a, b))
  if isinstance(mine, (list, tuple)) and isinstance(theirs, (list, tuple)):
    return sorted(norm_text(x) for x in mine) == sorted(norm_text(x) for x in theirs)
  return norm_text(mine) == norm_text(theirs)


def validate(facts) -> str | None:
  if not isinstance(facts, list) or not facts:
    return "`facts` must be a non-empty list of {id, question, answer}."
  if len(facts) > MAX_FACTS:
    return f"At most {MAX_FACTS} facts per call: keep the ones your checks and parameter ranges depend on."
  ids = set()
  for f in facts:
    if not isinstance(f, dict) or not all(k in f for k in ("id", "question", "answer")):
      return "Every fact needs `id`, `question` and `answer` (your own reading)."
    if f["id"] in ids:
      return f"Duplicate fact id {f['id']}."
    ids.add(f["id"])
  return None


def parse_answers(text: str):
  m = re.search(r"\[.*\]", text or "", re.S)
  try:
    out = json.loads(m.group(0)) if m else None
  except ValueError:
    return None
  return out if isinstance(out, list) and all(isinstance(x, dict) and "id" in x for x in out) else None


def question_prompt(instruction: str, facts: list[dict], listing: str) -> str:
  qs = "\n".join(f"- id {f['id']}: {f['question']}" + (f" (unit: {f['unit']})" if f.get("unit") else "") for f in facts)
  return f"TASK (for context only)\n\n{instruction}\n\n{listing}\n\nQUESTIONS\n{qs}"


def render(facts, answers) -> tuple[str, dict]:
  by_id = {a["id"]: a for a in answers}
  lines, count = [], {"agree": 0, "disagree": 0, "not_found": 0}
  for f in facts:
    a = by_id.get(f["id"])
    if a is None or norm_text(a.get("answer")) in ("not stated", "none", ""):
      count["not_found"] += 1
      lines.append(f"  [NOT FOUND] {f['id']}: the second reading found nothing for \"{f['question']}\" (your answer: {json.dumps(f['answer'])}). "
                   "Either the files do not state it (then it is an assumption: say so) or one of you missed it.")
    elif agree(f["answer"], a["answer"], f.get("tol")):
      count["agree"] += 1
      lines.append(f"  [agree] {f['id']}: {json.dumps(f['answer'])}  (second reading cites {a.get('source', '?')})")
    else:
      count["disagree"] += 1
      lines.append(f"  [DISAGREE] {f['id']}: \"{f['question']}\"\n        you: {json.dumps(f['answer'])}\n        second reading: {json.dumps(a['answer'])}"
                   f", from {a.get('source', '?')}\n        Re-read that sheet or note yourself and decide who is right; fix your checks, parameters and design if it is you.")
  head = (f"VERIFY: {count['agree']} agree, {count['disagree']} disagree, {count['not_found']} not found, of {len(facts)}."
          + (" Resolve every DISAGREE before you rely on those facts; agreement of two readings is evidence, not proof." if count["disagree"] or count["not_found"] else
             " Agreement of two readings is evidence, not proof."))
  return head + "\n" + "\n".join(lines), count


async def verify_tool(session, state, fields: dict, ask, listing: str = "") -> dict:
  facts = fields.get("facts")
  err = validate(facts)
  if err:
    return {"output": err}
  if getattr(state, "verify_calls", 0) >= MAX_CALLS:
    return {"output": f"verify_facts has been used {MAX_CALLS} times, the limit for one task."}
  state.verify_calls = getattr(state, "verify_calls", 0) + 1
  text = await ask(question_prompt(getattr(session, "instruction", ""), facts, listing))
  answers = parse_answers(text)
  if answers is None:
    await session.log("pi: VERIFY could not parse the second reading: " + (text or "")[:300].replace("\n", " "))
    return {"output": "The second reading did not produce answers in the expected form, so nothing was compared. You may call verify_facts again."}
  out, count = render(facts, answers)
  await session.log("pi: VERIFY " + json.dumps({"call": state.verify_calls, **count, "facts": [f["id"] for f in facts]}))
  return {"output": out}
