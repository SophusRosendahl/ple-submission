"""Plants known faults in a tiny synthetic model and runs the check-builder's configuration on it.

For each check there is a clean probe (must pass) and a faulty probe (must fail). A check that cannot fail its own planted fault is
miswired (a role bound to a glob that matches nothing, a limit on the wrong side, a scope that leaves the pair out), and the
check-builder is told so before the designer ever sees it. The probe model is built from the configuration's own role globs, so
the synthetic kinds are exactly what the globs name; it cannot tell whether the globs match the designer's real kinds.
"""
from __future__ import annotations

import engine


def kinds_of(patterns: list[str]) -> list[str]:
  """A concrete kind a glob would match: the glob without its wildcards (IfcPipeSegment* -> IfcPipeSegment)."""
  return [p.replace("*", "").replace("?", "") or "IfcBuildingElementProxy" for p in patterns]


def _box(i, kind, group, x, y, z, dx=100.0, dy=100.0, dz=100.0):
  return {"id": i, "kind": kind, "group": group, "aabb": [x, y, z, x + dx, y + dy, z + dz]}


def _role_kind(cfg, role):
  pats = cfg["roles"].get(role)
  if not pats:
    return None, None
  k = kinds_of(pats)
  return k[0], {role: [k[0]]}


def probes_for(cfg: dict, c: dict):
  """[(label, items, expect_fail)] for one check, or [] when the check type has no generic probe."""
  roles = {r: [kinds_of(p)[0]] for r, p in cfg["roles"].items() if p}
  t = c["type"]
  rk = lambda r: roles.get(r, ["IfcBuildingElementProxy"])[0]
  if t == "no_overlap":
    sel = c.get("roles") or ["*"]
    names = list(roles) if sel == ["*"] else [r for r in sel if r in roles]
    kinds = sorted({rk(r) for r in names}) or ["IfcBuildingElementProxy"]
    k = kinds[0]
    return [("two separate items", [_box("a", k, "G", 0, 0, 0), _box("b", k, "G", 1000, 0, 0)], False),
            ("two items overlapping 50 mm", [_box("a", k, "G", 0, 0, 0), _box("b", k, "G", 50, 0, 0)], True)]
  if t == "min_clearance":
    need = float(c["min"])
    a, b = rk(c["a"]), rk(c["b"])
    ia = lambda d: [_box("a", a, "G", 0, 0, 0), _box("b", b, "G", 100 + d, 0, 0)]
    return [("gap of twice the minimum", ia(2 * need), False), ("gap of half the minimum", ia(need / 2), True)]
  if t == "z_range":
    k = rk(c["role"])
    zmin, zmax = c.get("zmin"), c.get("zmax")
    out = []
    lo = float(zmin) if zmin is not None else 0.0
    hi = float(zmax) if zmax is not None else lo + 1000.0
    mid = (lo + hi) / 2
    out.append(("item inside the band", [_box("a", k, "G", 0, 0, mid - 5, dz=10.0)], False))
    if zmax is not None:
      out.append(("item 100 mm above the band", [_box("a", k, "G", 0, 0, hi + 100 - 10, dz=10.0 + 10.0)], True))
    if zmin is not None:
      out.append(("item 100 mm below the band", [_box("a", k, "G", 0, 0, lo - 110, dz=10.0)], True))
    return out
  if t == "nearest_within":
    need = float(c["max"])
    f, o = rk(c["from"]), rk(c["to"])
    return [("target within the limit", [_box("f", f, "G", 0, 0, 0), _box("t", o, "G", 100 + need / 2, 0, 0)], False),
            ("target twice the limit away", [_box("f", f, "G", 0, 0, 0), _box("t", o, "G", 100 + 2 * need, 0, 0)], True)]
  if t == "connected":
    k = rk(c["role"])
    return [("two touching segments", [_box("a", k, "G", 0, 0, 0), _box("b", k, "G", 100, 0, 0)], False),
            ("two segments 500 mm apart", [_box("a", k, "G", 0, 0, 0), _box("b", k, "G", 600, 0, 0)], True)]
  if t == "coverage_along":
    ln, by = rk(c["lines"]), rk(c["by"])
    long = _box("line", ln, "G", 0, 0, 0, dx=3000.0)
    return [("line fully served", [long, _box("s", by, "G", 0, 0, 0, dx=3000.0)], False),
            ("line served over a fifth", [long, _box("s", by, "G", 0, 0, 0, dx=600.0)], True)]
  return []


def run_probes(cfg: dict) -> dict:
  """Returns {"rows": [{check, probe, expected, got, ok}], "untested": [check ids]}."""
  rows, untested = [], []
  roles_all = {r: [kinds_of(p)[0]] for r, p in cfg["roles"].items() if p}
  for c in cfg["checks"]:
    ps = probes_for(cfg, c)
    if not ps:
      untested.append(f"{c['id']} ({c['type']})")
      continue
    for label, items, expect_fail in ps:
      try:
        res = engine.evaluate(items, [c], roles_all, self_test=False)["results"][c["id"]]
        got = res["status"]
        detail = res["offenders"][0] if res["offenders"] else ""
      except engine.EngineError as exc:
        got, detail = "error", str(exc)
      ok = got == ("fail" if expect_fail else "pass")
      rows.append({"check": c["id"], "probe": label, "expected": "fail" if expect_fail else "pass", "got": got, "ok": ok, "detail": detail})
  return {"rows": rows, "untested": untested}


def render(result: dict) -> str:
  rows = result["rows"]
  bad = [r for r in rows if not r["ok"]]
  lines = [f"PROBES: {len(rows) - len(bad)} of {len(rows)} behaved as planted"]
  for r in rows:
    lines.append(f"  [{'ok' if r['ok'] else 'WRONG'}] {r['check']}: {r['probe']}: expected {r['expected']}, got {r['got']}")
    if r["ok"] and r["expected"] == "fail" and r["detail"]:
      lines.append(f"        the designer would read: {r['detail']}")
    if not r["ok"] and r["detail"]:
      lines.append(f"        {r['detail']}")
  if result["untested"]:
    lines.append("  not probed (no generic probe): " + ", ".join(result["untested"]) + " -- test custom code yourself by reasoning through the helpers")
  return "\n".join(lines)
