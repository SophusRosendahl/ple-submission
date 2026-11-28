"""Coordinated 3D IFC4 model builder for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Builds the architectural/structural/MEP background from the 7-sheet drawing set
(A-101, A-301, A-601, A-602, E-101, F-101, M-101) and routes three clash-free,
code-compliant MEP services (Telecom Cable Tray CT-1, Power Busway BW-1,
Chilled Water CHW-1) as connected axis-aligned networks.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
from __future__ import annotations

import logging
import math
import os
import sys
import numpy as np

# ---------------------------------------------------------------------------
# Drawing-extracted constants (all dimensions in mm unless noted)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
TILE = 600.0

SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0
FLOOR_TOP_Z = 0.0
SOFFIT_Z = 3600.0
CEILING_DEFLECTOR_Z = 3574.6  # 25.4 mm below soffit
IN_AISLE_DEFLECTOR_Z = 1890.0  # 110 mm below containment roof underside
MIN_HEADROOM_Z = 2600.0
SPRINKLER_STANDOFF = 460.0

# Structural columns: 600 x 600 mm, full clear height (0..3600)
COL_SIZE = 600.0
COL_XS = (8400.0, 16800.0, 25200.0)
COL_YS = (8400.0, 16800.0)

# Cabinet rows (A-101 & A-601)
ROW_START_X = 1800.0  # Tile D
CROSS_AISLE_EAST_X = 11400.0  # Common east edge of cross aisle
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

BAY_WIDTHS = {
    "C1": 600.0,
    "N1": 800.0,
    "CU": 600.0,
    "SP": 600.0,
    "-600": 600.0,
    "-800": 800.0,
}

# (row_name, y_cl, facing, bay_sequence)
ROW_SPECS = [
    ("A", 3000.0, "SOUTH", [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH", [("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1), ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH", [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH", [("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1), ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4)]),
]

# Perimeter CRAHs (A-601): 1200 W x 900 D x 2000 H, facing NORTH, Y=0..900
PERIM_CRAHS = [
    ("CRAH-01", 600.0),    # B01
    ("CRAH-02", 9000.0),   # P01
    ("CRAH-03", 16800.0),  # AC01
    ("CRAH-04", 25200.0),  # AQ01
]

# PDUs (A-601 & A-101 Note 8): 762 W x 813 D x 1959 H, front flush with served row front face
PDU_W, PDU_D, PDU_H = 762.0, 813.0, 1959.0
PDU_SPECS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),        # AJ05, front at Y=2400
    ("PDU-02", "B", 21600.0, 6600.0 - 813.0, "NORTH"),  # AK10, front at Y=6600
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),        # AJ14, front at Y=7800
    ("PDU-04", "D", 21600.0, 12000.0 - 813.0, "NORTH"),  # AK19, front at Y=12000
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),       # AJ23, front at Y=13200
    ("PDU-06", "F", 21600.0, 17400.0 - 813.0, "NORTH"),  # AK28, front at Y=17400
]

# Cold-Aisle Containment (A-602 & A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5

# Service section dimensions (A-602, E-101, M-101)
CT_W, CT_H = 683.0, 127.0
BW_W, BW_H = 128.0, 147.0
CHW_BARE_OD = 114.3
CHW_INSUL_THK = 25.4
CHW_OD = 168.3  # ASTM C585 jacket OD coordinated for clash

# Service elevations (centrelines, mm above FF)
CT_Z = -236.5    # Under-floor plenum: Z = -300.0 .. -173.0 (138 mm clear below -35 floor panel)
BW_Z = 2693.5    # Overhead Tier 1:    Z = 2620.0 .. 2767.0 (20 mm above 2600 headroom)
CHW_Z = 2934.15  # Overhead Tier 2:    Z = 2850.0 .. 3018.3 (96.3 mm below 3114.6 standoff)

SERVICE_ENTRY_X = 0.0
SERVICE_ENTRY_Y = 9900.0


def build_geometry_data() -> dict:
    """Build deterministic pure-geometry data for all background elements and MEP routes."""
    racks = []
    crahs = []
    row_extents = {}

    # 1. Cabinet rows & in-row CRAHs
    for rname, y_cl, facing, seq in ROW_SPECS:
        x = ROW_START_X
        cab_num = 0
        crah_num = 0
        y0 = y_cl - CAB_DEPTH / 2.0
        y1 = y_cl + CAB_DEPTH / 2.0
        ca_west = None
        for kind, count in seq:
            if kind == "CA":
                ca_west = x
                x = CROSS_AISLE_EAST_X
                continue
            w = BAY_WIDTHS[kind]
            for _ in range(count):
                if kind in ("C1", "N1"):
                    cab_num += 1
                    racks.append({
                        "tag": f"RACK-{rname}{cab_num:02d}",
                        "row": rname,
                        "type": kind,
                        "facing": facing,
                        "width": w,
                        "depth": CAB_DEPTH,
                        "height": CAB_HEIGHT,
                        "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                    })
                elif kind == "CU":
                    crah_num += 1
                    crahs.append({
                        "tag": f"CRAH-{rname}{crah_num:02d}",
                        "placement": f"ROW {rname}",
                        "facing": facing,
                        "width": w,
                        "depth": CAB_DEPTH,
                        "height": CAB_HEIGHT,
                        "capacity_kw": 50.0,
                        "service": "CHILLED WATER, DN50",
                        "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                    })
                x += w
        row_extents[rname] = (ROW_START_X, ca_west, CROSS_AISLE_EAST_X, x)

    # 2. Perimeter CRAHs
    for tag, x0 in PERIM_CRAHS:
        crahs.append({
            "tag": tag,
            "placement": "PERIMETER",
            "facing": "NORTH",
            "width": 1200.0,
            "depth": 900.0,
            "height": 2000.0,
            "capacity_kw": 100.0,
            "service": "CHILLED WATER, DN100",
            "aabb": (x0, 0.0, 0.0, x0 + 1200.0, 900.0, 2000.0),
        })

    # 3. Structural columns
    columns = []
    for ci, cx in enumerate(COL_XS):
        g_let = chr(ord("A") + ci)
        for ri, cy in enumerate(COL_YS):
            g_num = ri + 1
            columns.append({
                "tag": f"COL-{g_let}{g_num}",
                "width": COL_SIZE,
                "depth": COL_SIZE,
                "height": SOFFIT_Z,
                "aabb": (cx - COL_SIZE / 2, cy - COL_SIZE / 2, 0.0,
                         cx + COL_SIZE / 2, cy + COL_SIZE / 2, SOFFIT_Z),
            })

    # 4. PDUs
    pdus = []
    for tag, rname, x0, y0, facing in PDU_SPECS:
        pdus.append({
            "tag": tag,
            "serves_row": rname,
            "facing": facing,
            "width": PDU_W,
            "depth": PDU_D,
            "height": PDU_H,
            "rating_kva": 225.0,
            "aabb": (x0, y0, 0.0, x0 + PDU_W, y0 + PDU_D, PDU_H),
        })

    # 5. Cold-Aisle Containment (CAC-BC at Y=7200, CAC-DE at Y=12600)
    containment_roofs = []
    containment_doors = []
    cac_specs = [
        ("CAC-BC", "B", "C", 7200.0),
        ("CAC-DE", "D", "E", 12600.0),
    ]
    for tag, r1, r2, y_cl in cac_specs:
        x_w0 = ROW_START_X
        x_w1 = min(row_extents[r1][1], row_extents[r2][1])
        x_e0 = CROSS_AISLE_EAST_X
        x_e1 = min(row_extents[r1][3], row_extents[r2][3])
        for side, xa, xb in (("W", x_w0, x_w1), ("E", x_e0, x_e1)):
            containment_roofs.append({
                "tag": f"{tag}-ROOF-{side}",
                "aisle": tag,
                "aabb": (xa, y_cl - CAC_ROOF_W / 2, CAC_ROOF_Z,
                         xb, y_cl + CAC_ROOF_W / 2, CAC_ROOF_Z + CAC_ROOF_THK),
            })
            # End doors at west and east ends of each roof panel
            containment_doors.append({
                "tag": f"{tag}-DOOR-{side}1",
                "aisle": tag,
                "aabb": (xa, y_cl - CAC_DOOR_W / 2, 0.0,
                         xa + CAC_DOOR_THK, y_cl + CAC_DOOR_W / 2, CAC_DOOR_H),
            })
            containment_doors.append({
                "tag": f"{tag}-DOOR-{side}2",
                "aisle": tag,
                "aabb": (xb - CAC_DOOR_THK, y_cl - CAC_DOOR_W / 2, 0.0,
                         xb, y_cl + CAC_DOOR_W / 2, CAC_DOOR_H),
            })

    # 6. Access floor panel (Z = -35..0)
    access_floor = [{
        "tag": "ACCESS-FLOOR",
        "aabb": (0.0, 0.0, -FLOOR_THK, ROOM_W, ROOM_D, FLOOR_TOP_Z),
    }]

    # 7. Sprinklers (63 ceiling + 16 in-aisle = 79)
    sprinklers = []
    sp_idx = 0
    for j in range(7):
        sy = 1500.0 + j * 3000.0
        for i in range(9):
            sx = 1500.0 + i * 3000.0
            # Relocate heads within 750 mm of a structural column (F-101 Note 3 & Detail 2)
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sx -= 600.0
            sp_idx += 1
            sprinklers.append({
                "tag": f"SPR-CEIL-{sp_idx:02d}",
                "kind": "CeilingSprinkler",
                "x": sx,
                "y": sy,
                "z": CEILING_DEFLECTOR_Z,
            })

    ia_idx = 0
    for tag, y_cl in (("CAC-BC", 7200.0), ("CAC-DE", 12600.0)):
        for sx in (2400.0, 4800.0, 7200.0, 9600.0, 12300.0, 14700.0, 17100.0, 19000.0):
            ia_idx += 1
            sprinklers.append({
                "tag": f"SPR-AISLE-{ia_idx:02d}",
                "kind": "InAisleSprinkler",
                "aisle": tag,
                "x": sx,
                "y": y_cl,
                "z": IN_AISLE_DEFLECTOR_Z,
            })

    # 8. MEP Services — connected axis-aligned straight segments
    # Hot-aisle centrelines: Y=4500 (Rows A/B), Y=9900 (Rows C/D), Y=15300 (Rows E/F)
    hot_aisles = (4500.0, 9900.0, 15300.0)
    branch_end_x = 18600.0  # Covers >93% of every row

    def make_seg(svc, idx, p0, p1, w, h, tier):
        return {
            "tag": f"{svc}-{idx:02d}",
            "service": svc,
            "p0": p0,
            "p1": p1,
            "width": w,
            "height": h,
            "tier": tier,
        }

    # Cable Tray (CT-1) — Under-floor plenum (Z = -236.5)
    ct_trunk_x = 900.0
    ct_segs = [
        make_seg("CT", 1, (0.0, 9900.0, CT_Z), (ct_trunk_x, 9900.0, CT_Z), CT_W, CT_H, "UnderFloor"),
        make_seg("CT", 2, (ct_trunk_x, 4500.0, CT_Z), (ct_trunk_x, 15300.0, CT_Z), CT_W, CT_H, "UnderFloor"),
    ]
    for k, ay in enumerate(hot_aisles, start=3):
        ct_segs.append(make_seg("CT", k, (ct_trunk_x, ay, CT_Z), (branch_end_x, ay, CT_Z), CT_W, CT_H, "UnderFloor"))

    # Busway (BW-1) — Overhead Tier 1 (Z = 2693.5)
    bw_trunk_x = 400.0
    bw_segs = [
        make_seg("BW", 1, (0.0, 9900.0, BW_Z), (bw_trunk_x, 9900.0, BW_Z), BW_W, BW_H, "OverheadTier1"),
        make_seg("BW", 2, (bw_trunk_x, 4500.0, BW_Z), (bw_trunk_x, 15300.0, BW_Z), BW_W, BW_H, "OverheadTier1"),
    ]
    for k, ay in enumerate(hot_aisles, start=3):
        bw_segs.append(make_seg("BW", k, (bw_trunk_x, ay, BW_Z), (branch_end_x, ay, BW_Z), BW_W, BW_H, "OverheadTier1"))

    # Chilled Water (CHW-1) — Overhead Tier 2 (Z = 2934.15)
    chw_trunk_x = 800.0
    chw_segs = [
        make_seg("CHW", 1, (0.0, 9900.0, CHW_Z), (chw_trunk_x, 9900.0, CHW_Z), CHW_OD, CHW_OD, "OverheadTier2"),
        make_seg("CHW", 2, (chw_trunk_x, 1500.0, CHW_Z), (chw_trunk_x, 15300.0, CHW_Z), CHW_OD, CHW_OD, "OverheadTier2"),
        # South perimeter CRAH header (serves CRAH-01..04 along Y=0..900, clears PDU-01 at Y>=2400)
        make_seg("CHW", 3, (chw_trunk_x, 1500.0, CHW_Z), (25800.0, 1500.0, CHW_Z), CHW_OD, CHW_OD, "OverheadTier2"),
    ]
    for k, ay in enumerate(hot_aisles, start=4):
        chw_segs.append(make_seg("CHW", k, (chw_trunk_x, ay, CHW_Z), (branch_end_x, ay, CHW_Z), CHW_OD, CHW_OD, "OverheadTier2"))

    return {
        "racks": racks,
        "crahs": crahs,
        "columns": columns,
        "pdus": pdus,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "access_floor": access_floor,
        "sprinklers": sprinklers,
        "services": {
            "CT": ct_segs,
            "BW": bw_segs,
            "CHW": chw_segs,
        },
    }


# ---------------------------------------------------------------------------
# IFC4 Model Builder (requires ifcopenshell==0.8.4)
# ---------------------------------------------------------------------------
def _placement_matrix(cx_mm: float, cy_mm: float, z_mm: float, rot_z_deg: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for is_si=True)."""
    rad = math.radians(rot_z_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def _add_rect_solid(model, body_ctx, product, xdim: float, ydim: float, zdim: float,
                    cx: float, cy: float, zmin: float, rot_z_deg: float = 0.0):
    import ifcopenshell.api

    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=float(xdim), YDim=float(ydim))
    pos = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=direction,
        Depth=float(zdim),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.run("geometry.assign_representation", model, product=product, representation=rep)
    mat = _placement_matrix(cx, cy, zmin, rot_z_deg)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=product, matrix=mat, is_si=True)


