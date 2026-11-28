"""Coordinated 3D IFC4 model generator for data hall `hall_seed000_d000`.

Rebuilds the architectural/structural/MEP background from the 7-sheet drawing set
(A-101, A-301, A-601, A-602, M-101, E-101, F-101) and routes telecom cable tray
(CT-1), power busway (BW-1), and insulated chilled-water piping (CHW-1) clash-free.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
import json
import math
import os
import sys
from pathlib import Path
import numpy as np

# ---------------------------------------------------------------------------
# Drawing-set literals (all dimensions in millimetres)
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
TILE_MM = 600.0

SLAB_TOP_Z = -900.0
FLOOR_PANEL_THK = 35.0
FLOOR_TOP_Z = 0.0
SOFFIT_Z = 3600.0
MIN_CLEAR_HEIGHT_Z = 2600.0
SPRINKLER_DEFLECTOR_Z = 3574.6  # 25.4 mm below +3600 soffit (A-301)
SPRINKLER_STANDOFF = 460.0      # 460 mm clear below deflector -> max Z = 3114.6

# Structural columns: 600 x 600 mm, full clear height (0 to 3600 mm)
COL_SIZE = 600.0
COL_CENTERS = [
    (8400.0, 8400.0),
    (16800.0, 8400.0),
    (25200.0, 8400.0),
    (8400.0, 16800.0),
    (16800.0, 16800.0),
    (25200.0, 16800.0),
]

# Cabinet rows (A-101, A-601)
# Cross-aisle east edge is common to every row at x = 11400 mm (tile 19/20, A-101 Note 5).
CA_EAST_X = 11400.0
ROW_DEFS = [
    ("A", 1800.0, 2400.0, "SOUTH",
     ["4C1", "CU", "3C1", "N1", "3C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("B", 1800.0, 5400.0, "NORTH",
     ["4C1", "CU", "5C1", "2N1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("C", 1800.0, 7800.0, "SOUTH",
     ["3C1", "CU", "6C1", "2-600", "CU", "CA", "N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"]),
    ("D", 1800.0, 10800.0, "NORTH",
     ["4C1", "CU", "3C1", "2N1", "2C1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("E", 1800.0, 13200.0, "SOUTH",
     ["4C1", "CU", "5C1", "N1", "C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("F", 1800.0, 16200.0, "NORTH",
     ["4C1", "CU", "5C1", "2-600", "CU", "CA", "2N1", "5C1", "SP", "-600", "CU", "4C1"]),
]
BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Perimeter CRAHs (A-601, M-101): 1200 x 900 x 2000 mm, facing NORTH
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0

# PDUs (A-601, E-101): 762 x 813 x 1959 mm, front flush with row front face
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_DEFS = [
    # (tag, serves_row, x0, y0, facing)
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Cold-Aisle Containment (A-602, A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z0 = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5
CAC_AISLE_W = 1200.0

# Service entries on west wall (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Pathway section dimensions (A-602, E-101, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_BARE_OD = 114.3
CHW_INSUL_THK = 25.4
CHW_OD = 168.3  # ASTM C585 jacket OD over insulation (M-101 Note 4)

# Service elevations (unambiguous tiers relative to FF = 0):
# - Telecom Cable Tray (CT-1): Overhead plenum, z = 2850..2977 mm (centre 2913.5)
#   Clear of 2600 headroom (+250 mm) and 3114.6 sprinkler standoff (+137.6 mm).
# - Power Busway (BW-1): Under-floor plenum, z = -250..-103 mm (centre -176.5)
#   Clear of -55 mm under-panel limit (+48 mm) and >= 2953 mm from Cable Tray.
# - Chilled Water (CHW-1): Under-floor plenum, z = -600..-431.7 mm (centre -515.85)
#   Clear of Busway (-250..-103, gap 181.7 mm), clear of slab (-900), and zero
#   entry into 1800 mm dedicated space above PDUs (z = 1959..3759).
TRAY_Z0 = 2850.0
BUSWAY_Z0 = -250.0
CHW_ZC = -515.85


def _expand_row(rname, x_start, y0, facing, seq):
    """Expand a row's bay sequence into racks, in-row CRAHs, and segment extents."""
    x = x_start
    racks = []
    inrow_crahs = []
    rack_idx = 0
    crah_idx = 0
    ca_west = None
    for tok in seq:
        if tok == "CA":
            ca_west = x
            x = CA_EAST_X
            continue
        if tok == "-600":
            cnt, kind = 1, "-600"
        elif tok[0].isdigit():
            cnt, kind = int(tok[0]), tok[1:]
        else:
            cnt, kind = 1, tok
        w = BAY_WIDTHS[kind]
        for _ in range(cnt):
            if kind in ("C1", "N1"):
                rack_idx += 1
                racks.append({
                    "id": f"RACK-{rname}{rack_idx:02d}",
                    "row": rname,
                    "type": kind,
                    "x0": x, "y0": y0, "z0": 0.0,
                    "x1": x + w, "y1": y0 + CAB_DEPTH, "z1": CAB_HEIGHT,
                    "w": w, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                    "facing": facing,
                })
            elif kind == "CU":
                crah_idx += 1
                inrow_crahs.append({
                    "id": f"CRAH-{rname}{crah_idx:02d}",
                    "row": rname,
                    "placement": f"IN-ROW {rname}",
                    "x0": x, "y0": y0, "z0": 0.0,
                    "x1": x + w, "y1": y0 + CAB_DEPTH, "z1": CAB_HEIGHT,
                    "w": w, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                    "facing": facing,
                    "capacity_kw": 50.0,
                    "airflow_m3h": 9000.0,
                    "service": "CHILLED WATER, DN50",
                })
            x += w
    return racks, inrow_crahs, ca_west, x


