"""Evaluation engine for the structured workflow (rung 3): a library of checks over a model made of boxes.

The model is a list of items: {"id", "kind", "group", "aabb": [x0, y0, z0, x1, y1, z1]} in millimetres. A check is a plain
dict (data, not code); a role is a name bound to a set of kinds by the designer. The engine is deterministic, has no state
between evaluations, and writes its report from numbers it computed itself.

Strict by default: `no_overlap` examines every pair of the items its roles select. Leaving a group of pairs out is an
explicit `exclude` rule; the report then states how many pairs were examined and excluded, and measures the overlaps inside
the excluded group separately, so an exclusion can be seen and judged from numbers alone.
"""
from __future__ import annotations

import copy
import itertools
import math
from typing import Any

import numpy as np

CHECK_TYPES = ("no_overlap", "min_clearance", "z_range", "nearest_within", "connected", "coverage_along", "count",
               "length_sum", "custom")
TOP = 5  # offenders listed per check


class EngineError(ValueError):
  """A configuration or model the engine refuses, with the reason."""


# ---------------------------------------------------------------- model

def load_items(raw: list[dict]) -> list[dict]:
  """Validates and normalises the items (floats, ordered boxes)."""
  if not isinstance(raw, list) or not raw:
    raise EngineError("the model has no items")
  seen, out = set(), []
  for it in raw:
    for key in ("id", "kind", "aabb"):
      if key not in it:
        raise EngineError(f"item without '{key}': {str(it)[:80]}")
    if it["id"] in seen:
      raise EngineError(f"duplicate item id {it['id']}")
    seen.add(it["id"])
    b = [float(v) for v in it["aabb"]]
    if len(b) != 6 or any(math.isnan(v) or math.isinf(v) for v in b):
      raise EngineError(f"item {it['id']}: aabb must be six finite numbers")
    if b[3] < b[0] or b[4] < b[1] or b[5] < b[2]:
      raise EngineError(f"item {it['id']}: aabb has a maximum below its minimum: {b}")
    out.append({"id": str(it["id"]), "kind": str(it["kind"]), "group": str(it.get("group", "")), "aabb": b,
                "attrs": it.get("attrs", {})})
  return out


def select(items: list[dict], roles: dict[str, list[str]], role: str) -> list[int]:
  """Indices of the items a role selects ('*' selects all)."""
  if role == "*":
    return list(range(len(items)))
  if role not in roles:
    present = sorted({it["kind"] for it in items})
    raise EngineError(f"role '{role}' is bound to no kind. Kinds in the model: {', '.join(present[:25])}{' ...' if len(present) > 25 else ''}")
  kinds = set(roles[role])
  return [i for i, it in enumerate(items) if it["kind"] in kinds]


def boxes(items: list[dict], idx: list[int]) -> np.ndarray:
  return np.array([items[i]["aabb"] for i in idx], dtype=float).reshape(-1, 6)


def overlap_depths(a: np.ndarray, b: np.ndarray) -> np.ndarray:
  """For every pair (rows of a, rows of b): the overlap depth along x, y, z (negative = a gap). Shape (na, nb, 3)."""
  lo = np.maximum(a[:, None, 0:3], b[None, :, 0:3])
  hi = np.minimum(a[:, None, 3:6], b[None, :, 3:6])
  return hi - lo


def gaps(a: np.ndarray, b: np.ndarray) -> np.ndarray:
  """Separation along each axis (positive = a gap, negative = overlap). Shape (na, nb, 3)."""
  return -overlap_depths(a, b)


# ---------------------------------------------------------------- checks

def _scope_sets(items, roles, spec):
  rs = spec.get("roles", ["*"])
  if len(rs) not in (1, 2):
    raise EngineError(f"{spec['id']}: 'roles' must hold one or two role names")
  ia = select(items, roles, rs[0])
  ib = ia if len(rs) == 1 else select(items, roles, rs[1])
  return ia, ib


def pair_in_scope(p, q, spec, roles) -> bool:
  """Would the check look at the pair (p, q) at all? (the one definition used by the check and by the self-test)"""
  rs = spec.get("roles", ["*"])
  def has(item, r):
    return r == "*" or item["kind"] in set(roles.get(r, []))
  if len(rs) == 1:
    return has(p, rs[0]) and has(q, rs[0])
  return (has(p, rs[0]) and has(q, rs[1])) or (has(p, rs[1]) and has(q, rs[0]))


def exclusion_of(p, q, exclude, roles):
  """The label of the first exclusion rule that removes the pair from the count, or None."""
  for rule in exclude:
    if rule.get("same_group") and p["group"] == q["group"] and p["group"] != "":
      return "same group"
    if rule.get("same_kind") and p["kind"] == q["kind"]:
      return "same kind"
    if "roles" in rule:
      ra, rb = rule["roles"]
      ka, kb = set(roles.get(ra, [])), set(roles.get(rb, []))
      if (p["kind"] in ka and q["kind"] in kb) or (p["kind"] in kb and q["kind"] in ka):
        return f"roles {ra} / {rb}"
  return None


