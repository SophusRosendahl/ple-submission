"""Coordinated 3D IFC4 model and clash-free MEP routing for dc_model hall_seed000_d000.

Self-contained script: all dimensions, equipment positions, elevations, and
clearances are baked in as literals reconciled from sheets A-101, A-301, A-601,
A-602, M-101, E-101, and F-101.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
import json
import math
import os
import sys
import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

# ---------------------------------------------------------------------------
# Reconciled Hall Constants (all lengths in mm, Z relative to Finished Floor)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
TILE = 600.0

Z_SLAB_TOP = -900.0
Z_FLOOR_BOT = -35.0
Z_FLOOR_TOP = 0.0
Z_SOFFIT = 3600.0
Z_MIN_CLEAR = 2600.0
Z_CEIL_DEFLECTOR = 3574.6  # 25.4 mm below soffit
SPRINKLER_STANDOFF = 460.0

CAB_D = 1200.0
CAB_H = 2000.0
C1_W = 600.0
N1_W = 800.0

CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z0 = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5
Z_INAISLE_DEFLECTOR = 1890.0

COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Cross aisle east edge is common to all 6 rows (A-101 Note 5)
CROSS_AISLE_EAST_X = 11200.0

# Pathway section dimensions (A-602, E-101, M-101)
CT_W = 683.0
CT_H = 127.0
BW_W = 128.0
BW_H = 147.0
CHW_OD = 168.3  # DN100 (114.3 mm) + 25.4 mm min insulation -> 168.3 mm ASTM C585 jacket OD
CHW_R = CHW_OD / 2.0

# Service elevation tiers (centreline Z in mm)
Z_CT = -250.0   # Under-floor plenum: -313.5 .. -186.5 (clear of -900 slab & -55 limit)
Z_BW = 2700.0   # Overhead lower tier: 2626.5 .. 2773.5 (>= 2600 headroom)
Z_CHW = 2950.0  # Overhead upper tier: 2865.85 .. 3034.15 (92.35 mm above BW, 540.45 mm below sprinklers)

SERVICE_ENTRY_XY = (0.0, 9900.0)
SPINE_X = 1200.0


def _col_idx(letters: str) -> int:
    if len(letters) == 1:
        return ord(letters) - ord("A")
    return 26 + (ord(letters[1]) - ord("A"))


def _rect_aabb(x0, y0, z0, x1, y1, z1):
    return (float(min(x0, x1)), float(min(y0, y1)), float(min(z0, z1)),
            float(max(x0, x1)), float(max(y0, y1)), float(max(z0, z1)))


def _make_rect_seg(p0, p1, width, height):
    """Axis-aligned rectangular pathway segment from p0 to p1 (centreline)."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    hw = width / 2.0
    hh = height / 2.0
    if abs(y1 - y0) < 1e-6 and abs(z1 - z0) < 1e-6:
        # Runs along X
        aabb = _rect_aabb(min(x0, x1) - hw, y0 - hw, z0 - hh,
                          max(x0, x1) + hw, y0 + hw, z0 + hh)
    elif abs(x1 - x0) < 1e-6 and abs(z1 - z0) < 1e-6:
        # Runs along Y
        aabb = _rect_aabb(x0 - hw, min(y0, y1) - hw, z0 - hh,
                          x0 + hw, max(y0, y1) + hw, z0 + hh)
    else:
        # Vertical or general axis-aligned
        aabb = _rect_aabb(min(x0, x1) - hw, min(y0, y1) - hw, min(z0, z1) - hh,
                          max(x0, x1) + hw, max(y0, y1) + hw, max(z0, z1) + hh)
    return {"p0": tuple(map(float, p0)), "p1": tuple(map(float, p1)),
            "w": float(width), "h": float(height), "aabb": aabb}


