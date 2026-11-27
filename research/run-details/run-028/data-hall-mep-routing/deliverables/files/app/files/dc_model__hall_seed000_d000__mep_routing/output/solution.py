"""Meridian Data Center Phase 1 — Data Hall 1 (hall_seed000_d000)
Coordinated IFC4 model generator (background + clash-free MEP routing).

Usage:
    python3 output/solution.py [OUT_PATH]
Default OUT_PATH: output/model.ifc
"""

from __future__ import annotations

import math
import os
import sys
from typing import Any

import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model.ifc"
)

# ---------------------------------------------------------------------------
# 1. HALL & DATUM CONSTANTS (mm) — reconciled from A-101, A-301, A-601, A-602
# ---------------------------------------------------------------------------
HALL_W = 27000.0   # East-West (X)
HALL_D = 21000.0   # North-South (Y)
TILE = 600.0

Z_SLAB_TOP = -900.0
Z_FLOOR_BOT = -35.0
Z_FLOOR_TOP = 0.0
Z_MIN_CLEAR = 2600.0
Z_SOFFIT = 3600.0
Z_SPR_CEIL_DEFL = 3574.6   # 3600 - 25.4
Z_SPR_AISLE_DEFL = 1890.0  # 2000 - 110

# Structural columns: 600x600, full height 0..3600, on Grid (A,B,C) x (1,2)
COL_SIZE = 600.0
GRID_X = {"A": 8400.0, "B": 16800.0, "C": 25200.0}
GRID_Y = {"1": 8400.0, "2": 16800.0}

# Row Y-centrelines, facings, and bay sequences (west to east, west start x=1800)
# Cross-aisle east edge is common to every row at x = 11400 mm (A-101 Note 5).
ROW_START_X = 1800.0
CROSS_AISLE_EAST_X = 11400.0

ROW_SPECS = [
    # (row_id, y_center, facing, west_bays, east_bays)
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
        [("C1", 3), ("CU", 1), ("C1", 6), ("OMIT", 2), ("CU", 1)],
        [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT", 2), ("C1", 3)],
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
        [("C1", 4), ("CU", 1), ("C1", 5), ("OMIT", 2), ("CU", 1)],
        [("N1", 2), ("C1", 5), ("SP", 1), ("OMIT", 1), ("CU", 1), ("C1", 4)],
    ),
]

BAY_WIDTH = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "OMIT": 600.0}
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Perimeter CRAHs (A-601): 1200 x 900 x 2000, facing NORTH
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),      # B01
    ("CRAH-02", 9000.0, 0.0),     # P01
    ("CRAH-03", 16800.0, 0.0),    # AC01
    ("CRAH-04", 25200.0, 0.0),    # AQ01
]
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0

# PDUs (A-601, A-101 Note 8): 762 x 813 x 1959, front flush with served row front
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_SPECS = [
    # (tag, serves_row, x_sw, y_sw, facing)
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),          # AJ05, front at 2400
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),  # AK10, front at 6600
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),          # AJ14, front at 7800
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"), # AK19, front at 12000
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),         # AJ23, front at 13200
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"), # AK28, front at 17400
]

# Service section dimensions (A-602, E-101, M-101)
CT_W, CT_H = 683.0, 127.0          # Cable tray (Telecom)
BW_W, BW_H = 128.0, 147.0          # Busway (Power)
CHW_BARE_OD = 114.3
CHW_INSUL_THK = 25.4
CHW_OD = 168.3                     # Jacket OD over insulation (M-101 Note 4)

# Service elevations (centreline Z in mm)
Z_CT = 2900.0   # Overhead plenum: [2836.5, 2963.5] (>= 2600, <= 3114.6)
Z_BW = -200.0   # Under-floor plenum: [-273.5, -126.5] (>= -900, <= -55)
Z_CHW = -600.0  # Under-floor plenum: [-684.15, -515.85] (>= -900, <= -55)

# Entry point (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0


