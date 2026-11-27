"""Coordinated IFC4 BIM model for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Rebuilds the architectural & fit-out coordination background from sheets A-101,
A-301, A-601, A-602, E-101, F-101, and M-101, and routes three clash-free,
code-compliant MEP services (Telecom Cable Tray, Power Busway, Chilled Water).
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

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# ---------------------------------------------------------------------------
# 1. Hall & Equipment Data (baked from drawing sheets A-101..M-101)
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
SOFFIT_Z = 3600.0
ACCESS_FLOOR_THK = 35.0
SLAB_Z = -900.0
MIN_CLEAR_HEIGHT = 2600.0
DEFLECTOR_Z = 3574.6  # 25.4 mm below +3600 soffit (A-301)
SPRINKLER_STANDOFF = 460.0

# Structural columns: 600 x 600 mm, Z = 0..3600 (A-101, A-301)
COL_SIZE = 600.0
COL_CENTRES = [
    (8400.0, 8400.0),
    (16800.0, 8400.0),
    (25200.0, 8400.0),
    (8400.0, 16800.0),
    (16800.0, 16800.0),
    (25200.0, 16800.0),
]

# Cabinet rows (A-101, A-601)
ROW_META = {
    "A": {"cl_y": 3000.0, "facing": "SOUTH"},
    "B": {"cl_y": 6000.0, "facing": "NORTH"},
    "C": {"cl_y": 8400.0, "facing": "SOUTH"},
    "D": {"cl_y": 11400.0, "facing": "NORTH"},
    "E": {"cl_y": 13800.0, "facing": "SOUTH"},
    "F": {"cl_y": 16800.0, "facing": "NORTH"},
}

ROW_SEQUENCES = {
    "A": [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    "B": [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    "C": [("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1), ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3)],
    "D": [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    "E": [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    "F": [("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1), ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4)],
}
BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}
ROW_WEST_START_X = 1800.0
ROW_EAST_START_X = 11400.0
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Perimeter CRAHs (A-601, M-101): 1200 W x 900 D x 2000 H, facing NORTH
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, "B01"),
    ("CRAH-02", 9000.0, 0.0, "P01"),
    ("CRAH-03", 16800.0, 0.0, "AC01"),
    ("CRAH-04", 25200.0, 0.0, "AQ01"),
]

# PDUs (A-601, E-101): 762 W x 813 D x 1959 H, front flush with served row front
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_SPECS = [
    ("PDU-01", "A", "AJ05"),
    ("PDU-02", "B", "AK10"),
    ("PDU-03", "C", "AJ14"),
    ("PDU-04", "D", "AK19"),
    ("PDU-05", "E", "AJ23"),
    ("PDU-06", "F", "AK28"),
]

# Containment (A-602, A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_W = 1200.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5

# MEP service cross-sections (A-602, E-101, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_OD = 168.3  # DN100 + 25.4 mm insulation jacket per M-101 Note 4

# Service entry on West wall (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0


# ---------------------------------------------------------------------------
# 2. Geometry & IFC Helpers
# ---------------------------------------------------------------------------
def rot_z_matrix(cx_mm, cy_mm, z0_mm, angle_rad=0.0):
    """4x4 placement matrix with translation in METRES for ifcopenshell.api."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def make_rect_solid(model, body_ctx, x_dim, y_dim, z_height):
    """Create a centered rectangular IfcExtrudedAreaSolid in mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(x_dim),
        YDim=float(y_dim),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(z_height),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cyl_solid(model, body_ctx, radius, length, axis="Z"):
    """Create a cylindrical IfcExtrudedAreaSolid along X, Y, or Z in mm."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
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
    elif axis == "Y":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
        )
    else:
        raise ValueError(axis)

    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(length),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def add_element(model, storey, body_ctx, ifc_class, name, predefined_type, object_type,
                rep, cx, cy, z0, angle_rad=0.0, pset_name=None, props=None):
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, predefined_type=predefined_type, name=name
    )
    if object_type is not None:
        el.ObjectType = object_type
    el.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=el, matrix=rot_z_matrix(cx, cy, z0, angle_rad)
    )
    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)
    if pset_name and props:
        pset = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)
    return el


