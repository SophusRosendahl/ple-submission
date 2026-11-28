"""Unit tests of the evaluation engine: tolerances, exclusions, the self-test, every library check, the custom sandbox, speed."""
import random
import time
import unittest

import engine as E


def box(i, kind, group, x0, y0, z0, x1, y1, z1):
  return {"id": i, "kind": kind, "group": group, "aabb": [x0, y0, z0, x1, y1, z1]}


ROLES = {"pipe": ["pipe-seg"], "rack": ["rack"], "solid": ["pipe-seg", "rack", "col"]}


def run(items, checks, roles=ROLES, self_test=False):
  return E.evaluate(items, checks, roles, self_test=self_test)


class Overlap(unittest.TestCase):
  def test_tolerance_edge(self):
    for depth, expect in ((1.9, 0), (2.0, 0), (2.1, 1), (0.0, 0), (-5.0, 0)):
      items = [box("a", "rack", "", 0, 0, 0, 100, 100, 100), box("b", "rack", "", 100 - depth, 0, 0, 200, 100, 100)]
      r = run(items, [{"id": "c", "type": "no_overlap"}])["results"]["c"]
      self.assertEqual(r["violations"], expect, f"depth {depth}")

  def test_overlap_on_one_axis_only_is_no_clash(self):
    items = [box("a", "rack", "", 0, 0, 0, 100, 100, 100), box("b", "rack", "", 50, 200, 0, 150, 300, 100)]
    self.assertEqual(run(items, [{"id": "c", "type": "no_overlap"}])["results"]["c"]["violations"], 0)

  def test_identical_boxes_overlap(self):
    items = [box("a", "rack", "", 0, 0, 0, 100, 100, 100), box("b", "rack", "", 0, 0, 0, 100, 100, 100)]
    self.assertEqual(run(items, [{"id": "c", "type": "no_overlap"}])["results"]["c"]["violations"], 1)

  def test_every_unordered_pair_is_examined_once(self):
    items = [box(str(i), "rack", "", i * 1000, 0, 0, i * 1000 + 10, 10, 10) for i in range(6)]
    self.assertEqual(run(items, [{"id": "c", "type": "no_overlap"}])["results"]["c"]["examined"], 15)

  def test_two_roles_with_shared_kinds_do_not_double_count(self):
    items = [box("a", "rack", "", 0, 0, 0, 100, 100, 100), box("b", "col", "", 50, 50, 50, 150, 150, 150)]
    r = run(items, [{"id": "c", "type": "no_overlap", "roles": ["solid", "rack"]}])["results"]["c"]
    self.assertEqual((r["examined"], r["violations"]), (1, 1))

  def test_empty_scope(self):
    items = [box("a", "rack", "", 0, 0, 0, 1, 1, 1)]
    r = run(items, [{"id": "c", "type": "no_overlap", "roles": ["pipe"]}], roles={"pipe": ["nothing"]})["results"]["c"]
    self.assertEqual((r["examined"], r["violations"]), (0, 0))


