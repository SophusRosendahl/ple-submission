"""Coordinated IFC4 BIM model for Data Hall 1 (dc_model hall_seed000_d000).

Rebuilds the architectural/structural/equipment background from drawing set
A-101, A-301, A-601, A-602, E-101, F-101, M-101 and routes three clash-free
MEP services (telecom cable tray CT-1, power busway BW-1, chilled water CHW-1).

Usage:
    python output/solution.py [output_ifc_path]
"""
from __future__ import annotations

import math
import os
import sys
from typing import Dict, List, Tuple

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import numpy as np


# ---------------------------------------------------------------------------
# Drawing-extracted constants (all dimensions in millimetres)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
TILE = 600.0

Z_SLAB_TOP = -900.0
Z_FLOOR_BOT = -35.0
Z_FF = 0.0
Z_CLEAR_MIN = 2600.0
Z_SOFFIT = 3600.0
Z_DEFLECTOR = 3574.6  # 25.4 mm below soffit (A-301)
SPRINKLER_STANDOFF = 460.0  # Keep clear below deflector -> 3114.6 mm max

# Structural columns: 600 x 600 mm, full height 0..3600 mm
COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Cabinet rows (A-101, A-601)
ROW_META = {
    "A": {"y": 3000.0, "facing": "SOUTH"},
    "B": {"y": 6000.0, "facing": "NORTH"},
    "C": {"y": 8400.0, "facing": "SOUTH"},
    "D": {"y": 11400.0, "facing": "NORTH"},
    "E": {"y": 13800.0, "facing": "SOUTH"},
    "F": {"y": 16800.0, "facing": "NORTH"},
}

CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
CA_EAST_X = 11400.0  # Common east edge of cross aisle (A-101 Note 5)
ROW_START_X = 1800.0  # Tile D (col 4 -> 3 * 600 mm)

