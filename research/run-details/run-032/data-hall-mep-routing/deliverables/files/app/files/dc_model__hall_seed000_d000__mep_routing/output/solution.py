"""Coordinated IFC4 BIM model for Meridian Data Center - Data Hall 1 (hall_seed000_d000).

Rebuilds the architectural/structural/MEP background from sheets A-101, A-301,
A-601, A-602, E-101, F-101, and M-101, and routes three clash-free, code-compliant
MEP networks (Power Busway BW-1, Telecom Cable Tray CT-1, Chilled Water CHW-1).
"""
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# ---------------------------------------------------------------------------
# Hall & Datum Constants (mm) from A-101, A-301, A-601, A-602
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
SOFFIT_Z = 3600.0
DEFLECTOR_Z = 3575.0
SPRINKLER_STANDOFF = 460.0
MIN_CLEAR_Z = 2600.0
FLOOR_THK = 35.0
SLAB_TOP_Z = -900.0

ROW_START_X = 1800.0
CA_EAST_X = 11200.0  # Common east edge of cross aisle (A-101 Note 5)

ROWS = [
    ("A", 3000.0, "SOUTH", "4C1 CU 3C1 N1 3C1 CU CA 6C1 SP CU 5C1"),
    ("B", 6000.0, "NORTH", "4C1 CU 5C1 2N1 CU CA 7C1 SP CU 5C1"),
    ("C", 8400.0, "SOUTH", "3C1 CU 6C1 2-600 CU CA N1 4C1 CU SP C1 2-600 3C1"),
    ("D", 11400.0, "NORTH", "4C1 CU 3C1 2N1 2C1 CU CA 7C1 SP CU 5C1"),
    ("E", 13800.0, "SOUTH", "4C1 CU 5C1 N1 C1 CU CA 6C1 SP CU 5C1"),
    ("F", 16800.0, "NORTH", "4C1 CU 5C1 2-600 CU CA 2N1 5C1 SP -600 CU 4C1"),
]

# Service entry coordinates on west wall (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Pathway section dimensions (A-602, E-101, M-101)
BW_W, BW_H = 128.0, 147.0
CT_W, CT_H = 683.0, 127.0
CHW_BARE_OD = 114.3
CHW_INS_OD = 168.3
CHW_R = CHW_INS_OD / 2.0

# Coordinated elevations (centerlines, mm)
BW_Z = 2700.0    # Overhead: 2626.5..2773.5 (>2600 clear, <3115 standoff)
CT_Z = -250.0    # Under-floor: -313.5..-186.5 (<-55 top, >-900 slab)
CHW_Z = -600.0   # Under-floor: -684.15..-515.85 (<-313.5 CT, >-900 slab)
TRUNK_X = 1000.0


def parse_row_bays(row_name, y_cl, facing, seq_str):
    tokens = seq_str.split()
    x = ROW_START_X
    racks = []
    crahs = []
    rack_idx = 0
    crah_idx = 0
    west_end_x = None
    for tok in tokens:
        if tok == "CA":
            west_end_x = x
            x = CA_EAST_X
            continue
        if tok == "CU":
            crah_idx += 1
            crahs.append({
                "tag": f"CRAH-{row_name}{crah_idx:02d}",
                "placement": "IN-ROW",
                "row": row_name,
                "cx": x + 300.0,
                "cy": y_cl,
                "w": 600.0,
                "d": 1200.0,
                "h": 2000.0,
                "facing": facing,
                "capacity_kw": 50.0,
                "airflow_m3h": 9000.0,
                "service": "CHILLED WATER, DN50",
            })
            x += 600.0
        elif tok == "SP":
            x += 600.0
        elif tok.endswith("-600"):
            cnt_str = tok[:-4]
            cnt = int(cnt_str) if cnt_str else 1
            x += cnt * 600.0
        elif tok.endswith("C1"):
            cnt_str = tok[:-2]
            cnt = int(cnt_str) if cnt_str else 1
            for _ in range(cnt):
                rack_idx += 1
                racks.append({
                    "tag": f"RACK-{row_name}{rack_idx:02d}",
                    "row": row_name,
                    "type": "C1",
                    "cx": x + 300.0,
                    "cy": y_cl,
                    "w": 600.0,
                    "d": 1200.0,
                    "h": 2000.0,
                    "facing": facing,
                })
                x += 600.0
        elif tok.endswith("N1"):
            cnt_str = tok[:-2]
            cnt = int(cnt_str) if cnt_str else 1
            for _ in range(cnt):
                rack_idx += 1
                racks.append({
                    "tag": f"RACK-{row_name}{rack_idx:02d}",
                    "row": row_name,
                    "type": "N1",
                    "cx": x + 400.0,
                    "cy": y_cl,
                    "w": 800.0,
                    "d": 1200.0,
                    "h": 2000.0,
                    "facing": facing,
                })
                x += 800.0
        else:
            raise ValueError(f"Unknown bay token: {tok}")
    return racks, crahs, west_end_x, x


