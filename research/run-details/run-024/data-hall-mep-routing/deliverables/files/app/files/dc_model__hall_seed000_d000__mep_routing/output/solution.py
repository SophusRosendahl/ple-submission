"""Coordinated IFC4 model and MEP routing for Data Hall 1 (hall_seed000_d000).

Generates the full architectural/structural/MEP coordination background and
clash-free, code-compliant routes for Cable Tray (CT-1), Power Busway (BW-1),
and Chilled Water (CHW-1).
"""
import os
import sys
import json
import math
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
# Baked-in drawing data (all dimensions in mm)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
SLAB_TOP_Z = -900.0
FLOOR_PANEL_THK = 35.0
FLOOR_TOP_Z = 0.0
SOFFIT_Z = 3600.0
DEFLECTOR_Z = 3574.6  # 25.4 mm below soffit
IN_AISLE_DEFLECTOR_Z = 1890.0

# Structural columns (600 x 600, full height 0..3600)
COLUMNS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Row definitions: (row_name, y_centre, facing, bay_sequence_tokens)
# CA = cross aisle whose east edge is fixed at X = 11400 mm
CA_EAST_X = 11400.0
ROW_START_X = 1800.0

ROWS = [
    ("A", 3000.0, "SOUTH", ["4C1", "CU", "3C1", "N1", "3C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("B", 6000.0, "NORTH", ["4C1", "CU", "5C1", "2N1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("C", 8400.0, "SOUTH", ["3C1", "CU", "6C1", "2-600", "CU", "CA", "N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"]),
    ("D", 11400.0, "NORTH", ["4C1", "CU", "3C1", "2N1", "2C1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("E", 13800.0, "SOUTH", ["4C1", "CU", "5C1", "N1", "C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("F", 16800.0, "NORTH", ["4C1", "CU", "5C1", "2-600", "CU", "CA", "2N1", "5C1", "SP", "-600", "CU", "4C1"]),
]

# Perimeter CRAHs: (tag, x_sw, y_sw, w, d, h, facing)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs: (tag, serves_row, x_sw, y_sw, w, d, h, facing)
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 5400.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 10800.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 16200.0, 762.0, 813.0, 1959.0, "NORTH"),
]

# Cold-aisle containment roofs & end doors
CONTAINMENT = [
    ("CAC-BC", 7200.0, [(1800.0, 9600.0), (11400.0, 19400.0)]),
    ("CAC-DE", 12600.0, [(1800.0, 9800.0), (11400.0, 19200.0)]),
]


def make_matrix(cx_mm, cy_mm, z_mm, rot_z_rad=0.0):
    """4x4 placement matrix with translations in METRES (for ifcopenshell is_si=True)."""
    c = math.cos(rot_z_rad)
    s = math.sin(rot_z_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def add_box_rep(f, body_ctx, w_mm, d_mm, h_mm):
    """Create an IfcShapeRepresentation with a centered 2D rectangle extruded by h_mm."""
    pt2d = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = f.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        XDim=float(w_mm),
        YDim=float(d_mm),
    )
    origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = f.create_entity("IfcAxis2Placement3D", Location=origin)
    z_dir = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=z_dir,
        Depth=float(h_mm),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def add_cyl_rep(f, body_ctx, radius_mm, length_mm, axis="X"):
    """Create a horizontal or vertical cylinder centered on its axis."""
    pt2d = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = f.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = f.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        Radius=float(radius_mm),
    )
    if axis == "X":
        origin = f.create_entity("IfcCartesianPoint", Coordinates=(-length_mm / 2.0, 0.0, 0.0))
        z_axis = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        ref_dir = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    elif axis == "Y":
        origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, -length_mm / 2.0, 0.0))
        z_axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0))
        ref_dir = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    else:
        origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, -length_mm / 2.0))
        z_axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
        ref_dir = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))

    pos3d = f.create_entity("IfcAxis2Placement3D", Location=origin, Axis=z_axis, RefDirection=ref_dir)
    ext_dir = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=ext_dir,
        Depth=float(length_mm),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def place_element(f, storey, body_ctx, ifc_class, name, rep, cx, cy, z0, rot_z=0.0,
                  predefined_type=None, object_type=None, pset_name=None, props=None):
    el = ifcopenshell.api.root.create_entity(f, ifc_class=ifc_class, name=name)
    if predefined_type is not None:
        el.PredefinedType = predefined_type
    if object_type is not None:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[el])
    ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(
        f, product=el, matrix=make_matrix(cx, cy, z0, rot_z), is_si=True
    )
    if pset_name and props:
        ps = ifcopenshell.api.pset.add_pset(f, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=ps, properties=props)
    return el


