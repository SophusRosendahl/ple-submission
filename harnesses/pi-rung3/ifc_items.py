"""Turns an IFC file into the engine's items, and a validator's cryptic output into messages that say what to change.

Runs in the serve container (ifcopenshell is installed there by the build). The agent never imports the library through this module:
it asks for an evaluation and reads the result.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

import numpy as np

FLOW_CLASSES = ("IfcPipeSegment", "IfcCableSegment", "IfcCableCarrierSegment", "IfcDuctSegment", "IfcFlowSegment")


def items_from_ifc(path: str) -> list[dict]:
  """One item per product with a shape: id = its Name (a short suffix is added if two share a name), kind = class/ObjectType,
  group = the service prefix of a flow segment's name (CHW, BW, CT, ...), aabb = its world bounding box in millimetres."""
  import ifcopenshell
  import ifcopenshell.geom

  model = ifcopenshell.open(path)
  settings = ifcopenshell.geom.settings()
  settings.set(settings.USE_WORLD_COORDS, True)
  items, names = [], Counter()
  for p in model.by_type("IfcProduct"):
    if not p.Representation:
      continue
    try:
      shape = ifcopenshell.geom.create_shape(settings, p)  # keep the shape alive while its buffer is read
      verts = np.array(list(shape.geometry.verts), dtype=float).reshape(-1, 3) * 1000.0
    except Exception:
      continue
    if not len(verts):
      continue
    lo, hi = verts.min(0), verts.max(0)
    name = p.Name or p.GlobalId
    names[name] += 1
    cls = p.is_a()
    kind = cls + (f"/{p.ObjectType}" if p.ObjectType else "")
    group = ""
    if any(p.is_a(c) for c in FLOW_CLASSES):
      m = re.match(r"([A-Za-z]+)", name)
      group = m.group(1).upper() if m else cls
    items.append({"id": name, "kind": kind, "group": group, "aabb": [float(x) for x in list(lo) + list(hi)], "guid": p.GlobalId})
  for it in items:  # ids must be unique for the engine
    if names[it["id"]] > 1:
      it["id"] = f"{it['id']}~{it['guid'][:5]}"
  return items


def validate_ifc(path: str) -> dict:
  """Schema and EXPRESS-rule validation, grouped by cause, each with a plain statement of what to change."""
  import ifcopenshell
  import ifcopenshell.validate

  model = ifcopenshell.open(path)
  logger = ifcopenshell.validate.json_logger()
  ifcopenshell.validate.validate(model, logger, express_rules=True)
  groups: dict[str, dict] = defaultdict(lambda: {"count": 0, "text": "", "examples": []})
  errors = [s for s in logger.statements if s.get("level") == "error"]
  for s in errors:
    key, text = explain(s)
    g = groups[key]
    g["count"] += 1
    g["text"] = text
    inst = str(s.get("instance") or "")[:90]
    if inst and len(g["examples"]) < 2:
      g["examples"].append(inst)
  return {"ok": not errors, "n_errors": len(errors), "groups": [{"cause": k, **v} for k, v in sorted(groups.items(), key=lambda kv: -kv[1]["count"])]}


def explain(statement: dict) -> tuple[str, str]:
  """(a key that groups the same cause, the message to show) for one validator statement."""
  msg = str(statement.get("message") or "")
  inst = str(statement.get("instance") or "")
  if "OfProductRepresentation" in msg and "sizeof" in msg:
    n = re.search(r"where (\d+) = sizeof", msg)
    rep = re.match(r"#(\d+)=(\w+)", inst)
    which = f"{rep.group(2)} #{rep.group(1)}" if rep else "a shape representation"
    if n and n.group(1) == "0":
      return ("orphan representation",
              f"{which} belongs to no product. Remove it, or assign it to an element (an unused representation is invalid).")
    return ("shared representation",
            f"{which} is assigned to {n.group(1) if n else 'several'} products, but IFC allows one representation to belong to one product. "
            "Create a new representation for every product (build it inside the loop that creates each element) instead of assigning one "
            "representation object to many elements. Sharing geometry is done with a representation map and mapped items, not by reuse.")
  first = msg.strip().splitlines()[0][:160] if msg.strip() else "no message"
  attr = statement.get("attribute")
  where = f"{inst[:70]}" + (f", attribute {attr}" if attr else "")
  return (first, f"{first} ({where})")


def render_validation(v: dict) -> str:
  if v["ok"]:
    return "SCHEMA: valid (express rules checked)"
  lines = [f"SCHEMA: {v['n_errors']} error(s), {len(v['groups'])} cause(s), fix these before anything else"]
  for g in v["groups"]:
    lines.append(f"  [{g['count']}x] {g['text']}")
    for e in g["examples"]:
      lines.append(f"        on {e}")
  return "\n".join(lines)