def make_box_rep(f, body_ctx, w, d, h):
    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w),
        YDim=float(d),
    )
    pos = f.create_entity(
        "IfcAxis2Placement3D",
        Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=direction,
        Depth=float(h),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cyl_rep(f, body_ctx, radius, length):
    profile = f.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    pos = f.create_entity(
        "IfcAxis2Placement3D",
        Location=f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=direction,
        Depth=float(length),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def placement_matrix(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    m = np.eye(4, dtype=float)
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def pipe_matrix(x0_mm, y0_mm, z0_mm, axis):
    m = np.eye(4, dtype=float)
    if axis == "X":
        # Local +Z -> World +X
        m[:3, 0] = [0.0, 0.0, -1.0]
        m[:3, 1] = [0.0, 1.0, 0.0]
        m[:3, 2] = [1.0, 0.0, 0.0]
    elif axis == "Y":
        # Local +Z -> World +Y
        m[:3, 0] = [1.0, 0.0, 0.0]
        m[:3, 1] = [0.0, 0.0, -1.0]
        m[:3, 2] = [0.0, 1.0, 0.0]
    elif axis == "Z":
        pass
    else:
        raise ValueError(f"Unsupported pipe axis: {axis}")
    m[0, 3] = x0_mm / 1000.0
    m[1, 3] = y0_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def add_element(f, storey, body_ctx, ifc_class, name, predefined_type, object_type,
                rep, matrix, pset_name=None, props=None):
    elem = ifcopenshell.api.root.create_entity(
        f, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type is not None:
        elem.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(f, products=[elem], relating_structure=storey)
    ifcopenshell.api.geometry.edit_object_placement(f, product=elem, matrix=matrix)
    ifcopenshell.api.geometry.assign_representation(f, product=elem, representation=rep)
    if pset_name and props:
        pset = ifcopenshell.api.pset.add_pset(f, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=props)
    return elem


def build_model():
    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        f, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1"
    )
    ifcopenshell.api.unit.assign_unit(
        f, length={"is_metric": True, "raw": "MILLIMETRE"}
    )
    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        f,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Meridian Data Center")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.aggregate.assign_object(f, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(f, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(f, products=[storey], relating_object=building)

    # 1. Access Floor (35 mm panel, top at +/-0)
    add_element(
        f, storey, body_ctx,
        "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        make_box_rep(f, body_ctx, ROOM_X, ROOM_Y, FLOOR_THK),
        placement_matrix(ROOM_X / 2.0, ROOM_Y / 2.0, -FLOOR_THK),
        "Pset_DCM_AccessFloor",
        {"Thickness_mm": FLOOR_THK, "TopElevation_mm": 0.0, "TileGrid_mm": 600.0},
    )

    # 2. Server Cabinets (128 racks) & In-Row CRAHs (18 units)
    row_extents = {}
    for row_name, y_cl, facing, seq_str in ROWS:
        racks, crahs, west_end, east_end = parse_row_bays(row_name, y_cl, facing, seq_str)
        row_extents[row_name] = (ROW_START_X, west_end, CA_EAST_X, east_end, y_cl)
        yaw = 0.0 if facing == "NORTH" else math.pi
        for r in racks:
            add_element(
                f, storey, body_ctx,
                "IfcFurniture", r["tag"], "USERDEFINED", "Rack",
                make_box_rep(f, body_ctx, r["w"], r["d"], r["h"]),
                placement_matrix(r["cx"], r["cy"], 0.0, yaw),
                "Pset_DCM_Rack",
                {
                    "Row": r["row"],
                    "BayType": r["type"],
                    "Width_mm": r["w"],
                    "Depth_mm": r["d"],
                    "Height_mm": r["h"],
                    "RU": 42,
                    "Facing": r["facing"],
                    "Power_kW": 8.0,
                    "Load_kg": 1363.0,
                },
            )
        for c in crahs:
            add_element(
                f, storey, body_ctx,
                "IfcUnitaryEquipment", c["tag"], "USERDEFINED", "CRAH",
                make_box_rep(f, body_ctx, c["w"], c["d"], c["h"]),
                placement_matrix(c["cx"], c["cy"], 0.0, yaw),
                "Pset_DCM_CRAH",
                {
                    "Placement": c["placement"],
                    "Row": c["row"],
                    "Width_mm": c["w"],
                    "Depth_mm": c["d"],
                    "Height_mm": c["h"],
                    "Facing": c["facing"],
                    "Capacity_kW": c["capacity_kw"],
                    "Airflow_m3h": c["airflow_m3h"],
                    "Service": c["service"],
                },
            )

    # 3. Perimeter CRAHs (4 units)
    perim_crahs = [
        ("CRAH-01", 600.0 + 600.0, 450.0),
        ("CRAH-02", 9000.0 + 600.0, 450.0),
        ("CRAH-03", 16800.0 + 600.0, 450.0),
        ("CRAH-04", 25200.0 + 600.0, 450.0),
    ]
    for tag, cx, cy in perim_crahs:
        add_element(
            f, storey, body_ctx,
            "IfcUnitaryEquipment", tag, "USERDEFINED", "CRAH",
            make_box_rep(f, body_ctx, 1200.0, 900.0, 2000.0),
            placement_matrix(cx, cy, 0.0, 0.0),
            "Pset_DCM_CRAH",
            {
                "Placement": "PERIMETER",
                "Row": "PERIMETER",
                "Width_mm": 1200.0,
                "Depth_mm": 900.0,
                "Height_mm": 2000.0,
                "Facing": "NORTH",
                "Capacity_kW": 100.0,
                "Airflow_m3h": 20000.0,
                "Service": "CHILLED WATER, DN100",
            },
        )

    # 4. PDUs (6 units)
    pdus = [
        ("PDU-01", "A", 21000.0 + 381.0, 2400.0 + 406.5, "SOUTH"),
        ("PDU-02", "B", 21600.0 + 381.0, 6600.0 - 406.5, "NORTH"),
        ("PDU-03", "C", 21000.0 + 381.0, 7800.0 + 406.5, "SOUTH"),
        ("PDU-04", "D", 21600.0 + 381.0, 12000.0 - 406.5, "NORTH"),
        ("PDU-05", "E", 21000.0 + 381.0, 13200.0 + 406.5, "SOUTH"),
        ("PDU-06", "F", 21600.0 + 381.0, 17400.0 - 406.5, "NORTH"),
    ]
    for tag, row_name, cx, cy, facing in pdus:
        yaw = 0.0 if facing == "NORTH" else math.pi
        add_element(
            f, storey, body_ctx,
            "IfcElectricDistributionBoard", tag, "USERDEFINED", "PDU",
            make_box_rep(f, body_ctx, 762.0, 813.0, 1959.0),
            placement_matrix(cx, cy, 0.0, yaw),
            "Pset_DCM_PDU",
            {
                "ServesRow": row_name,
                "Width_mm": 762.0,
                "Depth_mm": 813.0,
                "Height_mm": 1959.0,
                "Facing": facing,
                "Rating_kVA": 225.0,
                "WorkingSpace_mm": 900.0,
                "DedicatedSpace_mm": 1800.0,
            },
        )

    # 5. Structural Columns (6 columns, 400 x 400, z=0..3600)
    col_coords = []
    for gx_lbl, gx in [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]:
        for gy_lbl, gy in [("1", 8400.0), ("2", 16800.0)]:
            col_coords.append((gx, gy))
            add_element(
                f, storey, body_ctx,
                "IfcColumn", f"COL-{gx_lbl}{gy_lbl}", "COLUMN", None,
                make_box_rep(f, body_ctx, 400.0, 400.0, SOFFIT_Z),
                placement_matrix(gx, gy, 0.0, 0.0),
                "Pset_DCM_Column",
                {
                    "GridX": gx_lbl,
                    "GridY": gy_lbl,
                    "Width_mm": 400.0,
                    "Depth_mm": 400.0,
                    "Height_mm": SOFFIT_Z,
                },
            )

    # 6. Cold-Aisle Containment (CAC-BC, CAC-DE: 2 roof panels & 4 end doors each)
    for tag, r1, r2, y_cl, contains in [
        ("CAC-BC", "B", "C", 7200.0, "ROWS B / C"),
        ("CAC-DE", "D", "E", 12600.0, "ROWS D / E"),
    ]:
        w_start = ROW_START_X
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_start = CA_EAST_X
        e_end = min(row_extents[r1][3], row_extents[r2][3])
        for sec, (x0, x1) in [("W", (w_start, w_end)), ("E", (e_start, e_end))]:
            add_element(
                f, storey, body_ctx,
                "IfcCovering", f"{tag}-ROOF-{sec}", "USERDEFINED", "ContainmentRoof",
                make_box_rep(f, body_ctx, x1 - x0, 1400.0, 55.5),
                placement_matrix(0.5 * (x0 + x1), y_cl, 2000.0, 0.0),
                "Pset_DCM_Containment",
                {
                    "AisleTag": tag,
                    "Contains": contains,
                    "ComponentType": "Roof",
                    "RoofWidth_mm": 1400.0,
                    "RoofThickness_mm": 55.5,
                    "RoofUnderside_mm": 2000.0,
                },
            )
            # End doors placed flush outside roof span (zero overlap with roof or racks)
            for idx, dx in [(1, x0 - 30.0), (2, x1 + 30.0)]:
                add_element(
                    f, storey, body_ctx,
                    "IfcDoor", f"{tag}-DOOR-{sec}{idx}", "USERDEFINED", "ContainmentDoor",
                    make_box_rep(f, body_ctx, 60.0, 1200.0, 2055.5),
                    placement_matrix(dx, y_cl, 0.0, 0.0),
                    "Pset_DCM_Containment",
                    {
                        "AisleTag": tag,
                        "Contains": contains,
                        "ComponentType": "EndDoor",
                        "DoorThickness_mm": 60.0,
                        "DoorHeight_mm": 2055.5,
                    },
                )

    # 7. Sprinkler Heads (63 ceiling heads + 16 in-aisle heads per F-101)
    sprinkler_idx = 0
    for xi in range(9):
        sx = 1500.0 + xi * 3000.0
        for yi in range(7):
            sy = 1500.0 + yi * 3000.0
            # Relocate heads within column keep-out (750 mm half-width around column)
            for gx, gy in col_coords:
                if abs(sx - gx) < 750.0 and abs(sy - gy) < 750.0:
                    sx = gx - 900.0 if sx < gx else gx + 900.0
                    sy = gy - 900.0 if sy < gy else gy + 900.0
            sprinkler_idx += 1
            add_element(
                f, storey, body_ctx,
                "IfcFireSuppressionTerminal", f"SPR-CLG-{sprinkler_idx:02d}", "SPRINKLER", "CeilingSprinkler",
                make_cyl_rep(f, body_ctx, 25.0, 25.0),
                placement_matrix(sx, sy, DEFLECTOR_Z, 0.0),
                "Pset_DCM_Sprinkler",
                {
                    "HeadType": "Ceiling",
                    "DeflectorElevation_mm": DEFLECTOR_Z,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    in_aisle_idx = 0
    for tag, y_cl in [("CAC-BC", 7200.0), ("CAC-DE", 12600.0)]:
        # 4 heads in west section, 4 heads in east section (8 per aisle, 16 total)
        xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14400.0, 16500.0, 18600.0]
        for sx in xs:
            in_aisle_idx += 1
            add_element(
                f, storey, body_ctx,
                "IfcFireSuppressionTerminal", f"SPR-AISLE-{in_aisle_idx:02d}", "SPRINKLER", "InAisleSprinkler",
                make_cyl_rep(f, body_ctx, 25.0, 110.0),
                placement_matrix(sx, y_cl, 1890.0, 0.0),
                "Pset_DCM_Sprinkler",
                {
                    "HeadType": "InAisle",
                    "AisleTag": tag,
                    "DeflectorElevation_mm": 1890.0,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    # 8. Overhead Power Busway (BW-1: 128 W x 147 H, z_cl = 2700 mm)
    def add_rect_seg(ifc_class, predefined_type, obj_type, name, service, tag, zone,
                     x0, y0, x1, y1, z_cl, w, h):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx >= dy:
            length = dx
            bx, by = length, w
            cx, cy = 0.5 * (x0 + x1), y0
        else:
            length = dy
            bx, by = w, length
            cx, cy = x0, 0.5 * (y0 + y1)
        add_element(
            f, storey, body_ctx,
            ifc_class, name, predefined_type, obj_type,
            make_box_rep(f, body_ctx, bx, by, h),
            placement_matrix(cx, cy, z_cl - h / 2.0, 0.0),
            "Pset_DCM_MEP",
            {
                "Service": service,
                "PathwayTag": tag,
                "Zone": zone,
                "Elevation_mm": z_cl,
                "Width_mm": w,
                "Height_mm": h,
                "Length_mm": length,
                "Tier": "Overhead" if z_cl > 0 else "UnderFloor",
            },
        )

    bw_half = BW_W / 2.0
    # Entry stub
    add_rect_seg(
        "IfcCableSegment", "BUSBARSEGMENT", "Busway", "BW-ENTRY",
        "POWER", "BW-1", "OVERHEAD",
        ENTRY_X, ENTRY_Y, TRUNK_X - bw_half, ENTRY_Y, BW_Z, BW_W, BW_H,
    )
    # Main N-S trunk at x = TRUNK_X
    bw_y_min = 3000.0 - 400.0 - bw_half
    bw_y_max = 16800.0 - 400.0 + bw_half
    add_rect_seg(
        "IfcCableSegment", "BUSBARSEGMENT", "Busway", "BW-TRUNK",
        "POWER", "BW-1", "OVERHEAD",
        TRUNK_X, bw_y_min, TRUNK_X, bw_y_max, BW_Z, BW_W, BW_H,
    )
    # Row branches (offset -400 mm from row CL to clear all 400x400 columns)
    for row_name, y_cl, _, _ in ROWS:
        east_end = row_extents[row_name][3]
        add_rect_seg(
            "IfcCableSegment", "BUSBARSEGMENT", "Busway", f"BW-ROW-{row_name}",
            "POWER", "BW-1", "OVERHEAD",
            TRUNK_X + bw_half, y_cl - 400.0, east_end - 600.0, y_cl - 400.0, BW_Z, BW_W, BW_H,
        )

    # 9. Under-Floor Telecom Cable Tray (CT-1: 683 W x 127 H, z_cl = -250 mm)
    ct_half = CT_W / 2.0
    add_rect_seg(
        "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", "CT-ENTRY",
        "TELECOM", "CT-1", "PLENUM",
        ENTRY_X, ENTRY_Y, TRUNK_X - ct_half, ENTRY_Y, CT_Z, CT_W, CT_H,
    )
    add_rect_seg(
        "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", "CT-TRUNK",
        "TELECOM", "CT-1", "PLENUM",
        TRUNK_X, 3000.0 - ct_half, TRUNK_X, 16800.0 + ct_half, CT_Z, CT_W, CT_H,
    )
    for row_name, y_cl, _, _ in ROWS:
        east_end = row_extents[row_name][3]
        add_rect_seg(
            "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", f"CT-ROW-{row_name}",
            "TELECOM", "CT-1", "PLENUM",
            TRUNK_X + ct_half, y_cl, east_end - 600.0, y_cl, CT_Z, CT_W, CT_H,
        )

    # 10. Under-Floor Chilled Water Pipe (CHW-1: 168.3 mm insulated OD, z_cl = -600 mm)
    def add_pipe_seg(name, x0, y0, x1, y1, z_cl):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dx >= dy:
            axis = "X"
            length = dx
            sx, sy = min(x0, x1), y0
        else:
            axis = "Y"
            length = dy
            sx, sy = x0, min(y0, y1)
        add_element(
            f, storey, body_ctx,
            "IfcPipeSegment", name, "RIGIDSEGMENT", "ChilledWaterPipe",
            make_cyl_rep(f, body_ctx, CHW_R, length),
            pipe_matrix(sx, sy, z_cl, axis),
            "Pset_DCM_MEP",
            {
                "Service": "CHILLED_WATER",
                "PathwayTag": "CHW-1",
                "Zone": "PLENUM",
                "Elevation_mm": z_cl,
                "OuterDiameter_mm": CHW_BARE_OD,
                "InsulatedOD_mm": CHW_INS_OD,
                "Length_mm": length,
                "Tier": "UnderFloor",
            },
        )

    add_pipe_seg("CHW-ENTRY", ENTRY_X, ENTRY_Y, TRUNK_X - CHW_R, ENTRY_Y, CHW_Z)
    add_pipe_seg("CHW-TRUNK", TRUNK_X, 450.0 - CHW_R, TRUNK_X, 16800.0 + CHW_R, CHW_Z)
    add_pipe_seg("CHW-PERIM", TRUNK_X + CHW_R, 450.0, 25800.0, 450.0, CHW_Z)
    for row_name, y_cl, _, _ in ROWS:
        east_end = row_extents[row_name][3]
        add_pipe_seg(f"CHW-ROW-{row_name}", TRUNK_X + CHW_R, y_cl, east_end - 600.0, y_cl, CHW_Z)

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    f.write(OUT_PATH)


if __name__ == "__main__":
    build_model()
