"""The optimizer: search loop on a toy problem, integer parameters, and the tool around it with an injected measure."""
import asyncio
import math
import unittest

import evaluator
import optimizer


def report(violations, objective):
  res = {"c": {"status": "fail" if violations else "pass", "violations": violations}}
  return {"results": res, "objective": {"total_mm": objective}, "warnings": []}


def toy(values):  # feasible when x >= 3; the objective falls as x falls; y has an optimum at 7
  x, y = values["x"], values["y"]
  return report(0 if x >= 3 else int(3 - x) + 1, 100 * x + 10 * abs(y - 7))


class Search(unittest.TestCase):
  PARAMS = {"x": {"min": 0, "max": 10, "init": 9}, "y": {"min": 0, "max": 10, "init": 1}}

  def test_finds_the_feasible_optimum(self):
    best, fit, trace = optimizer.es_search(self.PARAMS, toy, 80, None)
    self.assertEqual(fit[0], 0)
    self.assertLess(best["x"], 3.6)
    self.assertLess(abs(best["y"] - 7), 1.0)
    self.assertLess(fit[1], toy({"x": 9, "y": 1})["objective"]["total_mm"])

  def test_is_deterministic(self):
    a = optimizer.es_search(self.PARAMS, toy, 30, None)
    b = optimizer.es_search(self.PARAMS, toy, 30, None)
    self.assertEqual(a[0], b[0])

  def test_integers_stay_integers_and_in_bounds(self):
    seen = []
    def m(v):
      seen.append(dict(v))
      return toy({"x": v["k"], "y": 7})
    optimizer.es_search({"k": {"min": 0, "max": 6, "integer": True, "init": 5}}, m, 25, None)
    self.assertTrue(all(float(v["k"]).is_integer() and 0 <= v["k"] <= 6 for v in seen))

  def test_infeasible_ranks_below_feasible_and_failed_builds_below_all(self):
    self.assertLess(optimizer.fitness(report(0, 1e6), True), optimizer.fitness(report(1, 1), True))
    self.assertLess(optimizer.fitness(report(5, 5), True), optimizer.fitness(None, True))

  def test_maximise(self):
    best, fit, _ = optimizer.es_search({"x": {"min": 0, "max": 10, "init": 4}, "y": {"min": 7, "max": 7.0001}}, toy, 60, None, minimize=False)
    self.assertGreater(best["x"], 8)


class FakeSession:
  def __init__(self):
    self.logs, self.written = [], []

  async def log(self, t):
    self.logs.append(t)

  async def write_file(self, path, data, append=False):
    self.written.append((path, data))
    return len(data)


class Tool(unittest.TestCase):
  def run_tool(self, fields, state=None):
    st = state or evaluator.DesignState()
    if state is None:
      st.config = {"roles": {}, "checks": [{"id": "c", "type": "count", "role": "*"}], "requirements": []}
    async def measure(session, state_, ifc, build, pfile, values):
      return toy(values)
    s = FakeSession()
    return asyncio.new_event_loop().run_until_complete(optimizer.optimize_tool(s, st, fields, measure=measure)), s

  def test_reports_improvement_and_tells_the_agent_to_bake_in_the_values(self):
    out, s = self.run_tool({"build": "python b.py", "ifc": "o.ifc", "params_file": "/tmp/p.json", "evaluations": 40,
                            "params": {"x": {"min": 0, "max": 10, "init": 9}, "y": {"min": 0, "max": 10, "init": 1}}})
    text = out["output"]
    self.assertIn("OPTIMIZE:", text)
    self.assertIn("start: x=9, y=1: 0 violation(s), objective 960", text)
    self.assertIn("Bake these values", text)
    self.assertTrue(any("pi: OPTIMIZE" in l for l in s.logs))

  def test_refuses_without_checks_and_with_bad_params(self):
    out, _ = self.run_tool({"build": "b", "ifc": "o", "params_file": "p", "params": {"x": {"min": 0, "max": 1}}}, state=evaluator.DesignState())
    self.assertIn("No checks are installed", out["output"])
    out, _ = self.run_tool({"build": "b", "ifc": "o", "params_file": "p", "params": {"x": {"min": 5, "max": 1}}})
    self.assertIn("`params` must map", out["output"])
    out, _ = self.run_tool({"ifc": "o", "params": {"x": {"min": 0, "max": 1}}})
    self.assertIn("optimize needs `build`", out["output"])

  def test_reports_a_parameter_stuck_at_its_bound(self):
    out, _ = self.run_tool({"build": "b", "ifc": "o", "params_file": "p", "evaluations": 60,
                            "params": {"x": {"min": 3, "max": 10, "init": 9}, "y": {"min": 0, "max": 10, "init": 1}}})
    self.assertIn("at a bound of its range", out["output"])


