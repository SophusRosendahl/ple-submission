"""Coordinated 3D IFC4 model of Data Hall 1 (hall_seed000_d000) with clash-free MEP routing.

Builds the room fit-out (access floor, structural columns, 128 racks, 4 perimeter CRAHs,
18 in-row CRAHs, 6 PDUs, cold-aisle containment, 63 ceiling + 16 in-aisle sprinklers)
and routes the three MEP services (telecom cable tray, power busway, chilled-water pipe)
from their West-wall service entries (X=0, Y=9900).

Usage:
    python3 output/solution.py [output_path.ifc]
"""
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.validate

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model.ifc"
)

# ---------------------------------------------------------------------------
# Hall geometry constants (all in millimetres, origin at SW corner, Z=0 at FF)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0
CEILING_Z = 3600.0

COL_SIZE = 400.0
COL_COORDS = [
    (x, y)
    for x in (8400.0, 16800.0, 25200.0)
    for y in (8400.0, 16800.0)
]

# Cabinet row definitions from A-101 & A-601
# Bay tokens: (type, width_mm)
# C1 = 600 rack, N1 = 800 rack, CU = 600 in-row CRAH, CA = 1200 cross aisle,
# SP = 600 spare, OMIT600 = 600 omitted for column
ROWS = [
    ("A", 3000.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
        ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("B", 6000.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
        ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("C", 8400.0, "SOUTH", [
        ("C1", 3), ("CU", 1), ("C1", 6), ("OMIT600", 2), ("CU", 1),
        ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1),
        ("OMIT600", 2), ("C1", 3),
    ]),
    ("D", 11400.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
        ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("E", 13800.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
        ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("F", 16800.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("OMIT600", 2), ("CU", 1),
        ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("OMIT600", 1),
        ("CU", 1), ("C1", 4),
    ]),
]

BAY_WIDTHS = {
    "C1": 600.0,
    "N1": 800.0,
    "CU": 600.0,
    "CA": 1200.0,
    "SP": 600.0,
    "OMIT600": 600.0,
}

ROW_START_X = 1800.0
RACK_DEPTH = 1200.0
RACK_HEIGHT = 2000.0

# Perimeter CRAHs (A-601, M-101): 1200 W x 900 D x 2000 H, facing NORTH
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, E-101): 762 W x 813 D x 1959 H, front flush with served row front
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Cold-aisle containment (A-602, A-301)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5

# Sprinklers (F-101, A-301)
SPRINKLER_CEILING_Z = 3574.6
SPRINKLER_INAISLE_Z = 1890.0
SPRINKLER_R = 25.0
SPRINKLER_H = 50.0

# MEP section dimensions (A-602, E-101, M-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_OD = 168.3  # DN100 bare 114.3 + insulation -> 168.3 mm OD


# ---------------------------------------------------------------------------
# IFC helper functions
# ---------------------------------------------------------------------------
def make_matrix(cx_mm: float, cy_mm: float, cz_mm: float, rot_z_deg: float = 0.0) -> np.ndarray:
    """Return 4x4 placement matrix with translations in METRES (ifcopenshell.api contract)."""
    rad = math.radians(rot_z_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = cz_mm / 1000.0
    return m


def add_box_rep(model, body_ctx, dx: float, dy: float, dz: float):
    """Create a centred-in-XY, Z-from-0-to-dz IfcExtrudedAreaSolid in mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(dz),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def add_cyl_rep(model, body_ctx, radius: float, length: float, axis: str = "Z"):
    """Create a cylinder representation centred on cross-section, extruded along axis."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    if axis == "Z":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        )
    elif axis == "X":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(-length / 2.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
        )
    elif axis == "Y":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, -length / 2.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(-1.0, 0.0, 0.0)),
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


def place_element(model, storey, body_ctx, ifc_class: str, name: str,
                  predefined_type: str, object_type: str,
                  cx: float, cy: float, cz: float,
                  dx: float, dy: float, dz: float,
                  rot_z_deg: float = 0.0, psets: dict | None = None):
    elem = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class=ifc_class, name=name
    )
    if predefined_type and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type
    rep = add_box_rep(model, body_ctx, dx, dy, dz)
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=elem,
        matrix=make_matrix(cx, cy, cz, rot_z_deg),
    )
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
    if psets:
        for pset_name, props in psets.items():
            pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)
    return elem