def _build_sprinklers():
    """Return 63 ceiling heads + 16 in-aisle heads per F-101 and A-301."""
    sprinklers = []
    # 63 ceiling heads: 9 x 7 grid at 1500 + 3000*k, relocated clear of 1500 mm column keep-out
    xs = [1500.0 + 3000.0 * i for i in range(9)]
    ys = [1500.0 + 3000.0 * j for j in range(7)]
    idx = 0
    for y in ys:
        for x in xs:
            idx += 1
            hx, hy = x, y
            # Check 1500 mm column keep-out (half-width 750 mm around column centre)
            for cx, cy in COL_CENTERS:
                if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                    # Relocate south-west to nearest clear tile edge per F-101 Detail 2
                    hy = cy - 900.0
            sprinklers.append({
                "id": f"SP-CEIL-{idx:02d}",
                "kind": "ceiling",
                "x": hx, "y": hy,
                "z_deflector": SPRINKLER_DEFLECTOR_Z,
            })

    # 16 in-aisle heads: 8 in CAC-BC (y=7200), 8 in CAC-DE (y=12600), deflector at +1890
    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9000.0, 12600.0, 15000.0, 17400.0, 19200.0]
    a_idx = 0
    for aisle_name, ay in (("BC", 7200.0), ("DE", 12600.0)):
        for ax in in_aisle_xs:
            a_idx += 1
            sprinklers.append({
                "id": f"SP-AISLE-{aisle_name}-{a_idx:02d}",
                "kind": "in_aisle",
                "x": ax, "y": ay,
                "z_deflector": 1890.0,
            })
    return sprinklers


def _rect_seg(seg_id, service, axis, p0, p1, w, h, z0):
    """Build an axis-aligned rectangular segment (tray or busway) between p0 and p1."""
    x0, y0 = p0
    x1, y1 = p1
    if axis == "X":
        xa, xb = min(x0, x1), max(x0, x1)
        aabb = (xa, y0 - w / 2.0, z0, xb, y0 + w / 2.0, z0 + h)
    else:
        ya, yb = min(y0, y1), max(y0, y1)
        aabb = (x0 - w / 2.0, ya, z0, x0 + w / 2.0, yb, z0 + h)
    return {
        "id": seg_id,
        "category": service,
        "service": service,
        "shape": "rect",
        "axis": axis,
        "p0": p0, "p1": p1,
        "w": w, "h": h, "z0": z0,
        "aabb": aabb,
    }


