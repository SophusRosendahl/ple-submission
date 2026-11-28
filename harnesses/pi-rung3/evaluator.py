"""The agent's set_checks and evaluate tools, on the serve side.

set_checks(config): validates the agent's checker configuration, probes it with planted faults, installs it as a new version.
evaluate(ifc, run?): optionally builds the IFC in the task container, reads it, validates the schema, extracts the items, resolves the
roles against the kinds actually present, and runs the installed checks. The report names the checks version and what changed since
the previous one, so a rewritten checker is always visible to whoever reads the evaluation.
"""
from __future__ import annotations

import asyncio
import base64
import fnmatch
import json
import os
import tempfile
import time

import catalogue
import engine
import ifc_items
import probe


def resolve_roles(items: list[dict], patterns: dict[str, list[str]]) -> dict[str, list[str]]:
  """Role -> the kinds in the model that match any of its glob patterns (case-insensitive)."""
  kinds = sorted({it["kind"] for it in items})
  return {role: [k for k in kinds if any(fnmatch.fnmatch(k.lower(), p.lower()) for p in pats)] for role, pats in patterns.items()}


def describe_change(old: dict | None, new: dict) -> list[str]:
  """What changed between two configurations, as short lines (checks added, removed, edited; roles; unchecked)."""
  if not old:
    return [f"first version: {len(new['checks'])} checks"]
  o, n = {c["id"]: c for c in old["checks"]}, {c["id"]: c for c in new["checks"]}
  out = [f"added {i} ({n[i]['type']}): {n[i].get('title', '')}" for i in n if i not in o]
  out += [f"removed {i} ({o[i]['type']}): {o[i].get('title', '')}" for i in o if i not in n]
  for i in n:
    if i in o and o[i] != n[i]:
      keys = sorted(k for k in set(o[i]) | set(n[i]) if o[i].get(k) != n[i].get(k) and k != "title")
      out.append(f"edited {i}: changed {', '.join(keys) or 'title'}" + "".join(
          f"; {k}: {str(o[i].get(k))[:60]} -> {str(n[i].get(k))[:60]}" for k in keys if k != "code")[:300])
  if old.get("roles") != new.get("roles"):
    out.append("roles changed: " + ", ".join(sorted(k for k in set(old["roles"]) | set(new["roles"]) if old["roles"].get(k) != new["roles"].get(k))))
  return out or ["no change"]


class DesignState:
  """What persists between calls within one task: the installed checks (with every earlier version) and the evaluations."""

  def __init__(self):
    self.config: dict | None = None
    self.versions: list[dict] = []  # {version, at_evaluation, config, change}
    self.previous: dict | None = None
    self.best_total: float | None = None
    self.evaluations: list[dict] = []  # one summary per call, logged at the end

  @property
  def checks(self):
    return self.config["checks"] if self.config else []

  @property
  def role_patterns(self):
    return self.config["roles"] if self.config else {}


async def set_checks_tool(session, state: DesignState, fields: dict) -> dict:
  try:
    cfg = json.loads(fields.get("config") or "")
  except ValueError as exc:
    return {"output": f"config is not valid JSON: {exc}. Nothing was installed."}
  problems = catalogue.validate(cfg)
  if problems:
    return {"output": "The configuration cannot be used, so it was NOT installed (the previous version stays):\n- " + "\n- ".join(problems[:15])}
  result = probe.run_probes(cfg)
  change = describe_change(state.config, cfg)
  state.config = cfg
  state.versions.append({"version": len(state.versions) + 1, "at_evaluation": len(state.evaluations), "config": cfg, "change": change})
  wrong = sum(1 for r in result["rows"] if not r["ok"])
  await session.log(f"pi: CHECKS v{len(state.versions)} " + json.dumps({"change": change, "wrong_probes": wrong, "config": cfg})[:20000])
  return {"output": f"Installed as version {len(state.versions)} ({'; '.join(change[:6])}).\n" + probe.render(result)
          + ("\nFix the WRONG rows and call set_checks again." if wrong else "")}


async def evaluate_tool(session, state: DesignState, fields: dict) -> dict:
  t0 = time.time()
  ifc, run = fields.get("ifc"), fields.get("run")
  if state.config is None:
    return {"output": "No checks are installed yet. Write them from the requirements with set_checks first, then evaluate."}
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
                            "objective_mm": (report.get("objective") or {}).get("total_mm"), "checks_version": state.versions[-1]["version"], "seconds": round(time.time() - t0, 1)})
  n = len(state.evaluations)
  recent = [x for x in state.versions if x["version"] > 1 and x["at_evaluation"] == n - 1]
  ver = f"CHECKS: version {state.versions[-1]['version']}" + (
      " (rewritten since the last evaluation: " + "; ".join(c for x in recent for c in x["change"])[:600] + ")" if recent else "")
  text = [head.rstrip(), ver, ("SCHEMA: could not be validated here (" + schema["unavailable"] + "); validate it yourself with ifcopenshell.validate"
                          if schema.get("unavailable") else ifc_items.render_validation(schema)), engine.render(report)]
  if state.best_total is not None and report.get("objective"):
    text.append(f"  best so far: {state.best_total:.0f} mm")
  if not schema["ok"]:
    text.append("NOT READY: the IFC schema errors above must be fixed too.")
  return {"output": "\n".join(x for x in text if x)}
