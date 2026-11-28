"""Data Hall 1 (hall_seed000_d000) coordinated MEP model builder.

Builds the complete IFC4 model of Data Hall 1 (27000 x 21000 mm, 128 cabinets,
22 CRAHs, 6 PDUs, 6 structural columns, access floor, cold-aisle containment,
63 ceiling + 16 in-aisle sprinklers, and clash-free routed Telecom Cable Tray,
Power Busway, and Chilled-Water Pipe networks) using ifcopenshell==0.8.4 + numpy.

Usage:
    python3 output/solution.py [OUT_PATH]
"""

import json
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 1. DRAWING-EXTRACTED CONSTANTS (all dimensions in mm)
# ---------------------------------------------------------------------------

ROOM_W = 27000.0
ROOM_D = 21000.0
TILE = 600.0

FF_Z = 0.0
SLAB_TOP_Z = -900.0
ACCESS_FLOOR_THK = 35.0
PLENUM_CLEAR_Z = -35.0 - 20.0  # -55.0 mm max top of under-floor pathway
SOFFIT_Z = 3600.0
MIN_CLEAR_HEIGHT_Z = 2600.0
SPRINKLER_DEFLECTOR_Z = 3574.6  # 25.4 mm below soffit
SPRINKLER_STANDOFF = 460.0
OVERHEAD_MAX_Z = SPRINKLER_DEFLECTOR_Z - SPRINKLER_STANDOFF  # 3114.6 mm

COL_SIZE = 400.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

ROW_START_X = 1800.0  # Tile D
CROSS_AISLE_EAST_X = 11200.0  # Common east edge of cross aisle for all rows
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
C1_W = 600.0
N1_W = 800.0
CU_W = 600.0
SP_W = 600.0