AX = "xyz"


def _sizes(b):
  return [b[3] - b[0], b[4] - b[1], b[5] - b[2]]


def _long_axis(b):
  sz = _sizes(b)
  k = int(np.argmax(sz))
  rest = sorted(sz)[:2]
  return k, (sz[k] / max(rest[1], 1e-9))


def diagnose_overlap(p, q, depth) -> dict:
  """Why two boxes overlap and the smallest change that separates them, in the units of the model.

  Relations: 'end into side' (an elongated piece whose end runs into the body of another, the classic joint made centre to
  centre), 'collinear' (two pieces along one line overlapping in length), 'crossing' (elongated pieces at an angle passing
  through each other), 'contained' (one inside the other), 'partial' (anything else).
  """
  a, b = p["aabb"], q["aabb"]
  d = [float(v) for v in depth]
  sa, sb = _sizes(a), _sizes(b)
  la, ra = _long_axis(a)
  lb, rb = _long_axis(b)

  def end_into_side(box, size, L, ratio, other):
    # elongated, only its end penetrates (depth along L is less than its length), cross-section inside the other's extent
    if ratio < 2.0 or d[L] >= size[L] - 1e-6:
      return None
    if any(d[k] < size[k] - 1e-6 for k in range(3) if k != L):
      return None
    mid_other = (other[L] + other[L + 3]) / 2
    end = "max" if (box[L] + box[L + 3]) / 2 < mid_other else "min"  # the end that points toward the other piece
    coord = box[L + 3] if end == "max" else box[L]
    new = coord - d[L] if end == "max" else coord + d[L]
    return {"relation": "end into side", "mover": box, "axis": AX[L], "end": end, "depth": d[L], "from": coord, "to": new}

  for item, box, size, L, ratio, other, other_item in ((p, a, sa, la, ra, b, q), (q, b, sb, lb, rb, a, p)):
    r = end_into_side(box, size, L, ratio, other)
    if r:
      who = item["id"]
      return {**r, "mover_id": who, "other_id": other_item["id"], "signature": ("end into side", AX[L], round(d[L])),
              "fix": f"end {who} at {AX[L]} = {r['to']:.0f} instead of {r['from']:.0f} (shorten its {r['end']} end by {d[L]:.0f} mm) so it butts against {other_item['id']} instead of entering it"}
  inside = lambda u, v: all(u[i] >= v[i] - 1e-6 and u[i + 3] <= v[i + 3] + 1e-6 for i in range(3))
  if inside(a, b) or inside(b, a):
    k = int(np.argmin(d))
    inner, outer = (p, q) if inside(a, b) else (q, p)
    return {"relation": "contained", "depth": min(d), "signature": ("contained",), "fix": f"{inner['id']} lies inside {outer['id']}: remove it or move it out"}
  # a corner: two elongated pieces at an angle, each running into the other (both ends meet at the centre lines)
  if ra >= 2.0 and rb >= 2.0 and la != lb and d[la] < sa[la] - 1e-6 and d[lb] < sb[lb] - 1e-6:
    mover, L, dep, box, other = (p, la, d[la], a, b) if d[la] <= d[lb] else (q, lb, d[lb], b, a)
    mid_other = (other[L] + other[L + 3]) / 2
    end = "max" if (box[L] + box[L + 3]) / 2 < mid_other else "min"
    coord = box[L + 3] if end == "max" else box[L]
    new = coord - dep if end == "max" else coord + dep
    return {"relation": "corner", "depth": dep, "signature": ("corner", AX[L], round(dep)),
            "fix": f"{p['id']} and {q['id']} meet at a corner and each runs into the other: end {mover['id']} at {AX[L]} = {new:.0f} instead of {coord:.0f} (shorten its {end} end by {dep:.0f} mm) so the two touch face to face"}
  if la == lb and ra >= 2.0 and rb >= 2.0 and d[la] > 0:
    return {"relation": "collinear", "depth": d[la], "signature": ("collinear", AX[la], round(d[la])),
            "fix": f"{p['id']} and {q['id']} run along {AX[la]} and overlap by {d[la]:.0f} mm in length: trim one of them by that amount"}
  if ra >= 2.0 and rb >= 2.0 and la != lb:
    k = int(np.argmin(d))
    return {"relation": "crossing", "depth": d[k], "signature": ("crossing", AX[k], round(d[k])),
            "fix": f"{p['id']} and {q['id']} pass through each other: separate them along {AX[k]} by at least {d[k]:.0f} mm (move one of them, for example to another elevation)"}
  k = int(np.argmin(d))
  lo = max(a[k], b[k])
  hi = min(a[k + 3], b[k + 3])
  below, above = (p, q) if (a[k] + a[k + 3]) <= (b[k] + b[k + 3]) else (q, p)
  bb, ab = (a, b) if below is p else (b, a)
  return {"relation": "partial", "depth": d[k], "signature": ("partial", AX[k], round(d[k])),
          "fix": f"{p['id']} and {q['id']} overlap along {AX[k]} between {lo:.0f} and {hi:.0f} ({d[k]:.0f} mm): "
                 f"either move the {AX[k]} maximum of {below['id']} from {bb[k + 3]:.0f} down to {lo:.0f}, or move the {AX[k]} minimum of {above['id']} from {ab[k]:.0f} up to {hi:.0f}"}


