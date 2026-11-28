"""The check catalogue the agent programs the engine from, and the validation of a checks configuration.

One agent does everything in rung 3 v2: it writes the checks (set_checks), builds, evaluates, and rewrites the checks when they are
wrong. This module holds the text that tells it how, and the structural validation of a configuration.
"""
from __future__ import annotations

import json
import re

import engine

CATALOGUE = """THE CHECKER
You have an automatic checker for your design. You program it yourself, from the task's requirements and objective: every requirement
that can be tested on the geometry of the delivered IFC model should be tested, strictly and completely, and the objective computed.

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
  z_range         "role", and "zmin" and/or "zmax" in mm, or "bands": [[lo, hi], ...] (every item lies fully inside one of the bands, e.g.
                  overhead [2600, 3100] or plenum [-900, -55]). Prefer this to custom code: the report then also lists items of other kinds
                  that would break the same limit.
  nearest_within  "from" role, "to" role, "max" mm: every "from" item has a "to" item within max (plan view unless "plan_only": false)
  connected       "role": items of one group form one touching network ("touch_tol" mm, default 5); optional "reach": {"point": [x, y], "tol": mm}
  coverage_along  "lines" role (long items), "by" role, "across" mm, "min_fraction" (0 to 1), optional "each_group": true.
                  For rows made of many small items (racks standing side by side) add "merge_lines": true (optional "row_gap" mm, default 300):
                  the items of a row are judged together along the row's whole length, not one by one.
  count           "role" and "equals" or "at_least"
  length_sum      "role": the objective's route length in mm, by group (use this when the objective is total length)
  custom          "code": Python defining  def check(items, roles, helpers)  returning {"violations": [strings], "examined": n}.
                  items are dicts as above; roles maps role to its kinds. helpers: np; helpers["items_of"](items, roles, "pipe") returns the
                  item DICTS of a role (helpers["select"] returns INDICES into items, not items); overlap_depths(a_aabb, b_aabb) returns
                  the (x, y, z) overlap depths of two boxes (negative = a gap); gaps(a, b) the per-axis gaps. No imports, no file access.
                  Example:  def check(items, roles, helpers):
                              v = []
                              for p in helpers["items_of"](items, roles, "pipe"):
                                if p["aabb"][5] > 2400: v.append(f"{p['id']} top at {p['aabb'][5]:.0f}, 2400 allowed: lower it")
                              return {"violations": v, "examined": len(helpers["items_of"](items, roles, "pipe"))}
                  The report lists which kinds the check covers from the roles your code asks the helpers for, so always go through
                  helpers["items_of"] or helpers["select"] with a role name; code that never asks for a role is reported as covering nothing.
                  Use only when the library cannot express the requirement; test_checks runs your code, so an error in it shows up there.

RULES
- Write the checks BEFORE you build, from the requirements, so the design is built against them. Encode every numeric limit in the task with its own number and unit (convert to mm). Do not soften, narrow or reinterpret.
- A requirement about every item or every pair must be a full sweep: do not exclude pairs unless the task text says so.
- One check per requirement is the norm. Put the requirement's id in the check.
- Requirements that cannot be tested on boxes (file format, naming, documents, anything about a deliverable other than the IFC geometry)
  go in "unchecked" with the reason.
- The objective: if the task scores a quantity, say what it is in "objective" and, when it is a length, add a length_sum check.

HOW TO READ THE evaluate REPORT (top to bottom)
- BUILD: your command's exit code and the end of its output. SCHEMA: IFC validity; fix these first, they can make the file unusable.
- CHECKS, failing first. A line "CAUSE: N overlap(s) with one cause" is one fix for N findings: apply the stated change (it gives the
  coordinates and the amount) and re-evaluate instead of fixing the N findings one by one. [ERROR] means the check itself is broken
  (its roles match nothing, its code fails): that is a problem with your checker, not your design, so repair it with set_checks.
- INSIDE THE EXCLUDED PAIRS: overlaps among pairs your check was told to skip. The check does not count them. Decide whether the
  exclusion is justified by the task text; if not, remove it.
- SCOPE FACTS, "kinds that no check selects": every element kind listed there is untested. For each, add a check or be able to say why none is needed.
- SELF-TEST: pairs of kinds for which a deliberate overlap would NOT be reported by your clash check. Each one is a blind spot in your own check.
- OBJECTIVE and "best so far": the quantity the task scores. When every check passes, use the remaining calls to improve it, re-evaluating
  after each change, and keep the best version that passes every check.
READY means your checks pass; it does not mean every requirement is met. Before you finish, re-read your checks once against the task text:
which requirement has no check, which threshold is looser than the text, which check selects fewer elements than the requirement covers?

HOW THE CHECKER WORKS WITH YOUR DESIGN
- set_checks(config) installs a configuration (the whole thing every time). It validates it, then plants a known fault and a clean case for
  every check in a small synthetic model built from your roles, runs your checks on them, and shows [ok] or WRONG for each, with the message
  you would read when the check fails. Custom code is run on the synthetic model too, so a bug in it shows up there. Fix WRONG rows first.
- evaluate(ifc, run?) builds your IFC (optional command), validates the schema, runs the installed checks on the delivered file and returns
  the report: where each check fails, by how much and what to change; the objective; the kinds no check covers; the scope of every
  exclusion. For a custom check YOU write the message: each violation string must name the elements, the amount and the change to make.
- The checker is only as good as your configuration. A check that is too strict sends you after something that is not a defect; one that is
  too lax or missing lets a defect through; one whose roles match nothing is an ERROR. READY means your checks pass, not that the design is right.
- You may rewrite the checks at any time, for example when a check errors, when you find that it measures something other than its
  requirement, when you learn from the drawings a number the task text only points to (read the input files first: coordinates, limits and
  facings are often only there), or when a requirement is missing. The evaluation shows the version of the checks and what changed since the
  previous version. Never loosen, narrow or delete a check just to make the design pass: change a check only because it is wrong against the
  requirement's own words, and say in your final summary what you changed and why.
- Requirements that cannot be tested on boxes (file format, naming, documents) are yours to verify directly.

CONFIGURATION FORMAT (set_checks takes it as one JSON string)
{"requirements": [{"id": "R1", "text": "the requirement in the task's own words"}],
 "roles": {"role": ["glob", ...]},
 "checks": [ ... as in the library above ... ],
 "unchecked": [{"requirement": "R9", "why": "..."}],
 "objective": {"description": "...", "check": "id of the check that computes it, or null"}}
Roles are glob patterns over kind, case-insensitive; you do not know the exact kinds until you have built a model, so start broad and
narrow once evaluate shows the kinds present."""


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
    for key in ("roles", "a", "b", "role", "from", "to", "lines", "by", "uses"):
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
