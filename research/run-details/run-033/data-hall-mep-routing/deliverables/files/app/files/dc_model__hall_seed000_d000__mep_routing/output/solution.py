"""Coordinated 3D IFC4 model builder for dc_model hall_seed000_d000.

Rebuilds Data Hall 1 (27000 x 21000 mm, 128 racks, 6 structural columns,
4 perimeter CRAHs, 18 in-row CRAHs, 6 PDUs, access floor, 2 cold-aisle
containments, 63 ceiling + 16 in-aisle sprinklers) and routes three
clash-free, code-compliant services (telecom cable tray, power busway,
chilled-water pipe) from the west-wall service entry at (0, 9900).

Usage:
    python output/solution.py [output/model.ifc]
"""
from __future__ import annotations

import logging
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Baked-in drawing data (A-101, A-301, A-601, A-602, E-101, F-101, M-101)
# All dimensions in millimetres; Z = 0 is Finished Floor (top of access floor).
# ---------------------------------------------------------------------------

HALL_W = 27000.0
HALL_D = 21000.0
TILE = 600.0

Z_SLAB = -900.0
Z_FLOOR_PANEL_THK = 35.0
Z_FLOOR_UNDERSIDE = -35.0
Z_FLOOR_TOP = 0.0
Z_MIN_CLEAR_HEIGHT = 2600.0
Z_SOFFIT = 3600.0
Z_CEIL_DEFLECTOR = 3574.6  # 25.4 mm below +3600 soffit (A-301)
SPRINKLER_STANDOFF = 460.0

ROW_SPECS = [
    # (row_letter, y_center, facing, tokens)
    ("A", 3000.0, "SOUTH", [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH", [("C1", 3), ("CU", 1), ("C1", 6), ("OMIT600", 2), ("CU", 1), ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT600", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH", [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 5), ("OMIT600", 2), ("CU", 1), ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("OMIT600", 1), ("CU", 1), ("C1", 4)]),
]

ROW_START_X = 1800.0       # Tile D (index 3 * 600)
CROSS_AISLE_EAST_X = 11400.0  # Common east edge of cross aisle (A-101 Note 5)

COLUMN_CENTERS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]
COLUMN_SIZE = 600.0

PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),     # B01
    ("CRAH-02", 9000.0, 0.0),    # P01
    ("CRAH-03", 16800.0, 0.0),   # AC01
    ("CRAH-04", 25200.0, 0.0),   # AQ01
]

# PDUs: 762 W x 813 D x 1959 H, front flush with served row front (A-101 Note 8)
PDU_SPECS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),   # AJ05, front at y=2400
    ("PDU-02", "B", 21600.0, 5787.0, "NORTH"),   # AK10, front at y=6600 -> y0=5787
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),   # AJ14, front at y=7800
    ("PDU-04", "D", 21000.0, 11187.0, "NORTH"),  # AJ19, front at y=12000 -> y0=11187
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),  # AJ23, front at y=13200
    ("PDU-06", "F", 21600.0, 16587.0, "NORTH"),  # AK28, front at y=17400 -> y0=16587
]

# Service entry (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Routing elevations (centreline Z in mm)
# - Power Busway (128 W x 147 H): overhead at Z = 2850 mm (2776.5..2923.5 mm)
#   -> >= 2600 mm headroom (176.5 mm margin) and <= 3114.6 mm standoff (191.1 mm margin)
# - Telecom Cable Tray (683 W x 127 H): under-floor plenum at Z = -150 mm (-213.5..-86.5 mm)
#   -> 51.5 mm clear below panel underside (-35 mm), >= 20 mm required
#   -> vertical separation from Busway = 2863 mm >> 300 mm required
# - Chilled-Water Pipe (DN100, bare OD 114.3, insulated OD 168.3): under-floor plenum at Z = -500 mm (-584.15..-415.85 mm)
#   -> 202.35 mm clear below Cable Tray, 315.85 mm clear above slab (-900 mm)
#   -> completely below PDU dedicated electrical space (1959..3759 mm)
Z_BUSWAY = 2850.0
Z_TRAY = -150.0
Z_CHW = -500.0