def place_pipe_segment(model, storey, body_ctx, name: str,
                       x0: float, y0: float, z0: float,
                       x1: float, y1: float, z1: float,
                       od: float, psets: dict | None = None):
    """Place an axis-aligned cylindrical IfcPipeSegment from (x0,y0,z0) to (x1,y1,z1)."""
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1.0:
        return None
    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        axis = "X"
    elif abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        axis = "Y"
    else:
        axis = "Z"

    elem = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcPipeSegment", name=name
    )
    elem.PredefinedType = "RIGIDSEGMENT"
    elem.ObjectType = "ChilledWaterPipe"
    if axis == "Z":
        rep = add_cyl_rep(model, body_ctx, od / 2.0, length, axis="Z")
        cx, cy, cz = x0, y0, min(z0, z1)
    else:
        rep = add_cyl_rep(model, body_ctx, od / 2.0, length, axis=axis)
        cx, cy, cz = (x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0

    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=elem,
        matrix=make_matrix(cx, cy, cz, 0.0),
    )
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
    if psets:
        for pset_name, props in psets.items():
            pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)
    return elem


def place_rect_segment(model, storey, body_ctx, ifc_class: str, predefined_type: str,
                       object_type: str, name: str,
                       x0: float, y0: float, z_bot: float,
                       x1: float, y1: float, width: float, height: float,
                       psets: dict | None = None):
    """Place a horizontal axis-aligned rectangular MEP segment (tray or busway)."""
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    if dx >= dy:
        seg_dx, seg_dy = dx, width
    else:
        seg_dx, seg_dy = width, dy
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    return place_element(
        model, storey, body_ctx,
        ifc_class=ifc_class,
        name=name,
        predefined_type=predefined_type,
        object_type=object_type,
        cx=cx, cy=cy, cz=z_bot,
        dx=seg_dx, dy=seg_dy, dz=height,
        rot_z_deg=0.0,
        psets=psets,
    )