def cluster(pairs):
  """Group diagnosed overlaps that have the same cause, largest group first."""
  groups: dict = {}
  for p, q, diag in pairs:
    key = (p["kind"], q["kind"], p["group"], q["group"]) + tuple(diag["signature"])
    g = groups.setdefault(key, {"count": 0, "examples": [], "diag": diag, "kinds": (p["kind"], q["kind"]), "groups": (p["group"], q["group"])})
    g["count"] += 1
    if len(g["examples"]) < 3:
      g["examples"].append((p["id"], q["id"], diag))
  out = sorted(groups.values(), key=lambda g: -g["count"])
  return out


def pattern_text(g) -> list[str]:
  d = g["diag"]
  ka, kb = g["kinds"]
  ga, gb = g["groups"]
  who = f"{ka}" if ka == kb else f"{ka} and {kb}"
  grp = f" of group {ga}" if ga and ga == gb else (f" (groups {ga} and {gb})" if ga or gb else "")
  head = f"{g['count']} overlap(s) with one cause: {who}{grp}, relation '{d['relation']}', typical depth {d['depth']:.0f} mm"
  lines = [head]
  for a_id, b_id, dg in g["examples"][:2]:
    lines.append(f"      e.g. {dg['fix']}")
  if g["count"] > 1:
    lines.append("      the same change applies to all " + str(g["count"]) + " (the others differ only in position)")
  return lines


def check_no_overlap(items, roles, spec) -> dict:
  """Strict by default: every pair of the selected items is examined; an exclusion is a declared rule, counted and reported."""
  tol = float(spec.get("tol", 2.0))
  exclude = spec.get("exclude", [])
  ia, ib = _scope_sets(items, roles, spec)
  a, b = boxes(items, ia), boxes(items, ib)
  d = overlap_depths(a, b)
  hit = np.all(d > tol, axis=2)  # deeper than the tolerance on every axis
  ia_arr, ib_arr = np.array(ia), np.array(ib)
  valid = ia_arr[:, None] != ib_arr[None, :]
  in_both = np.isin(ia_arr, ib_arr)[:, None] & np.isin(ib_arr, ia_arr)[None, :]
  valid &= ~(in_both & (ia_arr[:, None] > ib_arr[None, :]))  # an unordered pair is examined once
  # exclusion masks, first matching rule wins (vectorised through small integer codes)
  kind_codes = {k: n for n, k in enumerate(sorted({it["kind"] for it in items}))}
  group_codes = {g: n for n, g in enumerate(sorted({it["group"] for it in items}))}
  ka = np.array([kind_codes[items[i]["kind"]] for i in ia]); kb = np.array([kind_codes[items[i]["kind"]] for i in ib])
  ga = np.array([group_codes[items[i]["group"]] for i in ia]); gb = np.array([group_codes[items[i]["group"]] for i in ib])
  empty_g = group_codes.get("", -1)
  label = np.full(a.shape[:1] + b.shape[:1], -1, dtype=int)
  names: list[str] = []
  for rule in exclude:
    if rule.get("same_group"):
      m = (ga[:, None] == gb[None, :]) & (ga[:, None] != empty_g)
      name = "same group"
    elif rule.get("same_kind"):
      m = ka[:, None] == kb[None, :]
      name = "same kind"
    elif "roles" in rule:
      ra, rb = rule["roles"]
      sa, sb = {kind_codes[k] for k in roles.get(ra, []) if k in kind_codes}, {kind_codes[k] for k in roles.get(rb, []) if k in kind_codes}
      m = (np.isin(ka, list(sa))[:, None] & np.isin(kb, list(sb))[None, :]) | (np.isin(ka, list(sb))[:, None] & np.isin(kb, list(sa))[None, :])
      name = f"roles {ra} / {rb}"
    else:
      continue
    if name not in names:
      names.append(name)
    code = names.index(name)
    label = np.where((label == -1) & m, code, label)
  excl = valid & (label >= 0)
  viol_mask = valid & hit & (label < 0)
  shadow_mask = valid & hit & (label >= 0)
  rows, cols = np.nonzero(viol_mask)
  viol = sorted(((items[ia[r]]["id"], items[ib[c]]["id"], d[r, c].tolist()) for r, c in zip(rows, cols)), key=lambda v: -min(v[2]))
  by_id = {it["id"]: it for it in items}
  patterns = cluster([(by_id[x], by_id[y], diagnose_overlap(by_id[x], by_id[y], dd)) for x, y, dd in viol])
  srows, scols = np.nonzero(shadow_mask)
  shadow = sorted(((items[ia[r]]["id"], items[ib[c]]["id"], float(d[r, c].min()), names[label[r, c]]) for r, c in zip(srows, scols)), key=lambda v: -v[2])
  shadow_patterns = cluster([(items[ia[r]], items[ib[c]], diagnose_overlap(items[ia[r]], items[ib[c]], d[r, c])) for r, c in zip(srows, scols)])
  excluded_by = {names[k]: int(((label == k) & valid).sum()) for k in range(len(names)) if ((label == k) & valid).sum()}
  return {"status": "fail" if viol else "pass", "violations": len(viol),
          "offenders": [f"{x[0]} x {x[1]}: overlap {', '.join(f'{v:.0f}' for v in x[2])} mm (x, y, z)" for x in viol[:TOP]],
          "examined": int(valid.sum()), "excluded": int(excl.sum()), "excluded_by": excluded_by,
          "shadow_overlaps": len(shadow),
          "shadow_examples": [f"{s[0]} x {s[1]}: {s[2]:.0f} mm, excluded by '{s[3]}'" for s in shadow[:TOP]],
          "patterns": [pattern_text(g) for g in patterns], "shadow_patterns": [pattern_text(g) for g in shadow_patterns],
          "tol": tol, "narrowed": bool(exclude) or spec.get("roles", ["*"]) != ["*"]}