try:
  import ifcopenshell  # noqa: F401
  HAVE_IFC = True
except ImportError:
  HAVE_IFC = False

BUILD_SCRIPT = """
import json, os, sys
import ifcopenshell, ifcopenshell.api
height = json.load(open(sys.argv[1]))["h"] if os.path.exists(sys.argv[1]) else 4000.0
f = ifcopenshell.api.run("project.create_file", version="IFC4")
proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS"})
ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="s")
ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
prof = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((0.0, 0.0))), 400.0, 400.0)
solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))), f.createIfcDirection((0.0, 0.0, 1.0)), float(height))
col = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcColumn", name="COL-0")
ifcopenshell.api.run("geometry.assign_representation", f, product=col, representation=f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid]))
ifcopenshell.api.run("spatial.assign_container", f, products=[col], relating_structure=site)
f.write(sys.argv[2])
"""


class RealSession:
  """A task container that is the local machine: real commands, real files."""
  def __init__(self):
    self.logs = []

  async def log(self, t):
    self.logs.append(t)

  def time_left(self):
    return None

  async def exec(self, command, timeout_sec=120):
    import subprocess
    p = subprocess.run(["bash", "-c", command], capture_output=True, text=True, timeout=timeout_sec)
    return {"exit_code": p.returncode, "output": p.stdout + p.stderr, "timed_out": False}

  async def read_result(self, path):
    import base64
    d = open(path, "rb").read()
    return {"ok": True, "content_b64": base64.b64encode(d).decode(), "size": len(d), "truncated": False}

  async def write_file(self, path, data, append=False):
    open(path, "wb").write(data)
    return len(data)


@unittest.skipUnless(HAVE_IFC, "needs ifcopenshell")
class EndToEnd(unittest.TestCase):
  def test_search_over_a_real_build_finds_the_feasible_minimum(self):
    import sys, tempfile, os
    d = tempfile.mkdtemp()
    open(os.path.join(d, "b.py"), "w").write(BUILD_SCRIPT)
    st = evaluator.DesignState()
    st.config = {"requirements": [], "roles": {"col": ["IfcColumn*"]},
                 "checks": [{"id": "top", "type": "z_range", "role": "col", "zmax": 3000}, {"id": "len", "type": "length_sum", "role": "col"}]}
    s = RealSession()
    fields = {"build": f"{sys.executable} {d}/b.py {d}/p.json {d}/o.ifc", "ifc": f"{d}/o.ifc", "params_file": f"{d}/p.json", "evaluations": 14,
              "params": {"h": {"min": 1000, "max": 6000, "init": 5000}}}
    out = asyncio.new_event_loop().run_until_complete(optimizer.optimize_tool(s, st, fields))["output"]
    self.assertIn("start: h=5000: 1 violation(s)", out)
    self.assertIn("0 violation(s)", out.split("best:")[1].split("\n")[0])
    import json
    h = json.load(open(os.path.join(d, "p.json")))["h"]
    self.assertTrue(1000 <= h <= 3000, h)


if __name__ == "__main__":
  unittest.main()
