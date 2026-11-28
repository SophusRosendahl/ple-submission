"""Coordinated 3D IFC4 model builder for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Rebuilds the architectural/structural/MEP coordination background from the 7-sheet
drawing set (A-101, A-301, A-601, A-602, M-101, E-101, F-101) and routes the three
MEP services (telecom cable tray CT-1, power busway BW-1, chilled-water pipe CHW-1)
clash-free and code-compliant.

Usage:
    python3 output/solution.py [output_ifc_path]
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Baked-in drawing data (all dimensions in millimetres, origin at SW corner,
# Finished Floor = 0, +X = East, +Y = North, +Z = Up)
# ---------------------------------------------------------------------------

HALL_W = 27000.0
HALL_D = 21000.0
SLAB_Z = -900.0
ACCESS_FLOOR_THK = 35.0
PLENUM_CLEAR_TOP = -55.0  # 20 mm clear below -35 mm panel underside (A-301)
CLEAR_HEIGHT_MIN = 2600.0
SOFFIT_Z = 3600.0
CEIL_DEFLECTOR_Z = 3574.6  # 25.4 mm below +3600 soffit (A-301)
SPRINKLER_STANDOFF = 460.0
OVERHEAD_MAX_Z = CEIL_DEFLECTOR_Z - SPRINKLER_STANDOFF  # 3114.6 mm

COL_SIZE = 600.0
COL_XS = (8400.0, 16800.0, 25200.0)
COL_YS = (8400.0, 16800.0)

ROW_X_WEST = 1800.0
CROSS_AISLE_EAST_X = 11400.0  # Common east edge of cross aisle (A-101 Note 5)

# Row definitions: (row_id, y_center, facing, west_tokens, east_tokens)
# West tokens accumulate east from ROW_X_WEST; east tokens accumulate east from CROSS_AISLE_EAST_X.
ROW_SPECS = [
    ("A", 3000.0, "SOUTH", ["4C1", "CU", "3C1", "N1", "3C1", "CU"], ["6C1", "SP", "CU", "5C1"]),
    ("B", 6000.0, "NORTH", ["4C1", "CU", "5C1", "2N1", "CU"], ["7C1", "SP", "CU", "5C1"]),
    ("C", 8400.0, "SOUTH", ["3C1", "CU", "6C1", "2-600", "CU"], ["N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"]),
    ("D", 11400.0, "NORTH", ["4C1", "CU", "3C1", "2N1", "2C1", "CU"], ["7C1", "SP", "CU", "5C1"]),
    ("E", 13800.0, "SOUTH", ["4C1", "CU", "5C1", "N1", "C1", "CU"], ["6C1", "SP", "CU", "5C1"]),
    ("F", 16800.0, "NORTH", ["4C1", "CU", "5C1", "2-600", "CU"], ["2N1", "5C1", "SP", "-600", "CU", "4C1"]),
]

CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
CAB_RU = 42
CAB_KW = 8.0
CAB_LOAD_KG = 1363.0

# Perimeter CRAHs (A-601, M-101): (tag, x_sw, y_sw)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-101 Note 8, A-601, E-101): (tag, serves_row, x_sw, y_sw, facing)
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_SPECS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21000.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Cold-Aisle Containment (A-602, A-301): (tag, y_center)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z0 = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5

# Pathway section dimensions (A-602, E-101, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_BARE_OD = 114.3
CHW_INSUL_OD = 168.3  # ASTM C585 jacket over 25.4 mm min insulation (M-101 Note 4)

# Service elevations (z_center, mm relative to FF = 0)
# - Busway overhead in [2876.5, 3023.5]: >= 2600 clear height, >= 551.1 mm below ceiling deflector
# - Cable tray in under-floor plenum [-263.5, -136.5]: >= 81.5 mm below -55 mm plenum limit, > 3000 mm from busway
# - CHW pipe in under-floor plenum [-684.15, -515.85]: >= 215.85 mm above -900 slab, > 250 mm below cable tray
Z_BUSWAY = 2950.0
Z_TRAY = -200.0
Z_CHW = -600.0

SERVICE_ENTRY_XY = (0.0, 9900.0)


def _expand_tokens(tokens: list[str]) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for tok in tokens:
        if tok == "CU":
            out.append(("CU", 600.0))
        elif tok == "SP":
            out.append(("SP", 600.0))
        elif tok == "-600":
            out.append(("GAP", 600.0))
        elif tok == "2-600":
            out.extend([("GAP", 600.0), ("GAP", 600.0)])
        elif tok == "C1":
            out.append(("C1", 600.0))
        elif tok == "N1":
            out.append(("N1", 800.0))
        elif tok.endswith("C1"):
            out.extend([("C1", 600.0)] * int(tok[:-2]))
        elif tok.endswith("N1"):
            out.extend([("N1", 800.0)] * int(tok[:-2]))
        else:
            raise ValueError(f"Unknown bay token: {tok}")
    return out


def _make_route_segment(
    tag: str,
    service: str,
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    width: float,
    height: float,
    is_round: bool = False,
) -> dict[str, Any]:
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        raise ValueError(f"Zero-length segment {tag}")

    # Axis-aligned AABB
    if abs(dx) > 0:  # along X
        ax0, ax1 = min(x0, x1), max(x0, x1)
        ay0, ay1 = y0 - width / 2.0, y0 + width / 2.0
        az0, az1 = z0 - height / 2.0, z0 + height / 2.0
        axis = "X"
    elif abs(dy) > 0:  # along Y
        ax0, ax1 = x0 - width / 2.0, x0 + width / 2.0
        ay0, ay1 = min(y0, y1), max(y0, y1)
        az0, az1 = z0 - height / 2.0, z0 + height / 2.0
        axis = "Y"
    else:  # along Z
        ax0, ax1 = x0 - width / 2.0, x0 + width / 2.0
        ay0, ay1 = y0 - width / 2.0, y0 + width / 2.0
        az0, az1 = min(z0, z1), max(z0, z1)
        axis = "Z"

    return {
        "tag": tag,
        "service": service,
        "start": p0,
        "end": p1,
        "length": length,
        "axis": axis,
        "width": width,
        "height": height,
        "is_round": is_round,
        "z_center": 0.5 * (z0 + z1),
        "zone": "OVERHEAD" if z0 >= 0 else "PLENUM",
        "aabb": (ax0, ay0, az0, ax1, ay1, az1),
    }


def build_scene() -> dict[str, Any]:
    """Build all hall background elements and coordinated MEP routes in pure Python."""
    racks: list[dict[str, Any]] = []
    crahs: list[dict[str, Any]] = []
    row_west_ends: dict[str, float] = {}
    row_east_ends: dict[str, float] = {}

    # 1. Racks & In-Row CRAHs
    for row_id, yc, facing, west_toks, east_toks in ROW_SPECS:
        cab_idx = 0
        cu_idx = 0
        y0 = yc - CAB_DEPTH / 2.0
        y1 = yc + CAB_DEPTH / 2.0

        # West half
        x = ROW_X_WEST
        for kind, w in _expand_tokens(west_toks):
            if kind in ("C1", "N1"):
                cab_idx += 1
                racks.append({
                    "tag": f"RACK-{row_id}{cab_idx:02d}",
                    "row": row_id,
                    "type": kind,
                    "width": w,
                    "depth": CAB_DEPTH,
                    "height": CAB_HEIGHT,
                    "facing": facing,
                    "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                })
            elif kind == "CU":
                cu_idx += 1
                crahs.append({
                    "tag": f"CRAH-{row_id}{cu_idx:02d}",
                    "placement": f"IN-ROW-{row_id}",
                    "width": w,
                    "depth": CAB_DEPTH,
                    "height": CAB_HEIGHT,
                    "capacity_kw": 50.0,
                    "airflow_m3h": 9000.0,
                    "facing": facing,
                    "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                })
            x += w
        row_west_ends[row_id] = x

        # East half
        x = CROSS_AISLE_EAST_X
        for kind, w in _expand_tokens(east_toks):
            if kind in ("C1", "N1"):
                cab_idx += 1
                racks.append({
                    "tag": f"RACK-{row_id}{cab_idx:02d}",
                    "row": row_id,
                    "type": kind,
                    "width": w,
                    "depth": CAB_DEPTH,
                    "height": CAB_HEIGHT,
                    "facing": facing,
                    "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                })
            elif kind == "CU":
                cu_idx += 1
                crahs.append({
                    "tag": f"CRAH-{row_id}{cu_idx:02d}",
                    "placement": f"IN-ROW-{row_id}",
                    "width": w,
                    "depth": CAB_DEPTH,
                    "height": CAB_HEIGHT,
                    "capacity_kw": 50.0,
                    "airflow_m3h": 9000.0,
                    "facing": facing,
                    "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                })
            x += w
        row_east_ends[row_id] = x

    # Perimeter CRAHs
    for tag, x0, y0 in PERIMETER_CRAHS:
        crahs.append({
            "tag": tag,
            "placement": "PERIMETER",
            "width": 1200.0,
            "depth": 900.0,
            "height": 2000.0,
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
            "facing": "NORTH",
            "aabb": (x0, y0, 0.0, x0 + 1200.0, y0 + 900.0, 2000.0),
        })

    # 2. Structural Columns (FF = 0 to soffit +3600)
    columns: list[dict[str, Any]] = []
    for ci, cx in enumerate(COL_XS):
        for ri, cy in enumerate(COL_YS):
            col_label = f"COL-{chr(65 + ci)}{ri + 1}"
            columns.append({
                "tag": col_label,
                "cx": cx,
                "cy": cy,
                "size": COL_SIZE,
                "height": SOFFIT_Z,
                "aabb": (cx - COL_SIZE / 2.0, cy - COL_SIZE / 2.0, 0.0, cx + COL_SIZE / 2.0, cy + COL_SIZE / 2.0, SOFFIT_Z),
            })

    # 3. PDUs
    pdus: list[dict[str, Any]] = []
    for tag, row_id, x0, y0, facing in PDU_SPECS:
        pdus.append({
            "tag": tag,
            "serves_row": row_id,
            "width": PDU_W,
            "depth": PDU_D,
            "height": PDU_H,
            "rating_kva": 225.0,
            "facing": facing,
            "aabb": (x0, y0, 0.0, x0 + PDU_W, y0 + PDU_D, PDU_H),
        })

    # 4. Access Floor (35 mm panel, top at FF = 0)
    access_floor = {
        "tag": "AccessFloor",
        "aabb": (0.0, 0.0, -ACCESS_FLOOR_THK, HALL_W, HALL_D, 0.0),
    }

    # 5. Cold-Aisle Containment (CAC-BC at y=7200, CAC-DE at y=12600)
    containment_roofs: list[dict[str, Any]] = []
    containment_doors: list[dict[str, Any]] = []
    for cac_tag, r_south, r_north, yc in [
        ("CAC-BC", "B", "C", 7200.0),
        ("CAC-DE", "D", "E", 12600.0),
    ]:
        # West half spans from ROW_X_WEST to min(west_end)
        xw0 = ROW_X_WEST
        xw1 = min(row_west_ends[r_south], row_west_ends[r_north])
        # East half spans from CROSS_AISLE_EAST_X to min(east_end)
        xe0 = CROSS_AISLE_EAST_X
        xe1 = min(row_east_ends[r_south], row_east_ends[r_north])

        for half_label, hx0, hx1 in [("W", xw0, xw1), ("E", xe0, xe1)]:
            containment_roofs.append({
                "tag": f"{cac_tag}-ROOF-{half_label}",
                "aisle": cac_tag,
                "aabb": (hx0, yc - CAC_ROOF_W / 2.0, CAC_ROOF_Z0, hx1, yc + CAC_ROOF_W / 2.0, CAC_ROOF_Z0 + CAC_ROOF_THK),
            })
            # West & East end doors for this half (placed just outside roof ends to avoid overlapping roof)
            containment_doors.append({
                "tag": f"{cac_tag}-DOOR-{half_label}1",
                "aisle": cac_tag,
                "aabb": (hx0 - CAC_DOOR_THK, yc - CAC_DOOR_W / 2.0, 0.0, hx0, yc + CAC_DOOR_W / 2.0, CAC_DOOR_H),
            })
            containment_doors.append({
                "tag": f"{cac_tag}-DOOR-{half_label}2",
                "aisle": cac_tag,
                "aabb": (hx1, yc - CAC_DOOR_W / 2.0, 0.0, hx1 + CAC_DOOR_THK, yc + CAC_DOOR_W / 2.0, CAC_DOOR_H),
            })

    # 6. Sprinkler Heads (63 ceiling + 16 in-aisle = 79 total, F-101)
    sprinklers: list[dict[str, Any]] = []
    sp_idx = 0
    for i in range(9):
        nx = 1500.0 + 3000.0 * i
        for j in range(7):
            ny = 1500.0 + 3000.0 * j
            # Relocate if inside 1500 mm column keep-out (half-width 750 mm)
            x, y = nx, ny
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(x - cx) < 750.0 and abs(y - cy) < 750.0:
                        x = cx - 900.0 if x <= cx else cx + 900.0
                        y = cy - 900.0 if y <= cy else cy + 900.0
            sp_idx += 1
            sprinklers.append({
                "tag": f"SP-CEIL-{sp_idx:02d}",
                "kind": "ceiling",
                "x": x,
                "y": y,
                "z_deflector": CEIL_DEFLECTOR_Z,
            })

    # 16 in-aisle heads: 8 under CAC-BC (y=7200), 8 under CAC-DE (y=12600)
    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9300.0, 12300.0, 14700.0, 17100.0, 19200.0]
    ia_idx = 0
    for yc in (7200.0, 12600.0):
        for x in in_aisle_xs:
            ia_idx += 1
            sprinklers.append({
                "tag": f"SP-AISLE-{ia_idx:02d}",
                "kind": "in_aisle",
                "x": x,
                "y": yc,
                "z_deflector": 1890.0,
            })

    # 7. Coordinated MEP Routes (all axis-aligned, shortest shared hot-aisle spine)
    # Hot aisles at y = 4500 (serves Rows A & B), y = 9900 (serves Rows C & D), y = 15300 (serves Rows E & F).
    # West service trunk at x = 900 mm (clear of cabinets starting at x = 1800 and west wall x = 0).
    # Branches extend to x = 19500 mm (covers >= 96% of every row, clear of PDUs at x >= 21000).
    trunk_x = 900.0
    branch_x_end = 19500.0
    hot_aisle_ys = (4500.0, 9900.0, 15300.0)

    def build_comb(svc: str, prefix: str, z: float, w: float, h: float, is_round: bool) -> list[dict[str, Any]]:
        segs: list[dict[str, Any]] = []
        # Entry stub from (0, 9900, z) to (trunk_x, 9900, z)
        segs.append(_make_route_segment(f"{prefix}-ENTRY", svc, (0.0, 9900.0, z), (trunk_x, 9900.0, z), w, h, is_round))
        # North-South trunk in West service strip
        segs.append(_make_route_segment(f"{prefix}-TRUNK-S", svc, (trunk_x, 9900.0, z), (trunk_x, 4500.0, z), w, h, is_round))
        segs.append(_make_route_segment(f"{prefix}-TRUNK-N", svc, (trunk_x, 9900.0, z), (trunk_x, 15300.0, z), w, h, is_round))
        # 3 hot-aisle branches
        for idx, hy in enumerate(hot_aisle_ys, 1):
            segs.append(_make_route_segment(f"{prefix}-BR-{idx}", svc, (trunk_x, hy, z), (branch_x_end, hy, z), w, h, is_round))
        return segs

    telecom_segs = build_comb("telecom", "CT", Z_TRAY, TRAY_W, TRAY_H, is_round=False)
    busway_segs = build_comb("busway", "BW", Z_BUSWAY, BUSWAY_W, BUSWAY_H, is_round=False)
    chw_segs = build_comb("chw", "CHW", Z_CHW, CHW_INSUL_OD, CHW_INSUL_OD, is_round=True)

    # Extra CHW perimeter gallery branch for CRAH-01..04 (y = 1500, x = 900..24500)
    chw_segs.append(_make_route_segment("CHW-TRUNK-PERIM", "chw", (trunk_x, 4500.0, Z_CHW), (trunk_x, 1500.0, Z_CHW), CHW_INSUL_OD, CHW_INSUL_OD, is_round=True))
    chw_segs.append(_make_route_segment("CHW-PERIM-HDR", "chw", (trunk_x, 1500.0, Z_CHW), (24500.0, 1500.0, Z_CHW), CHW_INSUL_OD, CHW_INSUL_OD, is_round=True))

    return {
        "racks": racks,
        "columns": columns,
        "crahs": crahs,
        "pdus": pdus,
        "access_floor": access_floor,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "sprinklers": sprinklers,
        "routes": {
            "telecom": telecom_segs,
            "busway": busway_segs,
            "chw": chw_segs,
        },
    }


def _placement_matrix(cx_mm: float, cy_mm: float, z0_mm: float, rot_z_rad: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (ifcopenshell.api convention)."""
    c = math.cos(rot_z_rad)
    s = math.sin(rot_z_rad)
    mat = np.eye(4, dtype=float)
    mat[0, 0] = c
    mat[0, 1] = -s
    mat[1, 0] = s
    mat[1, 1] = c
    mat[0, 3] = cx_mm / 1000.0
    mat[1, 3] = cy_mm / 1000.0
    mat[2, 3] = z0_mm / 1000.0
    return mat


