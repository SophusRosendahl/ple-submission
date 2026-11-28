"""Coordinated 3D IFC4 model builder for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Builds the architectural/structural/MEP background from the 7-sheet drawing set
(A-101, A-301, A-601, A-602, E-101, F-101, M-101) and routes telecom cable tray
(CT-1), power busway (BW-1), and chilled-water piping (CHW-1) clash-free.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
from __future__ import annotations

import math
import os
import sys
import numpy as np


# ---------------------------------------------------------------------------
# Baked-in drawing data (all dimensions in mm)
# ---------------------------------------------------------------------------

ROOM_W = 27000.0
ROOM_D = 21000.0
SOFFIT_Z = 3600.0
FLOOR_THK = 35.0
SLAB_TOP_Z = -900.0

COL_SIZE = 600.0
COL_GRID_X = [8400.0, 16800.0, 25200.0]
COL_GRID_Y = [8400.0, 16800.0]

ROW_X_START = 1800.0
CA_EAST_X = 11400.0

# (row_id, y_center, facing, bay_tokens)
# Tokens: ("C1", n), ("N1", n), ("CU", 1), ("SP", 1), ("OMIT", width_mm), ("CA", 0)
ROW_SPECS = [
    ("A", 3000.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
        ("CA", 0),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("B", 6000.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
        ("CA", 0),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("C", 8400.0, "SOUTH", [
        ("C1", 3), ("CU", 1), ("C1", 6), ("OMIT", 1200.0), ("CU", 1),
        ("CA", 0),
        ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT", 1200.0), ("C1", 3),
    ]),
    ("D", 11400.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
        ("CA", 0),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("E", 13800.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
        ("CA", 0),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("F", 16800.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("OMIT", 1200.0), ("CU", 1),
        ("CA", 0),
        ("N1", 2), ("C1", 5), ("SP", 1), ("OMIT", 600.0), ("CU", 1), ("C1", 4),
    ]),
]

CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
CAB_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0}

# Perimeter CRAHs (A-601, A-101): 1200 W x 900 D x 2000 H, facing NORTH, Y=[0, 900]
PERIM_CRAHS = [
    ("CRAH-01", 600.0),
    ("CRAH-02", 9000.0),
    ("CRAH-03", 16800.0),
    ("CRAH-04", 25200.0),
]

# PDUs (A-601, A-101): 762 W x 813 D x 1959 H, front flush with served row front
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_SPECS = [
    ("PDU-01", "A", 21400.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 22000.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21400.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 22000.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21400.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 22000.0, 17400.0 - PDU_D, "NORTH"),
]

# Cold-Aisle Containment (A-602, A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5
CAC_SPECS = [
    ("CAC-BC", 7200.0, [(1800.0, 9600.0), (11400.0, 19400.0)]),
    ("CAC-DE", 12600.0, [(1800.0, 9800.0), (11400.0, 19200.0)]),
]

# Pathway section dimensions (A-602, E-101, M-101)
CT_W, CT_H = 683.0, 127.0
BW_W, BW_H = 128.0, 147.0
CHW_BARE_OD = 114.3
CHW_INS_OD = 168.3  # ASTM C585 jacketed OD over 25.4 mm insulation

# Tier elevations (mm, relative to FF = 0)
BW_Z_MIN = 2800.0              # Overhead: [2800, 2947], >= 2600 headroom, 627.6 mm below deflectors
CT_Z_MIN = -220.0              # Under-floor: [-220, -93], >= 20 mm below floor panel (-55)
CHW_Z_CENTER = -515.85         # Under-floor: [-600.0, -431.7], >= 211.7 mm below CT-1, >= -900 slab


def build_model_data() -> dict:
    """Construct all background solids, sprinklers, and MEP route segments."""
    solids = []
    rows_meta = []
    crahs_meta = []
    pdus_meta = []
    sprinklers = []
    mep_segments = []

    # 1. Access floor panel: Z = [-35, 0]
    solids.append({
        "name": "AccessFloor",
        "category": "AccessFloor",
        "aabb": (0.0, ROOM_W, 0.0, ROOM_D, -FLOOR_THK, 0.0),
        "facing": "NORTH",
        "props": {"ThicknessMm": FLOOR_THK, "TilePitchMm": 600.0},
    })

    # 2. Structural columns: Z = [0, 3600]
    col_labels_x = ["A", "B", "C"]
    col_labels_y = ["1", "2"]
    for ix, cx in enumerate(COL_GRID_X):
        for iy, cy in enumerate(COL_GRID_Y):
            name = f"COL-{col_labels_x[ix]}{col_labels_y[iy]}"
            solids.append({
                "name": name,
                "category": "Column",
                "aabb": (cx - COL_SIZE / 2, cx + COL_SIZE / 2,
                         cy - COL_SIZE / 2, cy + COL_SIZE / 2,
                         0.0, SOFFIT_Z),
                "facing": "NORTH",
                "props": {"GridX": col_labels_x[ix], "GridY": col_labels_y[iy], "SizeMm": COL_SIZE},
            })

    # 3. Server cabinets & in-row CRAHs
    for row_id, y_c, facing, tokens in ROW_SPECS:
        x = ROW_X_START
        y0, y1 = y_c - CAB_DEPTH / 2, y_c + CAB_DEPTH / 2
        rack_idx = 0
        cu_idx = 0
        for kind, count in tokens:
            if kind == "CA":
                x = CA_EAST_X
            elif kind == "OMIT":
                x += float(count)
            elif kind == "SP":
                x += CAB_WIDTHS["SP"] * count
            elif kind in ("C1", "N1"):
                w = CAB_WIDTHS[kind]
                for _ in range(count):
                    rack_idx += 1
                    name = f"RACK-{row_id}{rack_idx:02d}"
                    solids.append({
                        "name": name,
                        "category": "Rack",
                        "aabb": (x, x + w, y0, y1, 0.0, CAB_HEIGHT),
                        "facing": facing,
                        "props": {
                            "Row": row_id,
                            "CabinetType": kind,
                            "RU": 42,
                            "WidthMm": w,
                            "DepthMm": CAB_DEPTH,
                            "HeightMm": CAB_HEIGHT,
                            "Facing": facing,
                            "PowerKw": 8.0,
                            "LoadKg": 1363.0,
                        },
                    })
                    x += w
            elif kind == "CU":
                w = CAB_WIDTHS["CU"]
                for _ in range(count):
                    cu_idx += 1
                    name = f"CRAH-{row_id}{cu_idx:02d}"
                    solids.append({
                        "name": name,
                        "category": "CRAH",
                        "aabb": (x, x + w, y0, y1, 0.0, CAB_HEIGHT),
                        "facing": facing,
                        "props": {
                            "Placement": f"IN-ROW {row_id}",
                            "CapacityKw": 50.0,
                            "AirflowM3h": 9000.0,
                            "Facing": facing,
                            "Service": "CHILLED WATER, DN50",
                        },
                    })
                    crahs_meta.append({"name": name, "x_c": x + w / 2, "y_c": y_c})
                    x += w
        rows_meta.append({"row": row_id, "y_c": y_c, "x_min": ROW_X_START, "x_max": x})

    # 4. Perimeter CRAHs
    for name, x0 in PERIM_CRAHS:
        aabb = (x0, x0 + 1200.0, 0.0, 900.0, 0.0, 2000.0)
        solids.append({
            "name": name,
            "category": "CRAH",
            "aabb": aabb,
            "facing": "NORTH",
            "props": {
                "Placement": "PERIMETER",
                "CapacityKw": 100.0,
                "AirflowM3h": 20000.0,
                "Facing": "NORTH",
                "Service": "CHILLED WATER, DN100",
            },
        })
        crahs_meta.append({"name": name, "x_c": x0 + 600.0, "y_c": 450.0})

    # 5. PDUs
    for name, serves_row, x0, y0, facing in PDU_SPECS:
        aabb = (x0, x0 + PDU_W, y0, y0 + PDU_D, 0.0, PDU_H)
        solids.append({
            "name": name,
            "category": "PDU",
            "aabb": aabb,
            "facing": facing,
            "props": {
                "ServesRow": serves_row,
                "RatingKva": 225.0,
                "Facing": facing,
                "WorkingSpaceMm": 900.0,
                "DedicatedSpaceHeightMm": 1800.0,
            },
        })
        pdus_meta.append({"name": name, "aabb": aabb})

    # 6. Cold-Aisle Containment roofs & end doors
    for tag, y_c, spans in CAC_SPECS:
        for idx, (x0, x1) in enumerate(spans, start=1):
            solids.append({
                "name": f"{tag}-ROOF-{idx}",
                "category": "ContainmentRoof",
                "aabb": (x0, x1, y_c - CAC_ROOF_W / 2, y_c + CAC_ROOF_W / 2,
                         CAC_ROOF_Z, CAC_ROOF_Z + CAC_ROOF_THK),
                "facing": "NORTH",
                "props": {"ContainmentTag": tag, "Part": "Roof"},
            })
            # End doors at x0 (west face) and x1 (east face), inside the 1200 mm aisle
            solids.append({
                "name": f"{tag}-DOOR-{idx}W",
                "category": "ContainmentDoor",
                "aabb": (x0 - CAC_DOOR_THK, x0, y_c - 600.0, y_c + 600.0, 0.0, CAC_DOOR_H),
                "facing": "NORTH",
                "props": {"ContainmentTag": tag, "Part": "EndDoor"},
            })
            solids.append({
                "name": f"{tag}-DOOR-{idx}E",
                "category": "ContainmentDoor",
                "aabb": (x1, x1 + CAC_DOOR_THK, y_c - 600.0, y_c + 600.0, 0.0, CAC_DOOR_H),
                "facing": "NORTH",
                "props": {"ContainmentTag": tag, "Part": "EndDoor"},
            })

    # 7. Sprinklers (63 ceiling + 16 in-aisle)
    ceil_idx = 0
    for i in range(9):
        sx = 1500.0 + 3000.0 * i
        for j in range(7):
            sy = 1500.0 + 3000.0 * j
            # Relocate out of 1500 mm keep-out box (±750 mm) around structural columns
            for cx in COL_GRID_X:
                for cy in COL_GRID_Y:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sx = cx - 900.0 if sx <= cx else cx + 900.0
                        sy = cy - 900.0 if sy <= cy else cy + 900.0
            ceil_idx += 1
            sprinklers.append({
                "name": f"SPK-C{ceil_idx:02d}",
                "kind": "Ceiling",
                "x": sx,
                "y": sy,
                "z_deflector": SOFFIT_Z - 25.4,
            })

    aisle_idx = 0
    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9000.0, 12000.0, 14400.0, 16800.0, 18600.0]
    for tag, y_c in [("BC", 7200.0), ("DE", 12600.0)]:
        for sx in in_aisle_xs:
            aisle_idx += 1
            sprinklers.append({
                "name": f"SPK-A{aisle_idx:02d}",
                "kind": f"InAisle-{tag}",
                "x": sx,
                "y": y_c,
                "z_deflector": 1890.0,
            })

    # 8. MEP Routing (axis-aligned straight segments)
    def add_rect_seg(svc: str, name: str, p0: tuple, p1: tuple, w: float, h: float, z_min: float, tier: str):
        x0, y0 = p0
        x1, y1 = p1
        if abs(x1 - x0) >= abs(y1 - y0):
            # East-West run
            xmin, xmax = min(x0, x1), max(x0, x1)
            ymin, ymax = y0 - w / 2, y0 + w / 2
        else:
            # North-South run
            xmin, xmax = x0 - w / 2, x0 + w / 2
            ymin, ymax = min(y0, y1), max(y0, y1)
        mep_segments.append({
            "name": name,
            "service": svc,
            "shape": "rect",
            "p0": (x0, y0, z_min + h / 2),
            "p1": (x1, y1, z_min + h / 2),
            "w": w,
            "h": h,
            "aabb": (xmin, xmax, ymin, ymax, z_min, z_min + h),
            "z_center": z_min + h / 2,
            "tier": tier,
        })

    def add_pipe_seg(name: str, p0: tuple, p1: tuple, z_c: float, tier: str):
        x0, y0 = p0
        x1, y1 = p1
        r = CHW_INS_OD / 2.0
        xmin, xmax = min(x0, x1) - (0.0 if abs(x1 - x0) > 0 else r), max(x0, x1) + (0.0 if abs(x1 - x0) > 0 else r)
        ymin, ymax = min(y0, y1) - (0.0 if abs(y1 - y0) > 0 else r), max(y0, y1) + (0.0 if abs(y1 - y0) > 0 else r)
        mep_segments.append({
            "name": name,
            "service": "CHW-1",
            "shape": "pipe",
            "p0": (x0, y0, z_c),
            "p1": (x1, y1, z_c),
            "r_ins": r,
            "aabb": (xmin, xmax, ymin, ymax, z_c - r, z_c + r),
            "z_center": z_c,
            "tier": tier,
        })

    spine_x = 1200.0
    branch_end_x = 18600.0
    row_ys = [4500.0, 9900.0, 15300.0]

    # Power Busway (BW-1) — Overhead
    add_rect_seg("BW-1", "BW-ENTRY", (0.0, 9900.0), (spine_x, 9900.0), BW_W, BW_H, BW_Z_MIN, "Overhead")
    add_rect_seg("BW-1", "BW-SPINE-S", (spine_x, 4500.0), (spine_x, 9900.0), BW_W, BW_H, BW_Z_MIN, "Overhead")
    add_rect_seg("BW-1", "BW-SPINE-N", (spine_x, 9900.0), (spine_x, 15300.0), BW_W, BW_H, BW_Z_MIN, "Overhead")
    for idx, ry in enumerate(row_ys, start=1):
        add_rect_seg("BW-1", f"BW-BR-{idx}", (spine_x, ry), (branch_end_x, ry), BW_W, BW_H, BW_Z_MIN, "Overhead")

    # Telecom Cable Tray (CT-1) — Under-floor plenum
    add_rect_seg("CT-1", "CT-ENTRY", (0.0, 9900.0), (spine_x, 9900.0), CT_W, CT_H, CT_Z_MIN, "UnderFloor")
    add_rect_seg("CT-1", "CT-SPINE-S", (spine_x, 4500.0), (spine_x, 9900.0), CT_W, CT_H, CT_Z_MIN, "UnderFloor")
    add_rect_seg("CT-1", "CT-SPINE-N", (spine_x, 9900.0), (spine_x, 15300.0), CT_W, CT_H, CT_Z_MIN, "UnderFloor")
    for idx, ry in enumerate(row_ys, start=1):
        add_rect_seg("CT-1", f"CT-BR-{idx}", (spine_x, ry), (branch_end_x, ry), CT_W, CT_H, CT_Z_MIN, "UnderFloor")

    # Chilled Water (CHW-1) — Under-floor plenum
    add_pipe_seg("CHW-ENTRY", (0.0, 9900.0), (spine_x, 9900.0), CHW_Z_CENTER, "UnderFloor")
    add_pipe_seg("CHW-SPINE-P", (spine_x, 450.0), (spine_x, 4500.0), CHW_Z_CENTER, "UnderFloor")
    add_pipe_seg("CHW-SPINE-S", (spine_x, 4500.0), (spine_x, 9900.0), CHW_Z_CENTER, "UnderFloor")
    add_pipe_seg("CHW-SPINE-N", (spine_x, 9900.0), (spine_x, 15300.0), CHW_Z_CENTER, "UnderFloor")
    add_pipe_seg("CHW-BR-PERIM", (spine_x, 450.0), (25800.0, 450.0), CHW_Z_CENTER, "UnderFloor")
    for idx, ry in enumerate(row_ys, start=1):
        add_pipe_seg(f"CHW-BR-{idx}", (spine_x, ry), (branch_end_x, ry), CHW_Z_CENTER, "UnderFloor")

    return {
        "solids": solids,
        "rows": rows_meta,
        "crahs": crahs_meta,
        "pdus": pdus_meta,
        "sprinklers": sprinklers,
        "mep_segments": mep_segments,
    }


# ---------------------------------------------------------------------------
# IFC4 generation (requires ifcopenshell==0.8.4)
# ---------------------------------------------------------------------------

def _mat4(tx_mm: float, ty_mm: float, tz_mm: float, yaw_rad: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (as required by ifcopenshell.api)."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = tx_mm / 1000.0
    m[1, 3] = ty_mm / 1000.0
    m[2, 3] = tz_mm / 1000.0
    return m


def _pipe_mat4(p0: tuple, p1: tuple) -> tuple[np.ndarray, float]:
    """4x4 placement matrix (translations in metres) aligning local +Z along p0->p1."""
    dx, dy, dz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    ux, uy, uz = dx / length, dy / length, dz / length
    m = np.eye(4, dtype=float)
    if abs(ux) > 0.5:
        if ux > 0:
            m[:3, 0] = [0.0, 0.0, -1.0]
            m[:3, 1] = [0.0, 1.0, 0.0]
            m[:3, 2] = [1.0, 0.0, 0.0]
        else:
            m[:3, 0] = [0.0, 0.0, 1.0]
            m[:3, 1] = [0.0, 1.0, 0.0]
            m[:3, 2] = [-1.0, 0.0, 0.0]
    elif abs(uy) > 0.5:
        if uy > 0:
            m[:3, 0] = [1.0, 0.0, 0.0]
            m[:3, 1] = [0.0, 0.0, -1.0]
            m[:3, 2] = [0.0, 1.0, 0.0]
        else:
            m[:3, 0] = [1.0, 0.0, 0.0]
            m[:3, 1] = [0.0, 0.0, 1.0]
            m[:3, 2] = [0.0, -1.0, 0.0]
    m[0, 3] = p0[0] / 1000.0
    m[1, 3] = p0[1] / 1000.0
    m[2, 3] = p0[2] / 1000.0
    return m, length


def build_ifc(model_data: dict, out_path: str) -> None:
    import ifcopenshell
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1")
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

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    origin_3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    axis_pos_3d = model.create_entity("IfcAxis2Placement3D", Location=origin_3d)
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))

    def make_box_rep(dx: float, dy: float, dz: float):
        prof = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=float(dx), YDim=float(dy))
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=prof,
            Position=axis_pos_3d,
            ExtrudedDirection=dir_z,
            Depth=float(dz),
        )
        return model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_ctx,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

    def make_cyl_rep(radius: float, length: float):
        prof = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=prof,
            Position=axis_pos_3d,
            ExtrudedDirection=dir_z,
            Depth=float(length),
        )
        return model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_ctx,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )

    def attach_pset(elem, pset_name: str, props: dict):
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)

    cat_map = {
        "AccessFloor": ("IfcSlab", "FLOOR", "AccessFloor", "Pset_DCM_AccessFloor"),
        "Column": ("IfcColumn", "COLUMN", "StructuralColumn", "Pset_DCM_Column"),
        "Rack": ("IfcFurniture", "USERDEFINED", "Rack", "Pset_DCM_Rack"),
        "CRAH": ("IfcUnitaryEquipment", "AIRCONDITIONINGUNIT", "CRAH", "Pset_DCM_CRAH"),
        "PDU": ("IfcElectricDistributionBoard", "DISTRIBUTIONBOARD", "PDU", "Pset_DCM_PDU"),
        "ContainmentRoof": ("IfcBuildingElementProxy", "USERDEFINED", "ColdAisleContainment", "Pset_DCM_Containment"),
        "ContainmentDoor": ("IfcBuildingElementProxy", "USERDEFINED", "ColdAisleContainment", "Pset_DCM_Containment"),
    }

    all_products = []

    # Background solids
    for s in model_data["solids"]:
        ifc_cls, predef, obj_type, pset_name = cat_map[s["category"]]
        elem = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_cls, name=s["name"], predefined_type=predef)
        elem.ObjectType = obj_type
        x0, x1, y0, y1, z0, z1 = s["aabb"]
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        yaw = math.pi if s.get("facing") == "SOUTH" else 0.0
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=_mat4(cx, cy, z0, yaw))
        rep = make_box_rep(dx, dy, dz)
        ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
        attach_pset(elem, pset_name, s["props"])
        all_products.append(elem)

    # Sprinklers (small 50 mm dia x 50 mm tall body ending at deflector elevation)
    for sp in model_data["sprinklers"]:
        elem = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcFireSuppressionTerminal", name=sp["name"], predefined_type="SPRINKLER"
        )
        elem.ObjectType = "SprinklerHead"
        ifcopenshell.api.run(
            "geometry.edit_object_placement", model, product=elem, matrix=_mat4(sp["x"], sp["y"], sp["z_deflector"], 0.0)
        )
        rep = make_cyl_rep(25.0, 25.0)
        ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
        attach_pset(elem, "Pset_DCM_Sprinkler", {
            "HeadType": sp["kind"],
            "DeflectorElevationMm": sp["z_deflector"],
            "StandoffMm": 460.0,
        })
        all_products.append(elem)

    # MEP Segments
    for seg in model_data["mep_segments"]:
        svc = seg["service"]
        if svc == "CT-1":
            elem = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcCableCarrierSegment", name=seg["name"], predefined_type="CABLETRAYSEGMENT"
            )
            elem.ObjectType = "CableTray"
        elif svc == "BW-1":
            elem = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcCableCarrierSegment", name=seg["name"], predefined_type="USERDEFINED"
            )
            elem.ObjectType = "Busway"
        else:
            elem = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcPipeSegment", name=seg["name"], predefined_type="RIGIDSEGMENT"
            )
            elem.ObjectType = "ChilledWaterPipe"

        if seg["shape"] == "rect":
            x0, x1, y0, y1, z0, z1 = seg["aabb"]
            dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=_mat4(cx, cy, z0, 0.0))
            rep = make_box_rep(dx, dy, dz)
            props = {
                "Service": svc,
                "Tier": seg["tier"],
                "ElevationMm": seg["z_center"],
                "WidthMm": seg["w"],
                "HeightMm": seg["h"],
            }
        else:
            m, length = _pipe_mat4(seg["p0"], seg["p1"])
            ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=m)
            rep = make_cyl_rep(seg["r_ins"], length)
            props = {
                "Service": svc,
                "Tier": seg["tier"],
                "ElevationMm": seg["z_center"],
                "OuterDiameterMm": CHW_BARE_OD,
                "InsulatedODMm": CHW_INS_OD,
                "InsulationMm": 25.4,
            }

        ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
        attach_pset(elem, "Pset_DCM_MEP", props)
        all_products.append(elem)

    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=all_products)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    data = build_model_data()
    build_ifc(data, out_file)
