"""Coordinated 3D IFC4 model of Data Hall 1 (hall_seed000_d000) with clash-free MEP routing.

Builds the room fit-out (racks, columns, CRAHs, PDUs, access floor, cold-aisle containment,
sprinkler heads) and routes telecom cable tray (CT-1), power busway (BW-1), and chilled-water
pipe (CHW-1) from the west wall service entries.

Usage:
    python output/solution.py [output_ifc_path]
"""
import json
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.validate

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model.ifc"
)
PARAMS_FILE = os.environ.get("PARAMS_FILE", "/tmp/scratch/params.json")

# ---------------------------------------------------------------------------
# Tunable routing parameters (defaults baked in; overridden by PARAMS_FILE)
# ---------------------------------------------------------------------------
DEFAULT_PARAMS = {
    # West trunk X positions (mm)
    "bw_trunk_x": 1180.0,
    "ct_trunk_x": 1114.0,
    "chw_trunk_x": 1500.0,
    # Branch Y positions (mm) — 3 branches serving pairs (A,B), (C,D), (E,F)
    "bw_y1": 5200.0,
    "bw_y2": 9900.0,
    "bw_y3": 14500.0,
    "ct_y1": 4910.0,
    "ct_y2": 9900.0,
    "ct_y3": 14890.0,
    # CHW branches (3 branches: south perimeter+A+B, C+D, E+F)
    "chw_y1": 3167.0,
    "chw_y2": 9900.0,
    "chw_y3": 15007.0,
    # Branch east end X positions (mm)
    "bw_x_end": 16500.0,
    "ct_x_end": 16539.0,
    "chw_x_end": 15000.0,
    "chw_south_x_end": 24632.0,
}


