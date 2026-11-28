"""Coordinated IFC4 BIM model for Data Hall 1 (hall_seed000_d000).

Rebuilds the architectural/structural/MEP background from the 7-sheet drawing set
and routes telecom cable tray (CT-1), power busway (BW-1), and chilled water (CHW-1)
clash-free and code-compliant.
"""
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
import ifcopenshell.util.placement

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model.ifc"
)

# ---------------------------------------------------------------------------
# Drawing-extracted literal data (all dimensions in mm)
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
ACCESS_FLOOR_THK = 35.0
PLENUM_SLAB_Z = -900.0
CEILING_SOFFIT_Z = 3600.0
CEILING_DEFLECTOR_Z = 3574.6
IN_AISLE_DEFLECTOR_Z = 1890.0

# Structural columns: 600 x 600 mm, Z = 0..3600
COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Cabinet rows (A-101, A-601)
ROW_START_X = 1800.0
CROSS_AISLE_EAST_X = 11400.0
RACK_DEPTH = 1200.0
RACK_HEIGHT = 2000.0

ROWS = [
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
        ("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1),
        ("CA", 1),
        ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3),
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
        ("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1),
        ("CA", 1),
        ("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4),
    ]),
]

# Perimeter CRAHs (A-601, M-101): 1200 x 900 x 2000, NORTH facing, Y = 0..900
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, E-101): 762 x 813 x 1959, front flush with row front face
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", "SOUTH", 21000.0, 2400.0),
    ("PDU-02", "B", "NORTH", 21600.0, 6600.0 - PDU_D),
    ("PDU-03", "C", "SOUTH", 21000.0, 7800.0),
    ("PDU-04", "D", "NORTH", 21600.0, 12000.0 - PDU_D),
    ("PDU-05", "E", "SOUTH", 21000.0, 13200.0),
    ("PDU-06", "F", "NORTH", 21600.0, 17400.0 - PDU_D),
]

# Cold-Aisle Containment (A-602)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z0 = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5

# Pathway section dimensions (A-602, M-101, E-101)
TRAY_W = 683.0
TRAY_H = 127.0
BUSWAY_W = 128.0
BUSWAY_H = 147.0
CHW_OD = 168.3  # insulated OD


# ---------------------------------------------------------------------------
# IFC helper functions
# ---------------------------------------------------------------------------
def make_matrix(cx_mm, cy_mm, z0_mm, rot_deg=0.0):
    """4x4 placement matrix with translations in METRES (ifcopenshell is_si=True)."""
    rad = math.radians(rot_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def add_box(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
            cx, cy, z0, dx, dy, dz, rot_deg=0.0, pset_name=None, props=None):
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[el])

    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    z_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=z_dir,
        Depth=float(dz),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=el, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=el, matrix=make_matrix(cx, cy, z0, rot_deg), is_si=True
    )

    if pset_name and props:
        pset = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)
    return el


def add_cyl_z(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
              cx, cy, z0, radius, height, pset_name=None, props=None):
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[el])

    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    z_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=z_dir,
        Depth=float(height),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=el, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=el, matrix=make_matrix(cx, cy, z0, 0.0), is_si=True
    )

    if pset_name and props:
        pset = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)
    return el


def add_segment(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                x0, y0, x1, y1, z_bot, width, height, pset_name=None, props=None):
    """Axis-aligned horizontal MEP segment from (x0,y0) to (x1,y1)."""
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    if abs(x1 - x0) >= abs(y1 - y0):
        dx = abs(x1 - x0)
        dy = width
    else:
        dx = width
        dy = abs(y1 - y0)
    return add_box(
        model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
        cx, cy, z_bot, dx, dy, height, rot_deg=0.0, pset_name=pset_name, props=props
    )


