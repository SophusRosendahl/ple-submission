"""The agent's optimize tool: a derivative-free search over the design parameters of its own build script.

The agent makes the design choices that matter (header positions, elevations, offsets) parameters its script reads from a JSON file
(defaults baked into the script), and calls optimize with their bounds. Each trial writes a candidate parameter file, rebuilds, reads
the IFC, and runs the installed checks without the self-test or the schema validator (kept for the final report). A trial is better
when it has fewer check violations, then a better objective. The search is a (1+1) evolution strategy with a 1/5-success step rule and
a fixed seed: no model calls are spent inside the loop, so one tool call explores dozens of designs.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import random
import tempfile
import time
import os

import engine
import evaluator
import ifc_items

MAX_EVALS = 80
DEFAULT_EVALS = 30
DEFAULT_SECONDS = 600
RESERVE_SECONDS = 150  # always leave this much of the task's time for the agent to finish


def fitness(report: dict | None, minimize: bool) -> tuple[float, float]:
  """(violations, objective) to minimise; a trial that did not produce a model is (inf, inf)."""
  if report is None:
    return (math.inf, math.inf)
  bad = sum(r["violations"] if r["status"] == "fail" else 1000 for r in report["results"].values() if r["status"] in ("fail", "error"))
  obj = (report.get("objective") or {}).get("total_mm", 0.0)
  return (float(bad), obj if minimize else -obj)


def clip(spec: dict, value: float) -> float:
  v = min(max(float(value), float(spec["min"])), float(spec["max"]))
  return float(round(v)) if spec.get("integer") else v


def es_search(params: dict, measure, evaluations: int, deadline: float | None, minimize: bool = True, seed: int = 0):
  """Pure search loop. `measure(values) -> report or None`. Returns (best_values, best_fit, trace)."""
  rng = random.Random(seed)
  names = sorted(params)
  cur = {n: clip(params[n], params[n].get("init", (float(params[n]["min"]) + float(params[n]["max"])) / 2)) for n in names}
  cur_fit = fitness(measure(cur), minimize)
  trace = [{"n": 1, "values": dict(cur), "fit": cur_fit, "accepted": True, "note": "start"}]
  sigma = {n: 0.15 for n in names}  # fraction of the parameter's range
  for k in range(2, evaluations + 1):
    if deadline is not None and time.time() > deadline:
      trace.append({"n": k, "note": "stopped: time limit"})
      break
    cand = dict(cur)
    pick = rng.sample(names, rng.randint(1, max(1, min(3, len(names)))))
    for n in pick:
      span = float(params[n]["max"]) - float(params[n]["min"])
      cand[n] = clip(params[n], cur[n] + rng.gauss(0.0, sigma[n] * span))
    if cand == cur:
      continue
    fit = fitness(measure(cand), minimize)
    ok = fit < cur_fit
    for n in pick:
      sigma[n] = min(0.5, sigma[n] * 1.5) if ok else max(0.01, sigma[n] * 0.85)
    trace.append({"n": k, "values": {n: cand[n] for n in pick}, "fit": fit, "accepted": ok})
    if ok:
      cur, cur_fit = cand, fit
  return cur, cur_fit, trace


async def measure_once(session, state, ifc: str, build: str, params_file: str, values: dict) -> dict | None:
  """Write the candidate parameters, rebuild, read the IFC and run the installed checks. None if no model came out."""
  await session.write_file(params_file, json.dumps(values).encode())
  res = await session.exec(build, timeout_sec=600)
  if res.get("exit_code") != 0:
    state.trial_error = f"the build exited with {res.get('exit_code')}: " + (res.get("output") or "")[-600:]
    return None
  raw = await session.read_result(ifc)
  if not raw.get("ok", True) or raw.get("truncated"):
    state.trial_error = f"could not read {ifc}: {raw.get('error') or 'file too large'}"
    return None
  with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
    f.write(base64.b64decode(raw.get("content_b64") or ""))
    path = f.name
  try:
    items = await asyncio.to_thread(ifc_items.items_from_ifc, path)
  except Exception as exc:
    state.trial_error = f"{ifc} could not be read as IFC: {type(exc).__name__}: {str(exc)[:200]}"
    return None
  finally:
    os.unlink(path)
  if not items:
    state.trial_error = f"{ifc} has no elements with a shape"
    return None
  roles = evaluator.resolve_roles(items, state.role_patterns)
  return await asyncio.to_thread(engine.evaluate, items, state.checks, roles, None, False)


def describe(v: dict) -> str:
  return ", ".join(f"{k}={v[k]:g}" for k in sorted(v))


async def optimize_tool(session, state, fields: dict, measure=measure_once) -> dict:
  if state.config is None:
    return {"output": "No checks are installed yet: optimize judges designs with your checks. Call set_checks first."}
  build, ifc, pfile, params = fields.get("build"), fields.get("ifc"), fields.get("params_file"), fields.get("params")
  if not (isinstance(build, str) and build and isinstance(ifc, str) and ifc and isinstance(pfile, str) and pfile):
    return {"output": "optimize needs `build` (the command that builds the IFC from the parameter file), `ifc` (its output path) and `params_file` (where candidate values are written as one JSON object)."}
  if not isinstance(params, dict) or not params or not all(isinstance(s, dict) and "min" in s and "max" in s and float(s["min"]) < float(s["max"]) for s in params.values()):
    return {"output": "`params` must map each parameter name to {min, max} (min below max), optionally init and integer."}
  minimize = bool(fields.get("minimize", True))
  evals = max(2, min(int(fields.get("evaluations") or DEFAULT_EVALS), MAX_EVALS))
  seconds = min(float(fields.get("seconds") or DEFAULT_SECONDS), DEFAULT_SECONDS * 3)
  left = session.time_left() if hasattr(session, "time_left") else None
  if left is not None:
    seconds = min(seconds, max(0.0, left - RESERVE_SECONDS))
  if seconds < 30:
    return {"output": "Too little task time is left to optimize; finish with the design you have."}
  deadline = time.time() + seconds
  t0 = time.time()
  loop = asyncio.get_running_loop()
  cache: dict[str, dict | None] = {}

  async def run_trial(values):
    key = json.dumps(values, sort_keys=True)
    if key not in cache:
      cache[key] = await measure(session, state, ifc, build, pfile, values)
    return cache[key]

  # es_search is synchronous; drive it by running each trial on this loop through a small bridge
  def sync_measure(values):
    return asyncio.run_coroutine_threadsafe(run_trial(values), loop).result()

  best, fit, trace = await asyncio.to_thread(es_search, params, sync_measure, evals, deadline, minimize)
  final = await measure(session, state, ifc, build, pfile, best)  # leave the best design built and its parameters in place
  first = trace[0]["fit"]
  lines = [f"OPTIMIZE: {len([t for t in trace if 'fit' in t])} designs tried in {time.time() - t0:.0f} s, no model calls spent inside the search.",
           f"  start: {describe(trace[0]['values'])}: {int(first[0])} violation(s), objective {abs(first[1]):.0f}" if first[0] != math.inf else
           "  start: the starting design produced no model: " + str(getattr(state, "trial_error", "unknown reason")) + "\n  Fix the build, then call optimize again.",
           f"  best:  {describe(best)}: {int(fit[0]) if fit[0] != math.inf else 'no model'} violation(s), objective {abs(fit[1]):.0f}"]
  if first[0] != math.inf and fit[0] != math.inf:
    if fit[0] < first[0]:
      lines.append(f"  violations went from {int(first[0])} to {int(fit[0])}")
    if fit[0] == first[0] and first[1] != 0:
      lines.append(f"  objective changed by {abs(fit[1]) - abs(first[1]):+.0f} ({(abs(fit[1]) - abs(first[1])) / abs(first[1]) * 100:+.1f}%)")
  for t in trace:
    if t.get("accepted") and t["n"] > 1:
      lines.append(f"  trial {t['n']}: {int(t['fit'][0])} violation(s), objective {abs(t['fit'][1]):.0f} after changing {describe(t['values'])}")
  edge = [n for n in sorted(params) if best[n] in (clip(params[n], params[n]["min"]), clip(params[n], params[n]["max"]))]
  if edge:
    lines.append("  at a bound of its range (widen it if the design allows): " + ", ".join(f"{n}={best[n]:g}" for n in edge))
  if any("stopped" in str(t.get("note", "")) for t in trace):
    lines.append("  stopped at the time limit")
  lines.append(f"The best parameters are written to {pfile} and the IFC at {ifc} is built from them. Bake these values into your script's defaults so the "
               "delivered script reproduces this design without the file, then call evaluate on the final build.")
  if final is not None and final.get("warnings"):
    lines.append("  scope warnings in the best design: " + "; ".join(final["warnings"][:3])[:400])
  out = "\n".join(lines)
  await session.log("pi: OPTIMIZE " + json.dumps({"best": best, "fit": list(fit), "start": list(first), "trials": len([t for t in trace if 'fit' in t]),
                                                  "seconds": round(time.time() - t0)}))
  await evaluator.log_result(session, "optimize", len(state.evaluations), out)
  return {"output": out}