def build_model() -> ifcopenshell.file:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRES"})

    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    # 1. Access Floor (Z = -35 to 0)
    place_element(
        model, storey, body_ctx,
        ifc_class="IfcSlab", name="ACCESS-FLOOR",
        predefined_type="FLOOR", object_type="AccessFloor",
        cx=ROOM_W / 2.0, cy=ROOM_D / 2.0, cz=-FLOOR_THK,
        dx=ROOM_W, dy=ROOM_D, dz=FLOOR_THK,
        psets={"Pset_DCM_AccessFloor": {"TileSizeMm": 600.0, "PanelThicknessMm": FLOOR_THK, "PlenumDepthMm": 900.0}},
    )

    # 2. Structural Columns (6 columns, 600x600, Z = 0 to 3600)
    for idx, (cx, cy) in enumerate(COL_COORDS, 1):
        place_element(
            model, storey, body_ctx,
            ifc_class="IfcColumn", name=f"COL-{idx:02d}",
            predefined_type="COLUMN", object_type="StructuralColumn",
            cx=cx, cy=cy, cz=0.0,
            dx=COL_SIZE, dy=COL_SIZE, dz=CEILING_Z,
        )

    # 3. Cabinet Rows (128 racks) & In-Row CRAHs (18 units)
    # Per A-101 Note 5: the cross-aisle's east edge is common to every row (X = 11200 mm).
    CA_EAST_X = 11200.0
    row_extents = {}  # row_name -> (x_min, x_max, ca_x0, ca_x1)
    for row_name, row_cy, facing, seq in ROWS:
        x = ROW_START_X
        rack_num = 0
        crah_num = 0
        ca_x0 = ca_x1 = None
        rot_z = 0.0 if facing == "NORTH" else 180.0
        for tok, count in seq:
            w = BAY_WIDTHS[tok]
            for _ in range(count):
                if tok in ("C1", "N1"):
                    rack_num += 1
                    tag = f"RACK-{row_name}{rack_num:02d}"
                    place_element(
                        model, storey, body_ctx,
                        ifc_class="IfcFurniture", name=tag,
                        predefined_type="USERDEFINED", object_type="Rack",
                        cx=x + w / 2.0, cy=row_cy, cz=0.0,
                        dx=w, dy=RACK_DEPTH, dz=RACK_HEIGHT,
                        rot_z_deg=rot_z,
                        psets={"Pset_DCM_Rack": {
                            "Row": row_name,
                            "CabinetType": tok,
                            "FrontFaces": facing,
                            "RU": 42,
                            "PowerKW": 8.0,
                        }},
                    )
                elif tok == "CU":
                    crah_num += 1
                    tag = f"CRAH-{row_name}{crah_num:02d}"
                    place_element(
                        model, storey, body_ctx,
                        ifc_class="IfcUnitaryEquipment", name=tag,
                        predefined_type="AIRHANDLER", object_type="CRAH",
                        cx=x + w / 2.0, cy=row_cy, cz=0.0,
                        dx=w, dy=RACK_DEPTH, dz=RACK_HEIGHT,
                        rot_z_deg=rot_z,
                        psets={"Pset_DCM_CRAH": {
                            "Placement": f"ROW_{row_name}",
                            "CapacityKW": 50.0,
                            "FrontFaces": facing,
                            "Service": "CHW_DN50",
                        }},
                    )
                elif tok == "CA":
                    ca_x0 = x
                    ca_x1 = CA_EAST_X
                    x = CA_EAST_X
                    continue
                x += w
        row_extents[row_name] = (ROW_START_X, x, ca_x0, ca_x1)

    # 4. Perimeter CRAHs (4 units)
    for tag, x0, y0 in PERIMETER_CRAHS:
        place_element(
            model, storey, body_ctx,
            ifc_class="IfcUnitaryEquipment", name=tag,
            predefined_type="AIRHANDLER", object_type="CRAH",
            cx=x0 + 600.0, cy=y0 + 450.0, cz=0.0,
            dx=1200.0, dy=900.0, dz=2000.0,
            rot_z_deg=0.0,
            psets={"Pset_DCM_CRAH": {
                "Placement": "PERIMETER",
                "CapacityKW": 100.0,
                "FrontFaces": "NORTH",
                "Service": "CHW_DN100",
            }},
        )

    # 5. PDUs (6 units)
    for tag, row_name, x0, y0, facing in PDUS:
        rot_z = 0.0 if facing == "NORTH" else 180.0
        place_element(
            model, storey, body_ctx,
            ifc_class="IfcElectricDistributionBoard", name=tag,
            predefined_type="DISTRIBUTIONBOARD", object_type="PDU",
            cx=x0 + PDU_W / 2.0, cy=y0 + PDU_D / 2.0, cz=0.0,
            dx=PDU_W, dy=PDU_D, dz=PDU_H,
            rot_z_deg=rot_z,
            psets={"Pset_DCM_PDU": {
                "ServesRow": row_name,
                "RatingKVA": 225.0,
                "FrontFaces": facing,
            }},
        )

    # 6. Cold-Aisle Containment (CAC-BC, CAC-DE)
    for cac_tag, r1, r2, aisle_cy in [("CAC-BC", "B", "C", 7200.0), ("CAC-DE", "D", "E", 12600.0)]:
        x_start = ROW_START_X
        x_end = min(row_extents[r1][1], row_extents[r2][1])
        ca_x0 = row_extents[r1][2]
        ca_x1 = row_extents[r1][3]
        # Two roof panels (west and east of cross aisle)
        for seg_idx, (sx0, sx1) in enumerate([(x_start, ca_x0), (ca_x1, x_end)], 1):
            place_element(
                model, storey, body_ctx,
                ifc_class="IfcCovering", name=f"{cac_tag}-ROOF-{seg_idx}",
                predefined_type="CEILING", object_type="ContainmentRoof",
                cx=(sx0 + sx1) / 2.0, cy=aisle_cy, cz=CAC_ROOF_Z,
                dx=sx1 - sx0, dy=CAC_ROOF_W, dz=CAC_ROOF_THK,
            )
            # End doors at both ends of each contained segment (outside roof panel in X, face-to-face)
            for d_idx, dx_pos in enumerate([sx0 - CAC_DOOR_THK / 2.0, sx1 + CAC_DOOR_THK / 2.0], 1):
                place_element(
                    model, storey, body_ctx,
                    ifc_class="IfcDoor", name=f"{cac_tag}-DOOR-{seg_idx}-{d_idx}",
                    predefined_type="DOOR", object_type="ContainmentDoor",
                    cx=dx_pos, cy=aisle_cy, cz=0.0,
                    dx=CAC_DOOR_THK, dy=CAC_DOOR_W, dz=CAC_DOOR_H,
                )

    # 7. Sprinklers (63 ceiling + 16 in-aisle)
    # Ceiling grid: 9 x 7 (X = 1500..25500 step 3000, Y = 1500..19500 step 3000)
    sp_idx = 0
    for iy in range(7):
        sy = 1500.0 + iy * 3000.0
        for ix in range(9):
            sx = 1500.0 + ix * 3000.0
            # Relocate if within 750 mm of a structural column centre
            for cx, cy in COL_COORDS:
                if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                    sy_reloc = sy - 600.0 if sy <= cy else sy + 600.0
                    sy_use = sy_reloc
                    break
            else:
                sy_use = sy
            sp_idx += 1
            place_element(
                model, storey, body_ctx,
                ifc_class="IfcFireSuppressionTerminal", name=f"SPR-CLG-{sp_idx:02d}",
                predefined_type="SPRINKLER", object_type="Sprinkler",
                cx=sx, cy=sy_use, cz=SPRINKLER_CEILING_Z,
                dx=SPRINKLER_R * 2, dy=SPRINKLER_R * 2, dz=SPRINKLER_H,
                psets={"Pset_DCM_Sprinkler": {"Location": "CEILING", "DeflectorElevationMm": SPRINKLER_CEILING_Z}},
            )

    # In-aisle heads (8 in CAC-BC at Y=7200, 8 in CAC-DE at Y=12600)
    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9900.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 0
    for aisle_cy in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            place_element(
                model, storey, body_ctx,
                ifc_class="IfcFireSuppressionTerminal", name=f"SPR-AISLE-{ia_idx:02d}",
                predefined_type="SPRINKLER", object_type="Sprinkler",
                cx=sx, cy=aisle_cy, cz=SPRINKLER_INAISLE_Z,
                dx=SPRINKLER_R * 2, dy=SPRINKLER_R * 2, dz=SPRINKLER_H,
                psets={"Pset_DCM_Sprinkler": {"Location": "IN_AISLE", "DeflectorElevationMm": SPRINKLER_INAISLE_Z}},
            )

    # -----------------------------------------------------------------------
    # 8. MEP Routing — Connected, Clash-Free, Minimum-Length
    # -----------------------------------------------------------------------
    # Strategy:
    # - One East-West spine at Y = 9900 (service entry Y, hot aisle between C & D)
    #   from X = 0 to X = 18900, feeding 4 North-South comb branches at
    #   X = 3900, 8900, 13900, 18900 (clear of all columns at 8400, 16800, 25200).
    #   Each branch splits cleanly face-to-face at the spine (no corner overlaps).
    # - Cable Tray (CT-1, 683x127): OVERHEAD at Z = [2700, 2827]
    #   (headroom 2700 >= 2600; sprinkler clearance 3574.6 - 2827 = 747.6 >= 460).
    # - Power Busway (BW-1, 128x147): UNDER-FLOOR PLENUM at Z = [-450, -303]
    #   (clear below -35 floor panel by 268 mm >= 20 mm; vertical separation from
    #   cable tray = 2700 - (-303) = 3003 mm >= 300 mm everywhere).
    # - Chilled Water (CHW-1, OD 168.3): UNDER-FLOOR PLENUM at Z_centre = -700
    #   (Z = [-784.15, -615.85], clear of slab -900, clear of busway -450,
    #   below all PDUs so never in the 1800 mm space above any PDU).
    #   Includes a South perimeter branch at Y = 2000 reaching all 4 perimeter CRAHs.

    SPINE_Y = 9900.0
    BRANCH_XS = [4100.0, 9100.0, 14100.0, 19100.0]
    Y_SOUTH = 2400.0
    Y_NORTH = 17400.0

    # 8a. Telecom Cable Tray (Overhead, Z = 2700)
    TRAY_Z = 2700.0
    hw_ct = TRAY_W / 2.0
    place_rect_segment(
        model, storey, body_ctx,
        ifc_class="IfcCableCarrierSegment",
        predefined_type="CABLETRAYSEGMENT",
        object_type="CableTray",
        name="CT-SPINE",
        x0=0.0, y0=SPINE_Y, z_bot=TRAY_Z,
        x1=BRANCH_XS[-1] + hw_ct, y1=SPINE_Y, width=TRAY_W, height=TRAY_H,
        psets={"Pset_DCM_MEP": {"Service": "Telecom", "Zone": "OVERHEAD", "ElevationMm": TRAY_Z}},
    )
    for idx, bx in enumerate(BRANCH_XS, 1):
        place_rect_segment(
            model, storey, body_ctx,
            ifc_class="IfcCableCarrierSegment",
            predefined_type="CABLETRAYSEGMENT",
            object_type="CableTray",
            name=f"CT-BR-{idx}-S",
            x0=bx, y0=Y_SOUTH, z_bot=TRAY_Z,
            x1=bx, y1=SPINE_Y - hw_ct, width=TRAY_W, height=TRAY_H,
            psets={"Pset_DCM_MEP": {"Service": "Telecom", "Zone": "OVERHEAD", "ElevationMm": TRAY_Z}},
        )
        place_rect_segment(
            model, storey, body_ctx,
            ifc_class="IfcCableCarrierSegment",
            predefined_type="CABLETRAYSEGMENT",
            object_type="CableTray",
            name=f"CT-BR-{idx}-N",
            x0=bx, y0=SPINE_Y + hw_ct, z_bot=TRAY_Z,
            x1=bx, y1=Y_NORTH, width=TRAY_W, height=TRAY_H,
            psets={"Pset_DCM_MEP": {"Service": "Telecom", "Zone": "OVERHEAD", "ElevationMm": TRAY_Z}},
        )

    # 8b. Power Busway (Under-floor plenum, Z = -450)
    BW_Z = -450.0
    hw_bw = BUSWAY_W / 2.0
    place_rect_segment(
        model, storey, body_ctx,
        ifc_class="IfcCableSegment",
        predefined_type="BUSBARSEGMENT",
        object_type="Busway",
        name="BW-SPINE",
        x0=0.0, y0=SPINE_Y, z_bot=BW_Z,
        x1=BRANCH_XS[-1] + hw_bw, y1=SPINE_Y, width=BUSWAY_W, height=BUSWAY_H,
        psets={"Pset_DCM_MEP": {"Service": "Power", "Zone": "PLENUM", "ElevationMm": BW_Z}},
    )
    for idx, bx in enumerate(BRANCH_XS, 1):
        place_rect_segment(
            model, storey, body_ctx,
            ifc_class="IfcCableSegment",
            predefined_type="BUSBARSEGMENT",
            object_type="Busway",
            name=f"BW-BR-{idx}-S",
            x0=bx, y0=Y_SOUTH, z_bot=BW_Z,
            x1=bx, y1=SPINE_Y - hw_bw, width=BUSWAY_W, height=BUSWAY_H,
            psets={"Pset_DCM_MEP": {"Service": "Power", "Zone": "PLENUM", "ElevationMm": BW_Z}},
        )
        place_rect_segment(
            model, storey, body_ctx,
            ifc_class="IfcCableSegment",
            predefined_type="BUSBARSEGMENT",
            object_type="Busway",
            name=f"BW-BR-{idx}-N",
            x0=bx, y0=SPINE_Y + hw_bw, z_bot=BW_Z,
            x1=bx, y1=Y_NORTH, width=BUSWAY_W, height=BUSWAY_H,
            psets={"Pset_DCM_MEP": {"Service": "Power", "Zone": "PLENUM", "ElevationMm": BW_Z}},
        )

    # 8c. Chilled-Water Pipe (Under-floor plenum, Z_centre = -700)
    CHW_Z = -700.0
    hr_chw = CHW_OD / 2.0
    place_pipe_segment(
        model, storey, body_ctx,
        name="CHW-SPINE",
        x0=0.0, y0=SPINE_Y, z0=CHW_Z,
        x1=BRANCH_XS[-1] + hr_chw, y1=SPINE_Y, z1=CHW_Z,
        od=CHW_OD,
        psets={"Pset_DCM_MEP": {"Service": "ChilledWater", "Zone": "PLENUM", "ElevationMm": CHW_Z}},
    )
    for idx, bx in enumerate(BRANCH_XS, 1):
        y_s = 2000.0 + hr_chw if idx == 1 else Y_SOUTH
        place_pipe_segment(
            model, storey, body_ctx,
            name=f"CHW-BR-{idx}-S",
            x0=bx, y0=y_s, z0=CHW_Z,
            x1=bx, y1=SPINE_Y - hr_chw, z1=CHW_Z,
            od=CHW_OD,
            psets={"Pset_DCM_MEP": {"Service": "ChilledWater", "Zone": "PLENUM", "ElevationMm": CHW_Z}},
        )
        place_pipe_segment(
            model, storey, body_ctx,
            name=f"CHW-BR-{idx}-N",
            x0=bx, y0=SPINE_Y + hr_chw, z0=CHW_Z,
            x1=bx, y1=Y_NORTH, z1=CHW_Z,
            od=CHW_OD,
            psets={"Pset_DCM_MEP": {"Service": "ChilledWater", "Zone": "PLENUM", "ElevationMm": CHW_Z}},
        )
    # Perimeter CRAH header at Y = 2000 (west to CRAH-01 at X=1200, east to CRAH-04 at X=25000)
    place_pipe_segment(
        model, storey, body_ctx,
        name="CHW-CRAH-HDR",
        x0=1200.0, y0=2000.0, z0=CHW_Z,
        x1=25000.0, y1=2000.0, z1=CHW_Z,
        od=CHW_OD,
        psets={"Pset_DCM_MEP": {"Service": "ChilledWater", "Zone": "PLENUM", "ElevationMm": CHW_Z}},
    )

    return model


def main():
    model = build_model()
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
