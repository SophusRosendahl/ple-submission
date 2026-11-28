"""The check-builder: one fresh-context model call that programs the engine from the task text alone.

It never sees the design or the input files, only the instruction and the engine's catalogue. Its output is data: requirements,
roles (names bound to IFC kind patterns), checks from the library (or small custom ones) and the objective. The harness validates
it and, on an error, asks once more with the error message.
"""
from __future__ import annotations

import json
import re

import engine

SYSTEM = """You configure an automatic design checker. You will be given an engineering task. You do not design anything.
Your job: read the task's requirements and objective and program the checker so that every requirement that can be tested
on the geometry of the delivered IFC model is tested, strictly and completely, and the objective is computed.

HOW THE CHECKER SEES THE MODEL
The delivered IFC file is turned into a list of items, one per element that has a shape. Each item has:
  id    the element's Name
  kind  its IFC class, then "/" and its ObjectType when it has one, e.g. "IfcPipeSegment/CHW"
  group for pipe, duct and cable segments, the letters at the start of the Name in capitals (the service), else empty
  aabb  its axis-aligned bounding box in millimetres, [x0, y0, z0, x1, y1, z1], world coordinates
You do not know the exact kinds the designer will use. A ROLE is a name bound to glob patterns over kind, matched
case-insensitively, e.g. "pipe": ["IfcPipeSegment*", "IfcPipeFitting*"]. Use the IFC classes the task implies and be generous.

THE CHECK LIBRARY (each check is a JSON object with a unique "id", a "type", a short "title", a "requirement" id, and these fields)
  no_overlap      no two items of the selected roles overlap deeper than "tol" mm (default 2).
                  roles: list of role names or ["*"] for everything. exclude: optional list of declared exclusions, each one of
                  {"same_group": true}, {"same_kind": true}, {"roles": ["a","b"]}. Every exclusion must be justified by the task text;
                  the checker reports overlaps inside excluded pairs anyway.
  min_clearance   "a", "b" roles, "min" mm, "mode": "euclid" (distance between boxes), "best_axis" (at least one axis keeps it), "z" (vertical gap)
  z_range         "role", "zmin" and/or "zmax" in mm: every item of the role lies inside the band
  nearest_within  "from" role, "to" role, "max" mm: every "from" item has a "to" item within max (plan view unless "plan_only": false)
  connected       "role": items of one group form one touching network ("touch_tol" mm, default 5); optional "reach": {"point": [x, y], "tol": mm}
  coverage_along  "lines" role (long items), "by" role, "across" mm, "min_fraction" (0 to 1), optional "each_group": true
  count           "role" and "equals" or "at_least"
  length_sum      "role": the objective's route length in mm, by group (use this when the objective is total length)
  custom          "code": Python defining  def check(items, roles, helpers)  returning {"violations": [strings], "examined": n}.
                  items are dicts as above; roles maps role to its kinds; helpers has np, overlap_depths(a, b), gaps(a, b), select(items, roles, role).
                  No imports, no file access. Use only when the library cannot express the requirement.

RULES
- Encode every numeric limit in the task with its own number and unit (convert to mm). Do not soften, narrow or reinterpret.
- A requirement about every item or every pair must be a full sweep: do not exclude pairs unless the task text says so.
- One check per requirement is the norm. Put the requirement's id in the check.
- Requirements that cannot be tested on boxes (file format, naming, documents, anything about a deliverable other than the IFC geometry)
  go in "unchecked" with the reason.
- The objective: if the task scores a quantity, say what it is in "objective" and, when it is a length, add a length_sum check.

REPLY with a single JSON object and nothing else:
{"requirements": [{"id": "R1", "text": "the requirement in the task's own words"}],
 "roles": {"role": ["glob", ...]},
 "checks": [ ... ],
 "unchecked": [{"requirement": "R9", "why": "..."}],
 "objective": {"description": "...", "check": "id of the check that computes it, or null"}}"""


def prompt(instruction: str) -> str:
  return "TASK\n\n" + instruction


def extract_json(text: str) -> dict | None:
  m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
  cand = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1] if "{" in text else ""
  try:
    out = json.loads(cand)
    return out if isinstance(out, dict) else None
  except ValueError:
    return None


def validate(cfg: dict | None) -> list[str]:
  """Problems that make the configuration unusable, as messages the check-builder can act on."""
  if cfg is None:
    return ["the reply is not a single JSON object"]
  probs = []
  roles = cfg.get("roles")
  checks = cfg.get("checks")
  if not isinstance(roles, dict) or not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in roles.values()):
    probs.append("'roles' must map each role name to a list of glob strings")
    roles = {}
  if not isinstance(checks, list) or not checks:
    return probs + ["'checks' must be a non-empty list"]
  if any(not isinstance(c, dict) for c in checks):
    return probs + ["every check must be an object"]
  probs += engine.validate_config(checks)
  for c in checks:
    cid = c.get("id", "?")
    used = []
    for key in ("roles", "a", "b", "role", "from", "to", "lines", "by"):
      v = c.get(key)
      used += [v] if isinstance(v, str) else (v if isinstance(v, list) else [])
    for r in used:
      if r != "*" and r not in roles:
        probs.append(f"{cid}: role '{r}' is not defined in 'roles'")
    if c.get("type") == "custom" and isinstance(c.get("code"), str):
      try:
        compile(c["code"], f"custom:{cid}", "exec")
      except SyntaxError as exc:
        probs.append(f"{cid}: the code has a syntax error at line {exc.lineno}: {exc.msg}")
      if "def check(" not in c["code"]:
        probs.append(f"{cid}: the code must define check(items, roles, helpers)")
  return probs