AXES = "xyz"


def _move_text(g_row, need, val, a_id, b_id) -> str:
  """How to restore a clearance: the per-axis gaps and the shortest move along the axis that is already widest."""
  axis = int(np.argmax(g_row))
  short = need - val
  gx = ", ".join(f"{AXES[k]} {g_row[k]:.0f}" for k in range(3))
  return f"gaps per axis (mm): {gx}; moving {b_id} by {short:.0f} mm along {AXES[axis]} away from {a_id} restores {need:.0f} mm"


def check_min_clearance(items, roles, spec) -> dict:
  ia, ib = select(items, roles, spec["a"]), select(items, roles, spec["b"])
  need = float(spec["min"])
  mode = spec.get("mode", "euclid")
  g = gaps(boxes(items, ia), boxes(items, ib))
  if mode == "best_axis":  # at least one axis must keep the distance
    val = g.max(axis=2)
  elif mode == "z":
    val = g[:, :, 2]
  else:  # euclid distance between the boxes (0 when they touch or overlap)
    val = np.sqrt((np.clip(g, 0, None) ** 2).sum(axis=2))
  bad = np.argwhere(val < need)
  bad = [(i, j, float(val[i, j])) for i, j in bad if items[ia[i]]["id"] != items[ib[j]]["id"]]
  bad.sort(key=lambda v: v[2])
  return {"status": "fail" if bad else "pass", "violations": len(bad), "examined": int(val.size),
          "offenders": [f"{items[ia[i]]['id']} to {items[ib[j]]['id']}: {v:.0f} mm, need {need:.0f} ({mode}); "
                        + _move_text(g[i, j], need, v, items[ia[i]]["id"], items[ib[j]]["id"]) for i, j, v in bad[:TOP]]}


def _above_below(items, i, side, lo, hi):
  """Items whose plan footprint overlaps item i and that sit in the z band [lo, hi] (what the offender runs into)."""
  b = items[i]["aabb"]
  out = []
  for j, o in enumerate(items):
    if j == i:
      continue
    ob = o["aabb"]
    if ob[0] < b[3] and b[0] < ob[3] and ob[1] < b[4] and b[1] < ob[4] and ob[2] < hi and lo < ob[5]:
      out.append(f"{o['id']} ({o['kind']}, z {ob[2]:.0f} to {ob[5]:.0f})")
  return out[:2]


def check_z_range(items, roles, spec) -> dict:
  idx = select(items, roles, spec["role"])
  b = boxes(items, idx)
  zmin, zmax = spec.get("zmin"), spec.get("zmax")
  bad = []
  for k, i in enumerate(idx):
    lo, hi = b[k, 2], b[k, 5]
    if zmin is not None and lo < float(zmin):
      bad.append((i, "bottom", lo, float(zmin) - lo, float(zmin)))
    if zmax is not None and hi > float(zmax):
      bad.append((i, "top", hi, hi - float(zmax), float(zmax)))
  bad.sort(key=lambda v: -v[3])
  groups: dict[tuple, list] = {}
  for v in bad:
    groups.setdefault((items[v[0]]["kind"], v[1], round(v[3] / 10) * 10), []).append(v)
  patterns = []
  for (kind, side, over), vs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    if len(vs) > 1:
      lim = vs[0][4]
      patterns.append([f"{len(vs)} {kind} item(s) have their {side} about {over:.0f} mm {'above' if side == 'top' else 'below'} the limit {lim:.0f}"
                       f" (e.g. {items[vs[0][0]]['id']}): move all of them {'down' if side == 'top' else 'up'} by {over:.0f} mm"])
  lines = []
  for i, side, val, amt, lim in bad[:TOP]:
    near = _above_below(items, i, side, lim, val + 1) if side == "top" else _above_below(items, i, side, val - 1, lim)
    lines.append(f"{items[i]['id']}: {side} at {val:.0f}, limit {lim:.0f}, {amt:.0f} mm too {'high' if side == 'top' else 'low'}"
                 + (f"; in that band over the same footprint: {', '.join(near)}" if near else ""))
  return {"status": "fail" if bad else "pass", "violations": len(bad), "examined": len(idx), "offenders": lines, "patterns": patterns}