class JointsAndExclusions(unittest.TestCase):
  """The failure the whole design is about: pieces of one run that overlap at a joint."""

  def joint(self, gap=-170):
    trunk = box("trunk", "pipe-seg", "CHW", 900 - 85, 0, 0, 900 + 85, 5000, 170)
    branch = box("branch", "pipe-seg", "CHW", 900 + gap + 85 - 85 + 85, 2000 - 85, 0, 3000, 2000 + 85, 170)
    return [trunk, branch]

  def test_strict_default_reports_the_joint(self):
    r = run(self.joint(), [{"id": "c", "type": "no_overlap"}])["results"]["c"]
    self.assertEqual(r["violations"], 1)

  def test_butt_joint_passes(self):
    trunk = box("trunk", "pipe-seg", "CHW", 815, 0, 0, 985, 5000, 170)
    branch = box("branch", "pipe-seg", "CHW", 985, 1915, 0, 3000, 2085, 170)
    r = run([trunk, branch], [{"id": "c", "type": "no_overlap"}])["results"]["c"]
    self.assertEqual(r["violations"], 0)

  def test_exclusion_hides_the_failure_but_the_report_shows_it(self):
    cfg = [{"id": "c", "type": "no_overlap", "exclude": [{"same_group": True}]}]
    rep = run(self.joint(), cfg)
    r = rep["results"]["c"]
    self.assertEqual((r["status"], r["violations"], r["excluded"], r["shadow_overlaps"]), ("pass", 0, 1, 1))
    text = E.render(rep)
    self.assertIn("INSIDE THE EXCLUDED PAIRS", text)
    self.assertIn("same group", text)

  def test_self_test_names_the_exposure(self):
    cfg = [{"id": "c", "type": "no_overlap", "exclude": [{"same_group": True}]}]
    rep = run(self.joint() + [box("r", "rack", "", 5000, 0, 0, 5600, 1200, 2000), box("r2", "rack", "", 7000, 0, 0, 7600, 1200, 2000)], cfg, self_test=True)
    missed = {(m["kinds"], m["reason"]) for m in rep["self_test"]["missed"]}
    self.assertIn(("pipe-seg x pipe-seg", "excluded: same group"), missed)
    self.assertFalse(rep["ready"])

  def test_group_exclusion_ignores_items_without_a_group(self):
    items = [box("a", "rack", "", 0, 0, 0, 100, 100, 100), box("b", "rack", "", 10, 10, 10, 110, 110, 110)]
    r = run(items, [{"id": "c", "type": "no_overlap", "exclude": [{"same_group": True}]}])["results"]["c"]
    self.assertEqual(r["violations"], 1)

  def test_roles_exclusion(self):
    items = [box("p", "pipe-seg", "A", 0, 0, 0, 100, 100, 100), box("r", "rack", "", 10, 10, 10, 110, 110, 110)]
    r = run(items, [{"id": "c", "type": "no_overlap", "exclude": [{"roles": ["pipe", "rack"]}]}])["results"]["c"]
    self.assertEqual((r["violations"], r["excluded"]), (0, 1))


class Diagnosis(unittest.TestCase):
  """The report has to say what to change, with numbers."""

  def diag(self, a, b):
    d = E.overlap_depths(E.boxes([a, b], [0]), E.boxes([a, b], [1]))[0, 0]
    return E.diagnose_overlap(a, b, d)

  def test_branch_end_into_a_trunk_says_shorten_by_half_the_width(self):
    trunk = box("TRUNK", "tray", "CT", 815, 0, 0, 985, 5000, 127)     # 170 wide, long along y
    branch = box("BRANCH", "tray", "CT", 900, 1915, 0, 3000, 2085, 127)  # starts at the trunk's centre line
    r = self.diag(trunk, branch)
    self.assertEqual((r["relation"], r["mover_id"], r["from"], r["to"]), ("end into side", "BRANCH", 900.0, 985.0))
    self.assertIn("shorten its min end by 85 mm", r["fix"])

  def test_elbow_where_both_ends_run_to_the_centre_line(self):
    a = box("A", "pipe", "CHW", 0, 916, 0, 1000, 1084, 168)     # along x, ends at x=1000 (the centre of the corner)
    b = box("B", "pipe", "CHW", 916, 0, 0, 1084, 1000, 168)     # along y, ends at y=1000
    r = self.diag(a, b)
    self.assertEqual(r["relation"], "corner")
    self.assertAlmostEqual(r["depth"], 84.0)
    self.assertIn("touch face to face", r["fix"])

  def test_stacked_pieces_overlapping_by_a_thickness(self):
    rack = box("RACK", "rack", "", 0, 0, 0, 600, 1200, 2000)
    plate = box("PLATE", "plate", "", 0, 0, 1950, 600, 1200, 2050)
    r = self.diag(rack, plate)
    self.assertEqual(r["relation"], "partial")
    self.assertIn("overlap along z between 1950 and 2000", r["fix"])
    self.assertIn("from 2000 down to 1950", r["fix"])

  def test_roof_end_running_into_a_door_says_shorten_the_roof(self):
    roof = box("ROOF", "roof", "", 0, 0, 2000, 2400, 1200, 2055.5)
    door = box("DOOR", "door", "", 2340, 0, 0, 2400, 1200, 2055.5)
    r = self.diag(roof, door)
    self.assertEqual((r["relation"], r["mover_id"]), ("end into side", "ROOF"))
    self.assertIn("shorten its max end by 60 mm", r["fix"])

  def test_same_cause_is_reported_once_with_a_count(self):
    items = []
    for i in range(5):
      y = 1000.0 * (i + 1)
      items.append(box(f"T{i}", "tray", "CT", 815, y - 85, 0, 985, y + 85, 127))
      items.append(box(f"B{i}", "tray", "CT", 900, y - 85, 0, 3000, y + 85, 127))
    # make the trunk long so each branch end is inside it
    items.append(box("TRUNK", "tray", "CT", 815, 0, 0, 985, 7000, 127))
    items = [it for it in items if not it["id"].startswith("T") or it["id"] == "TRUNK"]
    rep = run(items, [{"id": "c", "type": "no_overlap"}])["results"]["c"]
    self.assertEqual(rep["violations"], 5)
    self.assertEqual(len(rep["patterns"]), 1)
    self.assertIn("5 overlap(s) with one cause", rep["patterns"][0][0])


