"""Do different runs read the drawings the same way? Build every delivered solution.py locally, take each element's
bounding-box centre in world coordinates, and compare runs class by class.

  python3 research/cross_run_geometry.py <python with ifcopenshell> run-028 run-029 ...

Writes /tmp/ifcruns/<run>.json (class -> list of [cx, cy, cz, dx, dy, dz] in mm) and prints the agreement per class.
Needs the delivered scripts pulled into research/run-details. Reads only what the agents delivered, never grader files.
"""
import glob
import json
import pathlib
import subprocess
import sys

BUILD = r'''
import json, sys, ifcopenshell, ifcopenshell.geom, numpy as np
m = ifcopenshell.open(sys.argv[1]); s = ifcopenshell.geom.settings(); s.set(s.USE_WORLD_COORDS, True)
out = {}
for p in m.by_type("IfcProduct"):
    if not p.Representation: continue
    try:
        shape = ifcopenshell.geom.create_shape(s, p)  # keep the shape alive: its vertex buffer is freed with it
        v = np.array(list(shape.geometry.verts), dtype=float).reshape(-1, 3) * 1000.0
    except Exception:
        continue
    lo, hi = v.min(0), v.max(0)
    key = p.is_a() + ("/" + (p.ObjectType or "") if p.ObjectType else "")
    out.setdefault(key, []).append([round(float(x), 1) for x in ((lo + hi) / 2).tolist() + (hi - lo).tolist()])
json.dump(out, open(sys.argv[2], "w"))
'''


def build(py, run):
    sol = glob.glob(f"{pathlib.Path(__file__).parent}/run-details/{run}/data-hall-mep-routing/deliverables/files/app/files/*/output/solution.py")
    if not sol:
        return None
    ifc, js = f"/tmp/ifcruns/{run}.ifc", f"/tmp/ifcruns/{run}.json"
    try:
        subprocess.run([py, sol[0], ifc], capture_output=True, text=True, timeout=180, check=True, cwd="/tmp/ifcruns")
        pathlib.Path("/tmp/ifcruns/_b.py").write_text(BUILD)
        subprocess.run([py, "/tmp/ifcruns/_b.py", ifc, js], capture_output=True, text=True, timeout=300, check=True)
    except Exception as exc:
        print(run, "could not build:", str(getattr(exc, "stderr", exc))[-200:])
        return None
    return json.load(open(js))


if __name__ == "__main__":
    py, runs = sys.argv[1], sys.argv[2:]
    data = {r: build(py, r) for r in runs}
    data = {r: d for r, d in data.items() if d}
    print("built:", list(data))