def check_nearest_within(items, roles, spec) -> dict:
  ia, ib = select(items, roles, spec["from"]), select(items, roles, spec["to"])
  g = gaps(boxes(items, ia), boxes(items, ib))
  plan = spec.get("plan_only", True)
  dist = np.sqrt((np.clip(g[:, :, :2], 0, None) ** 2).sum(axis=2)) if plan else np.sqrt((np.clip(g, 0, None) ** 2).sum(axis=2))
  need = float(spec["max"])
  near = dist.min(axis=1) if dist.shape[1] else np.full(len(ia), np.inf)
  bad = [(i, float(near[i])) for i in range(len(ia)) if near[i] > need]
  bad.sort(key=lambda v: -v[1])
  lines = []
  for i, d in bad[:TOP]:
    if dist.shape[1]:
      j = int(dist[i].argmin())
      a, bb = items[ia[i]]["aabb"], items[ib[j]]["aabb"]
      dx = (bb[0] + bb[3]) / 2 - (a[0] + a[3]) / 2
      dy = (bb[1] + bb[4]) / 2 - (a[1] + a[4]) / 2
      lines.append(f"{items[ia[i]]['id']}: nearest is {items[ib[j]]['id']}, {d:.0f} mm away ({'plan' if plan else '3D'}), limit {need:.0f}: "
                   f"{d - need:.0f} mm too far; it lies {abs(dx):.0f} mm {'east' if dx > 0 else 'west'} and {abs(dy):.0f} mm {'north' if dy > 0 else 'south'} of it (centre to centre)")
    else:
      lines.append(f"{items[ia[i]]['id']}: there is no item of role '{spec['to']}' to be near")
  return {"status": "fail" if bad else "pass", "violations": len(bad), "examined": len(ia), "offenders": lines}


def check_connected(items, roles, spec) -> dict:
  idx = select(items, roles, spec["role"])
  tol = float(spec.get("touch_tol", 5.0))
  groups: dict[str, list[int]] = {}
  for i in idx:
    groups.setdefault(items[i]["group"] if spec.get("group_by", "group") == "group" else "all", []).append(i)
  problems, detail = [], []
  for gname, gi in sorted(groups.items()):
    b = boxes(items, gi)
    g = gaps(b, b)
    gm = g.max(axis=2)  # touching or overlapping on every axis => max gap <= tol
    comp = _components(gm <= tol)
    ncomp = len(set(comp))
    detail.append(f"{gname or '(no group)'}: {len(gi)} items, {ncomp} component(s)")
    if ncomp > 1:
      sizes = {c: comp.count(c) for c in set(comp)}
      main = max(sizes, key=sizes.get)
      msgs = []
      for c in sorted(sizes, key=lambda c: sizes[c]):
        if c == main:
          continue
        mem = [k for k in range(len(gi)) if comp[k] == c]
        oth = [k for k in range(len(gi)) if comp[k] != c]
        sub = np.sqrt((np.clip(g[np.ix_(mem, oth)], 0, None) ** 2).sum(axis=2))
        a, o = np.unravel_index(sub.argmin(), sub.shape)
        ka, ko = mem[a], oth[o]
        gv = g[ka, ko]
        msgs.append(f"{sizes[c]} item(s) incl. {items[gi[ka]]['id']} are cut off; the closest other item is {items[gi[ko]]['id']}, "
                    f"{sub.min():.0f} mm away (gaps x {gv[0]:.0f}, y {gv[1]:.0f}, z {gv[2]:.0f}): close that gap")
      problems.append(f"group '{gname}' is split into {ncomp} separate networks: " + "; ".join(msgs[:3]))
    reach = spec.get("reach")
    if reach:
      px, py = reach["point"]
      r = float(reach.get("tol", 50.0))
      dx = np.maximum(np.maximum(b[:, 0] - px, px - b[:, 3]), 0)
      dy = np.maximum(np.maximum(b[:, 1] - py, py - b[:, 4]), 0)
      d = np.hypot(dx, dy)
      if not np.any(d <= r):
        k = int(d.argmin())
        problems.append(f"group '{gname}' does not reach ({px:.0f}, {py:.0f}) within {r:.0f} mm; the nearest end is {items[gi[k]]['id']}, {d[k]:.0f} mm away")
  return {"status": "fail" if problems else "pass", "violations": len(problems), "examined": len(groups),
          "offenders": problems[:TOP], "info": detail}


def _components(adj: np.ndarray) -> list[int]:
  n = adj.shape[0]
  comp = [-1] * n
  c = 0
  for s in range(n):
    if comp[s] != -1:
      continue
    stack = [s]
    comp[s] = c
    while stack:
      u = stack.pop()
      for v in np.nonzero(adj[u])[0]:
        if comp[v] == -1:
          comp[v] = c
          stack.append(int(v))
    c += 1
  return comp