def load_params():
    p = dict(DEFAULT_PARAMS)
    if os.path.isfile(PARAMS_FILE):
        with open(PARAMS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        for k, v in data.items():
            if k in p:
                p[k] = float(v)
    return p


# ---------------------------------------------------------------------------
# Drawing data (baked literals from A-101, A-301, A-601, A-602, E-101, F-101, M-101)
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
FLOOR_THK = 35.0
SOFFIT_Z = 3600.0
CA_EAST_X = 11400.0
ROW_START_X = 1800.0

COLUMNS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Bay sequences: list of (token, count)
# Tokens: C1 (600 rack), N1 (800 rack), CU (600 in-row CRAH), SP (600 spare),
#         OMIT (600 omitted for structure), CA (cross aisle jump to CA_EAST_X)
ROWS_SPEC = [
    ("A", 3000.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
        ("CA", 1),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("B", 6000.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
        ("CA", 1),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("C", 8400.0, "SOUTH", [
        ("C1", 3), ("CU", 1), ("C1", 6), ("OMIT", 2), ("CU", 1),
        ("CA", 1),
        ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT", 2), ("C1", 3),
    ]),
    ("D", 11400.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
        ("CA", 1),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("E", 13800.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
        ("CA", 1),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("F", 16800.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("OMIT", 2), ("CU", 1),
        ("CA", 1),
        ("N1", 2), ("C1", 5), ("SP", 1), ("OMIT", 1), ("CU", 1), ("C1", 4),
    ]),
]

PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

PDUS = [
    # (tag, serves_row, x0, y0, facing)
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 5787.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21000.0, 11187.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 16587.0, "NORTH"),
]


# ---------------------------------------------------------------------------
# IFC4 geometry helpers (units in mm, placement translations in metres!)
# ---------------------------------------------------------------------------
def make_placement_matrix(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def add_box(f, body_ctx, storey, ifc_class, name, predefined_type, object_type,
            cx, cy, z0, dx, dy, dz, yaw_rad=0.0, pset_name=None, pset_props=None):
    el = ifcopenshell.api.root.create_entity(
        f, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type is not None:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[el])

    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    extrusion = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=f.create_entity(
            "IfcAxis2Placement3D",
            Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(dz),
    )
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    el.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.geometry.edit_object_placement(
        f, product=el, matrix=make_placement_matrix(cx, cy, z0, yaw_rad)
    )
    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=pset_props)
    return el


def add_cylinder_z(f, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                   cx, cy, z0, radius, height, pset_name=None, pset_props=None):
    el = ifcopenshell.api.root.create_entity(
        f, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type is not None:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[el])

    profile = f.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    extrusion = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=f.create_entity(
            "IfcAxis2Placement3D",
            Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(height),
    )
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    el.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.geometry.edit_object_placement(
        f, product=el, matrix=make_placement_matrix(cx, cy, z0, 0.0)
    )
    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=pset_props)
    return el


def add_pipe_segment(f, body_ctx, storey, name, x0, y0, x1, y1, z_center, od, zone):
    """Axis-aligned horizontal pipe segment (extruded circle along X or Y)."""
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < 1.0:
        return None
    el = ifcopenshell.api.root.create_entity(
        f, ifc_class="IfcPipeSegment", name=name, predefined_type="RIGIDSEGMENT"
    )
    el.ObjectType = "CHW"
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[el])

    profile = f.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(od / 2.0))
    # Extrude along local +Z, then rotate local +Z to (+X or +Y)
    extrusion = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=f.create_entity(
            "IfcAxis2Placement3D",
            Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(length),
    )
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    el.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[rep])

    m = np.eye(4, dtype=float)
    if abs(dx) >= abs(dy):
        sx = 1.0 if dx > 0 else -1.0
        # local Z -> (sx, 0, 0), local X -> (0, 0, 1), local Y -> (0, -sx, 0)
        m[0, 0], m[1, 0], m[2, 0] = 0.0, 0.0, 1.0
        m[0, 1], m[1, 1], m[2, 1] = 0.0, -sx, 0.0
        m[0, 2], m[1, 2], m[2, 2] = sx, 0.0, 0.0
    else:
        sy = 1.0 if dy > 0 else -1.0
        # local Z -> (0, sy, 0), local X -> (0, 0, 1), local Y -> (sy, 0, 0)
        m[0, 0], m[1, 0], m[2, 0] = 0.0, 0.0, 1.0
        m[0, 1], m[1, 1], m[2, 1] = sy, 0.0, 0.0
        m[0, 2], m[1, 2], m[2, 2] = 0.0, sy, 0.0
    m[0, 3] = x0 / 1000.0
    m[1, 3] = y0 / 1000.0
    m[2, 3] = z_center / 1000.0

    ifcopenshell.api.geometry.edit_object_placement(f, product=el, matrix=m)
    pset = ifcopenshell.api.pset.add_pset(f, product=el, name="Pset_DCM_MEP")
    ifcopenshell.api.pset.edit_pset(f, pset=pset, properties={
        "Service": "CHW",
        "Tag": "CHW-1",
        "Zone": zone,
        "Elevation_mm": float(z_center),
        "OuterDiameter_mm": float(od),
        "Length_mm": float(length),
    })
    return el


def add_carrier_segment(f, body_ctx, storey, name, predefined_type, obj_type, tag,
                        x0, y0, x1, y1, z0, width, height, zone):
    """Axis-aligned horizontal rectangular carrier segment (cable tray or busway)."""
    dx = x1 - x0
    dy = y1 - y0
    if abs(dx) >= abs(dy):
        lx = abs(dx)
        ly = width
        cx = (x0 + x1) / 2.0
        cy = y0
    else:
        lx = width
        ly = abs(dy)
        cx = x0
        cy = (y0 + y1) / 2.0
    if lx < 1.0 or ly < 1.0:
        return None
    return add_box(
        f, body_ctx, storey, "IfcCableCarrierSegment", name, predefined_type, obj_type,
        cx, cy, z0, lx, ly, height, yaw_rad=0.0,
        pset_name="Pset_DCM_MEP",
        pset_props={
            "Service": obj_type,
            "Tag": tag,
            "Zone": zone,
            "Elevation_mm": float(z0),
            "Width_mm": float(width),
            "Height_mm": float(height),
            "Length_mm": float(max(abs(dx), abs(dy))),
        },
    )


