"""MEP Coordination Model for Data Hall 1 (hall_seed000_d000).

Builds the complete IFC4 coordination model (architectural background,
structural columns, fit-out equipment, fire protection sprinklers, and
clash-free overhead/under-floor MEP routing for telecom cable tray,
power busway, and chilled-water piping) using ifcopenshell==0.8.4 + numpy.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import ifcopenshell
import ifcopenshell.api


OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

# =============================================================================
# 1. HALL & DATUM CONSTANTS (mm, from A-101, A-301, A-601, A-602, E-101, F-101, M-101)
# =============================================================================
HALL_W = 27000.0
HALL_D = 21000.0
TILE = 600.0

Z_SLAB = -900.0
Z_FLOOR_BOT = -35.0
Z_FLOOR_TOP = 0.0
Z_MIN_CLEAR = 2600.0
Z_SOFFIT = 3600.0
Z_DEFLECTOR = 3574.6  # 25.4 mm below soffit
SPRINKLER_STANDOFF = 460.0

# Structural columns: Grid A/B/C (8400, 16800, 25200) x Grid 1/2 (8400, 16800)
COL_SIZE = 400.0
COL_POSITIONS: List[Tuple[str, float, float]] = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Cabinet rows (A-101, A-601)
ROW_START_X = 1800.0      # Tile column D
CA_EAST_X = 11200.0       # Common east edge of cross aisle (A-101 Note 5)
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
C1_W = 600.0
N1_W = 800.0

# Row specs: (row_id, y_cl, facing, west_tokens, east_tokens)
# Tokens: ("C1", n), ("N1", n), ("CU", 1), ("SP", 1), ("GAP600", n)
ROW_SPECS = [
    ("A", 3000.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
     [("C1", 7), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH",
     [("C1", 3), ("CU", 1), ("C1", 6), ("GAP600", 2), ("CU", 1)],
     [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("GAP600", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
     [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("GAP600", 2), ("CU", 1)],
     [("N1", 2), ("C1", 5), ("SP", 1), ("GAP600", 1), ("CU", 1), ("C1", 4)]),
]

# Perimeter CRAHs (A-601, M-101): (tag, x_sw, y_sw, w, d, h, facing)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0,   0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0,  0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs (A-601, E-101, A-101 Note 8: front flush with row front face)
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0,           "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D,   "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0,           "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D,  "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0,          "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D,  "NORTH"),
]

# Cold-Aisle Containment (A-602, A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5
CAC_AISLE_W = 1200.0

# Pathway section dimensions (A-602, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
TRAY_Z_BOT = 2970.0  # Top = 3097.0 (477.6 mm below 3574.6 deflector; >= 2600 headroom)

BUSWAY_W = 128.0
BUSWAY_H = 147.0
BUSWAY_Z_BOT = -380.0  # Top = -233.0 (198 mm below -35 floor panel; > 3000 mm from tray)

CHW_OD_BARE = 114.3
CHW_OD_INS = 168.3
CHW_Z_CL = -650.0  # Bottom = -734.15 (above -900 slab), Top = -565.85 (185.85 mm below busway)


# =============================================================================
# 2. GEOMETRY EXPANSION HELPERS
# =============================================================================
def build_row_equipment() -> Tuple[List[dict], List[dict], Dict[str, Tuple[float, float, float, float]]]:
    """Expand A-601 bay sequences into racks, in-row CRAHs, and row extents."""
    racks: List[dict] = []
    inrow_crahs: List[dict] = []
    row_extents: Dict[str, Tuple[float, float, float, float]] = {}

    for row_id, y_cl, facing, west_tokens, east_tokens in ROW_SPECS:
        y_sw = y_cl - CAB_DEPTH / 2.0
        rack_idx = 0
        crah_idx = 0

        # West side of cross aisle
        x = ROW_START_X
        for tok, count in west_tokens:
            for _ in range(count):
                if tok == "C1":
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id, "type": "C1",
                        "x": x, "y": y_sw, "w": C1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += C1_W
                elif tok == "N1":
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id, "type": "N1",
                        "x": x, "y": y_sw, "w": N1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += N1_W
                elif tok == "CU":
                    crah_idx += 1
                    inrow_crahs.append({
                        "tag": f"CRAH-{row_id}{crah_idx:02d}",
                        "row": row_id,
                        "x": x, "y": y_sw, "w": 600.0, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += 600.0
                elif tok in ("SP", "GAP600"):
                    x += 600.0
        west_end_x = x

        # East side of cross aisle
        x = CA_EAST_X
        for tok, count in east_tokens:
            for _ in range(count):
                if tok == "C1":
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id, "type": "C1",
                        "x": x, "y": y_sw, "w": C1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += C1_W
                elif tok == "N1":
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id, "type": "N1",
                        "x": x, "y": y_sw, "w": N1_W, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += N1_W
                elif tok == "CU":
                    crah_idx += 1
                    inrow_crahs.append({
                        "tag": f"CRAH-{row_id}{crah_idx:02d}",
                        "row": row_id,
                        "x": x, "y": y_sw, "w": 600.0, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                        "facing": facing,
                    })
                    x += 600.0
                elif tok in ("SP", "GAP600"):
                    x += 600.0
        east_end_x = x
        row_extents[row_id] = (ROW_START_X, west_end_x, CA_EAST_X, east_end_x)

    return racks, inrow_crahs, row_extents


def build_sprinklers() -> Tuple[List[Tuple[str, float, float, float]], List[Tuple[str, float, float, float]]]:
    """Return 63 ceiling heads and 16 in-aisle heads per F-101."""
    xs = [1500.0 + i * 3000.0 for i in range(9)]
    ys = [1500.0 + j * 3000.0 for j in range(7)]
    ceiling: List[Tuple[str, float, float, float]] = []
    idx = 0
    for y in ys:
        for x in xs:
            idx += 1
            hx, hy = x, y
            # Relocate heads inside 1500x1500 keep-out around columns (F-101 Detail 2)
            for _, cx, cy in COL_POSITIONS:
                if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                    hx = cx - 900.0 if hx <= cx else cx + 900.0
                    hy = cy - 900.0 if hy <= cy else cy + 900.0
            ceiling.append((f"SPR-C{idx:02d}", hx, hy, Z_DEFLECTOR))

    in_aisle: List[Tuple[str, float, float, float]] = []
    # 8 heads per contained aisle (4 west of CA, 4 east of CA) at Z = 1890
    aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]
    a_idx = 0
    for aisle_y in (7200.0, 12600.0):
        for ax in aisle_xs:
            a_idx += 1
            in_aisle.append((f"SPR-A{a_idx:02d}", ax, aisle_y, 1890.0))

    return ceiling, in_aisle


def build_route_segments() -> Tuple[List[dict], List[dict], List[dict]]:
    """Build butt-jointed, axis-aligned segments for Tray, Busway, and CHW.

    Every segment is a dict with:
      tag, axis ('X' or 'Y'), x0, y0, x1, y1, z_bot (or z_cl for pipe)
    Butt-jointing ensures 0 mm solid overlap at all corners and T-junctions
    while maintaining exact endpoint connectivity.
    """
    spine_x = 1200.0
    entry_y = 9900.0

    # Branch Y coordinates:
    #   Y=3000 serves Row A (dist 0)
    #   Y=7200 serves Rows B & C (dist 1200 each; clear of Grid 1 columns at Y=8400)
    #   Y=12600 serves Rows D & E (dist 1200 each)
    #   Y=15800 serves Row F (dist 1000; clear of Grid 2 columns at Y=16800)
    #   Y=1200 serves Perimeter CRAHs 01-04 (CHW only)
    row_branches = [
        ("A",  3000.0, 18800.0),
        ("BC", 7200.0, 19200.0),
        ("DE", 12600.0, 19600.0),
        ("F",  15800.0, 19400.0),
    ]

    def make_rect_network(prefix: str, width: float, height: float, z_bot: float,
                          include_perim: bool = False) -> List[dict]:
        hw = width / 2.0
        segs: List[dict] = []
        # 1. Entry from West wall (0, 9900) to west face of spine (spine_x - hw, 9900)
        segs.append({
            "tag": f"{prefix}-ENTRY", "axis": "X",
            "x0": 0.0, "y0": entry_y, "x1": spine_x - hw, "y1": entry_y,
            "w": width, "h": height, "z_bot": z_bot,
        })
        # 2. Spine along X = spine_x from south-most branch to north-most branch
        y_min = 1200.0 if include_perim else 3000.0
        y_max = 15800.0
        segs.append({
            "tag": f"{prefix}-SPINE", "axis": "Y",
            "x0": spine_x, "y0": y_min - hw, "x1": spine_x, "y1": y_max + hw,
            "w": width, "h": height, "z_bot": z_bot,
        })
        # 3. Eastward branches starting at east face of spine (spine_x + hw)
        if include_perim:
            segs.append({
                "tag": f"{prefix}-PERIM", "axis": "X",
                "x0": spine_x + hw, "y0": 1200.0, "x1": 25800.0, "y1": 1200.0,
                "w": width, "h": height, "z_bot": z_bot,
            })
        for bname, by, bx_end in row_branches:
            segs.append({
                "tag": f"{prefix}-ROW-{bname}", "axis": "X",
                "x0": spine_x + hw, "y0": by, "x1": bx_end, "y1": by,
                "w": width, "h": height, "z_bot": z_bot,
            })
        return segs

    tray_segs = make_rect_network("CT", TRAY_W, TRAY_H, TRAY_Z_BOT, include_perim=False)
    busway_segs = make_rect_network("BW", BUSWAY_W, BUSWAY_H, BUSWAY_Z_BOT, include_perim=False)
    chw_segs = make_rect_network("CHW", CHW_OD_INS, CHW_OD_INS, CHW_Z_CL - CHW_OD_INS / 2.0, include_perim=True)
    return tray_segs, busway_segs, chw_segs


# =============================================================================
# 3. IFC4 MODEL CONSTRUCTION HELPERS
# =============================================================================
def mat_translate_rotate_z(x_mm: float, y_mm: float, z_mm: float, angle_rad: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in metres (ifcopenshell is_si=True)."""
    c = math.cos(angle_rad)
    s = math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def make_box_rep(model, body_ctx, w_mm: float, d_mm: float, h_mm: float):
    """Create an extruded 2D rectangle centered at (0, 0) in XY, extruded +Z by h_mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w_mm),
        YDim=float(d_mm),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(h_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cylinder_rep(model, body_ctx, radius_mm: float, length_mm: float, axis: str = "Z"):
    """Create an extruded 2D circle along Z, X, or Y."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius_mm),
    )
    if axis == "Z":
        pos = None
    elif axis == "X":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
        )
    else:  # "Y"
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
        )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(length_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def add_pset(model, product, name: str, props: Dict[str, object]) -> None:
    pset = ifcopenshell.api.run("pset.add_pset", model, product=product, name=name)
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)