def _runs(mask, xs, step=100.0):
  """Intervals [from, to] of the positions xs where mask is False."""
  out, start = [], None
  for k, m in enumerate(mask):
    if not m and start is None:
      start = xs[k]
    if m and start is not None:
      out.append((start, xs[k - 1] + step))
      start = None
  if start is not None:
    out.append((start, xs[-1] + step))
  return out


def check_coverage_along(items, roles, spec) -> dict:
  """Every item of `lines` (a long box) must be served along min_fraction of its length by items of `by`, within `across` mm."""
  il, ib = select(items, roles, spec["lines"]), select(items, roles, spec["by"])
  across, frac_need = float(spec["across"]), float(spec.get("min_fraction", 0.8))
  groups = sorted({items[i]["group"] for i in ib}) if spec.get("each_group") else [None]
  bad, worst = [], []
  for li in il:
    lb = items[li]["aabb"]
    axis = 0 if (lb[3] - lb[0]) >= (lb[4] - lb[1]) else 1
    other = 1 - axis
    xs = np.arange(lb[axis], lb[axis + 3] + 1e-6, 100.0)
    for gname in groups:
      cand = [j for j in ib if gname is None or items[j]["group"] == gname]
      covered = np.zeros(len(xs), dtype=bool)
      for j in cand:
        jb = items[j]["aabb"]
        gap = max(lb[other] - jb[other + 3], jb[other] - lb[other + 3], 0.0)
        if gap <= across:
          covered |= (xs >= jb[axis] - 1e-6) & (xs <= jb[axis + 3] + 1e-6)
      frac = float(covered.mean()) if len(xs) else 0.0
      worst.append(frac)
      if frac < frac_need:
        bad.append((items[li]["id"], gname, frac, _runs(covered, xs), AXES[axis]))
  def line(a, g, f, runs, ax):
    gaps_txt = ", ".join(f"{ax} {r0:.0f} to {r1:.0f} ({r1 - r0:.0f} mm)" for r0, r1 in runs[:3])
    return f"{a}{' by ' + g if g else ''}: served along {f * 100:.0f}% of its length, need {frac_need * 100:.0f}%; not served at {gaps_txt}"
  return {"status": "fail" if bad else "pass", "violations": len(bad), "examined": len(il) * len(groups),
          "offenders": [line(*v) for v in sorted(bad, key=lambda v: v[2])[:TOP]],
          "info": [f"lowest coverage {min(worst) * 100:.0f}%"] if worst else []}


def check_count(items, roles, spec) -> dict:
  n = len(select(items, roles, spec["role"]))
  ok = True
  if "equals" in spec:
    ok = ok and n == int(spec["equals"])
  if "at_least" in spec:
    ok = ok and n >= int(spec["at_least"])
  return {"status": "pass" if ok else "fail", "violations": 0 if ok else 1, "examined": n,
          "offenders": [] if ok else [f"{n} items, expected {spec.get('equals', 'at least ' + str(spec.get('at_least')))}"]}


def check_length_sum(items, roles, spec) -> dict:
  idx = select(items, roles, spec["role"])
  by: dict[str, float] = {}
  for i in idx:
    b = items[i]["aabb"]
    length = max(b[3] - b[0], b[4] - b[1], b[5] - b[2])
    key = items[i]["group"] or "all"
    by[key] = by.get(key, 0.0) + length
  total = sum(by.values())
  return {"status": "info", "violations": 0, "examined": len(idx), "offenders": [], "objective": {"total_mm": total, "by_group_mm": by}}


SAFE_BUILTINS = {n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
                 for n in ("abs", "all", "any", "dict", "enumerate", "float", "int", "len", "list", "max", "min", "range",
                           "round", "set", "sorted", "str", "sum", "tuple", "zip", "bool")}


def check_custom(items, roles, spec) -> dict:
  """A check the library does not cover: `code` defines check(items, roles, helpers) returning {"violations": [str, ...]}."""
  helpers = {"overlap_depths": overlap_depths, "gaps": gaps, "np": np, "select": select}
  ns: dict[str, Any] = {"__builtins__": SAFE_BUILTINS}
  try:
    exec(compile(spec["code"], f"custom:{spec['id']}", "exec"), ns)
    out = ns["check"](copy.deepcopy(items), roles, helpers)
  except Exception as exc:
    line = ""
    tb = exc.__traceback__
    while tb is not None:
      if tb.tb_frame.f_code.co_filename == f"custom:{spec['id']}":
        src = spec["code"].splitlines()
        line = f" at line {tb.tb_lineno}: `{src[tb.tb_lineno - 1].strip() if tb.tb_lineno <= len(src) else ''}`"
      tb = tb.tb_next
    hint = ("; the code must define check(items, roles, helpers) and return {'violations': [...], 'examined': n}"
            if isinstance(exc, (KeyError, NameError)) and "check" in str(exc) else "")
    return {"status": "error", "violations": 0, "examined": 0,
            "offenders": [f"custom check '{spec['id']}' failed to run: {type(exc).__name__}: {exc}{line}{hint}"]}
  v = [str(x) for x in (out.get("violations") or [])]
  return {"status": "fail" if v else "pass", "violations": len(v), "examined": int(out.get("examined", len(items))), "offenders": v[:TOP]}