# Bay sequences from A-601 (west of CA, east of CA)
# Token types: ("C1", n), ("N1", n), ("CU", 1), ("SP", 1), ("GAP", width_mm)
ROW_BAYS: Dict[str, Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]] = {
    "A": (
        [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
        [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    "B": (
        [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
        [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    "C": (
        [("C1", 3), ("CU", 1), ("C1", 6), ("GAP", 1200), ("CU", 1)],
        [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("GAP", 1200), ("C1", 3)],
    ),
    "D": (
        [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
        [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    "E": (
        [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
        [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    ),
    "F": (
        [("C1", 4), ("CU", 1), ("C1", 5), ("GAP", 1200), ("CU", 1)],
        [("N1", 2), ("C1", 5), ("SP", 1), ("GAP", 600), ("CU", 1), ("C1", 4)],
    ),
}

# Perimeter CRAHs (A-601): 1200 W x 900 D x 2000 H, facing NORTH
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),    # Tile B01
    ("CRAH-02", 9000.0, 0.0),   # Tile P01
    ("CRAH-03", 16800.0, 0.0),  # Tile AC01
    ("CRAH-04", 25200.0, 0.0),  # Tile AQ01
]
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0

# PDUs (A-601, A-101 Note 8): 762 W x 813 D x 1959 H, front flush with row front
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),          # AJ05, front at y=2400
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),  # AK10, front at y=6600
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),          # AJ14, front at y=7800
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"), # AK19, front at y=12000
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),         # AJ23, front at y=13200
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"), # AK28, front at y=17400
]

# Cold-aisle containment (A-602, A-301 Detail 3)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5
CAC_AISLES = [
    # (tag, y_center, west_x0, west_x1, east_x0, east_x1)
    ("CAC-BC", 7200.0, 1800.0, 9600.0, 11400.0, 19400.0),
    ("CAC-DE", 12600.0, 1800.0, 9800.0, 11400.0, 19200.0),
]

# MEP pathway sections (A-602, E-101, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_OD = 168.3  # DN100 bare 114.3 + 25.4 mm insulation + jacket (M-101 Note 4)

# Coordinated elevations (centrelines in mm)
# - Telecom cable tray: under-floor plenum (top = -136.5 < -55 mm limit; bot = -263.5 > -900 mm)
# - Power busway: overhead lower tier (bot = 2646.5 > 2600 mm; top = 2793.5)
# - Chilled water: overhead upper tier (bot = 2925.85 > busway top; top = 3094.15 < 3114.6 mm)
Z_TRAY = -200.0
Z_BUSWAY = 2720.0
Z_CHW = 3010.0

# Service entry at West wall (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0
SPINE_X = 1000.0

# Branch Y coordinates (offset clear of structural columns at y=8400 and y=16800)
ROW_BRANCH_Y = {
    "A": 3000.0,
    "B": 6000.0,
    "C": 9400.0,   # 1000 mm north of Row C centreline, 700 mm clear of col face (8700)
    "D": 11400.0,
    "E": 13800.0,
    "F": 15600.0,  # 1200 mm south of Row F centreline, 900 mm clear of col face (16500)
}
ROW_BRANCH_X_END = {
    "A": 18600.0,
    "B": 19200.0,
    "C": 18600.0,
    "D": 19200.0,
    "E": 18600.0,
    "F": 19200.0,
}
PERIM_CHW_Y = 1200.0
PERIM_CHW_X_END = 25800.0


# ---------------------------------------------------------------------------
# Geometry & IFC helpers
# ---------------------------------------------------------------------------
def facing_angle(facing: str) -> float:
    return {"NORTH": 0.0, "SOUTH": math.pi, "WEST": math.pi / 2.0, "EAST": -math.pi / 2.0}[facing]


def make_matrix(x_mm: float, y_mm: float, z_mm: float, yaw_rad: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for ifcopenshell.api)."""
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    m = np.eye(4, dtype=np.float64)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def make_box_rep(
    model: ifcopenshell.file,
    body_ctx: ifcopenshell.entity_instance,
    x_dim: float,
    y_dim: float,
    z_dim: float,
) -> ifcopenshell.entity_instance:
    """Centered 2D rectangle profile extruded +Z by z_dim (all in mm)."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(x_dim),
        YDim=float(y_dim),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(z_dim),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cylinder_rep(
    model: ifcopenshell.file,
    body_ctx: ifcopenshell.entity_instance,
    radius: float,
    length: float,
) -> ifcopenshell.entity_instance:
    """Centered 2D circle profile extruded +Z by length (all in mm)."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(length),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def assign_rep(model: ifcopenshell.file, product: ifcopenshell.entity_instance, rep: ifcopenshell.entity_instance) -> None:
    product.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])


def add_pset(model: ifcopenshell.file, product: ifcopenshell.entity_instance, name: str, props: Dict[str, object]) -> None:
    pset = ifcopenshell.api.pset.add_pset(model, product=product, name=name)
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)


def create_element(
    model: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    ifc_class: str,
    name: str,
    rep: ifcopenshell.entity_instance,
    matrix: np.ndarray,
    predefined_type: str | None = None,
    object_type: str | None = None,
) -> ifcopenshell.entity_instance:
    kwargs = {"ifc_class": ifc_class, "name": name}
    if predefined_type is not None:
        kwargs["predefined_type"] = predefined_type
    elem = ifcopenshell.api.root.create_entity(model, **kwargs)
    if object_type is not None:
        elem.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, products=[elem], relating_structure=storey)
    ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=matrix)
    assign_rep(model, elem, rep)
    return elem


def add_axis_aligned_rect_segment(
    model: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
    ifc_class: str,
    predefined_type: str,
    object_type: str,
    name: str,
    p0: Tuple[float, float, float],
    p1: Tuple[float, float, float],
    width: float,
    height: float,
    service: str,
    zone: str,
) -> ifcopenshell.entity_instance:
    """Create a horizontal axis-aligned rectangular MEP segment between p0 and p1."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    assert length > 1.0, f"Degenerate segment {name}: {p0} -> {p1}"
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    cz = 0.5 * (z0 + z1)
    if abs(dx) >= abs(dy):
        x_dim, y_dim = length, width
    else:
        x_dim, y_dim = width, length
    rep = make_box_rep(model, body_ctx, x_dim, y_dim, height)
    mat = make_matrix(cx, cy, cz - height / 2.0, 0.0)
    elem = create_element(
        model, storey, ifc_class, name, rep, mat,
        predefined_type=predefined_type, object_type=object_type,
    )
    add_pset(model, elem, "Pset_DCM_MEP", {
        "Service": service,
        "Tag": object_type,
        "Zone": zone,
        "Elevation_mm": float(cz),
        "Section_mm": f"{int(round(width))}x{int(round(height))}",
        "Length_mm": float(length),
    })
    return elem


def add_axis_aligned_pipe_segment(
    model: ifcopenshell.file,
    storey: ifcopenshell.entity_instance,
    body_ctx: ifcopenshell.entity_instance,
    name: str,
    p0: Tuple[float, float, float],
    p1: Tuple[float, float, float],
    od: float,
    zone: str,
) -> ifcopenshell.entity_instance:
    """Create a horizontal axis-aligned cylindrical CHW pipe segment between p0 and p1."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    assert length > 1.0, f"Degenerate pipe {name}: {p0} -> {p1}"
    rep = make_cylinder_rep(model, body_ctx, od / 2.0, length)
    # Build orthonormal frame with local +Z along (dx, dy, 0)
    ux, uy = dx / length, dy / length
    mat = np.eye(4, dtype=np.float64)
    # Local Z = (ux, uy, 0), Local X = (-uy, ux, 0), Local Y = (0, 0, 1)
    mat[0, 0], mat[1, 0], mat[2, 0] = -uy, ux, 0.0
    mat[0, 1], mat[1, 1], mat[2, 1] = 0.0, 0.0, 1.0
    mat[0, 2], mat[1, 2], mat[2, 2] = ux, uy, 0.0
    mat[0, 3] = x0 / 1000.0
    mat[1, 3] = y0 / 1000.0
    mat[2, 3] = z0 / 1000.0
    elem = create_element(
        model, storey, "IfcPipeSegment", name, rep, mat,
        predefined_type="RIGIDSEGMENT", object_type="CHW-1",
    )
    add_pset(model, elem, "Pset_DCM_MEP", {
        "Service": "CHILLED_WATER",
        "Tag": "CHW-1",
        "Zone": zone,
        "Elevation_mm": float(z0),
        "Section_mm": f"OD {od}",
        "Length_mm": float(length),
    })
    return elem


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------
def build_model(out_path: str) -> None:
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor (35 mm panel, top at z=0)
    floor_rep = make_box_rep(model, body_ctx, ROOM_W, ROOM_D, 35.0)
    create_element(
        model, storey, "IfcSlab", "AccessFloor", floor_rep,
        make_matrix(ROOM_W / 2.0, ROOM_D / 2.0, Z_FLOOR_BOT),
        predefined_type="FLOOR", object_type="AccessFloor",
    )

    # 2. Structural Columns (6 columns, 600x600x3600 mm)
    col_rep = make_box_rep(model, body_ctx, COL_SIZE, COL_SIZE, Z_SOFFIT)
    grid_x_names = ["A", "B", "C"]
    grid_y_names = ["1", "2"]
    for ix, cx in enumerate(COL_XS):
        for iy, cy in enumerate(COL_YS):
            create_element(
                model, storey, "IfcColumn", f"COL-{grid_x_names[ix]}{grid_y_names[iy]}",
                col_rep, make_matrix(cx, cy, 0.0), predefined_type="COLUMN",
            )

    # 3. Cabinets & In-Row CRAHs (128 racks + 18 in-row CRAHs)
    c1_rep = make_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT)
    n1_rep = make_box_rep(model, body_ctx, 800.0, CAB_DEPTH, CAB_HEIGHT)
    inrow_crah_rep = make_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT)

    for row_id, (west_bays, east_bays) in ROW_BAYS.items():
        y_c = ROW_META[row_id]["y"]
        facing = ROW_META[row_id]["facing"]
        yaw = facing_angle(facing)
        rack_idx = 0
        crah_idx = 0

        for start_x, bays in [(ROW_START_X, west_bays), (CA_EAST_X, east_bays)]:
            cur_x = start_x
            for tok, count in bays:
                if tok == "GAP":
                    cur_x += float(count)
                    continue
                for _ in range(count):
                    if tok == "C1":
                        w = 600.0
                        rack_idx += 1
                        elem = create_element(
                            model, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                            c1_rep, make_matrix(cur_x + w / 2.0, y_c, 0.0, yaw),
                            predefined_type="USERDEFINED", object_type="Rack",
                        )
                        add_pset(model, elem, "Pset_DCM_Rack", {
                            "Row": row_id, "CabinetType": "C1", "Width_mm": 600.0,
                            "Depth_mm": CAB_DEPTH, "Height_mm": CAB_HEIGHT, "RU": 42,
                            "Facing": facing, "Power_kW": 8.0,
                        })
                        cur_x += w
                    elif tok == "N1":
                        w = 800.0
                        rack_idx += 1
                        elem = create_element(
                            model, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                            n1_rep, make_matrix(cur_x + w / 2.0, y_c, 0.0, yaw),
                            predefined_type="USERDEFINED", object_type="Rack",
                        )
                        add_pset(model, elem, "Pset_DCM_Rack", {
                            "Row": row_id, "CabinetType": "N1", "Width_mm": 800.0,
                            "Depth_mm": CAB_DEPTH, "Height_mm": CAB_HEIGHT, "RU": 42,
                            "Facing": facing, "Power_kW": 8.0,
                        })
                        cur_x += w
                    elif tok == "CU":
                        w = 600.0
                        crah_idx += 1
                        elem = create_element(
                            model, storey, "IfcUnitaryEquipment", f"CRAH-{row_id}{crah_idx:02d}",
                            inrow_crah_rep, make_matrix(cur_x + w / 2.0, y_c, 0.0, yaw),
                            predefined_type="AIRHANDLER", object_type="CRAH",
                        )
                        add_pset(model, elem, "Pset_DCM_CRAH", {
                            "Placement": f"IN_ROW_{row_id}", "Capacity_kW": 50.0,
                            "Airflow_m3h": 9000.0, "Facing": facing, "Service": "CHILLED_WATER_DN50",
                        })
                        cur_x += w
                    elif tok == "SP":
                        cur_x += 600.0

    # 4. Perimeter CRAHs (4 units)
    perim_rep = make_box_rep(model, body_ctx, PERIM_CRAH_W, PERIM_CRAH_D, PERIM_CRAH_H)
    for tag, x0, y0 in PERIMETER_CRAHS:
        elem = create_element(
            model, storey, "IfcUnitaryEquipment", tag, perim_rep,
            make_matrix(x0 + PERIM_CRAH_W / 2.0, y0 + PERIM_CRAH_D / 2.0, 0.0, facing_angle("NORTH")),
            predefined_type="AIRHANDLER", object_type="CRAH",
        )
        add_pset(model, elem, "Pset_DCM_CRAH", {
            "Placement": "PERIMETER", "Capacity_kW": 100.0,
            "Airflow_m3h": 20000.0, "Facing": "NORTH", "Service": "CHILLED_WATER_DN100",
        })

    # 5. PDUs (6 units)
    pdu_rep = make_box_rep(model, body_ctx, PDU_W, PDU_D, PDU_H)
    for tag, row_id, x0, y0, facing in PDUS:
        elem = create_element(
            model, storey, "IfcElectricDistributionBoard", tag, pdu_rep,
            make_matrix(x0 + PDU_W / 2.0, y0 + PDU_D / 2.0, 0.0, facing_angle(facing)),
            predefined_type="DISTRIBUTIONBOARD", object_type="PDU",
        )
        add_pset(model, elem, "Pset_DCM_PDU", {
            "ServesRow": row_id, "Rating_kVA": 225.0, "Facing": facing, "DedicatedSpace_mm": 1800.0,
        })

    # 6. Cold-Aisle Containment (2 contained aisles, 2 roof panels + 4 end doors each)
    door_rep = make_box_rep(model, body_ctx, CAC_DOOR_THK, CAC_DOOR_W, CAC_DOOR_H)
    for tag, y_c, wx0, wx1, ex0, ex1 in CAC_AISLES:
        for side, x0, x1 in [("W", wx0, wx1), ("E", ex0, ex1)]:
            roof_rep = make_box_rep(model, body_ctx, x1 - x0, CAC_ROOF_W, CAC_ROOF_THK)
            create_element(
                model, storey, "IfcCovering", f"{tag}-ROOF-{side}", roof_rep,
                make_matrix(0.5 * (x0 + x1), y_c, CAC_ROOF_Z),
                predefined_type="CEILING", object_type="ContainmentRoof",
            )
            create_element(
                model, storey, "IfcDoor", f"{tag}-DOOR-{side}1", door_rep,
                make_matrix(x0 + CAC_DOOR_THK / 2.0, y_c, 0.0),
                predefined_type="DOOR", object_type="ContainmentDoor",
            )
            create_element(
                model, storey, "IfcDoor", f"{tag}-DOOR-{side}2", door_rep,
                make_matrix(x1 - CAC_DOOR_THK / 2.0, y_c, 0.0),
                predefined_type="DOOR", object_type="ContainmentDoor",
            )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79 total, F-101)
    spr_rep = make_cylinder_rep(model, body_ctx, 25.0, 25.4)
    spr_idx = 0
    for j in range(7):
        sy = 1500.0 + j * 3000.0
        for i in range(9):
            sx = 1500.0 + i * 3000.0
            # Relocate heads within 1500 mm keep-out of columns (F-101 Detail 2)
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sy = cy - 900.0
            spr_idx += 1
            elem = create_element(
                model, storey, "IfcFireSuppressionTerminal", f"SPR-C{spr_idx:02d}",
                spr_rep, make_matrix(sx, sy, Z_DEFLECTOR),
                predefined_type="SPRINKLER", object_type="CeilingSprinkler",
            )
            add_pset(model, elem, "Pset_DCM_Sprinkler", {
                "SprinklerType": "CEILING_PENDENT",
                "DeflectorElevation_mm": Z_DEFLECTOR,
                "Standoff_mm": SPRINKLER_STANDOFF,
            })

    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9000.0, 12000.0, 14400.0, 16800.0, 18600.0]
    ia_idx = 0
    for tag, y_c, *_ in CAC_AISLES:
        for sx in in_aisle_xs:
            ia_idx += 1
            elem = create_element(
                model, storey, "IfcFireSuppressionTerminal", f"SPR-IA{ia_idx:02d}",
                spr_rep, make_matrix(sx, y_c, 1890.0),
                predefined_type="SPRINKLER", object_type="InAisleSprinkler",
            )
            add_pset(model, elem, "Pset_DCM_Sprinkler", {
                "SprinklerType": "IN_AISLE_PENDENT",
                "DeflectorElevation_mm": 1890.0,
                "Standoff_mm": SPRINKLER_STANDOFF,
            })

    # 8. MEP Routing — 3 clash-free, fully connected services
    # Helper to build a spine + branches with clean butt joints (zero self-overlap)
    # 8a. Telecom Cable Tray (CT-1) — Under-floor plenum at z = -200 mm
    tray_ys = sorted(set([ENTRY_Y] + list(ROW_BRANCH_Y.values())))
    add_axis_aligned_rect_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
        "CT-ENTRY", (ENTRY_X, ENTRY_Y, Z_TRAY), (SPINE_X - TRAY_W / 2.0, ENTRY_Y, Z_TRAY),
        TRAY_W, TRAY_H, "TELECOM", "UNDER_FLOOR",
    )
    add_axis_aligned_rect_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
        "CT-SPINE", (SPINE_X, min(tray_ys), Z_TRAY), (SPINE_X, max(tray_ys), Z_TRAY),
        TRAY_W, TRAY_H, "TELECOM", "UNDER_FLOOR",
    )
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        by = ROW_BRANCH_Y[row_id]
        bx_end = ROW_BRANCH_X_END[row_id]
        add_axis_aligned_rect_segment(
            model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
            f"CT-ROW-{row_id}", (SPINE_X + TRAY_W / 2.0, by, Z_TRAY), (bx_end, by, Z_TRAY),
            TRAY_W, TRAY_H, "TELECOM", "UNDER_FLOOR",
        )

    # 8b. Power Busway (BW-1) — Overhead lower tier at z = 2720 mm
    bw_ys = sorted(set([ENTRY_Y] + list(ROW_BRANCH_Y.values())))
    add_axis_aligned_rect_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
        "BW-ENTRY", (ENTRY_X, ENTRY_Y, Z_BUSWAY), (SPINE_X - BUSWAY_W / 2.0, ENTRY_Y, Z_BUSWAY),
        BUSWAY_W, BUSWAY_H, "POWER", "OVERHEAD",
    )
    add_axis_aligned_rect_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
        "BW-SPINE", (SPINE_X, min(bw_ys), Z_BUSWAY), (SPINE_X, max(bw_ys), Z_BUSWAY),
        BUSWAY_W, BUSWAY_H, "POWER", "OVERHEAD",
    )
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        by = ROW_BRANCH_Y[row_id]
        bx_end = ROW_BRANCH_X_END[row_id]
        add_axis_aligned_rect_segment(
            model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
            f"BW-ROW-{row_id}", (SPINE_X + BUSWAY_W / 2.0, by, Z_BUSWAY), (bx_end, by, Z_BUSWAY),
            BUSWAY_W, BUSWAY_H, "POWER", "OVERHEAD",
        )

    # 8c. Chilled Water Pipe (CHW-1) — Overhead upper tier at z = 3010 mm
    chw_r = CHW_OD / 2.0
    chw_ys = sorted(set([ENTRY_Y, PERIM_CHW_Y] + list(ROW_BRANCH_Y.values())))
    add_axis_aligned_pipe_segment(
        model, storey, body_ctx, "CHW-ENTRY",
        (ENTRY_X, ENTRY_Y, Z_CHW), (SPINE_X - chw_r, ENTRY_Y, Z_CHW),
        CHW_OD, "OVERHEAD",
    )
    add_axis_aligned_pipe_segment(
        model, storey, body_ctx, "CHW-SPINE",
        (SPINE_X, min(chw_ys), Z_CHW), (SPINE_X, max(chw_ys), Z_CHW),
        CHW_OD, "OVERHEAD",
    )
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        by = ROW_BRANCH_Y[row_id]
        bx_end = ROW_BRANCH_X_END[row_id]
        add_axis_aligned_pipe_segment(
            model, storey, body_ctx, f"CHW-ROW-{row_id}",
            (SPINE_X + chw_r, by, Z_CHW), (bx_end, by, Z_CHW),
            CHW_OD, "OVERHEAD",
        )
    # Perimeter CRAH header (reaches CRAH-01..04 within 750 mm)
    add_axis_aligned_pipe_segment(
        model, storey, body_ctx, "CHW-PERIMETER",
        (SPINE_X + chw_r, PERIM_CHW_Y, Z_CHW), (PERIM_CHW_X_END, PERIM_CHW_Y, Z_CHW),
        CHW_OD, "OVERHEAD",
    )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    out_file = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_model(out_file)