def place_and_contain(model, storey, product, rep, x_mm: float, y_mm: float, z_mm: float,
                      angle_rad: float = 0.0) -> None:
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[product])
    ifcopenshell.api.run("geometry.assign_representation", model, product=product, representation=rep)
    mat = mat_translate_rotate_z(x_mm, y_mm, z_mm, angle_rad)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=product, matrix=mat, is_si=True)


# =============================================================================
# 4. MAIN MODEL BUILDER
# =============================================================================
def build_model(out_path: str) -> None:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1")
    length_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI")
    ifcopenshell.api.run("unit.assign_unit", model, units=[length_unit])

    model_ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    # 4.1 Access Floor Panel (35 mm thick, Z = -35..0)
    floor = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcSlab",
        predefined_type="FLOOR", name="AccessFloor",
    )
    floor.ObjectType = "AccessFloor"
    floor_rep = make_box_rep(model, body_ctx, HALL_W, HALL_D, 35.0)
    place_and_contain(model, storey, floor, floor_rep, HALL_W / 2.0, HALL_D / 2.0, Z_FLOOR_BOT)

    # 4.2 Structural Columns (Z = 0..3600)
    col_rep = make_box_rep(model, body_ctx, COL_SIZE, COL_SIZE, Z_SOFFIT)
    for tag, cx, cy in COL_POSITIONS:
        col = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcColumn",
            predefined_type="COLUMN", name=tag,
        )
        col.ObjectType = "Column"
        place_and_contain(model, storey, col, col_rep, cx, cy, Z_FLOOR_TOP)

    # 4.3 Racks & In-Row CRAHs
    racks, inrow_crahs, row_extents = build_row_equipment()
    c1_rep = make_box_rep(model, body_ctx, C1_W, CAB_DEPTH, CAB_HEIGHT)
    n1_rep = make_box_rep(model, body_ctx, N1_W, CAB_DEPTH, CAB_HEIGHT)
    for r in racks:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcFurniture",
            predefined_type="USERDEFINED", name=r["tag"],
        )
        el.ObjectType = "Rack"
        cx = r["x"] + r["w"] / 2.0
        cy = r["y"] + r["d"] / 2.0
        ang = 0.0 if r["facing"] == "NORTH" else math.pi
        place_and_contain(model, storey, el, c1_rep if r["type"] == "C1" else n1_rep, cx, cy, Z_FLOOR_TOP, ang)
        add_pset(model, el, "Pset_DCM_Rack", {
            "Row": r["row"],
            "CabinetType": r["type"],
            "Width_mm": r["w"],
            "Depth_mm": r["d"],
            "Height_mm": r["h"],
            "RU": 42,
            "Facing": r["facing"],
            "Power_kW": 8.0,
            "Load_kg": 1363.0,
        })

    inrow_crah_rep = make_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT)
    for c in inrow_crahs:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcUnitaryEquipment",
            predefined_type="AIRHANDLER", name=c["tag"],
        )
        el.ObjectType = "CRAH"
        cx = c["x"] + c["w"] / 2.0
        cy = c["y"] + c["d"] / 2.0
        ang = 0.0 if c["facing"] == "NORTH" else math.pi
        place_and_contain(model, storey, el, inrow_crah_rep, cx, cy, Z_FLOOR_TOP, ang)
        add_pset(model, el, "Pset_DCM_CRAH", {
            "Placement": f"Row {c['row']}",
            "Capacity_kW": 50.0,
            "Airflow_m3h": 9000.0,
            "Facing": c["facing"],
            "Service": "Chilled Water, DN50",
        })

    # 4.4 Perimeter CRAHs
    perim_crah_rep = make_box_rep(model, body_ctx, 1200.0, 900.0, 2000.0)
    for tag, x, y, w, d, h, facing in PERIMETER_CRAHS:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcUnitaryEquipment",
            predefined_type="AIRHANDLER", name=tag,
        )
        el.ObjectType = "CRAH"
        place_and_contain(model, storey, el, perim_crah_rep, x + w / 2.0, y + d / 2.0, Z_FLOOR_TOP, 0.0)
        add_pset(model, el, "Pset_DCM_CRAH", {
            "Placement": "Perimeter",
            "Capacity_kW": 100.0,
            "Airflow_m3h": 20000.0,
            "Facing": facing,
            "Service": "Chilled Water, DN100",
        })

    # 4.5 PDUs
    pdu_rep = make_box_rep(model, body_ctx, PDU_W, PDU_D, PDU_H)
    for tag, serves_row, x, y, facing in PDUS:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcElectricDistributionBoard",
            predefined_type="DISTRIBUTIONBOARD", name=tag,
        )
        el.ObjectType = "PDU"
        ang = 0.0 if facing == "NORTH" else math.pi
        place_and_contain(model, storey, el, pdu_rep, x + PDU_W / 2.0, y + PDU_D / 2.0, Z_FLOOR_TOP, ang)
        add_pset(model, el, "Pset_DCM_PDU", {
            "ServesRow": serves_row,
            "Rating_kVA": 225.0,
            "Facing": facing,
            "WorkingSpace_mm": 900.0,
        })

    # 4.6 Cold-Aisle Containment (CAC-BC, CAC-DE)
    door_rep = make_box_rep(model, body_ctx, CAC_DOOR_THK, CAC_AISLE_W, CAC_DOOR_H)
    for cac_tag, r1, r2, aisle_y in [("CAC-BC", "B", "C", 7200.0), ("CAC-DE", "D", "E", 12600.0)]:
        w_start = max(row_extents[r1][0], row_extents[r2][0])
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_start = max(row_extents[r1][2], row_extents[r2][2])
        e_end = min(row_extents[r1][3], row_extents[r2][3])

        for side_idx, (sx, ex) in enumerate([(w_start, w_end), (e_start, e_end)], start=1):
            length = ex - sx
            roof = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcCovering",
                predefined_type="CEILING", name=f"{cac_tag}-ROOF-{side_idx}",
            )
            roof.ObjectType = "ContainmentRoof"
            roof_rep = make_box_rep(model, body_ctx, length, CAC_ROOF_W, CAC_ROOF_THK)
            place_and_contain(model, storey, roof, roof_rep, (sx + ex) / 2.0, aisle_y, CAC_ROOF_Z)
            add_pset(model, roof, "Pset_DCM_Containment", {"Tag": cac_tag, "Aisle": f"{r1}/{r2}"})

            # End doors at west and east ends of each roof panel (just outside panel span to avoid overlap)
            for d_idx, dx in enumerate([sx - CAC_DOOR_THK / 2.0, ex + CAC_DOOR_THK / 2.0], start=1):
                door = ifcopenshell.api.run(
                    "root.create_entity", model, ifc_class="IfcDoor",
                    predefined_type="DOOR", name=f"{cac_tag}-DOOR-{side_idx}-{d_idx}",
                )
                door.ObjectType = "ContainmentDoor"
                place_and_contain(model, storey, door, door_rep, dx, aisle_y, Z_FLOOR_TOP)

    # 4.7 Sprinkler Heads (63 ceiling + 16 in-aisle)
    ceiling_heads, in_aisle_heads = build_sprinklers()
    spr_rep = make_cylinder_rep(model, body_ctx, 25.0, 25.4, axis="Z")
    for tag, sx, sy, sz in ceiling_heads:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcFireSuppressionTerminal",
            predefined_type="SPRINKLER", name=tag,
        )
        el.ObjectType = "SprinklerHead"
        place_and_contain(model, storey, el, spr_rep, sx, sy, sz)
        add_pset(model, el, "Pset_DCM_Sprinkler", {
            "Type": "Ceiling",
            "DeflectorElevation_mm": sz,
            "Standoff_mm": SPRINKLER_STANDOFF,
        })
    for tag, sx, sy, sz in in_aisle_heads:
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcFireSuppressionTerminal",
            predefined_type="SPRINKLER", name=tag,
        )
        el.ObjectType = "SprinklerHead"
        place_and_contain(model, storey, el, spr_rep, sx, sy, sz)
        add_pset(model, el, "Pset_DCM_Sprinkler", {
            "Type": "InAisle",
            "DeflectorElevation_mm": sz,
            "Standoff_mm": SPRINKLER_STANDOFF,
        })

    # 4.8 MEP Routes (Telecom Cable Tray, Power Busway, Chilled Water Pipe)
    tray_segs, busway_segs, chw_segs = build_route_segments()

    for seg in tray_segs:
        length = abs(seg["x1"] - seg["x0"]) if seg["axis"] == "X" else abs(seg["y1"] - seg["y0"])
        w_x = length if seg["axis"] == "X" else seg["w"]
        w_y = seg["w"] if seg["axis"] == "X" else length
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcCableCarrierSegment",
            predefined_type="CABLETRAYSEGMENT", name=seg["tag"],
        )
        el.ObjectType = "CableTray"
        rep = make_box_rep(model, body_ctx, w_x, w_y, seg["h"])
        place_and_contain(
            model, storey, el, rep,
            (seg["x0"] + seg["x1"]) / 2.0,
            (seg["y0"] + seg["y1"]) / 2.0,
            seg["z_bot"],
        )
        add_pset(model, el, "Pset_DCM_Service", {
            "Service": "Telecom",
            "Tag": "CT-1",
            "Elevation_mm": seg["z_bot"] + seg["h"] / 2.0,
            "Zone": "Overhead",
        })

    for seg in busway_segs:
        length = abs(seg["x1"] - seg["x0"]) if seg["axis"] == "X" else abs(seg["y1"] - seg["y0"])
        w_x = length if seg["axis"] == "X" else seg["w"]
        w_y = seg["w"] if seg["axis"] == "X" else length
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcCableCarrierSegment",
            predefined_type="USERDEFINED", name=seg["tag"],
        )
        el.ObjectType = "Busway"
        rep = make_box_rep(model, body_ctx, w_x, w_y, seg["h"])
        place_and_contain(
            model, storey, el, rep,
            (seg["x0"] + seg["x1"]) / 2.0,
            (seg["y0"] + seg["y1"]) / 2.0,
            seg["z_bot"],
        )
        add_pset(model, el, "Pset_DCM_Service", {
            "Service": "Power",
            "Tag": "BW-1",
            "Elevation_mm": seg["z_bot"] + seg["h"] / 2.0,
            "Zone": "UnderFloor",
        })

    for seg in chw_segs:
        length = abs(seg["x1"] - seg["x0"]) if seg["axis"] == "X" else abs(seg["y1"] - seg["y0"])
        el = ifcopenshell.api.run(
            "root.create_entity", model, ifc_class="IfcPipeSegment",
            predefined_type="RIGIDSEGMENT", name=seg["tag"],
        )
        el.ObjectType = "ChilledWaterPipe"
        rep = make_cylinder_rep(model, body_ctx, CHW_OD_INS / 2.0, length, axis=seg["axis"])
        place_and_contain(
            model, storey, el, rep,
            min(seg["x0"], seg["x1"]) if seg["axis"] == "X" else seg["x0"],
            min(seg["y0"], seg["y1"]) if seg["axis"] == "Y" else seg["y0"],
            CHW_Z_CL,
        )
        add_pset(model, el, "Pset_DCM_Service", {
            "Service": "ChilledWater",
            "Tag": "CHW-1",
            "NominalDiameter_mm": 100.0,
            "OuterDiameter_mm": CHW_OD_BARE,
            "InsulatedDiameter_mm": CHW_OD_INS,
            "Elevation_mm": CHW_Z_CL,
            "Zone": "UnderFloor",
        })

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out))


if __name__ == "__main__":
    build_model(OUT_PATH)