def _make_pipe_seg(p0, p1, od):
    """Axis-aligned circular pipe segment from p0 to p1 (centreline)."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    r = od / 2.0
    aabb = _rect_aabb(min(x0, x1) - r, min(y0, y1) - r, min(z0, z1) - r,
                      max(x0, x1) + r, max(y0, y1) + r, max(z0, z1) + r)
    return {"p0": tuple(map(float, p0)), "p1": tuple(map(float, p1)),
            "od": float(od), "aabb": aabb}


def build_model_data():
    """Return all geometry and routing data as plain Python dicts (no ifcopenshell)."""
    # 1. Cabinet rows & in-row CRAHs (A-101, A-601, M-101)
    row_defs = [
        ("A", 3000.0, "SOUTH", "4C1 CU 3C1 N1 3C1 CU CA 6C1 SP CU 5C1"),
        ("B", 6000.0, "NORTH", "4C1 CU 5C1 2N1 CU CA 7C1 SP CU 5C1"),
        ("C", 8400.0, "SOUTH", "3C1 CU 6C1 2-600 CU CA N1 4C1 CU SP C1 2-600 3C1"),
        ("D", 11400.0, "NORTH", "4C1 CU 3C1 2N1 2C1 CU CA 7C1 SP CU 5C1"),
        ("E", 13800.0, "SOUTH", "4C1 CU 5C1 N1 C1 CU CA 6C1 SP CU 5C1"),
        ("F", 16800.0, "NORTH", "4C1 CU 5C1 2-600 CU CA 2N1 5C1 SP -600 CU 4C1"),
    ]

    racks = []
    crahs = []
    row_spans = {}
    row_sections = {}  # row -> ((west_x0, west_x1), (east_x0, east_x1))

    for row_name, y_c, facing, seq in row_defs:
        x = 1800.0  # Column D = 3 * 600
        y0 = y_c - CAB_D / 2.0
        y1 = y_c + CAB_D / 2.0
        r_idx = 0
        c_idx = 0
        west_x0 = x
        west_x1 = None
        east_x0 = None
        for tok in seq.split():
            if tok.endswith("C1"):
                n = int(tok[:-2]) if tok[:-2] else 1
                for _ in range(n):
                    r_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_name}{r_idx:02d}",
                        "row": row_name,
                        "type": "C1",
                        "facing": facing,
                        "aabb": _rect_aabb(x, y0, 0.0, x + C1_W, y1, CAB_H),
                    })
                    x += C1_W
            elif tok.endswith("N1"):
                n = int(tok[:-2]) if tok[:-2] else 1
                for _ in range(n):
                    r_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_name}{r_idx:02d}",
                        "row": row_name,
                        "type": "N1",
                        "facing": facing,
                        "aabb": _rect_aabb(x, y0, 0.0, x + N1_W, y1, CAB_H),
                    })
                    x += N1_W
            elif tok == "CU":
                c_idx += 1
                crahs.append({
                    "tag": f"CRAH-{row_name}{c_idx:02d}",
                    "placement": f"IN_ROW_{row_name}",
                    "facing": facing,
                    "capacity_kw": 50.0,
                    "service": "CHW DN50",
                    "aabb": _rect_aabb(x, y0, 0.0, x + 600.0, y1, CAB_H),
                })
                x += 600.0
            elif tok == "SP":
                x += 600.0
            elif tok == "CA":
                west_x1 = x
                x = CROSS_AISLE_EAST_X
                east_x0 = x
            elif tok.endswith("-600"):
                n = int(tok[:-4]) if tok[:-4] else 1
                x += n * 600.0
        row_spans[row_name] = (west_x0, x, y_c)
        row_sections[row_name] = ((west_x0, west_x1), (east_x0, x))

    # 2. Perimeter CRAHs (4 units: B01, P01, AC01, AQ01)
    perim_tiles = [("CRAH-01", "B"), ("CRAH-02", "P"), ("CRAH-03", "AC"), ("CRAH-04", "AQ")]
    for tag, col_str in perim_tiles:
        x0 = _col_idx(col_str) * TILE
        crahs.append({
            "tag": tag,
            "placement": "PERIMETER",
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "service": "CHW DN100",
            "aabb": _rect_aabb(x0, 0.0, 0.0, x0 + 1200.0, 900.0, 2000.0),
        })

    # 3. Structural columns (6 units: 600x600, z = 0..3600)
    columns = []
    for yi, cy in enumerate(COL_YS, start=1):
        for xi, cx in enumerate(COL_XS):
            grid_lbl = f"{chr(ord('A') + xi)}{yi}"
            columns.append({
                "tag": f"COL-{grid_lbl}",
                "grid": grid_lbl,
                "aabb": _rect_aabb(cx - COL_SIZE / 2.0, cy - COL_SIZE / 2.0, 0.0,
                                   cx + COL_SIZE / 2.0, cy + COL_SIZE / 2.0, Z_SOFFIT),
            })

    # 4. PDUs (6 units: 762 x 813 x 1959, front flush with served row front face)
    pdu_defs = [
        ("PDU-01", "A", "AJ", "SOUTH", 2400.0),
        ("PDU-02", "B", "AK", "NORTH", 6600.0),
        ("PDU-03", "C", "AJ", "SOUTH", 7800.0),
        ("PDU-04", "D", "AK", "NORTH", 12000.0),
        ("PDU-05", "E", "AJ", "SOUTH", 13200.0),
        ("PDU-06", "F", "AK", "NORTH", 17400.0),
    ]
    pdus = []
    for tag, serves_row, col_str, facing, front_y in pdu_defs:
        x0 = _col_idx(col_str) * TILE
        y0 = front_y if facing == "SOUTH" else front_y - 813.0
        pdus.append({
            "tag": tag,
            "serves_row": serves_row,
            "facing": facing,
            "aabb": _rect_aabb(x0, y0, 0.0, x0 + 762.0, y0 + 813.0, 1959.0),
        })

    # 5. Access floor panel (35 mm thick, z = -35..0)
    access_floor = {
        "tag": "ACCESS-FLOOR",
        "aabb": _rect_aabb(0.0, 0.0, Z_FLOOR_BOT, ROOM_W, ROOM_D, Z_FLOOR_TOP),
    }

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE, each 2 roof panels + 4 end doors)
    containment = []
    cac_defs = [
        ("CAC-BC", 6600.0, 7800.0, row_sections["B"], row_sections["C"]),
        ("CAC-DE", 12000.0, 13200.0, row_sections["D"], row_sections["E"]),
    ]
    for cac_tag, ay0, ay1, sec1, sec2 in cac_defs:
        w_x0 = min(sec1[0][0], sec2[0][0])
        w_x1 = max(sec1[0][1], sec2[0][1])
        e_x0 = min(sec1[1][0], sec2[1][0])
        e_x1 = max(sec1[1][1], sec2[1][1])
        for side, (sx0, sx1) in [("W", (w_x0, w_x1)), ("E", (e_x0, e_x1))]:
            containment.append({
                "tag": f"{cac_tag}-ROOF-{side}",
                "kind": "roof",
                "aabb": _rect_aabb(sx0, ay0 - 100.0, CAC_ROOF_Z0,
                                   sx1, ay1 + 100.0, CAC_ROOF_Z0 + CAC_ROOF_THK),
            })
            # West and East end doors
            containment.append({
                "tag": f"{cac_tag}-DOOR-{side}1",
                "kind": "door",
                "aabb": _rect_aabb(sx0 - CAC_DOOR_THK, ay0, 0.0, sx0, ay1, CAC_DOOR_H),
            })
            containment.append({
                "tag": f"{cac_tag}-DOOR-{side}2",
                "kind": "door",
                "aabb": _rect_aabb(sx1, ay0, 0.0, sx1 + CAC_DOOR_THK, ay1, CAC_DOOR_H),
            })

    # 7. Sprinkler heads (63 ceiling + 16 in-aisle = 79 total, F-101 & A-301)
    sprinklers = []
    sp_idx = 0
    for iy in range(7):
        sy = 1500.0 + iy * 3000.0
        for ix in range(9):
            sx = 1500.0 + ix * 3000.0
            # Check 1500 mm column keep-out (750 mm half-width around column centre)
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        # Relocate to nearest clear tile (west & south of column)
                        sx = cx - 900.0
                        sy = cy - 900.0
            sp_idx += 1
            sprinklers.append({
                "tag": f"SPR-C{sp_idx:02d}",
                "kind": "ceiling",
                "x": sx, "y": sy, "z": Z_CEIL_DEFLECTOR,
                "aabb": _rect_aabb(sx - 25.0, sy - 25.0, Z_CEIL_DEFLECTOR,
                                   sx + 25.0, sy + 25.0, Z_SOFFIT),
            })

    # 16 in-aisle heads (8 under CAC-BC at y=7200, 8 under CAC-DE at y=12600)
    inais_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12100.0, 14200.0, 16300.0, 18400.0]
    ia_idx = 0
    for ay in (7200.0, 12600.0):
        for sx in inais_xs:
            ia_idx += 1
            sprinklers.append({
                "tag": f"SPR-IA{ia_idx:02d}",
                "kind": "in_aisle",
                "x": sx, "y": ay, "z": Z_INAISLE_DEFLECTOR,
                "aabb": _rect_aabb(sx - 25.0, ay - 25.0, Z_INAISLE_DEFLECTOR,
                                   sx + 25.0, ay + 25.0, CAC_ROOF_Z0),
            })

    # 8. Coordinated MEP Routes (CT under-floor, BW overhead lower, CHW overhead upper)
    # Row branch Y coordinates for overhead services (offset Row C & F by 800 mm to clear columns)
    row_branch_y_oh = {
        "A": 3000.0,
        "B": 6000.0,
        "C": 9200.0,   # Row C centre 8400 -> +800 mm clears columns at y=8400 (±300)
        "D": 11400.0,
        "E": 13800.0,
        "F": 16000.0,  # Row F centre 16800 -> -800 mm clears columns at y=16800 (±300)
    }
    row_branch_x1 = {
        "A": 18000.0,
        "B": 18600.0,
        "C": 18000.0,
        "D": 18600.0,
        "E": 18000.0,
        "F": 18600.0,
    }

    # 8a. Telecom Cable Tray (CT-1, under-floor at Z_CT = -250 mm)
    ct_segs = [
        _make_rect_seg((0.0, 9900.0, Z_CT), (SPINE_X, 9900.0, Z_CT), CT_W, CT_H),
        _make_rect_seg((SPINE_X, 3000.0, Z_CT), (SPINE_X, 16800.0, Z_CT), CT_W, CT_H),
    ]
    for r_name, (_, _, ry) in row_spans.items():
        ct_segs.append(_make_rect_seg(
            (SPINE_X, ry, Z_CT), (row_branch_x1[r_name], ry, Z_CT), CT_W, CT_H
        ))

    # 8b. Power Busway (BW-1, overhead lower tier at Z_BW = 2700 mm)
    bw_segs = [
        _make_rect_seg((0.0, 9900.0, Z_BW), (SPINE_X, 9900.0, Z_BW), BW_W, BW_H),
        _make_rect_seg((SPINE_X, 3000.0, Z_BW), (SPINE_X, 16000.0, Z_BW), BW_W, BW_H),
    ]
    for r_name, by in row_branch_y_oh.items():
        bw_segs.append(_make_rect_seg(
            (SPINE_X, by, Z_BW), (row_branch_x1[r_name], by, Z_BW), BW_W, BW_H
        ))

    # 8c. Chilled Water Pipe (CHW-1, overhead upper tier at Z_CHW = 2950 mm, OD 168.3 mm)
    chw_segs = [
        _make_pipe_seg((0.0, 9900.0, Z_CHW), (SPINE_X, 9900.0, Z_CHW), CHW_OD),
        _make_pipe_seg((SPINE_X, 1200.0, Z_CHW), (SPINE_X, 16000.0, Z_CHW), CHW_OD),
        # South perimeter header serving CRAH-01..04 (y=1200 is 750 mm from CRAH centres at y=450)
        _make_pipe_seg((SPINE_X, 1200.0, Z_CHW), (25200.0, 1200.0, Z_CHW), CHW_OD),
    ]
    for r_name, by in row_branch_y_oh.items():
        chw_segs.append(_make_pipe_seg(
            (SPINE_X, by, Z_CHW), (row_branch_x1[r_name], by, Z_CHW), CHW_OD
        ))

    return {
        "racks": racks,
        "columns": columns,
        "crahs": crahs,
        "pdus": pdus,
        "access_floor": access_floor,
        "containment": containment,
        "sprinklers": sprinklers,
        "row_spans": row_spans,
        "routes": {"CT": ct_segs, "BW": bw_segs, "CHW": chw_segs},
    }


def _translation_matrix_m(x_mm, y_mm, z_mm, rot_z=0.0):
    c = math.cos(rot_z)
    s = math.sin(rot_z)
    return np.array([
        [c, -s, 0.0, x_mm / 1000.0],
        [s,  c, 0.0, y_mm / 1000.0],
        [0.0, 0.0, 1.0, z_mm / 1000.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=float)


def _pipe_matrix_m(p0, p1):
    """4x4 placement matrix (translations in metres) with local +Z along p0->p1."""
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        sgn = 1.0 if dx >= 0 else -1.0
        M = np.array([
            [0.0, 0.0, sgn, p0[0] / 1000.0],
            [sgn, 0.0, 0.0, p0[1] / 1000.0],
            [0.0, 1.0, 0.0, p0[2] / 1000.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=float)
    elif abs(dy) >= abs(dz):
        sgn = 1.0 if dy >= 0 else -1.0
        M = np.array([
            [0.0, sgn, 0.0, p0[0] / 1000.0],
            [0.0, 0.0, sgn, p0[1] / 1000.0],
            [1.0, 0.0, 0.0, p0[2] / 1000.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=float)
    else:
        sgn = 1.0 if dz >= 0 else -1.0
        M = np.array([
            [1.0, 0.0, 0.0, p0[0] / 1000.0],
            [0.0, sgn, 0.0, p0[1] / 1000.0],
            [0.0, 0.0, sgn, p0[2] / 1000.0],
            [0.0, 0.0, 0.0, 1.0],
        ], dtype=float)
    return M, L


def build_ifc(out_path: str):
    import ifcopenshell
    import ifcopenshell.api

    data = build_model_data()
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRES"})

    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model, context_type="Model",
        context_identifier="Body", target_view="MODEL_VIEW", parent=ctx
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    origin_3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    place_3d = model.create_entity("IfcAxis2Placement3D", Location=origin_3d)
    origin_2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    place_2d = model.create_entity("IfcAxis2Placement2D", Location=origin_2d)

    def add_box(ifc_class, name, predef, obj_type, aabb, facing="NORTH", pset_name=None, pset_props=None):
        x0, y0, z0, x1, y1, z1 = aabb
        w = x1 - x0
        d = y1 - y0
        h = z1 - z0
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        rot_z = math.pi if facing == "SOUTH" else 0.0

        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
        if predef is not None and hasattr(elem, "PredefinedType"):
            elem.PredefinedType = predef
        if obj_type is not None:
            elem.ObjectType = obj_type

        prof = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=place_2d, XDim=float(w), YDim=float(d))
        solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=prof, Position=place_3d, ExtrudedDirection=dir_z, Depth=float(h))
        rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
        ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=_translation_matrix_m(cx, cy, z0, rot_z))
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])

        if pset_name and pset_props:
            pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
        return elem

    def add_pipe(name, p0, p1, od, pset_props):
        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPipeSegment", name=name)
        elem.PredefinedType = "RIGIDSEGMENT"
        elem.ObjectType = "ChilledWaterPipe"
        M, L = _pipe_matrix_m(p0, p1)
        prof = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=place_2d, Radius=float(od / 2.0))
        solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=prof, Position=place_3d, ExtrudedDirection=dir_z, Depth=float(L))
        rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=body, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
        ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=M)
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name="Pset_DCM_Pathway")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
        return elem

    # Background elements
    for r in data["racks"]:
        add_box("IfcFurniture", r["tag"], "USERDEFINED", "Rack", r["aabb"], facing=r["facing"],
                pset_name="Pset_DCM_Rack", pset_props={"Row": r["row"], "RackType": r["type"], "Facing": r["facing"], "RU": 42})

    for c in data["columns"]:
        add_box("IfcColumn", c["tag"], "COLUMN", "StructuralColumn", c["aabb"],
                pset_name="Pset_DCM_Column", pset_props={"Grid": c["grid"]})

    for u in data["crahs"]:
        add_box("IfcUnitaryEquipment", u["tag"], "AIRCONDITIONINGUNIT", "CRAH", u["aabb"], facing=u["facing"],
                pset_name="Pset_DCM_CRAH", pset_props={"Placement": u["placement"], "Facing": u["facing"], "Capacity_kW": u["capacity_kw"]})

    for p in data["pdus"]:
        add_box("IfcElectricDistributionBoard", p["tag"], "DISTRIBUTIONBOARD", "PDU", p["aabb"], facing=p["facing"],
                pset_name="Pset_DCM_PDU", pset_props={"ServesRow": p["serves_row"], "Facing": p["facing"], "Rating_kVA": 225.0})

    add_box("IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor", data["access_floor"]["aabb"],
            pset_name="Pset_DCM_AccessFloor", pset_props={"Thickness_mm": 35.0, "PlenumDepth_mm": 865.0})

    for ct in data["containment"]:
        if ct["kind"] == "roof":
            add_box("IfcCovering", ct["tag"], "CEILING", "ContainmentRoof", ct["aabb"],
                    pset_name="Pset_DCM_Containment", pset_props={"ElementKind": "Roof"})
        else:
            add_box("IfcDoor", ct["tag"], "DOOR", "ContainmentDoor", ct["aabb"],
                    pset_name="Pset_DCM_Containment", pset_props={"ElementKind": "EndDoor"})

    for s in data["sprinklers"]:
        add_box("IfcFireSuppressionTerminal", s["tag"], "SPRINKLER", "SprinklerHead", s["aabb"],
                pset_name="Pset_DCM_Sprinkler", pset_props={"Kind": s["kind"], "DeflectorElevation_mm": s["z"], "Standoff_mm": SPRINKLER_STANDOFF})

    # MEP Routes
    for i, seg in enumerate(data["routes"]["CT"]):
        add_box("IfcCableCarrierSegment", f"CT-1-{i:02d}", "CABLETRAYSEGMENT", "CableTray", seg["aabb"],
                pset_name="Pset_DCM_Pathway",
                pset_props={"Service": "Telecom", "Tag": "CT-1", "Width_mm": CT_W, "Height_mm": CT_H, "Zone": "UnderFloor", "Elevation_mm": Z_CT})

    for i, seg in enumerate(data["routes"]["BW"]):
        add_box("IfcCableSegment", f"BW-1-{i:02d}", "BUSBARSEGMENT", "Busway", seg["aabb"],
                pset_name="Pset_DCM_Pathway",
                pset_props={"Service": "Power", "Tag": "BW-1", "Width_mm": BW_W, "Height_mm": BW_H, "Zone": "Overhead", "Elevation_mm": Z_BW})

    for i, seg in enumerate(data["routes"]["CHW"]):
        add_pipe(f"CHW-1-{i:02d}", seg["p0"], seg["p1"], CHW_OD,
                 pset_props={"Service": "ChilledWater", "Tag": "CHW-1", "OuterDiameter_mm": CHW_OD, "Insulation_mm": 25.4, "Zone": "Overhead", "Elevation_mm": Z_CHW})

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)

    # Optional diagnostic reconciliation log next to IFC
    rec_path = os.path.join(os.path.dirname(os.path.abspath(out_path)), "reconciliation.json")
    reconciliation = {
        "room_mm": {"width": ROOM_W, "depth": ROOM_D, "soffit": Z_SOFFIT, "slab_top": Z_SLAB_TOP},
        "clearances_mm": {
            "min_headroom": Z_MIN_CLEAR,
            "sprinkler_standoff": SPRINKLER_STANDOFF,
            "tray_busway_min_sep": 300.0,
            "pdu_dedicated_space": 1800.0,
            "underfloor_panel_clear": 20.0,
        },
        "tiers_mm": {"CT_underfloor": Z_CT, "BW_overhead": Z_BW, "CHW_overhead": Z_CHW},
        "sections_mm": {
            "CT-1": {"w": CT_W, "h": CT_H},
            "BW-1": {"w": BW_W, "h": BW_H},
            "CHW-1": {"bare_od": 114.3, "insulation": 25.4, "jacket_od": CHW_OD},
        },
    }
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(reconciliation, f, indent=2)


if __name__ == "__main__":
    build_ifc(OUT_PATH)