# ---------------------------------------------------------------------------
# 2. GEOMETRY DATA BUILDERS (pure Python / numpy, deterministic)
# ---------------------------------------------------------------------------
def build_scene_data() -> dict[str, list[dict[str, Any]]]:
    """Return all background elements and MEP route segments as plain dicts."""
    racks: list[dict[str, Any]] = []
    crahs: list[dict[str, Any]] = []
    pdus: list[dict[str, Any]] = []
    columns: list[dict[str, Any]] = []
    containment_roofs: list[dict[str, Any]] = []
    containment_doors: list[dict[str, Any]] = []
    sprinklers: list[dict[str, Any]] = []
    row_extents: dict[str, dict[str, float]] = {}

    # --- Racks & In-Row CRAHs ---
    for row_id, yc, facing, west_bays, east_bays in ROW_SPECS:
        rack_idx = 0
        crah_idx = 0
        x = ROW_START_X
        for kind, count in west_bays:
            w = BAY_WIDTH[kind]
            for _ in range(count):
                if kind in ("C1", "N1"):
                    rack_idx += 1
                    racks.append({
                        "name": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id,
                        "cab_type": kind,
                        "cx": x + w / 2.0,
                        "cy": yc,
                        "z0": 0.0,
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                elif kind == "CU":
                    crah_idx += 1
                    crahs.append({
                        "name": f"CRAH-{row_id}{crah_idx:02d}",
                        "placement": "IN_ROW",
                        "row": row_id,
                        "cx": x + w / 2.0,
                        "cy": yc,
                        "z0": 0.0,
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "airflow_m3h": 9000.0,
                    })
                x += w
        west_end_x = x

        x = CROSS_AISLE_EAST_X
        for kind, count in east_bays:
            w = BAY_WIDTH[kind]
            for _ in range(count):
                if kind in ("C1", "N1"):
                    rack_idx += 1
                    racks.append({
                        "name": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id,
                        "cab_type": kind,
                        "cx": x + w / 2.0,
                        "cy": yc,
                        "z0": 0.0,
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                elif kind == "CU":
                    crah_idx += 1
                    crahs.append({
                        "name": f"CRAH-{row_id}{crah_idx:02d}",
                        "placement": "IN_ROW",
                        "row": row_id,
                        "cx": x + w / 2.0,
                        "cy": yc,
                        "z0": 0.0,
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "airflow_m3h": 9000.0,
                    })
                x += w
        east_end_x = x
        row_extents[row_id] = {
            "y": yc,
            "x_min": ROW_START_X,
            "west_end_x": west_end_x,
            "east_start_x": CROSS_AISLE_EAST_X,
            "x_max": east_end_x,
        }

    # --- Perimeter CRAHs ---
    for name, x_sw, y_sw in PERIM_CRAHS:
        crahs.append({
            "name": name,
            "placement": "PERIMETER",
            "row": "PERIMETER",
            "cx": x_sw + PERIM_CRAH_W / 2.0,
            "cy": y_sw + PERIM_CRAH_D / 2.0,
            "z0": 0.0,
            "w": PERIM_CRAH_W,
            "d": PERIM_CRAH_D,
            "h": PERIM_CRAH_H,
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
        })

    # --- PDUs ---
    for tag, serves_row, x_sw, y_sw, facing in PDU_SPECS:
        pdus.append({
            "name": tag,
            "serves_row": serves_row,
            "cx": x_sw + PDU_W / 2.0,
            "cy": y_sw + PDU_D / 2.0,
            "z0": 0.0,
            "w": PDU_W,
            "d": PDU_D,
            "h": PDU_H,
            "facing": facing,
        })

    # --- Structural Columns ---
    for gx_name, gx in GRID_X.items():
        for gy_name, gy in GRID_Y.items():
            columns.append({
                "name": f"COL-{gx_name}{gy_name}",
                "cx": gx,
                "cy": gy,
                "z0": 0.0,
                "w": COL_SIZE,
                "d": COL_SIZE,
                "h": Z_SOFFIT,
            })

    # --- Cold-Aisle Containment (CAC-BC and CAC-DE) ---
    # Roof: width 1400 mm (100 mm overhang onto each cabinet top), z=2000..2055.5
    # Doors: 60 mm thick x 1200 mm wide x 2055.5 mm tall at each end of each panel
    cac_specs = [
        ("CAC-BC", 7200.0, min(row_extents["B"]["west_end_x"], row_extents["C"]["west_end_x"]),
         min(row_extents["B"]["x_max"], row_extents["C"]["x_max"])),
        ("CAC-DE", 12600.0, min(row_extents["D"]["west_end_x"], row_extents["E"]["west_end_x"]),
         min(row_extents["D"]["x_max"], row_extents["E"]["x_max"])),
    ]
    for cac_tag, yc, west_x_end, east_x_end in cac_specs:
        # West roof panel
        w_len = west_x_end - ROW_START_X
        containment_roofs.append({
            "name": f"{cac_tag}-ROOF-W",
            "cx": ROW_START_X + w_len / 2.0,
            "cy": yc,
            "z0": 2000.0,
            "w": w_len,
            "d": 1400.0,
            "h": 55.5,
        })
        # East roof panel
        e_len = east_x_end - CROSS_AISLE_EAST_X
        containment_roofs.append({
            "name": f"{cac_tag}-ROOF-E",
            "cx": CROSS_AISLE_EAST_X + e_len / 2.0,
            "cy": yc,
            "z0": 2000.0,
            "w": e_len,
            "d": 1400.0,
            "h": 55.5,
        })
        # 4 End doors (placed just outside panel ends so zero overlap with cabinets/roof)
        door_xs = [
            ROW_START_X - 30.0,
            west_x_end + 30.0,
            CROSS_AISLE_EAST_X - 30.0,
            east_x_end + 30.0,
        ]
        for idx, dx in enumerate(door_xs, 1):
            containment_doors.append({
                "name": f"{cac_tag}-DOOR-{idx}",
                "cx": dx,
                "cy": yc,
                "z0": 0.0,
                "w": 60.0,
                "d": 1200.0,
                "h": 2055.5,
            })

    # --- Ceiling Sprinklers (63 heads, F-101) ---
    # 9 x 7 grid at 1500 + 3000*i, relocated clear of 1500 mm column keep-out
    spr_idx = 0
    for iy in range(7):
        sy = 1500.0 + 3000.0 * iy
        for ix in range(9):
            sx = 1500.0 + 3000.0 * ix
            # Check column keep-out (750 mm half-width around column centre)
            for col in columns:
                if abs(sx - col["cx"]) < 750.0 and abs(sy - col["cy"]) < 750.0:
                    sx = col["cx"] - 900.0
                    sy = col["cy"] - 900.0
            spr_idx += 1
            sprinklers.append({
                "name": f"SPR-C{spr_idx:02d}",
                "location": "CEILING",
                "cx": sx,
                "cy": sy,
                "deflector_z": Z_SPR_CEIL_DEFL,
                "z0": Z_SPR_CEIL_DEFL,
                "h": Z_SOFFIT - Z_SPR_CEIL_DEFL,
                "r": 25.0,
            })

    # --- In-Aisle Sprinklers (16 heads, 8 per contained cold aisle, F-101) ---
    aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]
    aisle_idx = 0
    for yc in (7200.0, 12600.0):
        for sx in aisle_xs:
            aisle_idx += 1
            sprinklers.append({
                "name": f"SPR-A{aisle_idx:02d}",
                "location": "IN_AISLE",
                "cx": sx,
                "cy": yc,
                "deflector_z": Z_SPR_AISLE_DEFL,
                "z0": Z_SPR_AISLE_DEFL,
                "h": 2000.0 - Z_SPR_AISLE_DEFL,
                "r": 25.0,
            })

    # --- MEP Routes ---
    # Shared-aisle comb topology:
    #   Branch Y = 4500 serves Rows A (3000) & B (6000) (dist = 1500 mm <= 2500 mm)
    #   Branch Y = 9900 serves Rows C (8400) & D (11400) (dist = 1500 mm <= 2500 mm)
    #   Branch Y = 15300 serves Rows E (13800) & F (16800) (dist = 1500 mm <= 2500 mm)
    #   CHW also has south branch at Y = 1500 to X = 25500 for CRAH-01..04 (dist = 1050 mm)
    spine_x = 900.0
    branch_x_end = 17800.0  # covers 1800..17800 = 16000 mm (>=87% of every row, reaches CRAH-F03)

    def make_rect_seg(
        name: str, service: str, tag: str,
        p0: tuple[float, float, float], p1: tuple[float, float, float],
        width: float, height: float, zone: str,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "service": service,
            "tag": tag,
            "p0": p0,
            "p1": p1,
            "w": width,
            "h": height,
            "zone": zone,
            "shape": "RECT",
        }

    def make_pipe_seg(
        name: str, p0: tuple[float, float, float], p1: tuple[float, float, float],
        od: float, zone: str,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "service": "CHILLED_WATER",
            "tag": "CHW-1",
            "p0": p0,
            "p1": p1,
            "od": od,
            "zone": zone,
            "shape": "PIPE",
        }

    # Butt-jointed spine + branches: 0 mm gap (connected) and 0 mm overlap (clash-free)
    ct_hw = CT_W / 2.0
    bw_hw = BW_W / 2.0
    chw_r = CHW_OD / 2.0

    # 1. Telecom Cable Tray (CT-1) — Overhead at Z = 2900 mm
    ct_segs = [
        make_rect_seg("CT-ENTRY", "TELECOM", "CT-1", (ENTRY_X, ENTRY_Y, Z_CT), (spine_x - ct_hw, ENTRY_Y, Z_CT), CT_W, CT_H, "OVERHEAD"),
        make_rect_seg("CT-SPINE", "TELECOM", "CT-1", (spine_x, 4500.0 - ct_hw, Z_CT), (spine_x, 15300.0 + ct_hw, Z_CT), CT_W, CT_H, "OVERHEAD"),
        make_rect_seg("CT-BR-AB", "TELECOM", "CT-1", (spine_x + ct_hw, 4500.0, Z_CT), (branch_x_end, 4500.0, Z_CT), CT_W, CT_H, "OVERHEAD"),
        make_rect_seg("CT-BR-CD", "TELECOM", "CT-1", (spine_x + ct_hw, 9900.0, Z_CT), (branch_x_end, 9900.0, Z_CT), CT_W, CT_H, "OVERHEAD"),
        make_rect_seg("CT-BR-EF", "TELECOM", "CT-1", (spine_x + ct_hw, 15300.0, Z_CT), (branch_x_end, 15300.0, Z_CT), CT_W, CT_H, "OVERHEAD"),
    ]

    # 2. Power Busway (BW-1) — Under-floor plenum at Z = -200 mm
    bw_segs = [
        make_rect_seg("BW-ENTRY", "POWER", "BW-1", (ENTRY_X, ENTRY_Y, Z_BW), (spine_x - bw_hw, ENTRY_Y, Z_BW), BW_W, BW_H, "UNDERFLOOR"),
        make_rect_seg("BW-SPINE", "POWER", "BW-1", (spine_x, 4500.0 - bw_hw, Z_BW), (spine_x, 15300.0 + bw_hw, Z_BW), BW_W, BW_H, "UNDERFLOOR"),
        make_rect_seg("BW-BR-AB", "POWER", "BW-1", (spine_x + bw_hw, 4500.0, Z_BW), (branch_x_end, 4500.0, Z_BW), BW_W, BW_H, "UNDERFLOOR"),
        make_rect_seg("BW-BR-CD", "POWER", "BW-1", (spine_x + bw_hw, 9900.0, Z_BW), (branch_x_end, 9900.0, Z_BW), BW_W, BW_H, "UNDERFLOOR"),
        make_rect_seg("BW-BR-EF", "POWER", "BW-1", (spine_x + bw_hw, 15300.0, Z_BW), (branch_x_end, 15300.0, Z_BW), BW_W, BW_H, "UNDERFLOOR"),
    ]

    # 3. Chilled-Water Pipe (CHW-1) — Under-floor plenum at Z = -600 mm
    chw_segs = [
        make_pipe_seg("CHW-ENTRY", (ENTRY_X, ENTRY_Y, Z_CHW), (spine_x - chw_r, ENTRY_Y, Z_CHW), CHW_OD, "UNDERFLOOR"),
        make_pipe_seg("CHW-SPINE", (spine_x, 1500.0 - chw_r, Z_CHW), (spine_x, 15300.0 + chw_r, Z_CHW), CHW_OD, "UNDERFLOOR"),
        make_pipe_seg("CHW-BR-PERIM", (spine_x + chw_r, 1500.0, Z_CHW), (25500.0, 1500.0, Z_CHW), CHW_OD, "UNDERFLOOR"),
        make_pipe_seg("CHW-BR-AB", (spine_x + chw_r, 4500.0, Z_CHW), (branch_x_end, 4500.0, Z_CHW), CHW_OD, "UNDERFLOOR"),
        make_pipe_seg("CHW-BR-CD", (spine_x + chw_r, 9900.0, Z_CHW), (branch_x_end, 9900.0, Z_CHW), CHW_OD, "UNDERFLOOR"),
        make_pipe_seg("CHW-BR-EF", (spine_x + chw_r, 15300.0, Z_CHW), (branch_x_end, 15300.0, Z_CHW), CHW_OD, "UNDERFLOOR"),
    ]

    return {
        "racks": racks,
        "crahs": crahs,
        "pdus": pdus,
        "columns": columns,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "sprinklers": sprinklers,
        "ct_segs": ct_segs,
        "bw_segs": bw_segs,
        "chw_segs": chw_segs,
        "row_extents": row_extents,
    }


# ---------------------------------------------------------------------------
# 3. IFC4 MODEL GENERATION (ifcopenshell==0.8.4)
# ---------------------------------------------------------------------------
def _placement_matrix_m(cx_mm: float, cy_mm: float, z0_mm: float, yaw_deg: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for edit_object_placement)."""
    rad = math.radians(yaw_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def _make_box_rep(model: Any, body_ctx: Any, w: float, d: float, h: float) -> Any:
    """Create centered-XY extruded box (0..h in Z) in project units (mm), 2D profile."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        XDim=float(w),
        YDim=float(d),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=dir_z,
        Depth=float(h),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _make_cyl_rep(model: Any, body_ctx: Any, r: float, h: float) -> Any:
    """Create vertical cylinder (0..h in Z) in project units (mm), 2D profile."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        Radius=float(r),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=dir_z,
        Depth=float(h),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _segment_matrix_and_length(
    p0: tuple[float, float, float], p1: tuple[float, float, float]
) -> tuple[np.ndarray, float]:
    """Return 4x4 placement matrix (translations in metres) where local +Z is along p0->p1."""
    v = np.array(p1, dtype=float) - np.array(p0, dtype=float)
    length = float(np.linalg.norm(v))
    if length < 1e-6:
        raise ValueError(f"Zero-length segment: {p0} -> {p1}")
    z_axis = v / length
    # Choose local +Y to be world +Z for horizontal segments (so width is horizontal, height is vertical)
    if abs(z_axis[2]) < 0.99:
        y_axis = np.array([0.0, 0.0, 1.0])
        x_axis = np.cross(y_axis, z_axis)
        x_axis /= np.linalg.norm(x_axis)
        y_axis = np.cross(z_axis, x_axis)
    else:
        x_axis = np.array([1.0, 0.0, 0.0])
        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)
    m = np.eye(4, dtype=float)
    m[:3, 0] = x_axis
    m[:3, 1] = y_axis
    m[:3, 2] = z_axis
    m[0, 3] = p0[0] / 1000.0
    m[1, 3] = p0[1] / 1000.0
    m[2, 3] = p0[2] / 1000.0
    return m, length


def build_ifc(out_path: str) -> None:
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    scene = build_scene_data()
    model = ifcopenshell.file(schema="IFC4")

    # Project & units (millimetres)
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center Phase 1"
    )
    ifcopenshell.api.unit.assign_unit(
        model, length={"is_metric": True, "raw": "MILLIMETRES"}
    )

    # Geometric representation contexts
    ctx3d = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx3d,
    )

    # Spatial hierarchy
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Data Hall 1 Level 0"
    )
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    all_products: list[Any] = []

    def add_box_element(
        ifc_class: str,
        name: str,
        predefined_type: str | None,
        object_type: str | None,
        cx: float,
        cy: float,
        z0: float,
        w: float,
        d: float,
        h: float,
        yaw_deg: float = 0.0,
        pset_name: str | None = None,
        props: dict[str, Any] | None = None,
    ) -> Any:
        elem = ifcopenshell.api.root.create_entity(
            model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
        )
        if object_type is not None:
            elem.ObjectType = object_type
        rep = _make_box_rep(model, body_ctx, w, d, h)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=elem, matrix=_placement_matrix_m(cx, cy, z0, yaw_deg)
        )
        if pset_name and props:
            pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
            ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)
        all_products.append(elem)
        return elem

    # 1. Access Floor (-35..0)
    add_box_element(
        "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        HALL_W / 2.0, HALL_D / 2.0, Z_FLOOR_BOT, HALL_W, HALL_D, 35.0,
    )

    # 2. Structural Columns (0..3600)
    for col in scene["columns"]:
        add_box_element(
            "IfcColumn", col["name"], "COLUMN", "StructuralColumn",
            col["cx"], col["cy"], col["z0"], col["w"], col["d"], col["h"],
        )

    # 3. Racks (128)
    for r in scene["racks"]:
        yaw = 0.0 if r["facing"] == "NORTH" else 180.0
        add_box_element(
            "IfcFurniture", r["name"], "USERDEFINED", "Rack",
            r["cx"], r["cy"], r["z0"], r["w"], r["d"], r["h"],
            yaw_deg=yaw,
            pset_name="Pset_DCM_Rack",
            props={
                "Row": r["row"],
                "CabinetType": r["cab_type"],
                "Width_mm": float(r["w"]),
                "Depth_mm": float(r["d"]),
                "Height_mm": float(r["h"]),
                "RU": 42,
                "Facing": r["facing"],
                "Power_kW": 8.0,
                "Load_kg": 1363.0,
            },
        )

    # 4. CRAHs (4 perimeter + 18 in-row = 22)
    for c in scene["crahs"]:
        yaw = 0.0 if c["facing"] == "NORTH" else 180.0
        add_box_element(
            "IfcUnitaryEquipment", c["name"], "AIRCONDITIONINGUNIT", "CRAH",
            c["cx"], c["cy"], c["z0"], c["w"], c["d"], c["h"],
            yaw_deg=yaw,
            pset_name="Pset_DCM_CRAH",
            props={
                "Placement": c["placement"],
                "Row": c["row"],
                "Capacity_kW": float(c["capacity_kw"]),
                "Airflow_m3h": float(c["airflow_m3h"]),
                "Facing": c["facing"],
            },
        )

    # 5. PDUs (6)
    for p in scene["pdus"]:
        yaw = 0.0 if p["facing"] == "NORTH" else 180.0
        add_box_element(
            "IfcElectricDistributionBoard", p["name"], "DISTRIBUTIONBOARD", "PDU",
            p["cx"], p["cy"], p["z0"], p["w"], p["d"], p["h"],
            yaw_deg=yaw,
            pset_name="Pset_DCM_PDU",
            props={
                "ServesRow": p["serves_row"],
                "Rating_kVA": 225.0,
                "Facing": p["facing"],
                "WorkingSpace_mm": 900.0,
                "DedicatedSpaceAbove_mm": 1800.0,
            },
        )

    # 6. Cold-Aisle Containment (Roofs & Doors)
    for roof in scene["containment_roofs"]:
        add_box_element(
            "IfcCovering", roof["name"], "CEILING", "ContainmentRoof",
            roof["cx"], roof["cy"], roof["z0"], roof["w"], roof["d"], roof["h"],
        )
    for door in scene["containment_doors"]:
        add_box_element(
            "IfcDoor", door["name"], "DOOR", "ContainmentDoor",
            door["cx"], door["cy"], door["z0"], door["w"], door["d"], door["h"],
        )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79)
    for sp in scene["sprinklers"]:
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcFireSuppressionTerminal",
            name=sp["name"],
            predefined_type="SPRINKLER",
        )
        elem.ObjectType = "SprinklerHead" if sp["location"] == "CEILING" else "InAisleSprinklerHead"
        rep = _make_cyl_rep(model, body_ctx, sp["r"], sp["h"])
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=elem, matrix=_placement_matrix_m(sp["cx"], sp["cy"], sp["z0"], 0.0)
        )
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name="Pset_DCM_Sprinkler")
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "Location": sp["location"],
                "DeflectorElevation_mm": float(sp["deflector_z"]),
                "Standoff_mm": 460.0,
            },
        )
        all_products.append(elem)

    # 8. Telecom Cable Tray (CT-1)
    for seg in scene["ct_segs"]:
        mat, length = _segment_matrix_and_length(seg["p0"], seg["p1"])
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcCableCarrierSegment",
            name=seg["name"],
            predefined_type="CABLETRAYSEGMENT",
        )
        elem.ObjectType = "CableTray"
        rep = _make_box_rep(model, body_ctx, seg["w"], seg["h"], length)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=mat)
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name="Pset_DCM_Service")
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "Service": "TELECOM",
                "Tag": "CT-1",
                "Width_mm": float(seg["w"]),
                "Height_mm": float(seg["h"]),
                "Elevation_mm": float(seg["p0"][2]),
                "Zone": seg["zone"],
            },
        )
        all_products.append(elem)

    # 9. Power Busway (BW-1)
    for seg in scene["bw_segs"]:
        mat, length = _segment_matrix_and_length(seg["p0"], seg["p1"])
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcCableSegment",
            name=seg["name"],
            predefined_type="BUSBARSEGMENT",
        )
        elem.ObjectType = "Busway"
        rep = _make_box_rep(model, body_ctx, seg["w"], seg["h"], length)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=mat)
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name="Pset_DCM_Service")
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "Service": "POWER",
                "Tag": "BW-1",
                "Width_mm": float(seg["w"]),
                "Height_mm": float(seg["h"]),
                "Elevation_mm": float(seg["p0"][2]),
                "Zone": seg["zone"],
            },
        )
        all_products.append(elem)

    # 10. Chilled-Water Pipe (CHW-1)
    for seg in scene["chw_segs"]:
        mat, length = _segment_matrix_and_length(seg["p0"], seg["p1"])
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcPipeSegment",
            name=seg["name"],
            predefined_type="RIGIDSEGMENT",
        )
        elem.ObjectType = "ChilledWaterPipe"
        rep = _make_cyl_rep(model, body_ctx, seg["od"] / 2.0, length)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=mat)
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name="Pset_DCM_Service")
        ifcopenshell.api.pset.edit_pset(
            model,
            pset=pset,
            properties={
                "Service": "CHILLED_WATER",
                "Tag": "CHW-1",
                "NominalDiameter_mm": 100.0,
                "BareOD_mm": CHW_BARE_OD,
                "InsulatedOD_mm": CHW_OD,
                "InsulationThickness_mm": CHW_INSUL_THK,
                "Elevation_mm": float(seg["p0"][2]),
                "Zone": seg["zone"],
            },
        )
        all_products.append(elem)

    # Assign all products to storey
    ifcopenshell.api.spatial.assign_container(
        model, relating_structure=storey, products=all_products
    )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    build_ifc(OUT_PATH)