class SelfTestAgreesWithTheCheck(unittest.TestCase):
  """Property test: for random models and random configurations, the self-test's prediction for a pair of kinds is exactly what the
  real check does with two deeply overlapping items of those kinds."""

  def test_random(self):
    rng = random.Random(7)
    kinds = ["pipe-seg", "rack", "col"]
    for trial in range(60):
      items = []
      for n in range(9):
        k = rng.choice(kinds)
        x = n * 1000.0
        items.append(box(f"i{n}", k, rng.choice(["", "A", "B"]), x, 0, 0, x + 100, 100, 100))
      cfg = {"id": "c", "type": "no_overlap"}
      if rng.random() < 0.7:
        cfg["roles"] = rng.choice([["solid"], ["pipe", "rack"], ["rack"], ["pipe"], ["*"]])
      ex = []
      if rng.random() < 0.5:
        ex.append({"same_group": True})
      if rng.random() < 0.3:
        ex.append({"same_kind": True})
      if rng.random() < 0.3:
        ex.append({"roles": ["pipe", "rack"]})
      if ex:
        cfg["exclude"] = ex
      st = E.injected_fault_test(items, [cfg], ROLES)
      predicted_missed = {m["kinds"] for m in st["missed"]}
      by_kind = {}
      for it in items:
        by_kind.setdefault(it["kind"], []).append(it)
      ks = sorted(by_kind)
      for i, ka in enumerate(ks):
        for kb in ks[i:]:
          a = by_kind[ka][0]
          b = next((x for x in by_kind[kb] if x["id"] != a["id"]), None)
          if b is None:
            continue
          mutant_b = dict(b, aabb=list(a["aabb"]))  # deep overlap: same box as a
          mutant = [mutant_b if it["id"] == b["id"] else it for it in items]
          before = E.check_no_overlap(items, ROLES, cfg)["violations"]
          after = E.check_no_overlap(mutant, ROLES, cfg)["violations"]
          detected = after > before
          self.assertEqual(f"{ka} x {kb}" not in predicted_missed, detected, f"trial {trial} {ka} x {kb} cfg={cfg}")