def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1"
    )
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.spatial.assign_container(model, relating_structure=project, products=[])
    model.create_entity(
        "IfcRelAggregates",
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=project,
        RelatedObjects=[site],
    )
    model.create_entity(
        "IfcRelAggregates",
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=site,
        RelatedObjects=[building],
    )
    model.create_entity(
        "IfcRelAggregates",
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=building,
        RelatedObjects=[storey],
    )

    # 1. Access Floor Panel (35 mm thick, Z = -35..0)
    add_box(
        model, body_ctx, storey, "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        ROOM_X / 2.0, ROOM_Y / 2.0, -ACCESS_FLOOR_THK, ROOM_X, ROOM_Y, ACCESS_FLOOR_THK
    )

    # 2. Structural Columns (6 units, 600x600, Z = 0..3600)
    col_labels_x = ["A", "B", "C"]
    col_labels_y = ["1", "2"]
    for ix, cx in enumerate(COL_XS):
        for iy, cy in enumerate(COL_YS):
            add_box(
                model, body_ctx, storey, "IfcColumn",
                f"COL-{col_labels_x[ix]}{col_labels_y[iy]}", "COLUMN", "Column",
                cx, cy, 0.0, COL_SIZE, COL_SIZE, CEILING_SOFFIT_Z
            )

    # 3. Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_id, yc, facing, seq in ROWS:
        rot = 0.0 if facing == "NORTH" else 180.0
        x = ROW_START_X
        rack_idx = 0
        crah_idx = 0
        west_end_x = None
        east_end_x = None
        for kind, count in seq:
            if kind == "CA":
                west_end_x = x
                x = CROSS_AISLE_EAST_X
                continue
            for _ in range(count):
                if kind == "C1":
                    w = 600.0
                    rack_idx += 1
                    add_box(
                        model, body_ctx, storey, "IfcFurniture",
                        f"RACK-{row_id}{rack_idx:02d}", "USERDEFINED", "Rack",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, rot_deg=rot,
                        pset_name="Pset_DCM_Rack",
                        props={"Row": row_id, "BayType": "C1", "RU": 42, "PowerKW": 8.0, "LoadKg": 1363.0, "FrontFaces": facing}
                    )
                    x += w
                elif kind == "N1":
                    w = 800.0
                    rack_idx += 1
                    add_box(
                        model, body_ctx, storey, "IfcFurniture",
                        f"RACK-{row_id}{rack_idx:02d}", "USERDEFINED", "Rack",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, rot_deg=rot,
                        pset_name="Pset_DCM_Rack",
                        props={"Row": row_id, "BayType": "N1", "RU": 42, "PowerKW": 8.0, "LoadKg": 1363.0, "FrontFaces": facing}
                    )
                    x += w
                elif kind == "CU":
                    w = 600.0
                    crah_idx += 1
                    add_box(
                        model, body_ctx, storey, "IfcUnitaryEquipment",
                        f"CRAH-{row_id}{crah_idx:02d}", "AIRCONDITIONINGUNIT", "CRAH",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, rot_deg=rot,
                        pset_name="Pset_DCM_CRAH",
                        props={"Placement": f"IN ROW {row_id}", "CapacityKW": 50.0, "AirflowM3H": 9000.0, "FrontFaces": facing, "Service": "CHW DN50"}
                    )
                    x += w
                elif kind in ("SP", "-600"):
                    x += 600.0
        east_end_x = x
        row_extents[row_id] = (ROW_START_X, west_end_x, CROSS_AISLE_EAST_X, east_end_x)

    # 4. Perimeter CRAHs (4 units)
    for tag, x0, y0 in PERIM_CRAHS:
        add_box(
            model, body_ctx, storey, "IfcUnitaryEquipment",
            tag, "AIRCONDITIONINGUNIT", "CRAH",
            x0 + 600.0, y0 + 450.0, 0.0, 1200.0, 900.0, 2000.0, rot_deg=0.0,
            pset_name="Pset_DCM_CRAH",
            props={"Placement": "PERIMETER", "CapacityKW": 100.0, "AirflowM3H": 20000.0, "FrontFaces": "NORTH", "Service": "CHW DN100"}
        )

    # 5. PDUs (6 units)
    for tag, row_id, facing, x0, y0 in PDUS:
        rot = 0.0 if facing == "NORTH" else 180.0
        add_box(
            model, body_ctx, storey, "IfcElectricDistributionBoard",
            tag, "DISTRIBUTIONBOARD", "PDU",
            x0 + PDU_W / 2.0, y0 + PDU_D / 2.0, 0.0, PDU_W, PDU_D, PDU_H, rot_deg=rot,
            pset_name="Pset_DCM_PDU",
            props={"ServesRow": row_id, "RatingKVA": 225.0, "FrontFaces": facing, "WorkingSpaceMM": 900.0}
        )

    # 6. Cold-Aisle Containment (CAC-BC, CAC-DE)
    for tag, yc, r_south, r_north in [("CAC-BC", 7200.0, "B", "C"), ("CAC-DE", 12600.0, "D", "E")]:
        w_end = min(row_extents[r_south][1], row_extents[r_north][1])
        e_end = min(row_extents[r_south][3], row_extents[r_north][3])
        # West roof & East roof
        for sec, sx0, sx1 in [("W", ROW_START_X, w_end), ("E", CROSS_AISLE_EAST_X, e_end)]:
            add_box(
                model, body_ctx, storey, "IfcCovering",
                f"{tag}-ROOF-{sec}", "CEILING", "ContainmentRoof",
                0.5 * (sx0 + sx1), yc, CAC_ROOF_Z0, sx1 - sx0, CAC_ROOF_W, CAC_ROOF_THK
            )
            # End doors (outside roof ends to avoid clash with roof/racks)
            add_box(
                model, body_ctx, storey, "IfcDoor",
                f"{tag}-DOOR-{sec}1", "DOOR", "ContainmentDoor",
                sx0 - CAC_DOOR_THK / 2.0, yc, 0.0, CAC_DOOR_THK, 1200.0, CAC_DOOR_H
            )
            add_box(
                model, body_ctx, storey, "IfcDoor",
                f"{tag}-DOOR-{sec}2", "DOOR", "ContainmentDoor",
                sx1 + CAC_DOOR_THK / 2.0, yc, 0.0, CAC_DOOR_THK, 1200.0, CAC_DOOR_H
            )

    # 7. Sprinklers (63 ceiling + 16 in-aisle = 79 heads)
    sp_idx = 0
    for iy in range(7):
        sy = 1500.0 + iy * 3000.0
        for ix in range(9):
            sx = 1500.0 + ix * 3000.0
            # Relocate heads within 750 mm of a structural column (F-101 Note 3)
            if abs(sx - 16800.0) < 750.0 and abs(sy - 16800.0) < 750.0:
                sx, sy = 16200.0, 16200.0
            elif abs(sx - 25200.0) < 750.0 and abs(sy - 16800.0) < 750.0:
                sx, sy = 25800.0, 16200.0
            sp_idx += 1
            add_cyl_z(
                model, body_ctx, storey, "IfcFireSuppressionTerminal",
                f"SPR-C{sp_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx, sy, CEILING_DEFLECTOR_Z, 25.0, 25.4,
                pset_name="Pset_DCM_Sprinkler",
                props={"Location": "CEILING", "DeflectorElevationMM": CEILING_DEFLECTOR_Z, "StandoffMM": 460.0}
            )

    in_aisle_xs = [2800.0, 5000.0, 7200.0, 9200.0, 12400.0, 14600.0, 16800.0, 18800.0]
    ia_idx = 0
    for aisle_y in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            add_cyl_z(
                model, body_ctx, storey, "IfcFireSuppressionTerminal",
                f"SPR-A{ia_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx, aisle_y, IN_AISLE_DEFLECTOR_Z, 25.0, 110.0,
                pset_name="Pset_DCM_Sprinkler",
                props={"Location": "IN-AISLE", "DeflectorElevationMM": IN_AISLE_DEFLECTOR_Z, "StandoffMM": 460.0}
            )

    # -----------------------------------------------------------------------
    # 8. MEP Routing (butt-jointed axis-aligned segments, zero overlap)
    # -----------------------------------------------------------------------
    # A. Telecom Cable Tray (CT-1): 683 x 127 mm, OVERHEAD Z = 2850..2977
    #    3 E-W branches in hot aisles (Y=4500, 9900, 15300) serve all 6 rows!
    ct_z = 2850.0
    ct_x_trunk = 600.0
    ct_hw = TRAY_W / 2.0
    ct_segs = [
        # Entry stub from West wall (X=0) to trunk west edge
        ("CT-ENTRY", 0.0, 9900.0, ct_x_trunk - ct_hw, 9900.0),
        # N-S trunk at X=600 from Y=4500-hw to Y=15300+hw
        ("CT-TRUNK", ct_x_trunk, 4500.0 - ct_hw, ct_x_trunk, 15300.0 + ct_hw),
        # 3 E-W branches starting at trunk east edge (X=600+hw) to X=16900
        ("CT-AB", ct_x_trunk + ct_hw, 4500.0, 16900.0, 4500.0),
        ("CT-CD", ct_x_trunk + ct_hw, 9900.0, 16900.0, 9900.0),
        ("CT-EF", ct_x_trunk + ct_hw, 15300.0, 16900.0, 15300.0),
    ]
    for name, x0, y0, x1, y1 in ct_segs:
        add_segment(
            model, body_ctx, storey, "IfcCableCarrierSegment",
            name, "CABLETRAYSEGMENT", "CableTray",
            x0, y0, x1, y1, ct_z, TRAY_W, TRAY_H,
            pset_name="Pset_DCM_Pathway",
            props={"Service": "TELECOM", "Tag": "CT-1", "Tier": "OVERHEAD", "ElevationMM": ct_z}
        )

    # B. Power Busway (BW-1): 128 x 147 mm, UNDER-FLOOR Z = -600..-453
    bw_z = -600.0
    bw_x_trunk = 600.0
    bw_hw = BUSWAY_W / 2.0
    bw_segs = [
        ("BW-ENTRY", 0.0, 9900.0, bw_x_trunk - bw_hw, 9900.0),
        ("BW-TRUNK", bw_x_trunk, 4500.0 - bw_hw, bw_x_trunk, 15300.0 + bw_hw),
        ("BW-AB", bw_x_trunk + bw_hw, 4500.0, 16900.0, 4500.0),
        ("BW-CD", bw_x_trunk + bw_hw, 9900.0, 16900.0, 9900.0),
        ("BW-EF", bw_x_trunk + bw_hw, 15300.0, 16900.0, 15300.0),
    ]
    for name, x0, y0, x1, y1 in bw_segs:
        add_segment(
            model, body_ctx, storey, "IfcCableSegment",
            name, "BUSBARSEGMENT", "Busway",
            x0, y0, x1, y1, bw_z, BUSWAY_W, BUSWAY_H,
            pset_name="Pset_DCM_Pathway",
            props={"Service": "POWER", "Tag": "BW-1", "Tier": "UNDERFLOOR", "ElevationMM": bw_z}
        )

    # C. Chilled Water Pipe (CHW-1): insulated OD 168.3 mm, UNDER-FLOOR Z = -350..-181.7
    chw_z = -350.0
    chw_x_trunk = 600.0
    chw_hw = CHW_OD / 2.0
    chw_segs = [
        ("CHW-ENTRY", 0.0, 9900.0, chw_x_trunk - chw_hw, 9900.0),
        ("CHW-TRUNK", chw_x_trunk, 2500.0 - chw_hw, chw_x_trunk, 15300.0 + chw_hw),
        # Perimeter CRAHs + Row A (Y=2500 is 1600 mm from perimeter CRAHs, 500 mm from Row A)
        ("CHW-PERIM", chw_x_trunk + chw_hw, 2500.0, 23300.0, 2500.0),
        # Row B & C (Y=7200 is 1200 mm from both)
        ("CHW-BC", chw_x_trunk + chw_hw, 7200.0, 16900.0, 7200.0),
        # Row D & E (Y=12600 is 1200 mm from both)
        ("CHW-DE", chw_x_trunk + chw_hw, 12600.0, 16900.0, 12600.0),
        # Row F (Y=15300 is 1500 mm from Row F)
        ("CHW-F", chw_x_trunk + chw_hw, 15300.0, 16900.0, 15300.0),
    ]
    for name, x0, y0, x1, y1 in chw_segs:
        add_segment(
            model, body_ctx, storey, "IfcPipeSegment",
            name, "RIGIDSEGMENT", "CHW",
            x0, y0, x1, y1, chw_z, CHW_OD, CHW_OD,
            pset_name="Pset_DCM_Pathway",
            props={"Service": "CHW", "Tag": "CHW-1", "Tier": "UNDERFLOOR", "ElevationMM": chw_z}
        )

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)


if __name__ == "__main__":
    build_model()