RUNNERS = {"no_overlap": check_no_overlap, "min_clearance": check_min_clearance, "z_range": check_z_range,
           "nearest_within": check_nearest_within, "connected": check_connected, "coverage_along": check_coverage_along,
           "count": check_count, "length_sum": check_length_sum, "custom": check_custom}


def validate_config(checks: list[dict]) -> list[str]:
  """Problems with a configuration, as readable strings (empty = fine)."""
  probs, ids = [], set()
  for c in checks:
    cid = c.get("id", "?")
    if c.get("type") not in CHECK_TYPES:
      probs.append(f"{cid}: unknown type '{c.get('type')}'; use one of {', '.join(CHECK_TYPES)}")
    if cid in ids:
      probs.append(f"{cid}: duplicate id")
    ids.add(cid)
    need = {"no_overlap": (), "min_clearance": ("a", "b", "min"), "z_range": ("role",), "nearest_within": ("from", "to", "max"),
            "connected": ("role",), "coverage_along": ("lines", "by", "across"), "count": ("role",), "length_sum": ("role",),
            "custom": ("code",)}.get(c.get("type"), ())
    for k in need:
      if k not in c:
        probs.append(f"{cid}: missing '{k}'")
  return probs


# ---------------------------------------------------------------- evaluation

def evaluate(items_raw: list[dict], checks: list[dict], roles: dict[str, list[str]], previous: dict | None = None,
             self_test: bool = True) -> dict:
  """Runs every check, the scope facts and the injected-fault self-test; returns the structured report."""
  items = load_items(items_raw)
  probs = validate_config(checks)
  if probs:
    raise EngineError("; ".join(probs))
  results = {}
  for c in checks:
    try:
      results[c["id"]] = {"type": c["type"], "title": c.get("title", ""), **RUNNERS[c["type"]](items, roles, c)}
    except EngineError as exc:
      results[c["id"]] = {"type": c["type"], "title": c.get("title", ""), "status": "error", "violations": 0, "examined": 0, "offenders": [str(exc)]}
  for cid, r in results.items():
    c = next(x for x in checks if x["id"] == cid)
    if r["status"] in ("pass", "fail") and r["examined"] == 0 and c["type"] not in ("count",):
      r["status"] = "error"
      r["offenders"] = [f"examined 0 items, so this passes nothing: its roles select no items. Roles in use: "
                        + ", ".join(f"{k} = {roles.get(k, [])}" for k in sorted({x for key in ('roles', 'a', 'b', 'role', 'from', 'to', 'lines', 'by')
                                                                                for x in ([c[key]] if isinstance(c.get(key), str) else c.get(key, [])) if x != '*'}))] + r["offenders"]
  report = {"n_items": len(items), "results": results, "scope": scope_facts(items, checks, roles)}
  if self_test:
    report["self_test"] = injected_fault_test(items, checks, roles)
  obj = [r["objective"] for r in results.values() if "objective" in r]
  report["objective"] = {"total_mm": sum(o["total_mm"] for o in obj), "by_group_mm": _merge(o["by_group_mm"] for o in obj)} if obj else None
  report["objective_change"] = _change(report["objective"], previous)
  fails = [k for k, r in results.items() if r["status"] in ("fail", "error")]
  misses = [m for m in report.get("self_test", {}).get("missed", [])]
  report["ready"] = not fails and not misses
  report["not_ready_because"] = ([f"{len(fails)} check(s) failing or in error: {', '.join(fails)}"] if fails else []) + \
                                ([f"{len(misses)} injected fault(s) not caught by a check"] if misses else [])
  return report


def _merge(dicts):
  out: dict[str, float] = {}
  for d in dicts:
    for k, v in d.items():
      out[k] = out.get(k, 0.0) + v
  return out


def _change(now, prev):
  if not now or not prev or not prev.get("objective"):
    return None
  return {"vs_previous_mm": now["total_mm"] - prev["objective"]["total_mm"],
          "vs_best_mm": now["total_mm"] - min(prev.get("best_total_mm", prev["objective"]["total_mm"]), prev["objective"]["total_mm"])}


def scope_facts(items, checks, roles) -> dict:
  """Which kinds each check selects, and the kinds no check selects at all."""
  kinds = sorted({it["kind"] for it in items})
  touched: dict[str, set[str]] = {k: set() for k in kinds}
  for c in checks:
    sel: set[int] = set()
    for key in ("roles", "a", "b", "role", "from", "to", "lines", "by"):
      v = c.get(key)
      for r in ([v] if isinstance(v, str) else (v or [])):
        try:
          sel |= set(select(items, roles, r))
        except EngineError:
          pass
    for i in sel:
      touched[items[i]["kind"]].add(c["id"])
  unbound = [r for r in {x for c in checks for key in ("roles", "a", "b", "role", "from", "to", "lines", "by")
                         for x in ([c[key]] if isinstance(c.get(key), str) else c.get(key, []))} if r != "*" and r not in roles]
  return {"kinds": kinds, "by_kind": {k: sorted(v) for k, v in touched.items()}, "uncovered_kinds": [k for k, v in touched.items() if not v],
          "unbound_roles": sorted(unbound)}