def expand_bay_sequence(tokens):
    """Expand bay sequence tokens into list of (kind, width_mm)."""
    out = []
    for tok in tokens:
        if tok == "CA":
            out.append(("CA", 0.0))
        elif tok == "CU":
            out.append(("CU", 600.0))
        elif tok == "SP":
            out.append(("SP", 600.0))
        elif tok == "-600":
            out.append(("OMIT", 600.0))
        elif tok.endswith("-600"):
            n = int(tok.split("-")[0])
            for _ in range(n):
                out.append(("OMIT", 600.0))
        elif tok.endswith("C1"):
            n = int(tok[:-2]) if len(tok) > 2 else 1
            for _ in range(n):
                out.append(("C1", 600.0))
        elif tok.endswith("N1"):
            n = int(tok[:-2]) if len(tok) > 2 else 1
            for _ in range(n):
                out.append(("N1", 800.0))
        else:
            raise ValueError(f"Unknown bay token: {tok}")
    return out


def build_model():
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
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=building, products=[storey])

    # 1. Access floor panel (35 mm thick, top at 0 -> z = -35..0)
    floor_rep = add_box_rep(f, body_ctx, ROOM_W, ROOM_D, FLOOR_PANEL_THK)
    place_element(
        f, storey, body_ctx, "IfcSlab", "AccessFloor", floor_rep,
        ROOM_W / 2.0, ROOM_D / 2.0, -FLOOR_PANEL_THK,
        predefined_type="FLOOR",
    )

    # 2. Structural columns (600 x 600, z = 0..3600)
    for cname, cx, cy in COLUMNS:
        place_element(
            f, storey, body_ctx, "IfcColumn", cname, add_box_rep(f, body_ctx, 600.0, 600.0, SOFFIT_Z),
            cx, cy, 0.0, predefined_type="COLUMN",
        )

    # 3. Racks & In-Row CRAHs
    for row_name, row_yc, facing, tokens in ROWS:
        rot_z = 0.0 if facing == "SOUTH" else math.pi
        x = ROW_START_X
        rack_idx = 0
        crah_idx = 0
        for kind, w in expand_bay_sequence(tokens):
            if kind == "CA":
                x = CA_EAST_X
                continue
            cx = x + w / 2.0
            if kind in ("C1", "N1"):
                rack_idx += 1
                tag = f"RACK-{row_name}{rack_idx:02d}"
                rep = add_box_rep(f, body_ctx, w, 1200.0, 2000.0)
                place_element(
                    f, storey, body_ctx, "IfcFurniture", tag, rep,
                    cx, row_yc, 0.0, rot_z=rot_z,
                    predefined_type="USERDEFINED", object_type="Rack",
                    pset_name="Pset_DCM_Rack",
                    props={
                        "Tag": tag, "Row": row_name, "Type": kind, "Facing": facing,
                        "Width_mm": w, "Depth_mm": 1200.0, "Height_mm": 2000.0,
                        "RU": 42, "Power_kW": 8.0, "Load_kg": 1363.0,
                    },
                )
            elif kind == "CU":
                crah_idx += 1
                tag = f"CRAH-{row_name}{crah_idx:02d}"
                place_element(
                    f, storey, body_ctx, "IfcUnitaryEquipment", tag, add_box_rep(f, body_ctx, 600.0, 1200.0, 2000.0),
                    cx, row_yc, 0.0, rot_z=rot_z,
                    predefined_type="AIRHANDLER", object_type="CRAH",
                    pset_name="Pset_DCM_CRAH",
                    props={
                        "Tag": tag, "Placement": f"IN-ROW {row_name}", "Facing": facing,
                        "Capacity_kW": 50.0, "Airflow_m3h": 9000.0, "Service": "CHW DN50",
                    },
                )
            x += w

    # 4. Perimeter CRAHs
    for tag, x_sw, y_sw, w, d, h, facing in PERIMETER_CRAHS:
        rot_z = 0.0 if facing == "SOUTH" else math.pi
        place_element(
            f, storey, body_ctx, "IfcUnitaryEquipment", tag, add_box_rep(f, body_ctx, w, d, h),
            x_sw + w / 2.0, y_sw + d / 2.0, 0.0, rot_z=rot_z,
            predefined_type="AIRHANDLER", object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            props={
                "Tag": tag, "Placement": "PERIMETER", "Facing": facing,
                "Capacity_kW": 100.0, "Airflow_m3h": 20000.0, "Service": "CHW DN100",
            },
        )

    # 5. PDUs
    for tag, serves_row, x_sw, y_sw, w, d, h, facing in PDUS:
        rot_z = 0.0 if facing == "SOUTH" else math.pi
        place_element(
            f, storey, body_ctx, "IfcElectricDistributionBoard", tag, add_box_rep(f, body_ctx, w, d, h),
            x_sw + w / 2.0, y_sw + d / 2.0, 0.0, rot_z=rot_z,
            predefined_type="DISTRIBUTIONBOARD", object_type="PDU",
            pset_name="Pset_DCM_PDU",
            props={
                "Tag": tag, "ServesRow": serves_row, "Facing": facing,
                "Rating_kVA": 225.0, "WorkingSpace_mm": 900.0,
            },
        )

    # 6. Cold-Aisle Containment (roof panels + end doors)
    for cac_tag, yc, sections in CONTAINMENT:
        for idx, (x0, x1) in enumerate(sections, 1):
            roof_rep = add_box_rep(f, body_ctx, x1 - x0, 1400.0, 55.5)
            place_element(
                f, storey, body_ctx, "IfcCovering", f"{cac_tag}-ROOF-{idx}", roof_rep,
                0.5 * (x0 + x1), yc, 2000.0, predefined_type="CEILING",
                object_type="ContainmentRoof",
            )
            place_element(
                f, storey, body_ctx, "IfcDoor", f"{cac_tag}-DOOR-{idx}W", add_box_rep(f, body_ctx, 60.0, 1200.0, 2055.5),
                x0 + 30.0, yc, 0.0, predefined_type="DOOR",
            )
            place_element(
                f, storey, body_ctx, "IfcDoor", f"{cac_tag}-DOOR-{idx}E", add_box_rep(f, body_ctx, 60.0, 1200.0, 2055.5),
                x1 - 30.0, yc, 0.0, predefined_type="DOOR",
            )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79 total)
    ceil_xs = [1500.0 + 3000.0 * i for i in range(9)]
    ceil_ys = [1500.0 + 3000.0 * j for j in range(7)]
    sp_idx = 0
    for sx in ceil_xs:
        for sy in ceil_ys:
            # Relocate heads inside 1500 mm column keep-out (±750 mm from column centre)
            rx, ry = sx, sy
            for _, cx, cy in COLUMNS:
                if abs(rx - cx) < 750.0 and abs(ry - cy) < 750.0:
                    rx = cx - 900.0 if rx <= cx else cx + 900.0
                    ry = cy - 900.0 if ry <= cy else cy + 900.0
            sp_idx += 1
            place_element(
                f, storey, body_ctx, "IfcFireSuppressionTerminal", f"SP-CEIL-{sp_idx:02d}",
                add_cyl_rep(f, body_ctx, 25.0, 25.4, axis="Z"),
                rx, ry, DEFLECTOR_Z + 12.7, predefined_type="SPRINKLER",
                pset_name="Pset_DCM_Sprinkler",
                props={"Type": "CEILING", "DeflectorZ_mm": DEFLECTOR_Z, "Standoff_mm": 460.0},
            )

    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 0
    for cac_tag, yc, _ in CONTAINMENT:
        for sx in in_aisle_xs:
            ia_idx += 1
            place_element(
                f, storey, body_ctx, "IfcFireSuppressionTerminal", f"SP-AISLE-{ia_idx:02d}",
                add_cyl_rep(f, body_ctx, 25.0, 25.4, axis="Z"),
                sx, yc, IN_AISLE_DEFLECTOR_Z + 12.7, predefined_type="SPRINKLER",
                pset_name="Pset_DCM_Sprinkler",
                props={"Type": "IN-AISLE", "DeflectorZ_mm": IN_AISLE_DEFLECTOR_Z, "Standoff_mm": 460.0},
            )

    # 8. MEP Routing (3 services, straight axis-aligned segments)
    # Hot-aisle shared branches at Y = 4500 (rows A/B), 9900 (rows C/D), 15300 (rows E/F)
    # West service strip trunk at X = 1000 mm; entry at (0, 9900)
    def add_rect_segment(ifc_class, name, p1, p2, w_mm, h_mm, z_bottom, predefined_type, object_type, pset_props):
        x1, y1 = p1
        x2, y2 = p2
        if abs(x2 - x1) >= abs(y2 - y1):
            length = abs(x2 - x1)
            rep = add_box_rep(f, body_ctx, length, w_mm, h_mm)
        else:
            length = abs(y2 - y1)
            rep = add_box_rep(f, body_ctx, w_mm, length, h_mm)
        place_element(
            f, storey, body_ctx, ifc_class, name, rep,
            0.5 * (x1 + x2), 0.5 * (y1 + y2), z_bottom,
            predefined_type=predefined_type, object_type=object_type,
            pset_name="Pset_DCM_Service", props=pset_props,
        )

    def add_pipe_segment(name, p1, p2, od_mm, z_center, pset_props):
        x1, y1 = p1
        x2, y2 = p2
        if abs(x2 - x1) >= abs(y2 - y1):
            length = abs(x2 - x1)
            rep = add_cyl_rep(f, body_ctx, od_mm / 2.0, length, axis="X")
        else:
            length = abs(y2 - y1)
            rep = add_cyl_rep(f, body_ctx, od_mm / 2.0, length, axis="Y")
        place_element(
            f, storey, body_ctx, "IfcPipeSegment", name, rep,
            0.5 * (x1 + x2), 0.5 * (y1 + y2), z_center,
            predefined_type="RIGIDSEGMENT", object_type="ChilledWater",
            pset_name="Pset_DCM_Service", props=pset_props,
        )

    # 8a. Power Busway (BW-1: 128 W x 147 H, overhead Z = 2610..2757)
    bw_z0 = 2610.0
    bw_segs = [
        ("BW-ENTRY", (0.0, 9900.0), (1000.0, 9900.0)),
        ("BW-TRUNK-S", (1000.0, 4500.0), (1000.0, 9900.0)),
        ("BW-TRUNK-N", (1000.0, 9900.0), (1000.0, 15300.0)),
        ("BW-AISLE-AB", (1000.0, 4500.0), (19200.0, 4500.0)),
        ("BW-AISLE-CD", (1000.0, 9900.0), (19200.0, 9900.0)),
        ("BW-AISLE-EF", (1000.0, 15300.0), (19200.0, 15300.0)),
    ]
    for sname, p1, p2 in bw_segs:
        add_rect_segment(
            "IfcCableCarrierSegment", sname, p1, p2, 128.0, 147.0, bw_z0,
            "USERDEFINED", "Busway",
            {"Service": "POWER", "Tag": "BW-1", "Section_mm": "128x147",
             "ElevationZ_mm": bw_z0 + 73.5, "Zone": "OVERHEAD"},
        )

    # 8b. Telecom Cable Tray (CT-1: 683 W x 127 H, under-floor plenum Z = -200..-73)
    ct_z0 = -200.0
    ct_segs = [
        ("CT-ENTRY", (0.0, 9900.0), (1000.0, 9900.0)),
        ("CT-TRUNK-S", (1000.0, 4500.0), (1000.0, 9900.0)),
        ("CT-TRUNK-N", (1000.0, 9900.0), (1000.0, 15300.0)),
        ("CT-AISLE-AB", (1000.0, 4500.0), (19200.0, 4500.0)),
        ("CT-AISLE-CD", (1000.0, 9900.0), (19200.0, 9900.0)),
        ("CT-AISLE-EF", (1000.0, 15300.0), (19200.0, 15300.0)),
    ]
    for sname, p1, p2 in ct_segs:
        add_rect_segment(
            "IfcCableCarrierSegment", sname, p1, p2, 683.0, 127.0, ct_z0,
            "CABLETRAYSEGMENT", "CableTray",
            {"Service": "TELECOM", "Tag": "CT-1", "Section_mm": "683x127",
             "ElevationZ_mm": ct_z0 + 63.5, "Zone": "UNDERFLOOR"},
        )

    # 8c. Chilled Water Pipe (CHW-1: insulated OD 168.3 mm, under-floor plenum Z_center = -500)
    chw_zc = -500.0
    chw_od = 168.3
    chw_segs = [
        ("CHW-ENTRY", (0.0, 9900.0), (1000.0, 9900.0)),
        ("CHW-TRUNK-S", (1000.0, 1500.0), (1000.0, 9900.0)),
        ("CHW-TRUNK-N", (1000.0, 9900.0), (1000.0, 15300.0)),
        ("CHW-PERIM", (1000.0, 1500.0), (25800.0, 1500.0)),
        ("CHW-AISLE-AB", (1000.0, 4500.0), (19200.0, 4500.0)),
        ("CHW-AISLE-CD", (1000.0, 9900.0), (19200.0, 9900.0)),
        ("CHW-AISLE-EF", (1000.0, 15300.0), (19200.0, 15300.0)),
    ]
    for sname, p1, p2 in chw_segs:
        add_pipe_segment(
            sname, p1, p2, chw_od, chw_zc,
            {"Service": "CHILLED_WATER", "Tag": "CHW-1", "Section_mm": "OD168.3_INSULATED",
             "ElevationZ_mm": chw_zc, "Zone": "UNDERFLOOR"},
        )

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    f.write(OUT_PATH)

    # Optional diagnostic reconciliation log
    recon_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)), "reconciliation.json")
    recon = {
        "room_mm": {"width": ROOM_W, "depth": ROOM_D, "soffit_z": SOFFIT_Z, "slab_top_z": SLAB_TOP_Z},
        "clearances_mm": {
            "min_clear_height": 2600.0,
            "sprinkler_standoff": 460.0,
            "tray_busway_separation": 300.0,
            "underfloor_panel_clearance": 20.0,
            "pdu_dedicated_space_above": 1800.0,
            "chw_insulation_od": 168.3,
        },
        "tiers_mm": {
            "BW-1": {"zone": "OVERHEAD", "z_bottom": 2610.0, "z_top": 2757.0},
            "CT-1": {"zone": "UNDERFLOOR", "z_bottom": -200.0, "z_top": -73.0},
            "CHW-1": {"zone": "UNDERFLOOR", "z_bottom": -584.15, "z_top": -415.85},
        },
    }
    with open(recon_path, "w", encoding="utf-8") as rf:
        json.dump(recon, rf, indent=2)


if __name__ == "__main__":
    build_model()