class OtherChecks(unittest.TestCase):
  def test_z_range_headroom(self):
    items = [box("h1", "head", "", 0, 0, 1890, 50, 50, 1915), box("s1", "pipe-seg", "A", 0, 0, 2700, 100, 100, 2800)]
    r = run(items, [{"id": "z", "type": "z_range", "role": "*", "zmin": 2600}], roles={})["results"]["z"]
    self.assertEqual(r["violations"], 1)
    self.assertIn("h1", r["offenders"][0])

  def test_clearance_best_axis(self):
    tray = box("t", "tray", "", 0, 0, 0, 683, 5000, 127)
    for gap, expect in ((400, 0), (299, 1)):
      bus = box("b", "bus", "", 683 + gap, 100, 0, 683 + gap + 128, 4000, 147)
      r = run([tray, bus], [{"id": "c", "type": "min_clearance", "a": "t", "b": "b", "min": 300, "mode": "best_axis"}], roles={"t": ["tray"], "b": ["bus"]})["results"]["c"]
      self.assertEqual(r["violations"], expect, gap)

  def test_clearance_overlapping_boxes_fail(self):
    a, b = box("a", "x", "", 0, 0, 0, 100, 100, 100), box("b", "y", "", 50, 50, 50, 150, 150, 150)
    r = run([a, b], [{"id": "c", "type": "min_clearance", "a": "a", "b": "b", "min": 10}], roles={"a": ["x"], "b": ["y"]})["results"]["c"]
    self.assertEqual(r["violations"], 1)

  def test_nearest_within(self):
    units = [box("u1", "crah", "", 0, 0, 0, 600, 1200, 2000), box("u2", "crah", "", 10000, 0, 0, 10600, 1200, 2000)]
    pipe = [box("p", "pipe", "CHW", 0, 1500, 0, 5000, 1670, 170)]
    r = run(units + pipe, [{"id": "n", "type": "nearest_within", "from": "u", "to": "p", "max": 2500}], roles={"u": ["crah"], "p": ["pipe"]})["results"]["n"]
    self.assertEqual(r["violations"], 1)
    self.assertIn("u2", r["offenders"][0])

  def test_connected_and_reach(self):
    a = box("a", "seg", "S", 0, 0, 0, 1000, 100, 100)
    b = box("b", "seg", "S", 1000, 0, 0, 2000, 100, 100)
    c = box("c", "seg", "S", 2060, 0, 0, 3000, 100, 100)
    r = run([a, b], [{"id": "k", "type": "connected", "role": "s", "reach": {"point": [0, 50], "tol": 10}}], roles={"s": ["seg"]})["results"]["k"]
    self.assertEqual(r["status"], "pass")
    r = run([a, b, c], [{"id": "k", "type": "connected", "role": "s"}], roles={"s": ["seg"]})["results"]["k"]
    self.assertEqual(r["violations"], 1)
    r = run([a, b], [{"id": "k", "type": "connected", "role": "s", "reach": {"point": [-500, 50], "tol": 10}}], roles={"s": ["seg"]})["results"]["k"]
    self.assertEqual(r["status"], "fail")

  def test_coverage_along(self):
    row = box("row", "rack", "", 0, 0, 0, 10000, 1200, 2000)
    for run_x1, expect in ((9000, 0), (5000, 1)):
      svc = box("s", "seg", "TRAY", 0, 1500, 0, run_x1, 1600, 100)
      r = run([row, svc], [{"id": "c", "type": "coverage_along", "lines": "row", "by": "svc", "across": 2500, "min_fraction": 0.8}], roles={"row": ["rack"], "svc": ["seg"]})["results"]["c"]
      self.assertEqual(r["violations"], expect, run_x1)

  def test_count(self):
    items = [box(str(i), "rack", "", i * 10, 0, 0, i * 10 + 5, 5, 5) for i in range(4)]
    self.assertEqual(run(items, [{"id": "c", "type": "count", "role": "rack", "equals": 4}])["results"]["c"]["status"], "pass")
    self.assertEqual(run(items, [{"id": "c", "type": "count", "role": "rack", "equals": 5}])["results"]["c"]["status"], "fail")

  def test_length_sum_is_the_objective(self):
    items = [box("a", "seg", "S1", 0, 0, 0, 1000, 10, 10), box("b", "seg", "S2", 0, 0, 0, 10, 2000, 10)]
    rep = run(items, [{"id": "l", "type": "length_sum", "role": "s"}], roles={"s": ["seg"]})
    self.assertEqual(rep["objective"]["total_mm"], 3000.0)
    self.assertEqual(rep["objective"]["by_group_mm"], {"S1": 1000.0, "S2": 2000.0})