def _add_pipe_solid(model, body_ctx, product, p0, p1, od: float):
    import ifcopenshell.api

    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)

    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(od / 2.0))
    pos = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=direction,
        Depth=float(length),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.run("geometry.assign_representation", model, product=product, representation=rep)

    # Orthonormal right-handed basis mapping local +Z to segment direction
    m = np.eye(4, dtype=float)
    if abs(dx) >= abs(dy):
        sx = 1.0 if dx >= 0 else -1.0
        # local Z = (sx, 0, 0), local X = (0, sx, 0), local Y = (0, 0, 1)
        m[:3, 0] = [0.0, sx, 0.0]
        m[:3, 1] = [0.0, 0.0, 1.0]
        m[:3, 2] = [sx, 0.0, 0.0]
    else:
        sy = 1.0 if dy >= 0 else -1.0
        # local Z = (0, sy, 0), local X = (0, 0, 1), local Y = (sy, 0, 0)
        m[:3, 0] = [0.0, 0.0, 1.0]
        m[:3, 1] = [sy, 0.0, 0.0]
        m[:3, 2] = [0.0, sy, 0.0]
    m[0, 3] = x0 / 1000.0
    m[1, 3] = y0 / 1000.0
    m[2, 3] = z0 / 1000.0
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=product, matrix=m, is_si=True)


