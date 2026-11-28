"""Tests of the IFC bridge: items from a built model, and the validator's messages. Needs ifcopenshell (skipped without it)."""
import os
import tempfile
import unittest

try:
  import ifcopenshell
  import ifcopenshell.api
  HAVE = True
except ImportError:
  HAVE = False

import ifc_items


def build(path, shared: bool):
  f = ifcopenshell.api.run("project.create_file", version="IFC4")
  proj = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="p")
  ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS"})
  ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
  body = ifcopenshell.api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
  site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="s")
  ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=proj)
  def rep():
    prof = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((0.0, 0.0))), 400.0, 400.0)
    solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))), f.createIfcDirection((0.0, 0.0, 1.0)), 3000.0)
    return f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
  one = rep() if shared else None
  for n, x in enumerate((0.0, 1.0)):  # placements in metres, as the API wants
    col = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcColumn", name=f"COL-{n}")
    col.ObjectType = "StructuralColumn"
    ifcopenshell.api.run("geometry.assign_representation", f, product=col, representation=one if shared else rep())
    ifcopenshell.api.run("geometry.edit_object_placement", f, product=col, matrix=[[1, 0, 0, x], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
    ifcopenshell.api.run("spatial.assign_container", f, products=[col], relating_structure=site)
  f.write(path)


@unittest.skipUnless(HAVE, "ifcopenshell not installed")
class Bridge(unittest.TestCase):
  def setUp(self):
    self.dir = tempfile.mkdtemp()

  def test_items_have_names_kinds_and_millimetre_boxes(self):
    p = os.path.join(self.dir, "ok.ifc")
    build(p, shared=False)
    items = ifc_items.items_from_ifc(p)
    self.assertEqual(sorted(i["id"] for i in items), ["COL-0", "COL-1"])
    c = next(i for i in items if i["id"] == "COL-1")
    self.assertEqual(c["kind"], "IfcColumn/StructuralColumn")
    self.assertAlmostEqual(c["aabb"][3] - c["aabb"][0], 400.0, places=3)
    self.assertAlmostEqual(c["aabb"][5] - c["aabb"][2], 3000.0, places=3)
    self.assertAlmostEqual(c["aabb"][0], 1000.0 - 200.0, places=3)

  def test_a_valid_model_validates(self):
    p = os.path.join(self.dir, "ok.ifc")
    build(p, shared=False)
    self.assertTrue(ifc_items.validate_ifc(p)["ok"])

  def test_a_shared_representation_is_explained(self):
    p = os.path.join(self.dir, "bad.ifc")
    build(p, shared=True)
    v = ifc_items.validate_ifc(p)
    self.assertFalse(v["ok"])
    text = ifc_items.render_validation(v)
    self.assertIn("is assigned to 2 products", text)
    self.assertIn("Create a new representation for every product", text)


if __name__ == "__main__":
  unittest.main()
