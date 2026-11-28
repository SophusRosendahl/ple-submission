"""The evaluate tool end to end on real IFC files, with a fake task container (needs ifcopenshell)."""
import asyncio
import base64
import json
import os
import unittest

try:
  import ifcopenshell  # noqa: F401
  HAVE = True
except ImportError:
  HAVE = False

import catalogue
import evaluator

IFC_OK, IFC_BAD = "/tmp/ifcruns/run-028.ifc", "/tmp/ifcruns/run-030.ifc"


class FakeSession:
  def __init__(self, files, exit_code=0):
    self.files, self.exit_code, self.logs = files, exit_code, []

  async def exec(self, command, timeout_sec=120):
    return {"exit_code": self.exit_code, "output": "built it\n" if not self.exit_code else "Traceback: boom", "timed_out": False}

  async def read_result(self, path):
    if path not in self.files:
      return {"ok": False, "error": "no such file"}
    d = open(self.files[path], "rb").read()
    return {"ok": True, "content_b64": base64.b64encode(d).decode(), "size": len(d), "truncated": False}

  async def log(self, text):
    self.logs.append(text)


CHECKS = [{"id": "C1", "type": "no_overlap", "title": "no clash", "roles": ["*"]},
          {"id": "C2", "type": "z_range", "title": "pipes under 2.4 m", "role": "pipe", "zmax": 2400},
          {"id": "C3", "type": "z_range", "title": "typo role", "role": "pipes", "zmax": 2400}]
PATTERNS = {"pipe": ["IfcPipeSegment*"]}


def state():
  st = evaluator.DesignState()
  st.config = {"requirements": [], "roles": dict(PATTERNS), "checks": [dict(c) for c in CHECKS], "unchecked": []}
  st.versions = [{"version": 1, "at_evaluation": 0, "config": st.config, "change": ["first version"]}]
  return st


def run(coro):
  return asyncio.new_event_loop().run_until_complete(coro)


@unittest.skipUnless(HAVE and os.path.exists(IFC_OK), "needs ifcopenshell and the sample IFC files")
class Evaluate(unittest.TestCase):
  def test_valid_file_gets_a_report_with_failures_located(self):
    s, st = FakeSession({"/app/m.ifc": IFC_OK}), state()
    out = run(evaluator.evaluate_tool(s, st, {"ifc": "/app/m.ifc", "run": "python solution.py"}))["output"]
    self.assertIn("BUILD: `python solution.py` exited with 0", out)
    self.assertIn("SCHEMA: valid", out)
    self.assertIn("EVALUATION:", out)
    self.assertIn("role 'pipes' is bound to no kind", out)  # a typo is an error, not a pass
    self.assertEqual(len(st.evaluations), 1)

  def test_invalid_file_gets_the_schema_message_first(self):
    out = run(evaluator.evaluate_tool(FakeSession({"/app/m.ifc": IFC_BAD}), state(), {"ifc": "/app/m.ifc"}))["output"]
    self.assertIn("is assigned to", out)
    self.assertIn("NOT READY", out)

  def test_build_failure_stops_before_evaluation(self):
    out = run(evaluator.evaluate_tool(FakeSession({}, exit_code=1), state(), {"ifc": "/app/m.ifc", "run": "python solution.py"}))["output"]
    self.assertIn("The build failed", out)
    self.assertNotIn("EVALUATION", out)

  def test_missing_file_is_explained(self):
    out = run(evaluator.evaluate_tool(FakeSession({}), state(), {"ifc": "/app/none.ifc"}))["output"]
    self.assertIn("Could not read /app/none.ifc", out)

  def test_evaluate_without_checks_says_so(self):
    out = run(evaluator.evaluate_tool(FakeSession({"/app/m.ifc": IFC_OK}), evaluator.DesignState(), {"ifc": "/app/m.ifc"}))["output"]
    self.assertIn("No checks are installed yet", out)

  def test_set_checks_installs_versions_and_evaluation_shows_the_rewrite(self):
    s, st = FakeSession({"/app/m.ifc": IFC_OK}), evaluator.DesignState()
    cfg = {"requirements": [], "roles": {"pipe": ["IfcPipeSegment*"]}, "checks": [{"id": "Z", "type": "z_range", "role": "pipe", "zmax": 2400}]}
    out = run(evaluator.set_checks_tool(s, st, {"config": json.dumps(cfg)}))["output"]
    self.assertIn("Installed as version 1", out)
    run(evaluator.evaluate_tool(s, st, {"ifc": "/app/m.ifc"}))
    cfg["checks"][0]["zmax"] = 9000
    run(evaluator.set_checks_tool(s, st, {"config": json.dumps(cfg)}))
    out = run(evaluator.evaluate_tool(s, st, {"ifc": "/app/m.ifc"}))["output"]
    self.assertIn("CHECKS: version 2 (rewritten since the last evaluation: edited Z: changed zmax", out)

  def test_an_invalid_config_is_refused_and_the_old_version_stays(self):
    s, st = FakeSession({}), state()
    out = run(evaluator.set_checks_tool(s, st, {"config": json.dumps({"roles": {}, "checks": [{"id": "a", "type": "z_range", "role": "nope"}]})}))["output"]
    self.assertIn("NOT installed", out)
    self.assertEqual(len(st.versions), 1)

  def test_objective_tracks_best_so_far(self):
    st = state()
    st.config["checks"] = [{"id": "L", "type": "length_sum", "role": "pipe"}]
    out = run(evaluator.evaluate_tool(FakeSession({"/app/m.ifc": IFC_OK}), st, {"ifc": "/app/m.ifc"}))["output"]
    self.assertIn("OBJECTIVE", out)
    self.assertIsNotNone(st.best_total)