class Robustness(unittest.TestCase):
  def test_bad_items_are_refused_with_a_reason(self):
    for bad in ([], [{"id": "a", "kind": "k"}], [{"id": "a", "kind": "k", "aabb": [0, 0, 0, -1, 1, 1]}], [{"id": "a", "kind": "k", "aabb": [0, 0, 0, float("nan"), 1, 1]}],
                [box("a", "k", "", 0, 0, 0, 1, 1, 1), box("a", "k", "", 0, 0, 0, 1, 1, 1)]):
      with self.assertRaises(E.EngineError):
        E.load_items(bad)

  def test_bad_config_is_refused_with_a_reason(self):
    with self.assertRaises(E.EngineError):
      run([box("a", "k", "", 0, 0, 0, 1, 1, 1)], [{"id": "x", "type": "nonsense"}])
    with self.assertRaises(E.EngineError):
      run([box("a", "k", "", 0, 0, 0, 1, 1, 1)], [{"id": "x", "type": "min_clearance", "a": "q"}])

  def test_unbound_role_is_an_error_in_the_report_not_a_crash(self):
    rep = run([box("a", "k", "", 0, 0, 0, 1, 1, 1)], [{"id": "x", "type": "no_overlap", "roles": ["missing"]}], roles={})
    self.assertEqual(rep["results"]["x"]["status"], "error")
    self.assertIn("missing", rep["scope"]["unbound_roles"])

  def test_scope_facts_list_uncovered_kinds(self):
    items = [box("a", "rack", "", 0, 0, 0, 1, 1, 1), box("h", "head", "", 5, 5, 5, 6, 6, 6)]
    rep = run(items, [{"id": "z", "type": "z_range", "role": "r", "zmin": 0}], roles={"r": ["rack"]})
    self.assertEqual(rep["scope"]["uncovered_kinds"], ["head"])

  def test_custom_check_runs_and_is_sandboxed(self):
    items = [box("a", "rack", "", 0, 0, 0, 1, 1, 1)]
    ok = {"id": "u", "type": "custom", "code": "def check(items, roles, h):\n    return {'violations': ['x'] if len(items) > 0 else []}"}
    self.assertEqual(run(items, [ok])["results"]["u"]["status"], "fail")
    evil = {"id": "e", "type": "custom", "code": "def check(items, roles, h):\n    import os\n    return {'violations': []}"}
    self.assertEqual(run(items, [evil])["results"]["e"]["status"], "error")
    boom = {"id": "b", "type": "custom", "code": "def check(items, roles, h):\n    return 1/0"}
    self.assertEqual(run(items, [boom])["results"]["b"]["status"], "error")

  def test_deterministic(self):
    rng = random.Random(1)
    items = [box(str(i), rng.choice(["rack", "col"]), "", rng.random() * 500, rng.random() * 500, 0, rng.random() * 500 + 500, rng.random() * 500 + 500, 100) for i in range(60)]
    cfg = [{"id": "c", "type": "no_overlap"}]
    self.assertEqual(E.render(E.evaluate(items, cfg, ROLES)), E.render(E.evaluate(items, cfg, ROLES)))

  def test_speed_on_a_large_model(self):
    rng = random.Random(3)
    items = [box(str(i), rng.choice(["rack", "col", "pipe-seg"]), rng.choice(["A", "B"]), (i % 60) * 700.0, (i // 60) * 700.0, 0, (i % 60) * 700.0 + 600, (i // 60) * 700.0 + 600, 100) for i in range(2400)]
    t = time.time()
    E.evaluate(items, [{"id": "c", "type": "no_overlap", "exclude": [{"same_group": True}]}], ROLES)
    self.assertLess(time.time() - t, 15.0)


class Messages(unittest.TestCase):
  """The report says where, by how much, and what to do, for every library check."""

  def res(self, items, check):
    return run(items, [dict(check, id="c")])["results"]["c"]

  def test_clearance_gives_axis_gaps_and_the_move(self):
    items = [box("a", "pipe-seg", "", 0, 0, 0, 100, 100, 100), box("b", "rack", "", 150, 0, 0, 250, 100, 100)]
    r = self.res(items, {"type": "min_clearance", "a": "pipe", "b": "rack", "min": 200})
    self.assertIn("moving b by 150 mm along x away from a", r["offenders"][0])

  def test_z_range_groups_one_cause_and_names_what_is_in_the_way(self):
    items = [box(f"p{i}", "pipe-seg", "", i * 500, 0, 2000, i * 500 + 100, 100, 2400) for i in range(4)]
    items.append(box("roof", "col", "", 0, 0, 2350, 3000, 100, 2500))
    r = self.res(items, {"type": "z_range", "role": "pipe", "zmax": 2300})
    self.assertEqual(len(r["patterns"]), 1)
    self.assertIn("move all of them down by 100 mm", r["patterns"][0][0])
    self.assertIn("roof", r["offenders"][0])

  def test_nearest_within_gives_shortfall_and_direction(self):
    items = [box("h", "pipe-seg", "", 0, 0, 0, 10, 10, 10), box("r", "rack", "", 1000, 0, 0, 1100, 10, 10)]
    r = self.res(items, {"type": "nearest_within", "from": "pipe", "to": "rack", "max": 600})
    self.assertIn("990 mm away", r["offenders"][0])
    self.assertIn("390 mm too far", r["offenders"][0])
    self.assertIn("east", r["offenders"][0])

  def test_connected_names_the_gap_to_close(self):
    items = [box("a", "pipe-seg", "S", 0, 0, 0, 100, 10, 10), box("b", "pipe-seg", "S", 100, 0, 0, 200, 10, 10),
             box("c", "pipe-seg", "S", 440, 0, 0, 500, 10, 10)]
    r = self.res(items, {"type": "connected", "role": "pipe"})
    self.assertIn("c are cut off", r["offenders"][0])
    self.assertIn("240 mm away", r["offenders"][0])

  def test_coverage_names_the_unserved_interval(self):
    items = [box("line", "pipe-seg", "", 0, 0, 0, 3000, 100, 100), box("by", "rack", "", 0, 0, 0, 1000, 100, 100)]
    r = self.res(items, {"type": "coverage_along", "lines": "pipe", "by": "rack", "across": 50, "min_fraction": 0.9})
    self.assertIn("not served at x 1100 to 3100", r["offenders"][0])

  def test_a_check_that_selects_nothing_is_an_error_not_a_pass(self):
    items = [box("a", "col", "", 0, 0, 0, 10, 10, 10), box("b", "col", "", 100, 0, 0, 110, 10, 10)]
    r = self.res(items, {"type": "z_range", "role": "pipe", "zmax": 5})
    self.assertEqual(r["status"], "error")
    self.assertIn("examined 0 items", r["offenders"][0])

  def test_unbound_role_lists_the_kinds_present(self):
    r = self.res([box("a", "col", "", 0, 0, 0, 10, 10, 10)], {"type": "z_range", "role": "nonexistent", "zmax": 5})
    self.assertEqual(r["status"], "error")
    self.assertIn("Kinds in the model: col", r["offenders"][0])

  def test_custom_error_names_the_line(self):
    code = "def check(items, roles, helpers):\n  x = 1\n  return {'violations': [items[99]['id']]}\n"
    r = self.res([box("a", "col", "", 0, 0, 0, 10, 10, 10)], {"type": "custom", "code": code})
    self.assertEqual(r["status"], "error")
    self.assertIn("at line 3", r["offenders"][0])


if __name__ == "__main__":
  unittest.main()