def add_rect_segment(model, storey, body_ctx, ifc_class, predefined_type, object_type,
                     name, p1, p2, width, height, pset_name, props):
    """Add an axis-aligned rectangular MEP segment between 3D points p1 and p2 (centreline)."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-3:
        return None
    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        # Along X: x_dim = length, y_dim = width, z = height
        rep = make_rect_solid(model, body_ctx, length, width, height)
        cx, cy, z0 = 0.5 * (x1 + x2), y1, z1 - 0.5 * height
    elif abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        # Along Y: x_dim = width, y_dim = length, z = height
        rep = make_rect_solid(model, body_ctx, width, length, height)
        cx, cy, z0 = x1, 0.5 * (y1 + y2), z1 - 0.5 * height
    else:
        # Along Z: vertical riser
        rep = make_rect_solid(model, body_ctx, width, height, length)
        cx, cy, z0 = x1, y1, min(z1, z2)
    return add_element(
        model, storey, body_ctx, ifc_class, name, predefined_type, object_type,
        rep, cx, cy, z0, 0.0, pset_name, props
    )


def add_pipe_segment(model, storey, body_ctx, name, p1, p2, od, pset_name, props):
    """Add an axis-aligned circular pipe segment between 3D points p1 and p2 (centreline)."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-3:
        return None
    r = 0.5 * od
    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        rep = make_cyl_solid(model, body_ctx, r, length, axis="X")
        cx, cy, z0 = min(x1, x2), y1, z1
    elif abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        rep = make_cyl_solid(model, body_ctx, r, length, axis="Y")
        cx, cy, z0 = x1, min(y1, y2), z1
    else:
        rep = make_cyl_solid(model, body_ctx, r, length, axis="Z")
        cx, cy, z0 = x1, y1, min(z1, z2)
    return add_element(
        model, storey, body_ctx, "IfcPipeSegment", name, "RIGIDSEGMENT",
        "ChilledWaterPipe", rep, cx, cy, z0, 0.0, pset_name, props
    )