TRUNK_X = 900.0
HEADER_END_X = 19000.0
HEADER_YS = [4500.0, 9900.0, 15300.0]  # Serve (A,B), (C,D), (E,F) within 1500 mm
PERIM_CHW_Y = 1200.0
PERIM_CHW_END_X = 25800.0


def build_model_data() -> dict[str, Any]:
    """Generate all hall background elements and MEP route segments in mm."""
    racks: list[dict[str, Any]] = []
    crahs: list[dict[str, Any]] = []
    row_extents: dict[str, tuple[float, float, float]] = {}

    # 1. Racks and in-row CRAHs
    for row_letter, y_c, facing, tokens in ROW_SPECS:
        x = ROW_START_X
        rack_idx = 0
        crah_idx = 0
        y0, y1 = y_c - 600.0, y_c + 600.0
        west_end_x = ROW_START_X
        for kind, count in tokens:
            if kind == "CA":
                west_end_x = x
                x = CROSS_AISLE_EAST_X
                continue
            for _ in range(count):
                if kind == "C1":
                    w = 600.0
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_letter}{rack_idx:02d}",
                        "row": row_letter,
                        "type": "C1",
                        "width": w,
                        "depth": 1200.0,
                        "height": 2000.0,
                        "facing": facing,
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind == "N1":
                    w = 800.0
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_letter}{rack_idx:02d}",
                        "row": row_letter,
                        "type": "N1",
                        "width": w,
                        "depth": 1200.0,
                        "height": 2000.0,
                        "facing": facing,
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind == "CU":
                    w = 600.0
                    crah_idx += 1
                    crahs.append({
                        "tag": f"CRAH-{row_letter}{crah_idx:02d}",
                        "kind": "inrow",
                        "row": row_letter,
                        "width": w,
                        "depth": 1200.0,
                        "height": 2000.0,
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "airflow_m3h": 9000.0,
                        "service": "CHILLED WATER, DN50",
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind in ("SP", "OMIT600"):
                    x += 600.0
        row_extents[row_letter] = (ROW_START_X, west_end_x, x)

    # Perimeter CRAHs
    for tag, x0, y0 in PERIMETER_CRAHS:
        crahs.append({
            "tag": tag,
            "kind": "perimeter",
            "row": "PERIMETER",
            "width": 1200.0,
            "depth": 900.0,
            "height": 2000.0,
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
            "service": "CHILLED WATER, DN100",
            "aabb": (x0, y0, 0.0, x0 + 1200.0, y0 + 900.0, 2000.0),
        })

    # 2. Structural columns (0 to 3600 mm)
    columns = []
    half = COLUMN_SIZE / 2.0
    for tag, cx, cy in COLUMN_CENTERS:
        columns.append({
            "tag": tag,
            "aabb": (cx - half, cy - half, 0.0, cx + half, cy + half, Z_SOFFIT),
        })

    # 3. PDUs
    pdus = []
    for tag, row_letter, x0, y0, facing in PDU_SPECS:
        pdus.append({
            "tag": tag,
            "row": row_letter,
            "width": 762.0,
            "depth": 813.0,
            "height": 1959.0,
            "facing": facing,
            "aabb": (x0, y0, 0.0, x0 + 762.0, y0 + 813.0, 1959.0),
        })

    # 4. Access floor panel (-35 to 0 mm)
    access_floor = [{
        "tag": "ACCESS-FLOOR-01",
        "aabb": (0.0, 0.0, Z_FLOOR_UNDERSIDE, HALL_W, HALL_D, Z_FLOOR_TOP),
    }]

    # 5. Cold-aisle containment (CAC-BC and CAC-DE)
    containment = []
    for cac_tag, y_aisle_0, y_aisle_1, r1, r2 in [
        ("CAC-BC", 6600.0, 7800.0, "B", "C"),
        ("CAC-DE", 12000.0, 13200.0, "D", "E"),
    ]:
        west_end = min(row_extents[r1][1], row_extents[r2][1])
        east_end = max(row_extents[r1][2], row_extents[r2][2])
        for seg_idx, (sx0, sx1) in enumerate([(ROW_START_X, west_end), (CROSS_AISLE_EAST_X, east_end)], start=1):
            # Roof panel: width 1400 (100 overhang each side), z = 2000..2055.5
            containment.append({
                "tag": f"{cac_tag}-ROOF-{seg_idx}",
                "kind": "roof",
                "aabb": (sx0, y_aisle_0 - 100.0, 2000.0, sx1, y_aisle_1 + 100.0, 2055.5),
            })
            # West and east end doors: 60 thick x 1200 wide x 2055.5 high
            containment.append({
                "tag": f"{cac_tag}-DOOR-{seg_idx}W",
                "kind": "door",
                "aabb": (sx0 - 60.0, y_aisle_0, 0.0, sx0, y_aisle_1, 2055.5),
            })
            containment.append({
                "tag": f"{cac_tag}-DOOR-{seg_idx}E",
                "kind": "door",
                "aabb": (sx1, y_aisle_0, 0.0, sx1 + 60.0, y_aisle_1, 2055.5),
            })

    # 6. Sprinklers (63 ceiling + 16 in-aisle)
    sprinklers = []
    idx = 0
    for j in range(7):
        y = 1500.0 + 3000.0 * j
        for i in range(9):
            x = 1500.0 + 3000.0 * i
            # Relocate out of 1500 mm column keep-out if needed (F-101 Detail 2)
            for _, cx, cy in COLUMN_CENTERS:
                if abs(x - cx) < 750.0 and abs(y - cy) < 750.0:
                    y_reloc = y - 600.0
                    x_reloc = x - 600.0
                    x, y = x_reloc, y_reloc
            idx += 1
            sprinklers.append({
                "tag": f"SPR-CEIL-{idx:02d}",
                "kind": "ceiling",
                "x": x,
                "y": y,
                "z_deflector": Z_CEIL_DEFLECTOR,
                "aabb": (x - 40.0, y - 40.0, Z_CEIL_DEFLECTOR, x + 40.0, y + 40.0, Z_SOFFIT),
            })
    # 16 in-aisle heads (8 in CAC-BC at y=7200, 8 in CAC-DE at y=12600)
    aisle_xs = [2700.0, 5100.0, 7500.0, 9600.0, 12300.0, 14700.0, 17100.0, 19000.0]
    a_idx = 0
    for y_aisle in (7200.0, 12600.0):
        for ax in aisle_xs:
            a_idx += 1
            sprinklers.append({
                "tag": f"SPR-AISLE-{a_idx:02d}",
                "kind": "in_aisle",
                "x": ax,
                "y": y_aisle,
                "z_deflector": 1890.0,
                "aabb": (ax - 40.0, y_aisle - 40.0, 1890.0, ax + 40.0, y_aisle + 40.0, 2000.0),
            })

    # 7. MEP Routes (axis-aligned straight segments)
    def make_tree(z_elev: float, include_perimeter: bool) -> list[dict[str, Any]]:
        segs: list[dict[str, Any]] = [
            # Entry from west wall (0, 9900) to trunk (900, 9900)
            {"p0": (ENTRY_X, ENTRY_Y, z_elev), "p1": (TRUNK_X, ENTRY_Y, z_elev), "zone": "overhead" if z_elev > 0 else "plenum"},
            # North trunk (900, 9900) -> (900, 15300)
            {"p0": (TRUNK_X, ENTRY_Y, z_elev), "p1": (TRUNK_X, 15300.0, z_elev), "zone": "overhead" if z_elev > 0 else "plenum"},
            # South trunk (900, 9900) -> (900, 4500)
            {"p0": (TRUNK_X, ENTRY_Y, z_elev), "p1": (TRUNK_X, 4500.0, z_elev), "zone": "overhead" if z_elev > 0 else "plenum"},
        ]
        # Three shared row headers at y = 4500, 9900, 15300
        for hy in HEADER_YS:
            segs.append({
                "p0": (TRUNK_X, hy, z_elev),
                "p1": (HEADER_END_X, hy, z_elev),
                "zone": "overhead" if z_elev > 0 else "plenum",
            })
        if include_perimeter:
            # Continue south trunk to perimeter CRAH header at y = 1200
            segs.append({
                "p0": (TRUNK_X, 4500.0, z_elev),
                "p1": (TRUNK_X, PERIM_CHW_Y, z_elev),
                "zone": "overhead" if z_elev > 0 else "plenum",
            })
            segs.append({
                "p0": (TRUNK_X, PERIM_CHW_Y, z_elev),
                "p1": (PERIM_CHW_END_X, PERIM_CHW_Y, z_elev),
                "zone": "overhead" if z_elev > 0 else "plenum",
            })
        return segs

    routes = {
        "busway": make_tree(Z_BUSWAY, include_perimeter=False),
        "tray": make_tree(Z_TRAY, include_perimeter=False),
        "chw": make_tree(Z_CHW, include_perimeter=True),
    }

    return {
        "racks": racks,
        "columns": columns,
        "crahs": crahs,
        "pdus": pdus,
        "access_floor": access_floor,
        "containment": containment,
        "sprinklers": sprinklers,
        "routes": routes,
    }


def _placement_matrix(cx_mm: float, cy_mm: float, z0_mm: float, yaw_rad: float = 0.0) -> np.ndarray:
    """4x4 homogeneous placement matrix with translations in METRES (ifcopenshell API convention)."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def _make_rect_extrusion(model, body_ctx, xdim_mm: float, ydim_mm: float, depth_mm: float):
    """Create an IFC4 SweptSolid representation using 2D profile points only."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        XDim=float(xdim_mm),
        YDim=float(ydim_mm),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=direction,
        Depth=float(depth_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _make_circle_extrusion(model, body_ctx, radius_mm: float, depth_mm: float):
    """Create a cylindrical IFC4 SweptSolid using 2D profile points only."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        Radius=float(radius_mm),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=direction,
        Depth=float(depth_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def build_ifc(out_path: str) -> None:
    """Build and validate the IFC4 model and write it to out_path."""
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.validate

    data = build_model_data()

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRES"})

    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Data Center Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    def add_box(ifc_class: str, name: str, aabb: tuple[float, ...], predefined_type: str | None = None,
                object_type: str | None = None, facing: str = "NORTH", pset_name: str | None = None,
                props: dict[str, Any] | None = None):
        el = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
        if predefined_type and hasattr(el, "PredefinedType"):
            el.PredefinedType = predefined_type
        if object_type and hasattr(el, "ObjectType"):
            el.ObjectType = object_type
        x0, y0, z0, x1, y1, z1 = aabb
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        yaw = math.pi if facing == "SOUTH" else 0.0
        rep = _make_rect_extrusion(model, body_ctx, x1 - x0, y1 - y0, z1 - z0)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=_placement_matrix(cx, cy, z0, yaw))
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        if pset_name and props:
            pset = ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)
        return el

    # Racks
    for r in data["racks"]:
        add_box(
            "IfcFurniture", r["tag"], r["aabb"],
            predefined_type="USERDEFINED", object_type="Rack", facing=r["facing"],
            pset_name="Pset_DCM_Rack",
            props={
                "Tag": r["tag"], "Row": r["row"], "Type": r["type"],
                "Width_mm": r["width"], "Depth_mm": r["depth"], "Height_mm": r["height"],
                "RU": 42, "Facing": r["facing"], "Power_kW": 8.0, "Load_kg": 1363.0,
            },
        )

    # Columns
    for c in data["columns"]:
        add_box("IfcColumn", c["tag"], c["aabb"], predefined_type="COLUMN", object_type="Column")

    # CRAHs
    for c in data["crahs"]:
        add_box(
            "IfcUnitaryEquipment", c["tag"], c["aabb"],
            predefined_type="AIRHANDLER", object_type="CRAH", facing=c["facing"],
            pset_name="Pset_DCM_CRAH",
            props={
                "Tag": c["tag"], "Placement": c["kind"], "Capacity_kW": c["capacity_kw"],
                "Airflow_m3h": c["airflow_m3h"], "Facing": c["facing"], "Service": c["service"],
            },
        )

    # PDUs
    for p in data["pdus"]:
        add_box(
            "IfcElectricDistributionBoard", p["tag"], p["aabb"],
            predefined_type="DISTRIBUTIONBOARD", object_type="PDU", facing=p["facing"],
            pset_name="Pset_DCM_PDU",
            props={
                "Tag": p["tag"], "ServesRow": p["row"], "Rating_kVA": 225.0,
                "Facing": p["facing"], "WorkingSpace_mm": 900.0, "DedicatedSpaceHeight_mm": 1800.0,
            },
        )

    # Access floor
    for f in data["access_floor"]:
        add_box("IfcCovering", f["tag"], f["aabb"], predefined_type="FLOORING", object_type="AccessFloor")

    # Containment
    for c in data["containment"]:
        if c["kind"] == "roof":
            add_box("IfcRoof", c["tag"], c["aabb"], predefined_type="FLAT_ROOF", object_type="ContainmentRoof")
        else:
            add_box("IfcDoor", c["tag"], c["aabb"], predefined_type="DOOR", object_type="ContainmentDoor")

    # Sprinklers
    for s in data["sprinklers"]:
        el = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFireSuppressionTerminal", name=s["tag"])
        el.PredefinedType = "SPRINKLER"
        el.ObjectType = "Sprinkler"
        x0, y0, z0, x1, y1, z1 = s["aabb"]
        rep = _make_circle_extrusion(model, body_ctx, 40.0, z1 - z0)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=_placement_matrix(s["x"], s["y"], z0))
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        pset = ifcopenshell.api.run("pset.add_pset", model, product=el, name="Pset_DCM_Sprinkler")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
            "Tag": s["tag"], "Kind": s["kind"], "DeflectorElevation_mm": s["z_deflector"], "Standoff_mm": SPRINKLER_STANDOFF,
        })

    # MEP Route Segments
    svc_meta = {
        "tray": ("IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", 683.0, 127.0, "CT-1 683x127"),
        "busway": ("IfcCableSegment", "BUSBARSEGMENT", "Busway", 128.0, 147.0, "BW-1 128x147"),
        "chw": ("IfcPipeSegment", "RIGIDSEGMENT", "CHWPipe", 168.3, 168.3, "CHW-1 DN100 OD168.3"),
    }
    for svc, segs in data["routes"].items():
        ifc_cls, ptype, otype, w_mm, h_mm, sec_label = svc_meta[svc]
        for idx, seg in enumerate(segs, start=1):
            (x0, y0, z0), (x1, y1, z1) = seg["p0"], seg["p1"]
            dx, dy = x1 - x0, y1 - y0
            length_mm = math.hypot(dx, dy)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            tag = f"{svc.upper()}-SEG-{idx:02d}"
            if abs(dx) >= abs(dy):
                aabb = (min(x0, x1), cy - w_mm / 2.0, z0 - h_mm / 2.0, max(x0, x1), cy + w_mm / 2.0, z0 + h_mm / 2.0)
            else:
                aabb = (cx - w_mm / 2.0, min(y0, y1), z0 - h_mm / 2.0, cx + w_mm / 2.0, max(y0, y1), z0 + h_mm / 2.0)
            add_box(
                ifc_cls, tag, aabb,
                predefined_type=ptype, object_type=otype,
                pset_name="Pset_DCM_RouteSegment",
                props={
                    "Service": svc, "Tag": tag, "Section": sec_label,
                    "Elevation_mm": z0, "Zone": seg["zone"], "Length_mm": round(length_mm, 1),
                    "InsulatedOD_mm": 168.3 if svc == "chw" else 0.0,
                },
            )

    # Validate IFC4 schema & EXPRESS rules before writing
    logger = logging.getLogger("ifcopenshell.validate")
    ifcopenshell.validate.validate(model, logger, express_rules=True)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out))


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_ifc(out_file)