def injected_fault_test(items, checks, roles, max_pairs: int = 600) -> dict:
  """For every pair of kinds (including two items of one kind), asks each `no_overlap` check: if two such items overlapped
  deeply, would you report it? Uses the same scope and exclusion rules the check itself applies (and a property test in
  the unit tests proves the two agree), so no model copy is needed."""
  missed, probed = [], 0
  by_kind: dict[str, list[int]] = {}
  for i, it in enumerate(items):
    by_kind.setdefault(it["kind"], []).append(i)
  kinds = sorted(by_kind)
  pair_kinds = [(a, b) for n, a in enumerate(kinds) for b in kinds[n:]]
  for c in checks:
    if c["type"] != "no_overlap":
      continue
    for ka, kb in pair_kinds[:max_pairs]:
      ia = by_kind[ka][0]
      ib = next((j for j in by_kind[kb] if j != ia), None)
      if ib is None:
        continue
      p, q = items[ia], items[ib]
      probed += 1
      if not pair_in_scope(p, q, c, roles):
        missed.append({"check": c["id"], "kinds": f"{ka} x {kb}", "reason": "outside the check's roles"})
      else:
        why = exclusion_of(p, q, c.get("exclude", []), roles)
        if why is not None:
          missed.append({"check": c["id"], "kinds": f"{ka} x {kb}", "reason": f"excluded: {why}"})
  return {"probed": probed, "missed": missed}


# ---------------------------------------------------------------- the report as text

def render(report: dict) -> str:
  """The report the designer reads: what to fix first, then the facts about scope."""
  L = []
  L.append(f"EVALUATION: {'READY' if report['ready'] else 'NOT READY'}  ({report['n_items']} items, {len(report['results'])} checks)")
  for why in report["not_ready_because"]:
    L.append(f"  not ready: {why}")
  L.append("")
  L.append("CHECKS (failing first)")
  order = sorted(report["results"].items(), key=lambda kv: {"error": 0, "fail": 1, "pass": 2, "info": 3}.get(kv[1]["status"], 4))
  for cid, r in order:
    flag = {"fail": "FAIL", "pass": "pass", "error": "ERROR", "info": "info"}[r["status"]]
    L.append(f"  [{flag}] {cid} {r['type']} {r['title']}: {r['violations']} violation(s), {r['examined']} examined")
    for pat in r.get("patterns", []):
      L.append("        CAUSE: " + pat[0])
      L.extend(pat[1:])
    for o in r["offenders"]:
      L.append(f"        - {o}")
    if r["type"] == "no_overlap":
      scope = f"pairs examined {r['examined']}, excluded {r['excluded']}"
      if r["excluded"]:
        scope += " (" + ", ".join(f"{k}: {v}" for k, v in r["excluded_by"].items()) + ")"
      L.append(f"        scope: {scope}")
      if r["shadow_overlaps"]:
        L.append(f"        INSIDE THE EXCLUDED PAIRS: {r['shadow_overlaps']} overlap(s) deeper than {r['tol']} mm that this check does not count:")
        for pat in r.get("shadow_patterns", []):
          L.append("          cause: " + pat[0])
          L.extend("  " + x for x in pat[1:])
        for s in r["shadow_examples"][:2]:
          L.append(f"          . {s}")
    for i in r.get("info", []):
      L.append(f"        {i}")
  L.append("")
  sc = report["scope"]
  L.append("SCOPE FACTS")
  L.append(f"  kinds in the model: {', '.join(sc['kinds'])}")
  L.append(f"  kinds that no check selects: {', '.join(sc['uncovered_kinds']) or 'none'}")
  if sc["unbound_roles"]:
    L.append(f"  roles used by checks but bound to no kind: {', '.join(sc['unbound_roles'])}")
  if "self_test" in report:
    st = report["self_test"]
    L.append(f"SELF-TEST: injected a deliberate overlap for {st['probed']} kind pair(s); missed by a check: {len(st['missed'])}")
    for m in st["missed"][:8]:
      L.append(f"  - {m['check']} would NOT report an overlap between {m['kinds']} ({m['reason']})")
  if report.get("objective"):
    o = report["objective"]
    L.append("OBJECTIVE (route length, mm): total " + f"{o['total_mm']:.0f}" + "; " + ", ".join(f"{k} {v:.0f}" for k, v in sorted(o["by_group_mm"].items())))
    if report.get("objective_change"):
      ch = report["objective_change"]
      L.append(f"  change against the previous evaluation: {ch['vs_previous_mm']:+.0f} mm")
  return "\n".join(L)