def _pipe_seg(seg_id, axis, p0, p1, od, zc):
    """Build an axis-aligned circular pipe segment (CHW) between p0 and p1."""
    x0, y0 = p0
    x1, y1 = p1
    r = od / 2.0
    if axis == "X":
        xa, xb = min(x0, x1), max(x0, x1)
        aabb = (xa, y0 - r, zc - r, xb, y0 + r, zc + r)
    else:
        ya, yb = min(y0, y1), max(y0, y1)
        aabb = (x0 - r, ya, zc - r, x0 + r, yb, zc + r)
    return {
        "id": seg_id,
        "category": "chw",
        "service": "chw",
        "shape": "pipe",
        "axis": axis,
        "p0": p0, "p1": p1,
        "od": od, "zc": zc,
        "aabb": aabb,
    }


def build_geometry_data():
    """Return all hall geometry and MEP routing segments as pure-Python dicts."""
    solids = []
    rows = {}
    crahs = []
    pdus = []
    containment = []

    # 1. Access floor panel (z = -35..0)
    solids.append({
        "id": "ACCESS-FLOOR",
        "category": "floor",
        "service": None,
        "aabb": (0.0, 0.0, -FLOOR_PANEL_THK, ROOM_X, ROOM_Y, FLOOR_TOP_Z),
    })

    # 2. Structural columns (z = 0..3600)
    for idx, (cx, cy) in enumerate(COL_CENTERS, start=1):
        half = COL_SIZE / 2.0
        solids.append({
            "id": f"COL-{idx:02d}",
            "category": "column",
            "service": None,
            "cx": cx, "cy": cy,
            "aabb": (cx - half, cy - half, 0.0, cx + half, cy + half, SOFFIT_Z),
        })

    # 3. Cabinet rows & in-row CRAHs
    for rname, x_start, y0, facing, seq in ROW_DEFS:
        racks, inrow_crahs, ca_west, x_end = _expand_row(rname, x_start, y0, facing, seq)
        rows[rname] = {
            "x0": x_start, "x1": x_end,
            "y0": y0, "y1": y0 + CAB_DEPTH, "y_cl": y0 + CAB_DEPTH / 2.0,
            "facing": facing, "ca_west": ca_west, "ca_east": CA_EAST_X,
            "racks": racks,
        }
        for r in racks:
            solids.append({
                "id": r["id"],
                "category": "rack",
                "service": None,
                "meta": r,
                "aabb": (r["x0"], r["y0"], r["z0"], r["x1"], r["y1"], r["z1"]),
            })
        for c in inrow_crahs:
            solids.append({
                "id": c["id"],
                "category": "crah",
                "service": None,
                "meta": c,
                "aabb": (c["x0"], c["y0"], c["z0"], c["x1"], c["y1"], c["z1"]),
            })
            crahs.append({
                "id": c["id"],
                "x0": c["x0"], "y0": c["y0"], "x1": c["x1"], "y1": c["y1"],
                "cx": (c["x0"] + c["x1"]) / 2.0, "cy": (c["y0"] + c["y1"]) / 2.0,
            })

    # 4. Perimeter CRAHs
    for cid, x0, y0 in PERIM_CRAHS:
        meta = {
            "id": cid, "placement": "PERIMETER",
            "x0": x0, "y0": y0, "z0": 0.0,
            "x1": x0 + PERIM_CRAH_W, "y1": y0 + PERIM_CRAH_D, "z1": PERIM_CRAH_H,
            "w": PERIM_CRAH_W, "d": PERIM_CRAH_D, "h": PERIM_CRAH_H,
            "facing": "NORTH", "capacity_kw": 100.0, "airflow_m3h": 20000.0,
            "service": "CHILLED WATER, DN100",
        }
        solids.append({
            "id": cid, "category": "crah", "service": None, "meta": meta,
            "aabb": (meta["x0"], meta["y0"], meta["z0"], meta["x1"], meta["y1"], meta["z1"]),
        })
        crahs.append({
            "id": cid,
            "x0": meta["x0"], "y0": meta["y0"], "x1": meta["x1"], "y1": meta["y1"],
            "cx": (meta["x0"] + meta["x1"]) / 2.0, "cy": (meta["y0"] + meta["y1"]) / 2.0,
        })

    # 5. PDUs
    for pid, srow, x0, y0, facing in PDU_DEFS:
        p = {
            "id": pid, "serves_row": srow, "facing": facing,
            "x0": x0, "y0": y0, "z0": 0.0,
            "x1": x0 + PDU_W, "y1": y0 + PDU_D, "z1": PDU_H,
            "w": PDU_W, "d": PDU_D, "h": PDU_H,
        }
        pdus.append(p)
        solids.append({
            "id": pid, "category": "pdu", "service": None, "meta": p,
            "aabb": (p["x0"], p["y0"], p["z0"], p["x1"], p["y1"], p["z1"]),
        })

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE)
    for tag, r_south, r_north, y_aisle0 in (("CAC-BC", "B", "C", 6600.0), ("CAC-DE", "D", "E", 12000.0)):
        west_x1 = min(rows[r_south]["ca_west"], rows[r_north]["ca_west"])
        east_x1 = max(rows[r_south]["x1"], rows[r_north]["x1"])
        y_roof0 = y_aisle0 - 100.0  # 100 mm overhang onto cabinet tops each side
        for seg_name, sx0, sx1 in (("W", 1800.0, west_x1), ("E", CA_EAST_X, east_x1)):
            roof = {
                "id": f"{tag}-ROOF-{seg_name}",
                "category": "containment_roof",
                "service": None,
                "aabb": (sx0, y_roof0, CAC_ROOF_Z0, sx1, y_roof0 + CAC_ROOF_W, CAC_ROOF_Z0 + CAC_ROOF_THK),
            }
            solids.append(roof)
            containment.append(roof)
            # End doors at west & east ends of each contained aisle segment
            for d_side, dx0 in (("W", sx0 - CAC_DOOR_THK), ("E", sx1)):
                door = {
                    "id": f"{tag}-DOOR-{seg_name}-{d_side}",
                    "category": "containment_door",
                    "service": None,
                    "aabb": (dx0, y_aisle0, 0.0, dx0 + CAC_DOOR_THK, y_aisle0 + CAC_AISLE_W, CAC_DOOR_H),
                }
                solids.append(door)
                containment.append(door)

    # 7. Sprinklers (63 ceiling + 16 in-aisle)
    sprinklers = _build_sprinklers()
    for sp in sprinklers:
        # Small 50 x 50 x 25.4 mm sprinkler head body above deflector
        solids.append({
            "id": sp["id"],
            "category": "sprinkler",
            "service": None,
            "meta": sp,
            "aabb": (sp["x"] - 25.0, sp["y"] - 25.0, sp["z_deflector"],
                     sp["x"] + 25.0, sp["y"] + 25.0, sp["z_deflector"] + 25.4),
        })

    # 8. MEP Routing
    # Shared header Y coordinates:
    # - Row A (y_cl=3000): header at y=3000 (tray/busway), y=2000 (CHW, also serves perimeter CRAHs at y=450)
    # - Rows B & C (y_cl=6000, 8400): shared header at y=7200 (1200 mm from both, clear of columns at y=8400)
    # - Rows D & E (y_cl=11400, 13800): shared header at y=12600 (1200 mm from both)
    # - Row F (y_cl=16800): header at y=15800 (1000 mm from Row F, clear of columns at y=16800)
    # Row X extent: rows start at x=1800 and end at 19400..20200; 85%+ coverage reached by x=18600.
    SPINE_X = 900.0
    BRANCH_X_END = 18600.0

    # 8a. Telecom Cable Tray (CT-1, overhead z = 2850..2977)
    tray_segs = [
        _rect_seg("CT-ENTRY", "tray", "X", (ENTRY_X, ENTRY_Y), (SPINE_X, ENTRY_Y), TRAY_W, TRAY_H, TRAY_Z0),
        _rect_seg("CT-SPINE", "tray", "Y", (SPINE_X, 3000.0), (SPINE_X, 15800.0), TRAY_W, TRAY_H, TRAY_Z0),
        _rect_seg("CT-ROW-A", "tray", "X", (SPINE_X, 3000.0), (BRANCH_X_END, 3000.0), TRAY_W, TRAY_H, TRAY_Z0),
        _rect_seg("CT-ROW-BC", "tray", "X", (SPINE_X, 7200.0), (BRANCH_X_END, 7200.0), TRAY_W, TRAY_H, TRAY_Z0),
        _rect_seg("CT-ROW-DE", "tray", "X", (SPINE_X, 12600.0), (BRANCH_X_END, 12600.0), TRAY_W, TRAY_H, TRAY_Z0),
        _rect_seg("CT-ROW-F", "tray", "X", (SPINE_X, 15800.0), (BRANCH_X_END, 15800.0), TRAY_W, TRAY_H, TRAY_Z0),
    ]
    solids.extend(tray_segs)

    # 8b. Power Busway (BW-1, under-floor z = -250..-103)
    bus_segs = [
        _rect_seg("BW-ENTRY", "busway", "X", (ENTRY_X, ENTRY_Y), (SPINE_X, ENTRY_Y), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
        _rect_seg("BW-SPINE", "busway", "Y", (SPINE_X, 3000.0), (SPINE_X, 15800.0), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
        _rect_seg("BW-ROW-A", "busway", "X", (SPINE_X, 3000.0), (BRANCH_X_END, 3000.0), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
        _rect_seg("BW-ROW-BC", "busway", "X", (SPINE_X, 7200.0), (BRANCH_X_END, 7200.0), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
        _rect_seg("BW-ROW-DE", "busway", "X", (SPINE_X, 12600.0), (BRANCH_X_END, 12600.0), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
        _rect_seg("BW-ROW-F", "busway", "X", (SPINE_X, 15800.0), (BRANCH_X_END, 15800.0), BUSWAY_W, BUSWAY_H, BUSWAY_Z0),
    ]
    solids.extend(bus_segs)

    # 8c. Chilled Water Pipe (CHW-1, under-floor zc = -515.85, insulated OD = 168.3)
    # Row A header at y=2000 extends to x=25800 to reach CRAH-01..04 (all at y=450, dist=1550 <= 2500).
    chw_segs = [
        _pipe_seg("CHW-ENTRY", "X", (ENTRY_X, ENTRY_Y), (SPINE_X, ENTRY_Y), CHW_OD, CHW_ZC),
        _pipe_seg("CHW-SPINE", "Y", (SPINE_X, 2000.0), (SPINE_X, 15800.0), CHW_OD, CHW_ZC),
        _pipe_seg("CHW-ROW-A-PERIM", "X", (SPINE_X, 2000.0), (25800.0, 2000.0), CHW_OD, CHW_ZC),
        _pipe_seg("CHW-ROW-BC", "X", (SPINE_X, 7200.0), (BRANCH_X_END, 7200.0), CHW_OD, CHW_ZC),
        _pipe_seg("CHW-ROW-DE", "X", (SPINE_X, 12600.0), (BRANCH_X_END, 12600.0), CHW_OD, CHW_ZC),
        _pipe_seg("CHW-ROW-F", "X", (SPINE_X, 15800.0), (BRANCH_X_END, 15800.0), CHW_OD, CHW_ZC),
    ]
    solids.extend(chw_segs)

    return {
        "solids": solids,
        "rows": rows,
        "crahs": crahs,
        "pdus": pdus,
        "sprinklers": sprinklers,
        "entries": {"tray": (ENTRY_X, ENTRY_Y), "busway": (ENTRY_X, ENTRY_Y), "chw": (ENTRY_X, ENTRY_Y)},
    }


def _placement_matrix_m(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    """Return 4x4 placement matrix with translation in METRES (for ifcopenshell.api)."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    return np.array([
        [c, -s, 0.0, cx_mm / 1000.0],
        [s,  c, 0.0, cy_mm / 1000.0],
        [0.0, 0.0, 1.0, z0_mm / 1000.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=float)


def _pipe_matrix_m(axis, p0, p1, zc_mm):
    """Return 4x4 placement matrix (metres) to extrude a Z-aligned cylinder along X or Y."""
    x0, y0 = p0
    x1, y1 = p1
    if axis == "X":
        xa = min(x0, x1)
        # Local +Z -> World +X
        return np.array([
            [0.0, 0.0, 1.0, xa / 1000.0],
            [1.0, 0.0, 0.0, y0 / 1000.0],
            [0.0, 1.0, 0.0, zc_mm / 1000.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=float)
    else:
        ya = min(y0, y1)
        # Local +Z -> World +Y
        return np.array([
            [1.0, 0.0, 0.0, x0 / 1000.0],
            [0.0, 0.0, 1.0, ya / 1000.0],
            [0.0, -1.0, 0.0, zc_mm / 1000.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=float)


def _make_box_rep(f, body_ctx, w_mm, d_mm, h_mm):
    """Create an IfcShapeRepresentation for a centred 2D rectangle extruded +Z."""
    origin_2d = f.createIfcCartesianPoint((0.0, 0.0))
    pos_2d = f.createIfcAxis2Placement2D(origin_2d)
    profile = f.createIfcRectangleProfileDef("AREA", None, pos_2d, float(w_mm), float(d_mm))
    origin_3d = f.createIfcCartesianPoint((0.0, 0.0, 0.0))
    pos_3d = f.createIfcAxis2Placement3D(origin_3d)
    dir_z = f.createIfcDirection((0.0, 0.0, 1.0))
    solid = f.createIfcExtrudedAreaSolid(profile, pos_3d, dir_z, float(h_mm))
    return f.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])


def _make_cyl_rep(f, body_ctx, radius_mm, length_mm):
    """Create an IfcShapeRepresentation for a centred 2D circle extruded +Z."""
    origin_2d = f.createIfcCartesianPoint((0.0, 0.0))
    pos_2d = f.createIfcAxis2Placement2D(origin_2d)
    profile = f.createIfcCircleProfileDef("AREA", None, pos_2d, float(radius_mm))
    origin_3d = f.createIfcCartesianPoint((0.0, 0.0, 0.0))
    pos_3d = f.createIfcAxis2Placement3D(origin_3d)
    dir_z = f.createIfcDirection((0.0, 0.0, 1.0))
    solid = f.createIfcExtrudedAreaSolid(profile, pos_3d, dir_z, float(length_mm))
    return f.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])


def write_reconciliation_log(out_ifc_path):
    """Write optional drawing-note reconciliation log next to the IFC."""
    rec = {
        "hall": "hall_seed000_d000",
        "room_mm": {"x": ROOM_X, "y": ROOM_Y, "tile": TILE_MM},
        "datums_mm": {
            "structural_slab_top": SLAB_TOP_Z,
            "access_floor_panel_thk": FLOOR_PANEL_THK,
            "finished_floor": FLOOR_TOP_Z,
            "min_clear_height": MIN_CLEAR_HEIGHT_Z,
            "ceiling_soffit": SOFFIT_Z,
            "sprinkler_deflector": SPRINKLER_DEFLECTOR_Z,
            "sprinkler_standoff": SPRINKLER_STANDOFF,
            "under_floor_tray_clearance_below_panel": 20.0,
        },
        "services": {
            "CT-1": {"section_mm": [TRAY_W, TRAY_H], "zone": "overhead", "z_range_mm": [TRAY_Z0, TRAY_Z0 + TRAY_H]},
            "BW-1": {"section_mm": [BUSWAY_W, BUSWAY_H], "zone": "under_floor", "z_range_mm": [BUSWAY_Z0, BUSWAY_Z0 + BUSWAY_H]},
            "CHW-1": {"bare_od_mm": CHW_BARE_OD, "insulation_mm": CHW_INSUL_THK, "jacket_od_mm": CHW_OD,
                      "zone": "under_floor", "z_range_mm": [CHW_ZC - CHW_OD / 2.0, CHW_ZC + CHW_OD / 2.0]},
        },
        "clearances_applied": {
            "tray_busway_min_sep_mm": round(TRAY_Z0 - (BUSWAY_Z0 + BUSWAY_H), 1),
            "sprinkler_standoff_actual_mm": round(SPRINKLER_DEFLECTOR_Z - (TRAY_Z0 + TRAY_H), 1),
            "pdu_dedicated_space_chw_clear": True,
        },
    }
    rec_path = Path(out_ifc_path).parent / "reconciliation.json"
    rec_path.write_text(json.dumps(rec, indent=2))


def build_ifc(out_path):
    """Build the IFC4 model using ifcopenshell==0.8.4 and write to out_path."""
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    f = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    ifcopenshell.api.unit.assign_unit(f, length={"is_metric": True, "raw": "MILLIMETRE"})

    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=building)

    data = build_geometry_data()

    def _add_pset(el, pset_name, props):
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=props)

    for s in data["solids"]:
        cat = s["category"]
        x0, y0, z0, x1, y1, z1 = s["aabb"]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0

        if cat == "floor":
            el = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSlab", predefined_type="FLOOR", name=s["id"])
            el.ObjectType = "AccessFloor"
            rep = _make_box_rep(f, body_ctx, dx, dy, dz)
            mat = _placement_matrix_m(cx, cy, z0)
            _add_pset(el, "Pset_DCM_AccessFloor", {"ThicknessMm": FLOOR_PANEL_THK, "PlenumDepthMm": 865.0, "TileSizeMm": TILE_MM})

        elif cat == "column":
            el = ifcopenshell.api.root.create_entity(f, ifc_class="IfcColumn", predefined_type="COLUMN", name=s["id"])
            el.ObjectType = "StructuralColumn"
            rep = _make_box_rep(f, body_ctx, dx, dy, dz)
            mat = _placement_matrix_m(cx, cy, z0)
            _add_pset(el, "Pset_DCM_Column", {"WidthMm": COL_SIZE, "DepthMm": COL_SIZE, "HeightMm": SOFFIT_Z})

        elif cat == "rack":
            m = s["meta"]
            el = ifcopenshell.api.root.create_entity(f, ifc_class="IfcFurniture", predefined_type="USERDEFINED", name=s["id"])
            el.ObjectType = "Rack"
            yaw = 0.0 if m["facing"] == "NORTH" else math.pi
            rep = _make_box_rep(f, body_ctx, m["w"], m["d"], m["h"])
            mat = _placement_matrix_m(cx, cy, z0, yaw)
            _add_pset(el, "Pset_DCM_Rack", {
                "Row": m["row"], "RackType": m["type"], "WidthMm": m["w"], "DepthMm": m["d"],
                "HeightMm": m["h"], "RU": 42, "PowerKW": 8.0, "LoadKg": 1363.0, "FrontFacing": m["facing"],
            })

        elif cat == "crah":
            m = s["meta"]
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcUnitaryEquipment", predefined_type="AIRCONDITIONINGUNIT", name=s["id"]
            )
            el.ObjectType = "CRAH"
            yaw = 0.0 if m["facing"] == "NORTH" else math.pi
            rep = _make_box_rep(f, body_ctx, m["w"], m["d"], m["h"])
            mat = _placement_matrix_m(cx, cy, z0, yaw)
            _add_pset(el, "Pset_DCM_CRAH", {
                "Placement": m["placement"], "CapacityKW": m["capacity_kw"],
                "AirflowM3H": m["airflow_m3h"], "Service": m["service"], "FrontFacing": m["facing"],
            })

        elif cat == "pdu":
            m = s["meta"]
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcElectricDistributionBoard", predefined_type="DISTRIBUTIONBOARD", name=s["id"]
            )
            el.ObjectType = "PDU"
            yaw = 0.0 if m["facing"] == "NORTH" else math.pi
            rep = _make_box_rep(f, body_ctx, m["w"], m["d"], m["h"])
            mat = _placement_matrix_m(cx, cy, z0, yaw)
            _add_pset(el, "Pset_DCM_PDU", {
                "ServesRow": m["serves_row"], "RatingKVA": 225.0, "WorkingSpaceMm": 900.0,
                "DedicatedSpaceHeightMm": 1800.0, "FrontFacing": m["facing"],
            })

        elif cat in ("containment_roof", "containment_door"):
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcBuildingElementProxy", predefined_type="USERDEFINED", name=s["id"]
            )
            el.ObjectType = "ContainmentRoof" if cat == "containment_roof" else "ContainmentDoor"
            rep = _make_box_rep(f, body_ctx, dx, dy, dz)
            mat = _placement_matrix_m(cx, cy, z0)
            _add_pset(el, "Pset_DCM_Containment", {"PartType": el.ObjectType})

        elif cat == "sprinkler":
            m = s["meta"]
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=s["id"]
            )
            el.ObjectType = "SprinklerHead"
            rep = _make_cyl_rep(f, body_ctx, 25.0, 25.4)
            mat = _placement_matrix_m(m["x"], m["y"], m["z_deflector"])
            _add_pset(el, "Pset_DCM_Sprinkler", {
                "Location": m["kind"], "DeflectorElevationMm": m["z_deflector"],
                "StandoffMm": SPRINKLER_STANDOFF if m["kind"] == "ceiling" else 0.0,
            })

        elif cat == "tray":
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcCableCarrierSegment", predefined_type="CABLETRAYSEGMENT", name=s["id"]
            )
            el.ObjectType = "CableTray"
            rep = _make_box_rep(f, body_ctx, dx, dy, dz)
            mat = _placement_matrix_m(cx, cy, z0)
            _add_pset(el, "Pset_DCM_Pathway", {
                "Service": "Telecom", "Tag": "CT-1", "WidthMm": TRAY_W, "HeightMm": TRAY_H,
                "ElevationMm": z0, "Zone": "Overhead",
            })

        elif cat == "busway":
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcCableSegment", predefined_type="BUSBARSEGMENT", name=s["id"]
            )
            el.ObjectType = "Busway"
            rep = _make_box_rep(f, body_ctx, dx, dy, dz)
            mat = _placement_matrix_m(cx, cy, z0)
            _add_pset(el, "Pset_DCM_Pathway", {
                "Service": "Power", "Tag": "BW-1", "WidthMm": BUSWAY_W, "HeightMm": BUSWAY_H,
                "ElevationMm": z0, "Zone": "UnderFloor",
            })

        elif cat == "chw":
            el = ifcopenshell.api.root.create_entity(
                f, ifc_class="IfcPipeSegment", predefined_type="RIGIDSEGMENT", name=s["id"]
            )
            el.ObjectType = "ChilledWaterPipe"
            length = max(dx, dy)
            rep = _make_cyl_rep(f, body_ctx, CHW_OD / 2.0, length)
            mat = _pipe_matrix_m(s["axis"], s["p0"], s["p1"], s["zc"])
            _add_pset(el, "Pset_DCM_Pathway", {
                "Service": "ChilledWater", "Tag": "CHW-1", "BareODMm": CHW_BARE_OD,
                "InsulationMm": CHW_INSUL_THK, "InsulatedODMm": CHW_OD,
                "ElevationMm": s["zc"], "Zone": "UnderFloor",
            })
        else:
            continue

        ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(f, product=el, matrix=mat)
        ifcopenshell.api.spatial.assign_container(f, products=[el], relating_structure=storey)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    f.write(out_path)
    write_reconciliation_log(out_path)


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_ifc(out_file)
