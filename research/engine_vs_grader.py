"""Does our engine agree with the grader? Build each delivered solution locally, turn its solids into boxes, run the engine's strict
no_overlap check over all pairs, and compare the clash list with the grader's (the report the evaluator wrote for that run).

  python3 research/engine_vs_grader.py <python with ifcopenshell and numpy> run-029 run-032 ...

Reads only what the agents delivered and the grader's output report; never the grader's code.
"""
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "harnesses" / "pi-rung3"))
import engine  # noqa: E402

EXTRACT = r'''
import json, sys, ifcopenshell, ifcopenshell.geom, numpy as np
m = ifcopenshell.open(sys.argv[1]); s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
out = []
for p in m.by_type("IfcProduct"):
    if not p.Representation: continue
    try:
        shape = ifcopenshell.geom.create_shape(s, p)  # keep the shape alive: its vertex buffer is freed with it
        v = np.array(list(shape.geometry.verts), dtype=float).reshape(-1, 3) * 1000.0
    except Exception:
        continue
    lo, hi = v.min(0), v.max(0)
    out.append({"guid": p.GlobalId, "name": p.Name or "", "cls": p.is_a(), "otype": p.ObjectType or "", "aabb": [float(x) for x in list(lo) + list(hi)]})
json.dump(out, open(sys.argv[2], "w"))
'''


def build_items(py, run):
  sol = list((HERE / "run-details" / run / "data-hall-mep-routing" / "deliverables" / "files" / "app" / "files").glob("*/output/solution.py"))
  if not sol:
    return None
  work = pathlib.Path("/tmp/ifcruns"); work.mkdir(exist_ok=True)
  ifc, js = work / f"{run}.ifc", work / f"{run}.items.json"
  subprocess.run([py, str(sol[0]), str(ifc)], capture_output=True, text=True, timeout=180, check=True, cwd=work)
  (work / "_x.py").write_text(EXTRACT)
  subprocess.run([py, str(work / "_x.py"), str(ifc), str(js)], capture_output=True, text=True, timeout=300, check=True)
  return json.load(open(js))


def to_items(raw):
  items, skipped = [], 0
  for r in raw:
    if any(abs(v) > 1e7 for v in r["aabb"]):
      skipped += 1
      continue
    m = re.match(r"(CHW|BW|CT)", r["name"], re.I)
    group = (m.group(1).upper() if m else "")
    kind = r["cls"] + ("/" + r["otype"] if r["otype"] else "")
    items.append({"id": r["guid"], "kind": kind, "group": group, "aabb": r["aabb"], "name": r["name"]})
  return items, skipped


def grader_pairs(run):
  """The grader's clash pairs by element name (its ids are random per build, names are the agent's own)."""
  rep = json.load(open(HERE / "run-details" / run / "data-hall-mep-routing" / "verifier" / "artifacts.json"))["report"]
  out = set()
  for c in rep.get("clashes", []):
    m = re.match(r"(.+?) x (.+?) \(", c["detail"])
    out.add(frozenset((m.group(1), m.group(2))))
  return out, rep.get("checkable_pairs")


if __name__ == "__main__":
  py, runs = sys.argv[1], sys.argv[2:]
  print(f"{'run':8} {'items':>5} {'skipped':>7} {'grader clashes':>14} {'engine clashes':>14} {'both':>5} {'grader only':>11} {'engine only':>11}")
  for run in runs:
    try:
      raw = build_items(py, run)
    except Exception as exc:
      print(run, "could not build:", str(getattr(exc, "stderr", exc))[-150:]); continue
    items, skipped = to_items(raw)
    gp, _ = grader_pairs(run)
    r = engine.check_no_overlap(engine.load_items(items), {}, {"id": "c", "type": "no_overlap", "tol": 2.0})
    # recover the engine's pairs by id
    ids = {it["id"]: it for it in items}
    a, b = engine.boxes(items, list(range(len(items)))), None
    d = engine.overlap_depths(a, a)
    hit = (d > 2.0).all(axis=2)
    ep = {frozenset((items[i]["name"], items[j]["name"])) for i in range(len(items)) for j in range(i + 1, len(items)) if hit[i, j]}
    print(f"{run:8} {len(items):5d} {skipped:7d} {len(gp):14d} {len(ep):14d} {len(gp & ep):5d} {len(gp - ep):11d} {len(ep - gp):11d}")