def _facing_angle(facing: str) -> float:
    return math.pi if facing == "SOUTH" else 0.0


def write_ifc(scene: dict[str, Any], out_path: str) -> None:
    """Author the IFC4 model using ifcopenshell==0.8.4 and write to out_path."""
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    model = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    ifcopenshell.api.unit.assign_unit(model, length={"is_metric": True, "raw": "MILLIMETRES"})

    ctx_model = ifcopenshell.api.context.add_context(model, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx_model
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Data Center")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    dir_z = model.createIfcDirection((0.0, 0.0, 1.0))

    def add_box(el, x_dim: float, y_dim: float, z_dim: float, cx: float, cy: float, z0: float, rot_z: float = 0.0):
        prof = model.createIfcRectangleProfileDef("AREA", None, None, float(x_dim), float(y_dim))
        solid = model.createIfcExtrudedAreaSolid(prof, None, dir_z, float(z_dim))
        rep = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        ifcopenshell.api.geometry.assign_representation(model, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=el, matrix=_placement_matrix(cx, cy, z0, rot_z))
        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[el])

    def add_cyl(el, radius: float, length: float, mat: np.ndarray):
        prof = model.createIfcCircleProfileDef("AREA", None, None, float(radius))
        solid = model.createIfcExtrudedAreaSolid(prof, None, dir_z, float(length))
        rep = model.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        ifcopenshell.api.geometry.assign_representation(model, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=el, matrix=mat)
        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[el])

    def add_pset(el, pset_name: str, props: dict[str, Any]):
        pset = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)

    # 1. Racks
    for r in scene["racks"]:
        x0, y0, z0, x1, y1, z1 = r["aabb"]
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcFurniture", predefined_type="USERDEFINED", name=r["tag"])
        el.ObjectType = "Rack"
        add_box(el, r["width"], r["depth"], r["height"], 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0, _facing_angle(r["facing"]))
        add_pset(el, "Pset_DCM_Rack", {
            "Tag": r["tag"],
            "Row": r["row"],
            "CabinetType": r["type"],
            "Width_mm": r["width"],
            "Depth_mm": r["depth"],
            "Height_mm": r["height"],
            "RU": CAB_RU,
            "Facing": r["facing"],
            "Power_kW": CAB_KW,
            "Load_kg": CAB_LOAD_KG,
        })

    # 2. Structural Columns
    for c in scene["columns"]:
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcColumn", predefined_type="COLUMN", name=c["tag"])
        el.ObjectType = "StructuralColumn"
        add_box(el, c["size"], c["size"], c["height"], c["cx"], c["cy"], 0.0)
        add_pset(el, "Pset_DCM_Column", {"Tag": c["tag"], "Width_mm": c["size"], "Depth_mm": c["size"], "Height_mm": c["height"]})

    # 3. CRAHs
    for u in scene["crahs"]:
        x0, y0, z0, x1, y1, z1 = u["aabb"]
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRCONDITIONINGUNIT", name=u["tag"])
        el.ObjectType = "CRAH"
        add_box(el, u["width"], u["depth"], u["height"], 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0, _facing_angle(u["facing"]))
        add_pset(el, "Pset_DCM_CRAH", {
            "Tag": u["tag"],
            "Placement": u["placement"],
            "Capacity_kW": u["capacity_kw"],
            "Airflow_m3h": u["airflow_m3h"],
            "Facing": u["facing"],
        })

    # 4. PDUs
    for p in scene["pdus"]:
        x0, y0, z0, x1, y1, z1 = p["aabb"]
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcElectricDistributionBoard", predefined_type="DISTRIBUTIONBOARD", name=p["tag"])
        el.ObjectType = "PDU"
        add_box(el, p["width"], p["depth"], p["height"], 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0, _facing_angle(p["facing"]))
        add_pset(el, "Pset_DCM_PDU", {
            "Tag": p["tag"],
            "ServesRow": p["serves_row"],
            "Rating_kVA": p["rating_kva"],
            "Facing": p["facing"],
            "DedicatedSpace_mm": 1800.0,
        })

    # 5. Access Floor
    af = scene["access_floor"]
    x0, y0, z0, x1, y1, z1 = af["aabb"]
    el_af = ifcopenshell.api.root.create_entity(model, ifc_class="IfcCovering", predefined_type="FLOORING", name=af["tag"])
    el_af.ObjectType = "AccessFloor"
    add_box(el_af, x1 - x0, y1 - y0, z1 - z0, 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0)
    add_pset(el_af, "Pset_DCM_AccessFloor", {"PanelThickness_mm": ACCESS_FLOOR_THK, "PlenumDepth_mm": 865.0})

    # 6. Containment Roofs & Doors
    for cr in scene["containment_roofs"]:
        x0, y0, z0, x1, y1, z1 = cr["aabb"]
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingElementProxy", predefined_type="USERDEFINED", name=cr["tag"])
        el.ObjectType = "ContainmentRoof"
        add_box(el, x1 - x0, y1 - y0, z1 - z0, 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0)
        add_pset(el, "Pset_DCM_Containment", {"Tag": cr["tag"], "Aisle": cr["aisle"], "Part": "Roof"})

    for cd in scene["containment_doors"]:
        x0, y0, z0, x1, y1, z1 = cd["aabb"]
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingElementProxy", predefined_type="USERDEFINED", name=cd["tag"])
        el.ObjectType = "ContainmentDoor"
        add_box(el, x1 - x0, y1 - y0, z1 - z0, 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0)
        add_pset(el, "Pset_DCM_Containment", {"Tag": cd["tag"], "Aisle": cd["aisle"], "Part": "EndDoor"})

    # 7. Sprinkler Heads (small pendent cylinder at deflector elevation)
    for sp in scene["sprinklers"]:
        el = ifcopenshell.api.root.create_entity(model, ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=sp["tag"])
        el.ObjectType = "CeilingSprinkler" if sp["kind"] == "ceiling" else "InAisleSprinkler"
        mat = _placement_matrix(sp["x"], sp["y"], sp["z_deflector"])
        add_cyl(el, 25.0, 25.4, mat)
        add_pset(el, "Pset_DCM_Sprinkler", {
            "Tag": sp["tag"],
            "Kind": sp["kind"],
            "DeflectorElevation_mm": sp["z_deflector"],
            "Standoff_mm": SPRINKLER_STANDOFF,
        })

    # 8. MEP Route Segments
    svc_meta = {
        "telecom": ("IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray"),
        "busway": ("IfcCableSegment", "BUSBARSEGMENT", "Busway"),
        "chw": ("IfcPipeSegment", "RIGIDSEGMENT", "ChilledWaterPipe"),
    }
    for svc, segs in scene["routes"].items():
        ifc_cls, predef, obj_type = svc_meta[svc]
        for seg in segs:
            el = ifcopenshell.api.root.create_entity(model, ifc_class=ifc_cls, predefined_type=predef, name=seg["tag"])
            el.ObjectType = obj_type
            x0, y0, z0, x1, y1, z1 = seg["aabb"]
            if seg["is_round"]:
                # Extrude cylinder along segment axis
                p0, p1 = seg["start"], seg["end"]
                mat = np.eye(4, dtype=float)
                if seg["axis"] == "X":
                    sx = 1.0 if p1[0] >= p0[0] else -1.0
                    # Local Z -> +X or -X
                    mat[:3, 0] = [0.0, 1.0, 0.0]
                    mat[:3, 1] = [0.0, 0.0, sx]
                    mat[:3, 2] = [sx, 0.0, 0.0]
                elif seg["axis"] == "Y":
                    sy = 1.0 if p1[1] >= p0[1] else -1.0
                    # Local Z -> +Y or -Y
                    mat[:3, 0] = [-sy, 0.0, 0.0]
                    mat[:3, 1] = [0.0, 0.0, 1.0]
                    mat[:3, 2] = [0.0, sy, 0.0]
                mat[0, 3] = p0[0] / 1000.0
                mat[1, 3] = p0[1] / 1000.0
                mat[2, 3] = p0[2] / 1000.0
                add_cyl(el, seg["width"] / 2.0, seg["length"], mat)
            else:
                add_box(el, x1 - x0, y1 - y0, z1 - z0, 0.5 * (x0 + x1), 0.5 * (y0 + y1), z0)

            props = {
                "Tag": seg["tag"],
                "Service": svc,
                "Elevation_mm": seg["z_center"],
                "Zone": seg["zone"],
                "Length_mm": seg["length"],
                "Width_mm": seg["width"],
                "Height_mm": seg["height"],
            }
            if svc == "chw":
                props["BareOD_mm"] = CHW_BARE_OD
                props["InsulatedOD_mm"] = CHW_INSUL_OD
            add_pset(el, "Pset_DCM_Pathway", props)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    out_ifc = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    scene_data = build_scene()
    write_ifc(scene_data, out_ifc)
