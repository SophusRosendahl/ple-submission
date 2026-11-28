"""The designer's evaluate and note_concern tools, on the serve side.

evaluate(ifc, run?): optionally builds the IFC in the task container, reads it, validates the schema, extracts the items,
resolves the check-builder's roles against the kinds actually present, and runs the engine. The checks are fixed: the designer
can only record a concern, which is shown with every later report.
"""
from __future__ import annotations

import asyncio
import base64
import fnmatch
import os
import tempfile
import time

import engine
import ifc_items


def resolve_roles(items: list[dict], patterns: dict[str, list[str]]) -> dict[str, list[str]]:
  """Role -> the kinds in the model that match any of its glob patterns (case-insensitive)."""
  kinds = sorted({it["kind"] for it in items})
  return {role: [k for k in kinds if any(fnmatch.fnmatch(k.lower(), p.lower()) for p in pats)] for role, pats in patterns.items()}


class DesignState:
  """What persists between evaluations of one task."""

  def __init__(self, checks: list[dict], role_patterns: dict[str, list[str]], requirements: list[dict]):
    self.checks, self.role_patterns, self.requirements = checks, role_patterns, requirements
    self.previous: dict | None = None
    self.best_total: float | None = None
    self.concerns: list[dict] = []
    self.evaluations: list[dict] = []  # one summary per call, logged at the end


async def evaluate_tool(session, state: DesignState, fields: dict) -> dict:
  t0 = time.time()
  ifc, run = fields.get("ifc"), fields.get("run")
  if not isinstance(ifc, str) or not ifc:
    return {"output": "evaluate needs `ifc`: the path of the IFC file."}
  head = ""
  if run:
    res = await session.exec(run, timeout_sec=600)
    out = (res.get("output") or "")
    tail = out[-1800:]
    head = f"BUILD: `{run}` exited with {res.get('exit_code')}" + (" (timed out)" if res.get("timed_out") else "") + "\n" + \
           (("  " + tail.replace("\n", "\n  ") + "\n") if tail.strip() else "")
    if res.get("exit_code") != 0:
      return {"output": head + "The build failed, so nothing was evaluated. Fix the error above first."}
  try:
    raw = await session.read_result(ifc)
  except Exception as exc:
    return {"output": head + f"Could not read {ifc}: {exc}. Does the build write it there?"}
  if not raw.get("ok", True):
    return {"output": head + f"Could not read {ifc}: {raw.get('error')}. Does the build write it there?"}
  if raw.get("truncated"):
    return {"output": head + f"{ifc} is {raw.get('size')} bytes, over the 10 MB the evaluator can read. Make the model smaller."}
  data = base64.b64decode(raw.get("content_b64") or "")
  with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
    f.write(data)
    path = f.name
  try:
    try:
      items = await asyncio.to_thread(ifc_items.items_from_ifc, path)
    except Exception as exc:  # an unreadable IFC is a finding, not a crash
      return {"output": head + f"The file {ifc} cannot be opened as IFC: {type(exc).__name__}: {str(exc)[:300]}"}
    try:
      schema = await asyncio.to_thread(ifc_items.validate_ifc, path)
    except Exception as exc:  # the validator failing must not hide the checks; say so, loudly
      schema = {"ok": True, "n_errors": 0, "groups": [], "unavailable": f"{type(exc).__name__}: {str(exc)[:200]}"}
      await session.log(f"pi: SCHEMA VALIDATION UNAVAILABLE {schema['unavailable']}")
  finally:
    os.unlink(path)
  if not items:
    return {"output": head + ifc_items.render_validation(schema) + "\nThe file has no elements with a shape, so no check can run."}
  roles = resolve_roles(items, state.role_patterns)
  prev = dict(state.previous or {})
  if state.best_total is not None:
    prev["best_total_mm"] = state.best_total
  report = await asyncio.to_thread(engine.evaluate, items, state.checks, roles, prev or None)
  state.previous = report
  if report.get("objective"):
    tot = report["objective"]["total_mm"]
    state.best_total = tot if state.best_total is None else min(state.best_total, tot)
  state.evaluations.append({"n": len(state.evaluations) + 1, "ready": report["ready"] and schema["ok"] and not schema.get("unavailable"), "schema_errors": schema["n_errors"],
                            "failing": [k for k, r in report["results"].items() if r["status"] in ("fail", "error")],
                            "objective_mm": (report.get("objective") or {}).get("total_mm"), "seconds": round(time.time() - t0, 1)})
  text = [head.rstrip(), ("SCHEMA: could not be validated here (" + schema["unavailable"] + "); validate it yourself with ifcopenshell.validate"
                          if schema.get("unavailable") else ifc_items.render_validation(schema)), engine.render(report)]
  if state.best_total is not None and report.get("objective"):
    text.append(f"  best so far: {state.best_total:.0f} mm")
  if state.concerns:
    text.append("CONCERNS YOU RECORDED (the checks stay as they are)")
    text += [f"  - {c['check']}: {c['text']}" for c in state.concerns]
  if not schema["ok"]:
    text.append("NOT READY: the IFC schema errors above must be fixed too.")
  return {"output": "\n".join(x for x in text if x)}


async def concern_tool(session, state: DesignState, fields: dict) -> dict:
  state.concerns.append({"check": str(fields.get("check", "?"))[:60], "text": str(fields.get("text", ""))[:1500]})
  await session.log("pi: CONCERN " + repr(state.concerns[-1]))
  return {"output": f"Recorded ({len(state.concerns)} in all). The check is unchanged; it will be shown with each later evaluation."}