# Row definitions: (name, y_centre, facing, west_bays, east_bays)
# Facing: "SOUTH" (-Y, rot=180 deg) or "NORTH" (+Y, rot=0 deg)
ROW_DEFS = [
    (
        "A", 3000.0, "SOUTH",
        [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
        [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    (
        "B", 6000.0, "NORTH",
        [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
        [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    (
        "C", 8400.0, "SOUTH",
        [("C1", 3), ("CU", 1), ("C1", 6), ("OMIT600", 2), ("CU", 1)],
        [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT600", 2), ("C1", 3)],
    ),
    (
        "D", 11400.0, "NORTH",
        [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
        [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    (
        "E", 13800.0, "SOUTH",
        [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
        [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    (
        "F", 16800.0, "NORTH",
        [("C1", 4), ("CU", 1), ("C1", 5), ("OMIT600", 2), ("CU", 1)],
        [("N1", 2), ("C1", 5), ("SP", 1), ("OMIT600", 1), ("CU", 1), ("C1", 4)],
    ),
]

# Perimeter CRAHs: (tag, x_sw, y_sw, w, d, h, facing)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs: (tag, serves_row, x_sw, y_sw, w, d, h, facing)
# Front flush with front face of the row it serves
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, PDU_W, PDU_D, PDU_H, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, PDU_W, PDU_D, PDU_H, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, PDU_W, PDU_D, PDU_H, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, PDU_W, PDU_D, PDU_H, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, PDU_W, PDU_D, PDU_H, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, PDU_W, PDU_D, PDU_H, "NORTH"),
]

# Cold-Aisle Containment (CAC-BC and CAC-DE)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5
CAC_AISLES = [
    ("CAC-BC", 7200.0, [(1800.0, 9600.0), (11200.0, 19200.0)]),
    ("CAC-DE", 12600.0, [(1800.0, 9800.0), (11200.0, 19000.0)]),
]

# Pathway section dimensions
CT_W = 683.0
CT_H = 127.0
BW_W = 128.0
BW_H = 147.0
CHW_BARE_OD = 114.3
CHW_INS_OD = 168.3  # Coordinated OD including 25.4 mm insulation + jacket

# Service entry on West wall
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Service elevations (centreline Z)
BW_Z = 2693.5   # Overhead: z = 2620.0 .. 2767.0 (clear >= 2600, standoff >= 807)
CT_Z = -300.0   # Under-floor: z = -363.5 .. -236.5 (201.5 mm below panel, >= 20 mm)
CHW_Z = -650.0  # Under-floor: z = -734.15 .. -565.85 (202.35 mm below CT, 165.85 mm above slab)


# ---------------------------------------------------------------------------
# 2. GEOMETRY GENERATION HELPERS (PURE DATA, TESTABLE WITHOUT IFCOPENSHELL)
# ---------------------------------------------------------------------------

def build_layout_data() -> Dict:
    """Compute exact 3D bounding boxes and metadata for all architectural & MEP items."""
    racks = []
    inrow_crahs = []
    row_extents = {}

    for row_name, y_c, facing, west_bays, east_bays in ROW_DEFS:
        rack_idx = 0
        crah_idx = 0
        y_sw = y_c - CAB_DEPTH / 2.0

        def place_bays(x_start: float, bays: List[Tuple[str, int]]) -> float:
            nonlocal rack_idx, crah_idx
            x = x_start
            for btype, count in bays:
                for _ in range(count):
                    if btype == "C1":
                        rack_idx += 1
                        racks.append({
                            "tag": f"RACK-{row_name}{rack_idx:02d}",
                            "row": row_name,
                            "bay_type": "C1",
                            "x": x, "y": y_sw, "z": 0.0,
                            "w": C1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                            "facing": facing,
                        })
                        x += C1_W
                    elif btype == "N1":
                        rack_idx += 1
                        racks.append({
                            "tag": f"RACK-{row_name}{rack_idx:02d}",
                            "row": row_name,
                            "bay_type": "N1",
                            "x": x, "y": y_sw, "z": 0.0,
                            "w": N1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                            "facing": facing,
                        })
                        x += N1_W
                    elif btype == "CU":
                        crah_idx += 1
                        inrow_crahs.append({
                            "tag": f"CRAH-{row_name}{crah_idx:02d}",
                            "row": row_name,
                            "placement": "IN-ROW",
                            "x": x, "y": y_sw, "z": 0.0,
                            "w": CU_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                            "facing": facing,
                            "capacity_kw": 50.0,
                            "airflow_m3h": 9000.0,
                            "service": "CHILLED WATER, DN50",
                        })
                        x += CU_W
                    elif btype == "SP":
                        x += SP_W
                    elif btype == "OMIT600":
                        x += 600.0
            return x

        west_end = place_bays(ROW_START_X, west_bays)
        east_end = place_bays(CROSS_AISLE_EAST_X, east_bays)
        row_extents[row_name] = {
            "y_c": y_c,
            "x_min": ROW_START_X,
            "x_max": east_end,
            "west_end": west_end,
        }

    # Columns
    columns = []
    for ci, cx in enumerate(COL_XS):
        for ri, cy in enumerate(COL_YS):
            columns.append({
                "tag": f"COL-{chr(65 + ci)}{ri + 1}",
                "x": cx - COL_SIZE / 2.0,
                "y": cy - COL_SIZE / 2.0,
                "z": 0.0,
                "w": COL_SIZE,
                "d": COL_SIZE,
                "h": SOFFIT_Z,
            })

    # Ceiling sprinklers (63 heads: 9 x 7 grid, relocated if within 600 mm of column centre)
    ceiling_sprinklers = []
    idx = 0
    for ix in range(9):
        sx = 1500.0 + ix * 3000.0
        for iy in range(7):
            sy = 1500.0 + iy * 3000.0
            # Relocate if obstructed by column keep-out (750 mm half-width per F-101 Detail 2)
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sy = cy - 900.0  # Relocate south clear of column keep-out
            idx += 1
            ceiling_sprinklers.append({
                "tag": f"SPR-C{idx:02d}",
                "x": sx, "y": sy, "z": SPRINKLER_DEFLECTOR_Z,
                "zone": "CEILING",
            })

    # In-aisle sprinklers (16 heads: 8 in CAC-BC, 8 in CAC-DE)
    in_aisle_sprinklers = []
    ia_idx = 0
    for tag, y_c, spans in CAC_AISLES:
        for (x0, x1) in spans:
            length = x1 - x0
            for k in range(4):
                sx = x0 + (k + 0.5) * (length / 4.0)
                ia_idx += 1
                in_aisle_sprinklers.append({
                    "tag": f"SPR-IA{ia_idx:02d}",
                    "x": sx, "y": y_c, "z": 1890.0,
                    "zone": tag,
                })

    # Containment roofs & end doors
    containment_roofs = []
    containment_doors = []
    for tag, y_c, spans in CAC_AISLES:
        for pi, (x0, x1) in enumerate(spans):
            containment_roofs.append({
                "tag": f"{tag}-ROOF-{pi + 1}",
                "x": x0, "y": y_c - CAC_ROOF_W / 2.0, "z": CAC_ROOF_Z,
                "w": x1 - x0, "d": CAC_ROOF_W, "h": CAC_ROOF_THK,
            })
            containment_doors.append({
                "tag": f"{tag}-DOOR-{pi * 2 + 1}",
                "x": x0 - CAC_DOOR_THK, "y": y_c - CAC_DOOR_W / 2.0, "z": 0.0,
                "w": CAC_DOOR_THK, "d": CAC_DOOR_W, "h": CAC_DOOR_H,
            })
            containment_doors.append({
                "tag": f"{tag}-DOOR-{pi * 2 + 2}",
                "x": x1, "y": y_c - CAC_DOOR_W / 2.0, "z": 0.0,
                "w": CAC_DOOR_THK, "d": CAC_DOOR_W, "h": CAC_DOOR_H,
            })

    # -----------------------------------------------------------------------
    # 3. MEP ROUTING (AXIS-ALIGNED SEGMENTS, CLASH-FREE, CONNECTED)
    # -----------------------------------------------------------------------
    # Helper to create axis-aligned segments: (p0, p1) where p = (x, y, z)
    busway_segs = []
    tray_segs = []
    chw_segs = []

    # Row branch Y offsets (clear of columns at y=8400, 16800):
    # Column footprint in Y is [8200, 8600] and [16600, 17000].
    # For Busway (half-width 64): y_c + 450 -> min y = 8786 > 8600 (clear!)
    # For Cable Tray (half-width 341.5): y_c + 600 -> min y = 8658.5 > 8600 (clear!)
    # For CHW (half-OD 84.15): y_c + 450 -> min y = 8765.85 > 8600 (clear!)
    row_names = ["A", "B", "C", "D", "E", "F"]

    # --- A. POWER BUSWAY (Overhead, z = BW_Z = 2693.5) ---
    # Entry at (0, 9900, BW_Z) -> trunk at x = 1200 -> branches east along each row
    bw_trunk_x = 1200.0
    bw_ys = [row_extents[r]["y_c"] + 450.0 for r in row_names]
    busway_segs.append(("BW-ENTRY", (ENTRY_X, ENTRY_Y, BW_Z), (bw_trunk_x, ENTRY_Y, BW_Z)))
    # North/South trunk along x = 1200 from Row A to Row F
    bw_trunk_pts = sorted(set(bw_ys + [ENTRY_Y]))
    for i in range(len(bw_trunk_pts) - 1):
        busway_segs.append((
            f"BW-TRUNK-{i + 1}",
            (bw_trunk_x, bw_trunk_pts[i], BW_Z),
            (bw_trunk_x, bw_trunk_pts[i + 1], BW_Z),
        ))
    # Row branches from trunk to east end of each row
    for r, by in zip(row_names, bw_ys):
        x_end = row_extents[r]["x_max"]
        busway_segs.append((f"BW-ROW-{r}", (bw_trunk_x, by, BW_Z), (x_end, by, BW_Z)))

    # --- B. TELECOM CABLE TRAY (Under-floor, z = CT_Z = -300.0) ---
    # Entry at (0, 9900, CT_Z) -> trunk at x = 1000 -> branches east along each row
    ct_trunk_x = 1000.0
    ct_ys = [row_extents[r]["y_c"] + 600.0 for r in row_names]
    tray_segs.append(("CT-ENTRY", (ENTRY_X, ENTRY_Y, CT_Z), (ct_trunk_x, ENTRY_Y, CT_Z)))
    ct_trunk_pts = sorted(set(ct_ys + [ENTRY_Y]))
    for i in range(len(ct_trunk_pts) - 1):
        tray_segs.append((
            f"CT-TRUNK-{i + 1}",
            (ct_trunk_x, ct_trunk_pts[i], CT_Z),
            (ct_trunk_x, ct_trunk_pts[i + 1], CT_Z),
        ))
    for r, cy in zip(row_names, ct_ys):
        x_end = row_extents[r]["x_max"]
        tray_segs.append((f"CT-ROW-{r}", (ct_trunk_x, cy, CT_Z), (x_end, cy, CT_Z)))

    # --- C. CHILLED WATER PIPE (Under-floor, z = CHW_Z = -650.0) ---
    # Entry at (0, 9900, CHW_Z) -> trunk at x = 1200 -> branches east along each row
    # PLUS south extension to y = 450 and perimeter header east to CRAH-04 (x = 25800)
    chw_trunk_x = 1200.0
    chw_ys = [row_extents[r]["y_c"] + 450.0 for r in row_names]
    perim_y = 450.0
    chw_segs.append(("CHW-ENTRY", (ENTRY_X, ENTRY_Y, CHW_Z), (chw_trunk_x, ENTRY_Y, CHW_Z)))
    chw_trunk_pts = sorted(set([perim_y] + chw_ys + [ENTRY_Y]))
    for i in range(len(chw_trunk_pts) - 1):
        chw_segs.append((
            f"CHW-TRUNK-{i + 1}",
            (chw_trunk_x, chw_trunk_pts[i], CHW_Z),
            (chw_trunk_x, chw_trunk_pts[i + 1], CHW_Z),
        ))
    # Row headers (serve all 6 rows + all 18 in-row CRAHs)
    for r, wy in zip(row_names, chw_ys):
        x_end = row_extents[r]["x_max"]
        chw_segs.append((f"CHW-ROW-{r}", (chw_trunk_x, wy, CHW_Z), (x_end, wy, CHW_Z)))
    # Perimeter CRAH header (serves CRAH-01 at 1200, CRAH-02 at 9600, CRAH-03 at 17400, CRAH-04 at 25800)
    chw_segs.append(("CHW-PERIM", (chw_trunk_x, perim_y, CHW_Z), (25800.0, perim_y, CHW_Z)))

    return {
        "racks": racks,
        "inrow_crahs": inrow_crahs,
        "perimeter_crahs": [
            {
                "tag": t, "placement": "PERIMETER",
                "x": x, "y": y, "z": 0.0, "w": w, "d": d, "h": h,
                "facing": f, "capacity_kw": 100.0, "airflow_m3h": 20000.0,
                "service": "CHILLED WATER, DN100",
            }
            for (t, x, y, w, d, h, f) in PERIMETER_CRAHS
        ],
        "pdus": [
            {
                "tag": t, "serves_row": sr,
                "x": x, "y": y, "z": 0.0, "w": w, "d": d, "h": h,
                "facing": f, "rating_kva": 225.0,
            }
            for (t, sr, x, y, w, d, h, f) in PDUS
        ],
        "columns": columns,
        "ceiling_sprinklers": ceiling_sprinklers,
        "in_aisle_sprinklers": in_aisle_sprinklers,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "row_extents": row_extents,
        "busway_segs": busway_segs,
        "tray_segs": tray_segs,
        "chw_segs": chw_segs,
    }


# ---------------------------------------------------------------------------
# 3. IFC4 MODEL BUILDER (ifcopenshell==0.8.4)
# ---------------------------------------------------------------------------

def make_matrix(tx_mm: float, ty_mm: float, tz_mm: float, rot_z_deg: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for is_si=True)."""
    rad = math.radians(rot_z_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = tx_mm / 1000.0
    m[1, 3] = ty_mm / 1000.0
    m[2, 3] = tz_mm / 1000.0
    return m


def add_box(model, body_ctx, storey, ifc_class: str, name: str,
            x: float, y: float, z: float, w: float, d: float, h: float,
            facing: str = "NORTH", predefined_type: str = None,
            object_type: str = None, pset_name: str = None, pset_props: Dict = None):
    """Create an extruded rectangular solid centred in XY at footprint centre, rotated by facing."""
    import ifcopenshell.api

    elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if predefined_type is not None and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type is not None and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    ifcopenshell.api.run("spatial.assign_container", model, products=[elem], relating_structure=storey)

    # Local extruded box: centred at (0, 0) in XY, spanning z = 0..h
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w),
        YDim=float(d),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(h),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    cx = x + w / 2.0
    cy = y + d / 2.0
    rot = 180.0 if facing == "SOUTH" else 0.0
    mat = make_matrix(cx, cy, z, rot)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=mat, is_si=True)

    if pset_name and pset_props:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
    return elem


def add_cylinder_z(model, body_ctx, storey, ifc_class: str, name: str,
                   cx: float, cy: float, z0: float, radius: float, height: float,
                   predefined_type: str = None, object_type: str = None,
                   pset_name: str = None, pset_props: Dict = None):
    """Create a vertical cylinder extruded along +Z."""
    import ifcopenshell.api

    elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if predefined_type is not None and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type is not None and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    ifcopenshell.api.run("spatial.assign_container", model, products=[elem], relating_structure=storey)

    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(height),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    mat = make_matrix(cx, cy, z0, 0.0)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=mat, is_si=True)

    if pset_name and pset_props:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
    return elem


def add_segment(model, body_ctx, storey, ifc_class: str, name: str,
                p0: Tuple[float, float, float], p1: Tuple[float, float, float],
                sec_w: float, sec_h: float, is_round: bool = False,
                predefined_type: str = None, object_type: str = None,
                pset_name: str = None, pset_props: Dict = None):
    """Create a straight axis-aligned MEP segment from p0 to p1."""
    import ifcopenshell.api

    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-3:
        return None

    elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if predefined_type is not None and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type is not None and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    ifcopenshell.api.run("spatial.assign_container", model, products=[elem], relating_structure=storey)

    if is_round:
        profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(sec_w / 2.0))
    else:
        # Local extrusion is along +Z; local X = width, local Y = height
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=float(sec_w),
            YDim=float(sec_h),
        )

    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
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
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    # Build orthonormal frame: local Z = segment axis, local Y = world +Z (for horizontal runs)
    uz = np.array([dx / length, dy / length, dz / length], dtype=float)
    if abs(uz[2]) < 0.99:
        uy = np.array([0.0, 0.0, 1.0], dtype=float)
        ux = np.cross(uy, uz)
        ux = ux / np.linalg.norm(ux)
        uy = np.cross(uz, ux)
    else:
        ux = np.array([1.0, 0.0, 0.0], dtype=float)
        uy = np.cross(uz, ux)
        uy = uy / np.linalg.norm(uy)

    mat = np.eye(4, dtype=float)
    mat[0:3, 0] = ux
    mat[0:3, 1] = uy
    mat[0:3, 2] = uz
    mat[0, 3] = p0[0] / 1000.0
    mat[1, 3] = p0[1] / 1000.0
    mat[2, 3] = p0[2] / 1000.0

    ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=mat, is_si=True)

    if pset_name and pset_props:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
    return elem


def write_reconciliation_log(out_ifc_path: str) -> None:
    """Write optional drawing-note reconciliation log next to the IFC."""
    rec_path = Path(out_ifc_path).parent / "reconciliation.json"
    data = {
        "project": "Meridian Data Center - Phase 1 - Data Hall 1 (hall_seed000_d000)",
        "sheets_reconciled": ["A-101", "A-301", "A-601", "A-602", "E-101", "F-101", "M-101"],
        "notes": [
            {"sheet": "A-101", "item": "Room footprint", "value_mm": [27000, 21000], "applied": "Access floor 0..27000 x 0..21000"},
            {"sheet": "A-101", "item": "Cross aisle east edge", "value_mm": 11200, "applied": "Common east edge of CA for all 6 rows"},
            {"sheet": "A-301", "item": "Access floor panel", "value_mm": 35, "applied": "z = -35 to 0; plenum below to -900"},
            {"sheet": "A-301", "item": "Under-floor clearance", "value_mm": 20, "applied": "Tray top at -236.5 mm (201.5 mm below panel)"},
            {"sheet": "A-301", "item": "Minimum clear height", "value_mm": 2600, "applied": "Busway bottom at 2620 mm"},
            {"sheet": "A-301/F-101", "item": "Sprinkler standoff", "value_mm": 460, "applied": "Busway top at 2767 mm (807.6 mm below deflector)"},
            {"sheet": "A-602/E-101", "item": "Tray-busway separation", "value_mm": 300, "applied": "Busway overhead (2693.5), Tray under-floor (-300.0): 2856.5 mm clear"},
            {"sheet": "E-101/M-101", "item": "PDU dedicated space", "value_mm": 1800, "applied": "CHW routed under-floor (-650.0), zero piping above PDUs"},
            {"sheet": "M-101", "item": "CHW insulated OD", "value_mm": 168.3, "applied": "Modelled at full 168.3 mm OD for clash coordination"},
        ],
    }
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def build_ifc(out_path: str) -> None:
    import ifcopenshell
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    layout = build_layout_data()

    # 1. Access Floor Panel (z = -35..0)
    add_box(
        model, body_ctx, storey, "IfcSlab", "AccessFloor",
        0.0, 0.0, -ACCESS_FLOOR_THK, ROOM_W, ROOM_D, ACCESS_FLOOR_THK,
        predefined_type="FLOOR", object_type="AccessFloor",
    )

    # 2. Structural Columns (z = 0..3600)
    for col in layout["columns"]:
        add_box(
            model, body_ctx, storey, "IfcColumn", col["tag"],
            col["x"], col["y"], col["z"], col["w"], col["d"], col["h"],
            predefined_type="COLUMN", object_type="StructuralColumn",
        )

    # 3. Server Cabinets (128 racks)
    for r in layout["racks"]:
        add_box(
            model, body_ctx, storey, "IfcFurniture", r["tag"],
            r["x"], r["y"], r["z"], r["w"], r["d"], r["h"],
            facing=r["facing"], predefined_type="USERDEFINED", object_type="Rack",
            pset_name="Pset_DCM_Rack",
            pset_props={
                "Row": r["row"],
                "BayType": r["bay_type"],
                "RU": 42,
                "Facing": r["facing"],
                "PowerKW": 8.0,
                "LoadKg": 1363.0,
            },
        )

    # 4. CRAH Units (4 perimeter + 18 in-row = 22)
    for c in layout["perimeter_crahs"] + layout["inrow_crahs"]:
        add_box(
            model, body_ctx, storey, "IfcUnitaryEquipment", c["tag"],
            c["x"], c["y"], c["z"], c["w"], c["d"], c["h"],
            facing=c["facing"], predefined_type="AIRHANDLER", object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": c["placement"],
                "CapacityKW": c["capacity_kw"],
                "AirflowM3H": c["airflow_m3h"],
                "Facing": c["facing"],
                "Service": c["service"],
            },
        )

    # 5. PDUs (6 units)
    for p in layout["pdus"]:
        add_box(
            model, body_ctx, storey, "IfcElectricDistributionBoard", p["tag"],
            p["x"], p["y"], p["z"], p["w"], p["d"], p["h"],
            facing=p["facing"], predefined_type="DISTRIBUTIONBOARD", object_type="PDU",
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": p["serves_row"],
                "RatingKVA": p["rating_kva"],
                "Facing": p["facing"],
                "DedicatedSpaceMM": 1800.0,
            },
        )

    # 6. Cold-Aisle Containment (Roofs + End Doors)
    for rf in layout["containment_roofs"]:
        add_box(
            model, body_ctx, storey, "IfcCovering", rf["tag"],
            rf["x"], rf["y"], rf["z"], rf["w"], rf["d"], rf["h"],
            predefined_type="CEILING", object_type="ContainmentRoof",
        )
    for dr in layout["containment_doors"]:
        add_box(
            model, body_ctx, storey, "IfcDoor", dr["tag"],
            dr["x"], dr["y"], dr["z"], dr["w"], dr["d"], dr["h"],
            predefined_type="DOOR", object_type="ContainmentDoor",
        )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle)
    for sp in layout["ceiling_sprinklers"]:
        add_cylinder_z(
            model, body_ctx, storey, "IfcFireSuppressionTerminal", sp["tag"],
            sp["x"], sp["y"], sp["z"], 25.0, 25.4,
            predefined_type="SPRINKLER", object_type="SprinklerHead",
            pset_name="Pset_DCM_Sprinkler",
            pset_props={"DeflectorElevationMM": sp["z"], "StandoffMM": SPRINKLER_STANDOFF, "Zone": "CEILING"},
        )
    for sp in layout["in_aisle_sprinklers"]:
        add_cylinder_z(
            model, body_ctx, storey, "IfcFireSuppressionTerminal", sp["tag"],
            sp["x"], sp["y"], sp["z"], 25.0, 110.0,
            predefined_type="SPRINKLER", object_type="InAisleSprinklerHead",
            pset_name="Pset_DCM_Sprinkler",
            pset_props={"DeflectorElevationMM": sp["z"], "StandoffMM": SPRINKLER_STANDOFF, "Zone": sp["zone"]},
        )

    # 8. Overhead Power Busway (BW-1: 128 x 147 mm, z = 2693.5)
    for name, p0, p1 in layout["busway_segs"]:
        add_segment(
            model, body_ctx, storey, "IfcCableSegment", name,
            p0, p1, BW_W, BW_H, is_round=False,
            predefined_type="BUSBARSEGMENT", object_type="Busway",
            pset_name="Pset_DCM_MEP",
            pset_props={"Service": "Power", "Tag": "BW-1", "Zone": "OVERHEAD", "ElevationMM": BW_Z},
        )

    # 9. Under-Floor Telecom Cable Tray (CT-1: 683 x 127 mm, z = -300.0)
    for name, p0, p1 in layout["tray_segs"]:
        add_segment(
            model, body_ctx, storey, "IfcCableCarrierSegment", name,
            p0, p1, CT_W, CT_H, is_round=False,
            predefined_type="CABLETRAYSEGMENT", object_type="CableTray",
            pset_name="Pset_DCM_MEP",
            pset_props={"Service": "Telecom", "Tag": "CT-1", "Zone": "UNDERFLOOR", "ElevationMM": CT_Z},
        )

    # 10. Under-Floor Chilled Water Pipe (CHW-1: OD 168.3 mm, z = -650.0)
    for name, p0, p1 in layout["chw_segs"]:
        add_segment(
            model, body_ctx, storey, "IfcPipeSegment", name,
            p0, p1, CHW_INS_OD, CHW_INS_OD, is_round=True,
            predefined_type="RIGIDSEGMENT", object_type="ChilledWaterPipe",
            pset_name="Pset_DCM_MEP",
            pset_props={
                "Service": "ChilledWater",
                "Tag": "CHW-1",
                "NominalDiameterMM": 100.0,
                "InsulatedODMM": CHW_INS_OD,
                "Zone": "UNDERFLOOR",
                "ElevationMM": CHW_Z,
            },
        )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    model.write(out_path)
    write_reconciliation_log(out_path)


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_ifc(out_file)
