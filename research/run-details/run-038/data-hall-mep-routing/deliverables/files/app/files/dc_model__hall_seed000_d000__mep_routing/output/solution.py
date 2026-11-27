"""Meridian Data Center — Phase 1, Data Hall 1 (hall_seed000_d000)
Coordinated IFC4 BIM model: architectural/equipment background + clash-free MEP routing.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
from __future__ import annotations

import math
import os
import sys
from typing import Any

import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

# ---------------------------------------------------------------------------
# 1. Hall geometry & vertical datums (mm) — from A-101, A-301, A-601, A-602
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
SLAB_TOP_Z = -900.0
FLOOR_PANEL_THK = 35.0
FLOOR_TOP_Z = 0.0
MIN_CLEAR_Z = 2600.0
SOFFIT_Z = 3600.0
CEIL_DEFLECTOR_Z = 3574.6  # 25.4 mm below soffit
SPRINKLER_STANDOFF = 460.0
IN_AISLE_DEFLECTOR_Z = 1890.0

# Structural columns (A-101, A-301): 400 x 400 mm, Z = 0..3600
COL_SIZE = 400.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Cabinet rows (A-101, A-601)
ROW_START_X = 1800.0  # Tile D (index 3 * 600)
RACK_DEPTH = 1200.0
RACK_HEIGHT = 2000.0
C1_WIDTH = 600.0
N1_WIDTH = 800.0
CU_WIDTH = 600.0
SP_WIDTH = 600.0
CA_WIDTH = 1200.0

ROW_SPECS = [
    # (row_id, y_center, facing, bay_tokens)
    (
        "A",
        3000.0,
        "SOUTH",
        ["4C1", "CU", "3C1", "N1", "3C1", "CU", "CA", "6C1", "SP", "CU", "5C1"],
    ),
    (
        "B",
        6000.0,
        "NORTH",
        ["4C1", "CU", "5C1", "2N1", "CU", "CA", "7C1", "SP", "CU", "5C1"],
    ),
    (
        "C",
        8400.0,
        "SOUTH",
        ["3C1", "CU", "6C1", "2-600", "CU", "CA", "N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"],
    ),
    (
        "D",
        11400.0,
        "NORTH",
        ["4C1", "CU", "3C1", "2N1", "2C1", "CU", "CA", "7C1", "SP", "CU", "5C1"],
    ),
    (
        "E",
        13800.0,
        "SOUTH",
        ["4C1", "CU", "5C1", "N1", "C1", "CU", "CA", "6C1", "SP", "CU", "5C1"],
    ),
    (
        "F",
        16800.0,
        "NORTH",
        ["4C1", "CU", "5C1", "2-600", "CU", "CA", "2N1", "5C1", "SP", "2-600", "CU", "4C1"],
    ),
]

# Perimeter CRAHs (A-601): tiles B01, P01, AC01, AQ01 -> X = 600, 9000, 16800, 25200
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, A-101 Note 8: front flush with front face of row it serves)
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    # (tag, row_id, x_sw, y_sw, facing)
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21000.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Cold-Aisle Containment (A-602, A-301 Detail 3)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5
CAC_AISLES = [
    # (tag, y_center, segments_x)
    ("CAC-BC", 7200.0, [(1800.0, 9600.0), (10800.0, 18800.0)]),
    ("CAC-DE", 12600.0, [(1800.0, 9600.0), (10800.0, 18800.0)]),
]

# MEP Pathway sections (A-602, M-101)
CT_W, CT_H = 683.0, 127.0
BW_W, BW_H = 128.0, 147.0
CHW_OD = 168.3  # DN100 + 25.4 mm insulation jacket per M-101 Note 4

# Service routing elevations (centreline Z in mm)
BW_Z = 2800.0    # Overhead: Z = 2726.5..2873.5 (>= 2600, 701 mm below deflector)
CT_Z = -200.0    # Under-floor: Z = -263.5..-136.5 (>= 20 mm below -35 panel)
CHW_Z = -600.0   # Under-floor: Z = -684.15..-515.85 (above -900 slab, below CT)
ENTRY_Y = 9900.0
TRUNK_X = 900.0  # West service strip (0..1800)


def expand_row_bays() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[float, float]]]:
    """Expand A-601 bay sequences into exact rack and in-row CRAH placements."""
    racks: list[dict[str, Any]] = []
    inrow_crahs: list[dict[str, Any]] = []
    row_extents: dict[str, tuple[float, float]] = {}

    for row_id, y_center, facing, tokens in ROW_SPECS:
        x = ROW_START_X
        rack_idx = 0
        crah_idx = 0
        for tok in tokens:
            if tok == "CU":
                crah_idx += 1
                inrow_crahs.append({
                    "name": f"CRAH-{row_id}{crah_idx:02d}",
                    "row": row_id,
                    "cx": x + CU_WIDTH / 2.0,
                    "cy": y_center,
                    "w": CU_WIDTH,
                    "d": RACK_DEPTH,
                    "h": RACK_HEIGHT,
                    "facing": facing,
                })
                x += CU_WIDTH
            elif tok == "CA":
                x += CA_WIDTH
            elif tok == "SP":
                x += SP_WIDTH
            elif tok.endswith("-600"):
                cnt = int(tok.split("-")[0]) if tok[0].isdigit() else 1
                x += cnt * 600.0
            elif tok.endswith("-800"):
                cnt = int(tok.split("-")[0]) if tok[0].isdigit() else 1
                x += cnt * 800.0
            elif tok.endswith("C1"):
                cnt = int(tok[:-2]) if len(tok) > 2 else 1
                for _ in range(cnt):
                    rack_idx += 1
                    racks.append({
                        "name": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id,
                        "type": "C1",
                        "cx": x + C1_WIDTH / 2.0,
                        "cy": y_center,
                        "w": C1_WIDTH,
                        "d": RACK_DEPTH,
                        "h": RACK_HEIGHT,
                        "facing": facing,
                    })
                    x += C1_WIDTH
            elif tok.endswith("N1"):
                cnt = int(tok[:-2]) if len(tok) > 2 else 1
                for _ in range(cnt):
                    rack_idx += 1
                    racks.append({
                        "name": f"RACK-{row_id}{rack_idx:02d}",
                        "row": row_id,
                        "type": "N1",
                        "cx": x + N1_WIDTH / 2.0,
                        "cy": y_center,
                        "w": N1_WIDTH,
                        "d": RACK_DEPTH,
                        "h": RACK_HEIGHT,
                        "facing": facing,
                    })
                    x += N1_WIDTH
            else:
                raise ValueError(f"Unknown bay token: {tok}")
        row_extents[row_id] = (ROW_START_X, x)
    return racks, inrow_crahs, row_extents


def build_sprinklers() -> list[dict[str, Any]]:
    """Generate 63 ceiling heads + 16 in-aisle heads per F-101 and A-301."""
    heads: list[dict[str, Any]] = []
    # 63 ceiling heads: 9 x 7 grid at 3000 mm spacing starting at 1500 mm
    idx = 0
    for j in range(7):
        y = 1500.0 + j * 3000.0
        for i in range(9):
            x = 1500.0 + i * 3000.0
            idx += 1
            heads.append({
                "name": f"SPR-CEIL-{idx:02d}",
                "kind": "Ceiling",
                "x": x,
                "y": y,
                "z_deflector": CEIL_DEFLECTOR_Z,
            })
    # 16 in-aisle heads: 8 in CAC-BC, 8 in CAC-DE
    aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 11700.0, 13800.0, 15900.0, 18000.0]
    idx = 0
    for y_aisle in [7200.0, 12600.0]:
        for x in aisle_xs:
            idx += 1
            heads.append({
                "name": f"SPR-AISLE-{idx:02d}",
                "kind": "InAisle",
                "x": x,
                "y": y_aisle,
                "z_deflector": IN_AISLE_DEFLECTOR_Z,
            })
    return heads


def build_mep_segments(row_extents: dict[str, tuple[float, float]]) -> dict[str, list[dict[str, Any]]]:
    """Build axis-aligned straight MEP segments for Busway, Cable Tray, and CHW.

    Every segment is a dict with p0=(x0,y0,z0), p1=(x1,y1,z1), kind, name.
    Branches start flush with the trunk outer face (0 mm overlap, 0 mm gap).
    """
    # Row Y coordinates for Busway (offset in Rows C & F to clear 400x400 columns at 8400, 16800)
    bw_row_y = {
        "A": 3000.0,
        "B": 6000.0,
        "C": 8900.0,   # clears Col at 8400 ± 200
        "D": 11400.0,
        "E": 13800.0,
        "F": 16300.0,  # clears Col at 16800 ± 200
    }
    # Under-floor rows run straight down row centrelines (columns start at Z = 0)
    uf_row_y = {r[0]: r[1] for r in ROW_SPECS}

    def make_network(
        prefix: str,
        z: float,
        trunk_w: float,
        row_ys: dict[str, float],
        include_perim_crah: bool = False,
    ) -> list[dict[str, Any]]:
        segs: list[dict[str, Any]] = []
        hw = trunk_w / 2.0
        y_min = 450.0 if include_perim_crah else min(row_ys.values())
        y_max = max(row_ys.values())

        # 1. Entry stub from West wall (X=0, Y=9900) to West face of trunk
        segs.append({
            "name": f"{prefix}-ENTRY",
            "p0": (0.0, ENTRY_Y, z),
            "p1": (TRUNK_X - hw, ENTRY_Y, z),
        })
        # 2. Main North-South trunk in West service strip
        segs.append({
            "name": f"{prefix}-TRUNK",
            "p0": (TRUNK_X, y_min - hw, z),
            "p1": (TRUNK_X, y_max + hw, z),
        })
        # 3. Row branches going East from East face of trunk
        for row_id in ["A", "B", "C", "D", "E", "F"]:
            _, x_end = row_extents[row_id]
            y = row_ys[row_id]
            segs.append({
                "name": f"{prefix}-ROW-{row_id}",
                "p0": (TRUNK_X + hw, y, z),
                "p1": (x_end - 300.0, y, z),
            })
        # 4. Perimeter CRAH branch (CHW only)
        if include_perim_crah:
            segs.append({
                "name": f"{prefix}-PERIM-CRAH",
                "p0": (TRUNK_X + hw, 450.0, z),
                "p1": (25800.0, 450.0, z),
            })
        return segs

    return {
        "BW": make_network("BW-1", BW_Z, BW_W, bw_row_y, include_perim_crah=False),
        "CT": make_network("CT-1", CT_Z, CT_W, uf_row_y, include_perim_crah=False),
        "CHW": make_network("CHW-1", CHW_Z, CHW_OD, uf_row_y, include_perim_crah=True),
    }


# ---------------------------------------------------------------------------
# 2. IFC4 model construction
# ---------------------------------------------------------------------------
def _placement_matrix(
    x_mm: float,
    y_mm: float,
    z_mm: float,
    rot_z_rad: float = 0.0,
) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for ifcopenshell is_si=True)."""
    c = math.cos(rot_z_rad)
    s = math.sin(rot_z_rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def _segment_matrix(p0: tuple[float, float, float], p1: tuple[float, float, float]) -> tuple[np.ndarray, float]:
    """Return (4x4 matrix with translation in METRES, length_mm) aligning local +Z along p0->p1.

    Local +X is horizontal perpendicular, local +Y is vertical (+Z world) for horizontal runs.
    """
    v = np.array([p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]], dtype=float)
    length = float(np.linalg.norm(v))
    if length < 1e-6:
        raise ValueError("Zero-length MEP segment")
    z_axis = v / length
    world_up = np.array([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(z_axis, world_up))) > 0.99:
        x_axis = np.array([1.0, 0.0, 0.0], dtype=float)
        y_axis = np.cross(z_axis, x_axis)
    else:
        y_axis = world_up
        x_axis = np.cross(y_axis, z_axis)
        x_axis = x_axis / np.linalg.norm(x_axis)
        y_axis = np.cross(z_axis, x_axis)

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

    f = ifcopenshell.file(schema="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.unit.assign_unit(f, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=building, products=[storey])

    dir_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    origin_3d = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    origin_2d = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos_3d = f.create_entity("IfcAxis2Placement3D", Location=origin_3d)
    pos_2d = f.create_entity("IfcAxis2Placement2D", Location=origin_2d)

    def make_box_rep(w: float, d: float, h: float):
        prof = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", Position=pos_2d, XDim=float(w), YDim=float(d))
        solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=prof, Position=pos_3d, ExtrudedDirection=dir_z, Depth=float(h))
        return f.create_entity("IfcShapeRepresentation", ContextOfItems=body_ctx, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])

    def make_cyl_rep(diameter: float, length: float):
        prof = f.create_entity("IfcCircleProfileDef", ProfileType="AREA", Position=pos_2d, Radius=float(diameter) / 2.0)
        solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=prof, Position=pos_3d, ExtrudedDirection=dir_z, Depth=float(length))
        return f.create_entity("IfcShapeRepresentation", ContextOfItems=body_ctx, RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])

    def add_element(
        ifc_class: str,
        name: str,
        rep,
        matrix: np.ndarray,
        predefined_type: str | None = None,
        object_type: str | None = None,
        pset_name: str | None = None,
        pset_props: dict[str, Any] | None = None,
    ):
        kwargs: dict[str, Any] = {"ifc_class": ifc_class, "name": name}
        if predefined_type is not None:
            kwargs["predefined_type"] = predefined_type
        el = ifcopenshell.api.root.create_entity(f, **kwargs)
        if object_type is not None:
            el.ObjectType = object_type
        ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[el])
        ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(f, product=el, matrix=matrix)
        if pset_name and pset_props:
            pset = ifcopenshell.api.pset.add_pset(f, product=el, name=pset_name)
            ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=pset_props)
        return el

    # --- Access Floor ---
    add_element(
        "IfcSlab",
        "ACCESS-FLOOR",
        make_box_rep(HALL_W, HALL_D, FLOOR_PANEL_THK),
        _placement_matrix(HALL_W / 2.0, HALL_D / 2.0, FLOOR_TOP_Z - FLOOR_PANEL_THK),
        predefined_type="FLOOR",
        object_type="AccessFloor",
    )

    # --- Structural Columns (6) ---
    col_rep = make_box_rep(COL_SIZE, COL_SIZE, SOFFIT_Z)
    for ci, cx in enumerate(COL_XS):
        col_letter = ["A", "B", "C"][ci]
        for cj, cy in enumerate(COL_YS):
            add_element(
                "IfcColumn",
                f"COL-{col_letter}{cj + 1}",
                col_rep,
                _placement_matrix(cx, cy, 0.0),
                predefined_type="COLUMN",
            )

    # --- Racks (128) & In-Row CRAHs (18) ---
    racks, inrow_crahs, row_extents = expand_row_bays()
    c1_rep = make_box_rep(C1_WIDTH, RACK_DEPTH, RACK_HEIGHT)
    n1_rep = make_box_rep(N1_WIDTH, RACK_DEPTH, RACK_HEIGHT)
    for r in racks:
        rot = 0.0 if r["facing"] == "NORTH" else math.pi
        add_element(
            "IfcFurniture",
            r["name"],
            c1_rep if r["type"] == "C1" else n1_rep,
            _placement_matrix(r["cx"], r["cy"], 0.0, rot),
            predefined_type="USERDEFINED",
            object_type="Rack",
            pset_name="Pset_DCM_Rack",
            pset_props={
                "Row": r["row"],
                "RackType": r["type"],
                "Width_mm": r["w"],
                "Depth_mm": r["d"],
                "Height_mm": r["h"],
                "RU": 42,
                "Facing": r["facing"],
                "Power_kW": 8.0,
                "Load_kg": 1363.0,
            },
        )

    inrow_crah_rep = make_box_rep(CU_WIDTH, RACK_DEPTH, RACK_HEIGHT)
    for c in inrow_crahs:
        rot = 0.0 if c["facing"] == "NORTH" else math.pi
        add_element(
            "IfcUnitaryEquipment",
            c["name"],
            inrow_crah_rep,
            _placement_matrix(c["cx"], c["cy"], 0.0, rot),
            predefined_type="AIRHANDLER",
            object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "IN_ROW",
                "Row": c["row"],
                "Capacity_kW": 50.0,
                "Airflow_m3h": 9000.0,
                "Facing": c["facing"],
                "Service": "CHW_DN50",
            },
        )

    # --- Perimeter CRAHs (4) ---
    perim_crah_rep = make_box_rep(PERIM_CRAH_W, PERIM_CRAH_D, PERIM_CRAH_H)
    for tag, x_sw, y_sw in PERIM_CRAHS:
        add_element(
            "IfcUnitaryEquipment",
            tag,
            perim_crah_rep,
            _placement_matrix(x_sw + PERIM_CRAH_W / 2.0, y_sw + PERIM_CRAH_D / 2.0, 0.0, 0.0),
            predefined_type="AIRHANDLER",
            object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "PERIMETER",
                "Capacity_kW": 100.0,
                "Airflow_m3h": 20000.0,
                "Facing": "NORTH",
                "Service": "CHW_DN100",
            },
        )

    # --- PDUs (6) ---
    pdu_rep = make_box_rep(PDU_W, PDU_D, PDU_H)
    for tag, row_id, x_sw, y_sw, facing in PDUS:
        rot = 0.0 if facing == "NORTH" else math.pi
        add_element(
            "IfcElectricDistributionBoard",
            tag,
            pdu_rep,
            _placement_matrix(x_sw + PDU_W / 2.0, y_sw + PDU_D / 2.0, 0.0, rot),
            predefined_type="DISTRIBUTIONBOARD",
            object_type="PDU",
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": row_id,
                "Rating_kVA": 225.0,
                "Facing": facing,
                "DedicatedSpace_mm": 1800.0,
            },
        )

    # --- Cold-Aisle Containment (4 roofs + 8 end doors) ---
    door_rep = make_box_rep(CAC_DOOR_THK, CAC_DOOR_W, CAC_DOOR_H)
    for tag, y_center, segs_x in CAC_AISLES:
        door_idx = 0
        for s_idx, (x0, x1) in enumerate(segs_x):
            side = "W" if s_idx == 0 else "E"
            roof_len = x1 - x0
            add_element(
                "IfcBuildingElementProxy",
                f"{tag}-ROOF-{side}",
                make_box_rep(roof_len, CAC_ROOF_W, CAC_ROOF_THK),
                _placement_matrix((x0 + x1) / 2.0, y_center, CAC_ROOF_Z),
                predefined_type="USERDEFINED",
                object_type="ContainmentRoof",
                pset_name="Pset_DCM_Containment",
                pset_props={"Aisle": tag, "Component": "Roof"},
            )
            for dx in [x0 - CAC_DOOR_THK / 2.0, x1 + CAC_DOOR_THK / 2.0]:
                door_idx += 1
                add_element(
                    "IfcBuildingElementProxy",
                    f"{tag}-DOOR-{door_idx}",
                    door_rep,
                    _placement_matrix(dx, y_center, 0.0),
                    predefined_type="USERDEFINED",
                    object_type="ContainmentDoor",
                    pset_name="Pset_DCM_Containment",
                    pset_props={"Aisle": tag, "Component": "Door"},
                )

    # --- Sprinkler Heads (79) ---
    spr_rep = make_cyl_rep(50.0, 25.0)
    for h in build_sprinklers():
        add_element(
            "IfcFireSuppressionTerminal",
            h["name"],
            spr_rep,
            _placement_matrix(h["x"], h["y"], h["z_deflector"]),
            predefined_type="SPRINKLER",
            object_type="SprinklerHead",
            pset_name="Pset_DCM_Sprinkler",
            pset_props={
                "Type": h["kind"],
                "DeflectorElevation_mm": h["z_deflector"],
                "Standoff_mm": SPRINKLER_STANDOFF,
            },
        )

    # --- MEP Services (Busway, Cable Tray, Chilled Water) ---
    mep = build_mep_segments(row_extents)

    for seg in mep["BW"]:
        m, length = _segment_matrix(seg["p0"], seg["p1"])
        add_element(
            "IfcCableSegment",
            seg["name"],
            make_box_rep(BW_W, BW_H, length),
            m,
            predefined_type="BUSBARSEGMENT",
            object_type="Busway",
            pset_name="Pset_DCM_Service",
            pset_props={"Service": "Power", "Tag": "BW-1", "Elevation_mm": BW_Z, "Zone": "Overhead"},
        )

    for seg in mep["CT"]:
        m, length = _segment_matrix(seg["p0"], seg["p1"])
        add_element(
            "IfcCableCarrierSegment",
            seg["name"],
            make_box_rep(CT_W, CT_H, length),
            m,
            predefined_type="CABLETRAYSEGMENT",
            object_type="CableTray",
            pset_name="Pset_DCM_Service",
            pset_props={"Service": "Telecom", "Tag": "CT-1", "Elevation_mm": CT_Z, "Zone": "UnderFloor"},
        )

    for seg in mep["CHW"]:
        m, length = _segment_matrix(seg["p0"], seg["p1"])
        add_element(
            "IfcPipeSegment",
            seg["name"],
            make_cyl_rep(CHW_OD, length),
            m,
            predefined_type="RIGIDSEGMENT",
            object_type="ChilledWaterPipe",
            pset_name="Pset_DCM_Service",
            pset_props={
                "Service": "ChilledWater",
                "Tag": "CHW-1",
                "Elevation_mm": CHW_Z,
                "Zone": "UnderFloor",
                "NominalDiameter_mm": 100.0,
                "InsulatedOD_mm": CHW_OD,
            },
        )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    f.write(out_path)


if __name__ == "__main__":
    build_ifc(OUT_PATH)