class Builder(unittest.TestCase):
  def test_roundtrip_validation(self):
    cfg = {"requirements": [], "roles": {"p": ["IfcPipe*"]}, "checks": [{"id": "a", "type": "z_range", "role": "p", "zmax": 1}]}
    self.assertEqual(catalogue.validate(cfg), [])
    self.assertTrue(catalogue.validate({"roles": {}, "checks": [{"id": "a", "type": "custom", "code": "def check(:"}]}))
    self.assertTrue(catalogue.validate(None))


class Probes(unittest.TestCase):
  CFG = {"roles": {"pipe": ["IfcPipeSegment*"], "rack": ["IfcCableCarrier*"]},
         "checks": [{"id": "b", "type": "z_range", "role": "pipe", "zmax": 2400},
                    {"id": "c", "type": "min_clearance", "a": "pipe", "b": "rack", "min": 300},
                    {"id": "e", "type": "connected", "role": "pipe"}]}

  def test_a_wired_config_passes_every_probe(self):
    import probe
    r = probe.run_probes(self.CFG)
    self.assertTrue(r["rows"] and all(x["ok"] for x in r["rows"]), probe.render(r))

  def test_a_miswired_check_is_caught(self):
    import probe
    cfg = {"roles": {"pipe": ["IfcPipeSegment*"]}, "checks": [{"id": "z", "type": "z_range", "role": "pipes", "zmax": 2400}]}
    r = probe.run_probes(cfg)
    self.assertTrue(any(not x["ok"] for x in r["rows"]))


class CustomProbe(unittest.TestCase):
  def test_the_run047_bug_is_caught_by_the_probe(self):
    import probe
    bad = "def check(items, roles, helpers):\n  v = []\n  for m in helpers['select'](items, roles, 'pipe'):\n    z = m['aabb'][2]\n  return {'violations': v}\n"
    cfg = {"roles": {"pipe": ["IfcPipeSegment*"]}, "checks": [{"id": "h", "type": "custom", "code": bad}]}
    rows = probe.run_probes(cfg)["rows"]
    self.assertFalse(rows[0]["ok"])
    self.assertIn("at line 4", rows[0]["detail"])

  def test_a_working_custom_check_passes_the_probe(self):
    import probe
    good = "def check(items, roles, helpers):\n  return {'violations': [i['id'] for i in helpers['items_of'](items, roles, 'pipe') if i['aabb'][5] > 5]}\n"
    cfg = {"roles": {"pipe": ["IfcPipeSegment*"]}, "checks": [{"id": "h", "type": "custom", "code": good}]}
    self.assertTrue(probe.run_probes(cfg)["rows"][0]["ok"])


if __name__ == "__main__":
  unittest.main()