# ---------------------------------------------------------------------------
# 3. Build Model
# ---------------------------------------------------------------------------
def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1"
    )
    length_unit = ifcopenshell.api.unit.add_si_unit(
        model, unit_type="LENGTHUNIT", prefix="MILLI"
    )
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Data Hall 1"
    )
    storey.Elevation = 0.0
    ifcopenshell.api.spatial.assign_container  # keep import used
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 3.1 Access Floor (Z = -35..0)
    floor_rep = make_rect_solid(model, body_ctx, HALL_W, HALL_D, ACCESS_FLOOR_THK)
    add_element(
        model, storey, body_ctx, "IfcSlab", "AccessFloor-Hall1", "FLOOR", "AccessFloor",
        floor_rep, HALL_W / 2.0, HALL_D / 2.0, -ACCESS_FLOOR_THK, 0.0,
        "Pset_DCM_Floor", {"ThicknessMm": ACCESS_FLOOR_THK, "PlenumDepthMm": 865.0},
    )

    # 3.2 Structural Columns (6, Z = 0..3600)
    for idx, (cx, cy) in enumerate(COL_CENTRES, 1):
        col_rep = make_rect_solid(model, body_ctx, COL_SIZE, COL_SIZE, SOFFIT_Z)
        add_element(
            model, storey, body_ctx, "IfcColumn", f"COL-{idx:02d}", "COLUMN", "StructuralColumn",
            col_rep, cx, cy, 0.0, 0.0,
            "Pset_DCM_Structure", {"WidthMm": COL_SIZE, "DepthMm": COL_SIZE, "HeightMm": SOFFIT_Z},
        )

    # 3.3 Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_id, seq in ROW_SEQUENCES.items():
        cl_y = ROW_META[row_id]["cl_y"]
        facing = ROW_META[row_id]["facing"]
        angle = 0.0 if facing == "NORTH" else math.pi
        x = ROW_WEST_START_X
        cab_idx = 0
        cu_idx = 0
        west_end_x = None
        for btype, count in seq:
            for _ in range(count):
                if btype == "CA":
                    west_end_x = x
                    x = ROW_EAST_START_X
                    continue
                w = BAY_WIDTHS[btype]
                cx = x + w / 2.0
                if btype in ("C1", "N1"):
                    cab_idx += 1
                    rep = make_rect_solid(model, body_ctx, w, CAB_DEPTH, CAB_HEIGHT)
                    add_element(
                        model, storey, body_ctx, "IfcFurniture",
                        f"RACK-{row_id}{cab_idx:02d}", "USERDEFINED", "Rack",
                        rep, cx, cl_y, 0.0, angle,
                        "Pset_DCM_Rack",
                        {
                            "Row": row_id,
                            "CabinetType": btype,
                            "WidthMm": w,
                            "DepthMm": CAB_DEPTH,
                            "HeightMm": CAB_HEIGHT,
                            "Facing": facing,
                        },
                    )
                elif btype == "CU":
                    cu_idx += 1
                    rep = make_rect_solid(model, body_ctx, w, CAB_DEPTH, CAB_HEIGHT)
                    add_element(
                        model, storey, body_ctx, "IfcUnitaryEquipment",
                        f"CRAH-{row_id}{cu_idx:02d}", "AIRCONDITIONINGUNIT", "CRAH",
                        rep, cx, cl_y, 0.0, angle,
                        "Pset_DCM_CRAH",
                        {
                            "Placement": "IN_ROW",
                            "Row": row_id,
                            "WidthMm": w,
                            "DepthMm": CAB_DEPTH,
                            "HeightMm": CAB_HEIGHT,
                            "Facing": facing,
                        },
                    )
                x += w
        row_extents[row_id] = (ROW_WEST_START_X, west_end_x, ROW_EAST_START_X, x)

    # 3.4 Perimeter CRAHs (4)
    for tag, x0, y0, tile in PERIMETER_CRAHS:
        pcrah_rep = make_rect_solid(model, body_ctx, 1200.0, 900.0, 2000.0)
        add_element(
            model, storey, body_ctx, "IfcUnitaryEquipment", tag, "AIRCONDITIONINGUNIT", "CRAH",
            pcrah_rep, x0 + 600.0, y0 + 450.0, 0.0, 0.0,
            "Pset_DCM_CRAH",
            {
                "Placement": "PERIMETER",
                "Tile": tile,
                "WidthMm": 1200.0,
                "DepthMm": 900.0,
                "HeightMm": 2000.0,
                "Facing": "NORTH",
            },
        )

    # 3.5 PDUs (6)
    for tag, row_id, tile in PDU_SPECS:
        pdu_rep = make_rect_solid(model, body_ctx, PDU_W, PDU_D, PDU_H)
        cl_y = ROW_META[row_id]["cl_y"]
        facing = ROW_META[row_id]["facing"]
        angle = 0.0 if facing == "NORTH" else math.pi
        row_end_x = row_extents[row_id][3]
        x0 = row_end_x + 1800.0
        if facing == "SOUTH":
            front_y = cl_y - CAB_DEPTH / 2.0
            cy = front_y + PDU_D / 2.0
        else:
            front_y = cl_y + CAB_DEPTH / 2.0
            cy = front_y - PDU_D / 2.0
        add_element(
            model, storey, body_ctx, "IfcElectricDistributionBoard",
            tag, "DISTRIBUTIONBOARD", "PDU",
            pdu_rep, x0 + PDU_W / 2.0, cy, 0.0, angle,
            "Pset_DCM_PDU",
            {
                "ServesRow": row_id,
                "Tile": tile,
                "WidthMm": PDU_W,
                "DepthMm": PDU_D,
                "HeightMm": PDU_H,
                "Facing": facing,
                "DedicatedSpaceMm": 1800.0,
            },
        )

    # 3.6 Cold-Aisle Containment (CAC-BC, CAC-DE)
    cac_defs = [
        ("CAC-BC", 7200.0, 1800.0, 9600.0, 11400.0, 19400.0),
        ("CAC-DE", 12600.0, 1800.0, 9800.0, 11400.0, 19200.0),
    ]
    for tag, cy, wx1, wx2, ex1, ex2 in cac_defs:
        for half, (x1, x2) in [("W", (wx1, wx2)), ("E", (ex1, ex2))]:
            roof_rep = make_rect_solid(model, body_ctx, x2 - x1, CAC_ROOF_W, CAC_ROOF_THK)
            add_element(
                model, storey, body_ctx, "IfcCovering",
                f"{tag}-ROOF-{half}", "CEILING", "ContainmentRoof",
                roof_rep, 0.5 * (x1 + x2), cy, CAC_ROOF_Z, 0.0,
                "Pset_DCM_Containment",
                {"ContainmentTag": tag, "WidthMm": CAC_ROOF_W, "ThicknessMm": CAC_ROOF_THK},
            )
            for side, dx in [("L", x1 - CAC_DOOR_THK / 2.0), ("R", x2 + CAC_DOOR_THK / 2.0)]:
                door_rep = make_rect_solid(model, body_ctx, CAC_DOOR_THK, CAC_DOOR_W, CAC_DOOR_H)
                add_element(
                    model, storey, body_ctx, "IfcDoor",
                    f"{tag}-DOOR-{half}{side}", "DOOR", "ContainmentDoor",
                    door_rep, dx, cy, 0.0, 0.0,
                    "Pset_DCM_Containment", {"ContainmentTag": tag},
                )

    # 3.7 Sprinkler Heads (63 ceiling + 16 in-aisle)
    c_idx = 0
    for iy in range(7):
        hy = 1500.0 + iy * 3000.0
        for ix in range(9):
            hx = 1500.0 + ix * 3000.0
            # Relocate heads inside 1500x1500 column keep-out (F-101 Detail 2)
            for cx, cy in COL_CENTRES:
                if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                    hx = cx - 900.0 if hx <= cx else cx + 900.0
                    hy = cy - 900.0 if hy <= cy else cy + 900.0
            c_idx += 1
            head_rep = make_cyl_solid(model, body_ctx, 25.0, 25.4, axis="Z")
            add_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal",
                f"SPR-C{c_idx:02d}", "SPRINKLER", "SprinklerHead",
                head_rep, hx, hy, DEFLECTOR_Z, 0.0,
                "Pset_DCM_Sprinkler",
                {"Mount": "CEILING", "DeflectorElevationMm": DEFLECTOR_Z, "StandoffMm": SPRINKLER_STANDOFF},
            )

    in_aisle_xs = [2800.0, 5000.0, 7200.0, 9000.0, 12400.0, 14600.0, 16800.0, 18600.0]
    ia_idx = 0
    for tag, cy in [("CAC-BC", 7200.0), ("CAC-DE", 12600.0)]:
        for hx in in_aisle_xs:
            ia_idx += 1
            head_rep = make_cyl_solid(model, body_ctx, 25.0, 25.4, axis="Z")
            add_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal",
                f"SPR-IA{ia_idx:02d}", "SPRINKLER", "SprinklerHead",
                head_rep, hx, cy, 1890.0, 0.0,
                "Pset_DCM_Sprinkler",
                {"Mount": "IN_AISLE", "ContainmentTag": tag, "DeflectorElevationMm": 1890.0},
            )

    # -----------------------------------------------------------------------
    # 4. MEP Routing (All 3 Services Connected to Entry, Clash-Free)
    # -----------------------------------------------------------------------
    # 4.1 Telecom Cable Tray (CT-1: 683 x 127 mm) — Under-floor plenum at Z = -200
    #     (Z = -263.5..-136.5, >2800 mm vertical separation from overhead busway)
    TRAY_Z = -200.0
    TRAY_SPINE_X = 900.0
    tray_segs = [
        ((ENTRY_X, ENTRY_Y, TRAY_Z), (TRAY_SPINE_X, ENTRY_Y, TRAY_Z)),
        ((TRAY_SPINE_X, 3000.0, TRAY_Z), (TRAY_SPINE_X, 16800.0, TRAY_Z)),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = ROW_META[row_id]["cl_y"]
        tray_segs.append(((TRAY_SPINE_X, ry, TRAY_Z), (19200.0, ry, TRAY_Z)))
    for i, (p1, p2) in enumerate(tray_segs, 1):
        add_rect_segment(
            model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT",
            "CableTray", f"CT-1-SEG-{i:02d}", p1, p2, TRAY_W, TRAY_H,
            "Pset_DCM_MEP",
            {"Service": "Telecom", "Tier": "UNDER_FLOOR", "ElevationMm": TRAY_Z, "WidthMm": TRAY_W, "HeightMm": TRAY_H},
        )

    # 4.2 Power Busway (BW-1: 128 x 147 mm) — Overhead at Z = 2700 (Z = 2626.5..2773.5)
    #     Row branches at Y = row_CL + 450 (clears all columns by 86 mm)
    BW_Z = 2700.0
    BW_SPINE_X = 600.0
    bw_segs = [
        ((ENTRY_X, ENTRY_Y, BW_Z), (BW_SPINE_X, ENTRY_Y, BW_Z)),
        ((BW_SPINE_X, 3450.0, BW_Z), (BW_SPINE_X, 17250.0, BW_Z)),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = ROW_META[row_id]["cl_y"] + 450.0
        bw_segs.append(((BW_SPINE_X, ry, BW_Z), (19200.0, ry, BW_Z)))
    for i, (p1, p2) in enumerate(bw_segs, 1):
        add_rect_segment(
            model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT",
            "Busway", f"BW-1-SEG-{i:02d}", p1, p2, BUSWAY_W, BUSWAY_H,
            "Pset_DCM_MEP",
            {"Service": "Power", "Tier": "OVERHEAD_LOW", "ElevationMm": BW_Z, "WidthMm": BUSWAY_W, "HeightMm": BUSWAY_H},
        )

    # 4.3 Chilled Water Pipe (CHW-1: OD 168.3 mm) — Overhead at Z = 2950 (Z = 2865.85..3034.15)
    #     Row headers at Y = row_CL - 450 (clears all columns by 65.85 mm, clears Busway by 92 mm)
    #     Perimeter CRAH header at Y = 900 from X = 1200 to X = 25800 (reaches all 4 perimeter CRAHs)
    CHW_Z = 2950.0
    CHW_SPINE_X = 1200.0
    chw_segs = [
        ((ENTRY_X, ENTRY_Y, CHW_Z), (CHW_SPINE_X, ENTRY_Y, CHW_Z)),
        ((CHW_SPINE_X, 900.0, CHW_Z), (CHW_SPINE_X, 16350.0, CHW_Z)),
        ((CHW_SPINE_X, 900.0, CHW_Z), (25800.0, 900.0, CHW_Z)),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = ROW_META[row_id]["cl_y"] - 450.0
        chw_segs.append(((CHW_SPINE_X, ry, CHW_Z), (19200.0, ry, CHW_Z)))
    for i, (p1, p2) in enumerate(chw_segs, 1):
        add_pipe_segment(
            model, storey, body_ctx, f"CHW-1-SEG-{i:02d}", p1, p2, CHW_OD,
            "Pset_DCM_MEP",
            {"Service": "ChilledWater", "Tier": "OVERHEAD_HIGH", "ElevationMm": CHW_Z, "OuterDiameterMm": CHW_OD},
        )

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)

    # Optional drawing-note reconciliation log
    recon_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)), "reconciliation.json")
    recon = {
        "hall_dimensions_mm": {"x": HALL_W, "y": HALL_D, "soffit_z": SOFFIT_Z, "slab_z": SLAB_Z},
        "clearances_mm": {
            "min_clear_height": MIN_CLEAR_HEIGHT,
            "sprinkler_deflector_z": DEFLECTOR_Z,
            "sprinkler_standoff": SPRINKLER_STANDOFF,
            "tray_busway_min_separation": 300.0,
            "pdu_dedicated_space_above": 1800.0,
            "underfloor_tray_clearance_below_panel": 20.0,
        },
        "pathway_tiers_mm": {
            "CT-1_Telecom": {"zone": "UNDER_FLOOR", "center_z": TRAY_Z, "section": [TRAY_W, TRAY_H]},
            "BW-1_Power": {"zone": "OVERHEAD", "center_z": BW_Z, "section": [BUSWAY_W, BUSWAY_H]},
            "CHW-1_ChilledWater": {"zone": "OVERHEAD", "center_z": CHW_Z, "od_insulated": CHW_OD},
        },
    }
    with open(recon_path, "w", encoding="utf-8") as f:
        json.dump(recon, f, indent=2)


if __name__ == "__main__":
    build_model()