def build_model(out_path):
    params = load_params()

    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    ifcopenshell.api.unit.assign_unit(f, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.spatial.assign_container(f, relating_structure=project, products=[])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=building, products=[storey])

    # 1. Access Floor (Z = [-35, 0])
    add_box(
        f, body_ctx, storey, "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        ROOM_X / 2.0, ROOM_Y / 2.0, -FLOOR_THK, ROOM_X, ROOM_Y, FLOOR_THK,
    )

    # 2. Structural Columns (600 x 600, Z = [0, 3600])
    for cname, cx, cy in COLUMNS:
        add_box(
            f, body_ctx, storey, "IfcColumn", cname, "COLUMN", "Column",
            cx, cy, 0.0, 600.0, 600.0, SOFFIT_Z,
        )

    # 3. Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_id, yc, facing, seq in ROWS_SPEC:
        yaw = 0.0 if facing == "NORTH" else math.pi
        x = ROW_START_X
        rack_idx = 0
        crah_idx = 0
        west_end = ROW_START_X
        for tok, cnt in seq:
            for _ in range(cnt):
                if tok == "CA":
                    west_end = x
                    x = CA_EAST_X
                elif tok == "C1":
                    rack_idx += 1
                    add_box(
                        f, body_ctx, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                        "USERDEFINED", "Rack",
                        x + 300.0, yc, 0.0, 600.0, 1200.0, 2000.0, yaw_rad=yaw,
                        pset_name="Pset_DCM_Rack",
                        pset_props={
                            "Row": row_id, "Bay": rack_idx, "Facing": facing,
                            "Width_mm": 600.0, "Depth_mm": 1200.0, "Height_mm": 2000.0,
                            "RU": 42, "Power_kW": 8.0, "Load_kg": 1363.0,
                        },
                    )
                    x += 600.0
                elif tok == "N1":
                    rack_idx += 1
                    add_box(
                        f, body_ctx, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                        "USERDEFINED", "Rack",
                        x + 400.0, yc, 0.0, 800.0, 1200.0, 2000.0, yaw_rad=yaw,
                        pset_name="Pset_DCM_Rack",
                        pset_props={
                            "Row": row_id, "Bay": rack_idx, "Facing": facing,
                            "Width_mm": 800.0, "Depth_mm": 1200.0, "Height_mm": 2000.0,
                            "RU": 42, "Power_kW": 8.0, "Load_kg": 1363.0,
                        },
                    )
                    x += 800.0
                elif tok == "CU":
                    crah_idx += 1
                    add_box(
                        f, body_ctx, storey, "IfcUnitaryEquipment", f"CRAH-{row_id}{crah_idx:02d}",
                        "AIRCONDITIONINGUNIT", "CRAH",
                        x + 300.0, yc, 0.0, 600.0, 1200.0, 2000.0, yaw_rad=yaw,
                        pset_name="Pset_DCM_CRAH",
                        pset_props={
                            "Placement": f"IN-ROW {row_id}", "Capacity_kW": 50.0,
                            "Airflow_m3h": 9000.0, "Facing": facing, "Service": "CHW DN50",
                        },
                    )
                    x += 600.0
                elif tok in ("SP", "OMIT"):
                    x += 600.0
        row_extents[row_id] = (ROW_START_X, west_end, CA_EAST_X, x)

    # 4. Perimeter CRAHs (1200 x 900 x 2000, facing NORTH)
    for tag, x0, y0 in PERIMETER_CRAHS:
        add_box(
            f, body_ctx, storey, "IfcUnitaryEquipment", tag,
            "AIRCONDITIONINGUNIT", "CRAH",
            x0 + 600.0, y0 + 450.0, 0.0, 1200.0, 900.0, 2000.0, yaw_rad=0.0,
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "PERIMETER", "Capacity_kW": 100.0,
                "Airflow_m3h": 20000.0, "Facing": "NORTH", "Service": "CHW DN100",
            },
        )

    # 5. PDUs (762 x 813 x 1959)
    for tag, srow, x0, y0, facing in PDUS:
        yaw = 0.0 if facing == "NORTH" else math.pi
        add_box(
            f, body_ctx, storey, "IfcElectricDistributionBoard", tag,
            "DISTRIBUTIONBOARD", "PDU",
            x0 + 762.0 / 2.0, y0 + 813.0 / 2.0, 0.0, 762.0, 813.0, 1959.0, yaw_rad=yaw,
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": srow, "Rating_kVA": 225.0, "Facing": facing,
                "WorkingSpace_mm": 900.0, "DedicatedSpace_mm": 1800.0,
            },
        )

    # 6. Cold-Aisle Containment (CAC-BC at Y=7200, CAC-DE at Y=12600)
    for cac_name, y_mid, r1, r2 in [("CAC-BC", 7200.0, "B", "C"), ("CAC-DE", 12600.0, "D", "E")]:
        w_start = ROW_START_X
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_start = CA_EAST_X
        e_end = min(row_extents[r1][3], row_extents[r2][3])
        for side, sx0, sx1 in [("W", w_start, w_end), ("E", e_start, e_end)]:
            # Roof panel: Z = [2000, 2055.5], width = 1400 mm
            add_box(
                f, body_ctx, storey, "IfcCovering", f"{cac_name}-ROOF-{side}",
                "CEILING", "ContainmentRoof",
                (sx0 + sx1) / 2.0, y_mid, 2000.0, sx1 - sx0, 1400.0, 55.5,
            )
            # End doors: 60 x 1200 x 2055.5 (just outside panel ends so zero clash)
            add_box(
                f, body_ctx, storey, "IfcDoor", f"{cac_name}-DOOR-{side}1",
                "DOOR", "ContainmentDoor",
                sx0 - 30.0, y_mid, 0.0, 60.0, 1200.0, 2055.5,
            )
            add_box(
                f, body_ctx, storey, "IfcDoor", f"{cac_name}-DOOR-{side}2",
                "DOOR", "ContainmentDoor",
                sx1 + 30.0, y_mid, 0.0, 60.0, 1200.0, 2055.5,
            )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79)
    sp_idx = 0
    for j in range(7):
        sy = 1500.0 + 3000.0 * j
        for i in range(9):
            sx = 1500.0 + 3000.0 * i
            # Relocate heads within 750 mm of a column centre to clear tile
            for _, colx, coly in COLUMNS:
                if abs(sx - colx) < 750.0 and abs(sy - coly) < 750.0:
                    sx += -600.0 if sx <= colx else 600.0
                    sy += -600.0 if sy <= coly else 600.0
            sp_idx += 1
            add_cylinder_z(
                f, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPK-C{sp_idx:02d}",
                "SPRINKLER", "Sprinkler",
                sx, sy, 3574.6, 25.0, 25.4,
                pset_name="Pset_DCM_Sprinkler",
                pset_props={"Type": "CeilingPendent", "DeflectorElevation_mm": 3574.6, "Standoff_mm": 460.0},
            )
    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 0
    for y_mid in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            add_cylinder_z(
                f, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPK-IA{ia_idx:02d}",
                "SPRINKLER", "Sprinkler",
                sx, y_mid, 1890.0, 25.0, 110.0,
                pset_name="Pset_DCM_Sprinkler",
                pset_props={"Type": "InAislePendent", "DeflectorElevation_mm": 1890.0, "Standoff_mm": 460.0},
            )

    # -----------------------------------------------------------------------
    # 8. MEP Routing (zero-overlap face-to-face butt joints!)
    # -----------------------------------------------------------------------
    # A) Power Busway (BW-1: 128 W x 147 H) — OVERHEAD at Z = [2620, 2767]
    bw_w, bw_h, bw_z = 128.0, 147.0, 2620.0
    bw_tx = params["bw_trunk_x"]
    bw_ys = sorted([params["bw_y1"], params["bw_y2"], params["bw_y3"]])
    bw_x_end = params["bw_x_end"]
    bw_n = 0

    def add_bw(x0, y0, x1, y1):
        nonlocal bw_n
        bw_n += 1
        add_carrier_segment(
            f, body_ctx, storey, f"BW-{bw_n:02d}", "CABLETRUNKINGSEGMENT", "BW", "BW-1",
            x0, y0, x1, y1, bw_z, bw_w, bw_h, "OVERHEAD",
        )

    # Entry stub from west wall (0, 9900) to west side of trunk (bw_tx - bw_w/2, 9900)
    add_bw(0.0, 9900.0, bw_tx - bw_w / 2.0, 9900.0)
    # West trunk from min(bw_ys) - bw_w/2 to max(bw_ys) + bw_w/2
    add_bw(bw_tx, min(bw_ys[0], 9900.0) - bw_w / 2.0, bw_tx, max(bw_ys[-1], 9900.0) + bw_w / 2.0)
    # 3 east branches starting from east face of trunk (bw_tx + bw_w/2)
    for by in bw_ys:
        add_bw(bw_tx + bw_w / 2.0, by, bw_x_end, by)

    # B) Telecom Cable Tray (CT-1: 683 W x 127 H) — UNDER-FLOOR at Z = [-200, -73]
    ct_w, ct_h, ct_z = 683.0, 127.0, -200.0
    ct_tx = params["ct_trunk_x"]
    ct_ys = sorted([params["ct_y1"], params["ct_y2"], params["ct_y3"]])
    ct_x_end = params["ct_x_end"]
    ct_n = 0

    def add_ct(x0, y0, x1, y1):
        nonlocal ct_n
        ct_n += 1
        add_carrier_segment(
            f, body_ctx, storey, f"CT-{ct_n:02d}", "CABLELADDERSEGMENT", "CT", "CT-1",
            x0, y0, x1, y1, ct_z, ct_w, ct_h, "UNDERFLOOR",
        )

    add_ct(0.0, 9900.0, ct_tx - ct_w / 2.0, 9900.0)
    add_ct(ct_tx, min(ct_ys[0], 9900.0) - ct_w / 2.0, ct_tx, max(ct_ys[-1], 9900.0) + ct_w / 2.0)
    for cy in ct_ys:
        add_ct(ct_tx + ct_w / 2.0, cy, ct_x_end, cy)

    # C) Chilled Water Pipe (CHW-1: OD 168.3) — UNDER-FLOOR at Z_center = -450 (Z = [-534.15, -365.85])
    chw_od = 168.3
    chw_r = chw_od / 2.0
    chw_zc = -450.0
    chw_tx = params["chw_trunk_x"]
    chw_ys = [params["chw_y1"], params["chw_y2"], params["chw_y3"]]
    chw_x_end = params["chw_x_end"]
    chw_sx_end = params["chw_south_x_end"]
    chw_n = 0

    def add_chw(x0, y0, x1, y1):
        nonlocal chw_n
        chw_n += 1
        add_pipe_segment(f, body_ctx, storey, f"CHW-{chw_n:02d}", x0, y0, x1, y1, chw_zc, chw_od, "UNDERFLOOR")

    add_chw(0.0, 9900.0, chw_tx - chw_r, 9900.0)
    add_chw(chw_tx, min(min(chw_ys), 9900.0) - chw_r, chw_tx, max(max(chw_ys), 9900.0) + chw_r)
    for idx, py in enumerate(chw_ys):
        xend = chw_sx_end if idx == 0 else chw_x_end
        add_chw(chw_tx + chw_r, py, xend, py)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    f.write(out_path)


if __name__ == "__main__":
    build_model(OUT_PATH)