def _add_pset(model, product, name: str, props: dict):
    import ifcopenshell.api

    ps = ifcopenshell.api.run("pset.add_pset", model, product=product, name=name)
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)


def build_ifc(out_path: str):
    import ifcopenshell
    import ifcopenshell.api
    import ifcopenshell.validate

    data = build_geometry_data()

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRE"})

    model_ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Phase 1")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Data Hall Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    def create_el(ifc_class, name, predefined=None, obj_type=None):
        el = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
        if predefined is not None and hasattr(el, "PredefinedType"):
            el.PredefinedType = predefined
        if obj_type is not None and hasattr(el, "ObjectType"):
            el.ObjectType = obj_type
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[el])
        return el

    # 1. Access floor
    af = data["access_floor"][0]
    el = create_el("IfcSlab", af["tag"], predefined="FLOOR", obj_type="AccessFloor")
    _add_rect_solid(model, body_ctx, el, ROOM_W, ROOM_D, FLOOR_THK, ROOM_W / 2, ROOM_D / 2, -FLOOR_THK)
    _add_pset(model, el, "Pset_DCM_AccessFloor", {"TileSize_mm": 600.0, "PanelThickness_mm": FLOOR_THK, "PlenumDepth_mm": 865.0})

    # 2. Structural columns
    for col in data["columns"]:
        x0, y0, z0, x1, y1, z1 = col["aabb"]
        el = create_el("IfcColumn", col["tag"], predefined="COLUMN", obj_type="StructuralColumn")
        _add_rect_solid(model, body_ctx, el, x1 - x0, y1 - y0, z1 - z0, (x0 + x1) / 2, (y0 + y1) / 2, z0)

    # 3. Racks (IfcFurniture / USERDEFINED / "Rack")
    for r in data["racks"]:
        x0, y0, z0, x1, y1, z1 = r["aabb"]
        rot = 0.0 if r["facing"] == "NORTH" else 180.0
        el = create_el("IfcFurniture", r["tag"], predefined="USERDEFINED", obj_type="Rack")
        _add_rect_solid(model, body_ctx, el, r["width"], r["depth"], r["height"], (x0 + x1) / 2, (y0 + y1) / 2, z0, rot)
        _add_pset(model, el, "Pset_DCM_Rack", {
            "Row": r["row"],
            "CabinetType": r["type"],
            "Facing": r["facing"],
            "Width_mm": r["width"],
            "Depth_mm": r["depth"],
            "Height_mm": r["height"],
            "RU": 42,
            "Power_kW": 8.0,
        })

    # 4. CRAHs
    for c in data["crahs"]:
        x0, y0, z0, x1, y1, z1 = c["aabb"]
        rot = 0.0 if c["facing"] == "NORTH" else 180.0
        el = create_el("IfcUnitaryEquipment", c["tag"], predefined="AIRCONDITIONINGUNIT", obj_type="CRAH")
        _add_rect_solid(model, body_ctx, el, c["width"], c["depth"], c["height"], (x0 + x1) / 2, (y0 + y1) / 2, z0, rot)
        _add_pset(model, el, "Pset_DCM_CRAH", {
            "Placement": c["placement"],
            "Facing": c["facing"],
            "Capacity_kW": c["capacity_kw"],
            "Service": c["service"],
        })

    # 5. PDUs
    for p in data["pdus"]:
        x0, y0, z0, x1, y1, z1 = p["aabb"]
        rot = 0.0 if p["facing"] == "NORTH" else 180.0
        el = create_el("IfcElectricDistributionBoard", p["tag"], predefined="DISTRIBUTIONBOARD", obj_type="PDU")
        _add_rect_solid(model, body_ctx, el, p["width"], p["depth"], p["height"], (x0 + x1) / 2, (y0 + y1) / 2, z0, rot)
        _add_pset(model, el, "Pset_DCM_PDU", {
            "ServesRow": p["serves_row"],
            "Facing": p["facing"],
            "Rating_kVA": p["rating_kva"],
            "DedicatedSpaceAbove_mm": 1800.0,
        })

    # 6. Cold-Aisle Containment
    for rf in data["containment_roofs"]:
        x0, y0, z0, x1, y1, z1 = rf["aabb"]
        el = create_el("IfcBuildingElementProxy", rf["tag"], predefined="USERDEFINED", obj_type="ContainmentRoof")
        _add_rect_solid(model, body_ctx, el, x1 - x0, y1 - y0, z1 - z0, (x0 + x1) / 2, (y0 + y1) / 2, z0)
        _add_pset(model, el, "Pset_DCM_Containment", {"Aisle": rf["aisle"], "Component": "Roof"})

    for dr in data["containment_doors"]:
        x0, y0, z0, x1, y1, z1 = dr["aabb"]
        el = create_el("IfcBuildingElementProxy", dr["tag"], predefined="USERDEFINED", obj_type="ContainmentDoor")
        _add_rect_solid(model, body_ctx, el, x1 - x0, y1 - y0, z1 - z0, (x0 + x1) / 2, (y0 + y1) / 2, z0)
        _add_pset(model, el, "Pset_DCM_Containment", {"Aisle": dr["aisle"], "Component": "EndDoor"})

    # 7. Sprinklers
    for sp in data["sprinklers"]:
        el = create_el("IfcFireSuppressionTerminal", sp["tag"], predefined="SPRINKLER", obj_type=sp["kind"])
        _add_rect_solid(model, body_ctx, el, 50.0, 50.0, 25.0, sp["x"], sp["y"], sp["z"])
        _add_pset(model, el, "Pset_DCM_Sprinkler", {
            "Kind": sp["kind"],
            "DeflectorElevation_mm": sp["z"],
            "StandoffBelow_mm": SPRINKLER_STANDOFF,
        })

    # 8. MEP Services
    for s in data["services"]["CT"]:
        x0, y0, z0 = s["p0"]
        x1, y1, z1 = s["p1"]
        if abs(x1 - x0) >= abs(y1 - y0):
            dx, dy = abs(x1 - x0), s["width"]
        else:
            dx, dy = s["width"], abs(y1 - y0)
        el = create_el("IfcCableCarrierSegment", s["tag"], predefined="CABLETRAYSEGMENT", obj_type="CableTray")
        _add_rect_solid(model, body_ctx, el, dx, dy, s["height"], (x0 + x1) / 2, (y0 + y1) / 2, z0 - s["height"] / 2)
        _add_pset(model, el, "Pset_DCM_ServiceSegment", {
            "Service": "CT-1",
            "Tier": s["tier"],
            "Elevation_mm": z0,
            "Width_mm": s["width"],
            "Height_mm": s["height"],
        })

    for s in data["services"]["BW"]:
        x0, y0, z0 = s["p0"]
        x1, y1, z1 = s["p1"]
        if abs(x1 - x0) >= abs(y1 - y0):
            dx, dy = abs(x1 - x0), s["width"]
        else:
            dx, dy = s["width"], abs(y1 - y0)
        el = create_el("IfcCableSegment", s["tag"], predefined="BUSBARSEGMENT", obj_type="Busway")
        _add_rect_solid(model, body_ctx, el, dx, dy, s["height"], (x0 + x1) / 2, (y0 + y1) / 2, z0 - s["height"] / 2)
        _add_pset(model, el, "Pset_DCM_ServiceSegment", {
            "Service": "BW-1",
            "Tier": s["tier"],
            "Elevation_mm": z0,
            "Width_mm": s["width"],
            "Height_mm": s["height"],
            "MaxSupportSpacing_mm": 1500.0,
        })

    for s in data["services"]["CHW"]:
        el = create_el("IfcPipeSegment", s["tag"], predefined="RIGIDSEGMENT", obj_type="ChilledWaterPipe")
        _add_pipe_solid(model, body_ctx, el, s["p0"], s["p1"], s["width"])
        _add_pset(model, el, "Pset_DCM_ServiceSegment", {
            "Service": "CHW-1",
            "Tier": s["tier"],
            "Elevation_mm": s["p0"][2],
            "BareOD_mm": CHW_BARE_OD,
            "InsulationThickness_mm": CHW_INSUL_THK,
            "InsulatedOD_mm": CHW_OD,
        })

    # Validate against IFC4 express rules before writing
    logger = logging.getLogger("validate")
    ifcopenshell.validate.validate(model, logger, express_rules=True)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_ifc(OUT_PATH)
