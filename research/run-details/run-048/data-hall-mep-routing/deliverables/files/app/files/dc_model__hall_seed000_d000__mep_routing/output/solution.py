"""Coordinated IFC4 model for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Builds the architectural/equipment background and clash-free MEP routing
(CT-1 cable tray, BW-1 busway, CHW-1 chilled water) from the 7-sheet drawing set.
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

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

# Hall dimensions (mm)
HALL_W = 27000.0
HALL_D = 21000.0
FLOOR_THK = 35.0
SOFFIT_Z = 3600.0
SLAB_TOP_Z = -900.0
DEFLECTOR_Z = 3574.6
IN_AISLE_DEFLECTOR_Z = 1890.0

# Structural columns: 600 x 600 mm, z = 0..3600
COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Cabinet rows (A-101, A-601)
# Sequence tokens: (count, type) where type in {"C1", "N1", "CU", "SP", "CA", "OMIT600"}
CA_EAST_X = 11400.0
ROW_START_X = 1800.0
RACK_DEPTH = 1200.0
RACK_HEIGHT = 2000.0

ROWS = [
    ("A", 3000.0, "SOUTH", [
        (4, "C1"), (1, "CU"), (3, "C1"), (1, "N1"), (3, "C1"), (1, "CU"),
        (1, "CA"), (6, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
    ]),
    ("B", 6000.0, "NORTH", [
        (4, "C1"), (1, "CU"), (5, "C1"), (2, "N1"), (1, "CU"),
        (1, "CA"), (7, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
    ]),
    ("C", 8400.0, "SOUTH", [
        (3, "C1"), (1, "CU"), (6, "C1"), (2, "OMIT600"), (1, "CU"),
        (1, "CA"), (1, "N1"), (4, "C1"), (1, "CU"), (1, "SP"), (1, "C1"), (2, "OMIT600"), (3, "C1"),
    ]),
    ("D", 11400.0, "NORTH", [
        (4, "C1"), (1, "CU"), (3, "C1"), (2, "N1"), (2, "C1"), (1, "CU"),
        (1, "CA"), (7, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
    ]),
    ("E", 13800.0, "SOUTH", [
        (4, "C1"), (1, "CU"), (5, "C1"), (1, "N1"), (1, "C1"), (1, "CU"),
        (1, "CA"), (6, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
    ]),
    ("F", 16800.0, "NORTH", [
        (4, "C1"), (1, "CU"), (5, "C1"), (2, "OMIT600"), (1, "CU"),
        (1, "CA"), (2, "N1"), (5, "C1"), (1, "SP"), (1, "OMIT600"), (1, "CU"), (4, "C1"),
    ]),
]

# Perimeter CRAHs (A-601, M-101): 1200 W x 900 D x 2000 H, faces NORTH
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, E-101): 762 W x 813 D x 1959 H, front flush with served row front
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - 813.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - 813.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - 813.0, "NORTH"),
]


def make_placement_matrix(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    """4x4 placement matrix with translations in METRES (for edit_object_placement)."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
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
            cx, cy, z0, sx, sy, sz, yaw_rad=0.0, pset_name=None, pset_props=None):
    """Create an extruded rectangular solid centred at (cx, cy) with base at z0 (mm)."""
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)

    pos2d = model.create_entity(
        "IfcAxis2Placement2D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0)),
    )
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        XDim=float(sx),
        YDim=float(sy),
    )
    pos3d = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=extrude_dir,
        Depth=float(sz),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    el.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[rep]
    )
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=el, matrix=make_placement_matrix(cx, cy, z0, yaw_rad)
    )
    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=ps, properties=pset_props)
    return el


def add_cylinder_z(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                   cx, cy, z0, radius, height, pset_name=None, pset_props=None):
    """Create a vertical cylinder centred at (cx, cy) from z0 to z0+height (mm)."""
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type:
        el.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)

    pos2d = model.create_entity(
        "IfcAxis2Placement2D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0)),
    )
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        Radius=float(radius),
    )
    pos3d = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=extrude_dir,
        Depth=float(height),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    el.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[rep]
    )
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=el, matrix=make_placement_matrix(cx, cy, z0, 0.0)
    )
    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=ps, properties=pset_props)
    return el


def add_segment(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                x0, y0, x1, y1, z_center, width, height, service, tier):
    """Add an axis-aligned horizontal MEP segment from (x0,y0) to (x1,y1) at z_center."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    if dx >= dy:
        sx, sy = dx, width
    else:
        sx, sy = width, dy
    z0 = z_center - 0.5 * height
    return add_box(
        model, body_ctx, storey,
        ifc_class=ifc_class, name=name, predefined_type=predefined_type,
        object_type=object_type,
        cx=cx, cy=cy, z0=z0, sx=sx, sy=sy, sz=height, yaw_rad=0.0,
        pset_name="Pset_DCM_MEP",
        pset_props={
            "Service": service,
            "Section": object_type,
            "Tier": tier,
            "Elevation_mm": float(z_center),
            "Length_mm": float(max(dx, dy)),
        },
    )


def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center")
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.spatial.assign_container(model, products=[], relating_structure=storey)
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor Panel (z = -35..0)
    add_box(
        model, body_ctx, storey,
        "IfcSlab", "AccessFloor", "FLOOR", "AccessFloor",
        HALL_W / 2.0, HALL_D / 2.0, -FLOOR_THK, HALL_W, HALL_D, FLOOR_THK,
        pset_name="Pset_DCM_Floor", pset_props={"Thickness_mm": FLOOR_THK, "Plenum_mm": 865.0},
    )

    # 2. Structural Columns (6 columns, 600 x 600, z = 0..3600)
    col_idx = 1
    for gx, col_letter in zip(COL_XS, ["A", "B", "C"]):
        for gy, grid_num in zip(COL_YS, ["1", "2"]):
            add_box(
                model, body_ctx, storey,
                "IfcColumn", f"COL-{col_letter}{grid_num}", "COLUMN", "Column",
                gx, gy, 0.0, COL_SIZE, COL_SIZE, SOFFIT_Z,
                pset_name="Pset_DCM_Structure", pset_props={"Grid": f"{col_letter}{grid_num}"},
            )
            col_idx += 1

    # 3. Cabinet Rows & In-Row CRAHs (128 racks + 18 in-row CRAHs)
    row_extents = {}
    for row_id, yc, facing, seq in ROWS:
        yaw = 0.0 if facing == "NORTH" else math.pi
        x = ROW_START_X
        rack_num = 1
        crah_num = 1
        west_end = ROW_START_X
        for count, tok in seq:
            if tok == "CA":
                west_end = x
                x = CA_EAST_X
                continue
            for _ in range(count):
                if tok == "C1":
                    w = 600.0
                    add_box(
                        model, body_ctx, storey,
                        "IfcFurniture", f"RACK-{row_id}{rack_num:02d}", "USERDEFINED", "Rack",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, yaw_rad=yaw,
                        pset_name="Pset_DCM_Rack",
                        pset_props={"Row": row_id, "Type": "C1", "RU": 42, "Power_kW": 8.0, "Load_kg": 1363.0, "Facing": facing},
                    )
                    rack_num += 1
                    x += w
                elif tok == "N1":
                    w = 800.0
                    add_box(
                        model, body_ctx, storey,
                        "IfcFurniture", f"RACK-{row_id}{rack_num:02d}", "USERDEFINED", "Rack",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, yaw_rad=yaw,
                        pset_name="Pset_DCM_Rack",
                        pset_props={"Row": row_id, "Type": "N1", "RU": 42, "Power_kW": 8.0, "Load_kg": 1363.0, "Facing": facing},
                    )
                    rack_num += 1
                    x += w
                elif tok == "CU":
                    w = 600.0
                    add_box(
                        model, body_ctx, storey,
                        "IfcUnitaryEquipment", f"CRAH-{row_id}{crah_num:02d}", "AIRHANDLER", "CRAH",
                        x + w / 2.0, yc, 0.0, w, RACK_DEPTH, RACK_HEIGHT, yaw_rad=yaw,
                        pset_name="Pset_DCM_CRAH",
                        pset_props={"Placement": f"IN_ROW_{row_id}", "Capacity_kW": 50.0, "Airflow_m3h": 9000.0, "Facing": facing},
                    )
                    crah_num += 1
                    x += w
                elif tok in ("SP", "OMIT600"):
                    x += 600.0
        row_extents[row_id] = (ROW_START_X, west_end, CA_EAST_X, x)

    # 4. Perimeter CRAHs (4 units)
    for tag, x0, y0 in PERIM_CRAHS:
        add_box(
            model, body_ctx, storey,
            "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
            x0 + 600.0, y0 + 450.0, 0.0, 1200.0, 900.0, 2000.0, yaw_rad=0.0,
            pset_name="Pset_DCM_CRAH",
            pset_props={"Placement": "PERIMETER", "Capacity_kW": 100.0, "Airflow_m3h": 20000.0, "Facing": "NORTH"},
        )

    # 5. PDUs (6 units)
    for tag, serves_row, x0, y0, facing in PDUS:
        yaw = 0.0 if facing == "NORTH" else math.pi
        add_box(
            model, body_ctx, storey,
            "IfcElectricDistributionBoard", tag, "DISTRIBUTIONBOARD", "PDU",
            x0 + 762.0 / 2.0, y0 + 813.0 / 2.0, 0.0, 762.0, 813.0, 1959.0, yaw_rad=yaw,
            pset_name="Pset_DCM_PDU",
            pset_props={"ServesRow": serves_row, "Rating_kVA": 225.0, "Facing": facing},
        )

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE)
    for cac_name, y_mid, r1, r2 in [("CAC-BC", 7200.0, "B", "C"), ("CAC-DE", 12600.0, "D", "E")]:
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_end = min(row_extents[r1][3], row_extents[r2][3])
        for seg_idx, (xa, xb) in enumerate([(ROW_START_X, w_end), (CA_EAST_X, e_end)], start=1):
            # Roof panel: z = 2000..2055.5, width = 1400 mm
            add_box(
                model, body_ctx, storey,
                "IfcCovering", f"{cac_name}-ROOF-{seg_idx}", "CEILING", "ContainmentRoof",
                0.5 * (xa + xb), y_mid, 2000.0, xb - xa, 1400.0, 55.5,
            )
            # Two end doors: 60 mm thick x 1200 mm wide x 2000 mm high (under roof, clear of roof)
            add_box(
                model, body_ctx, storey,
                "IfcDoor", f"{cac_name}-DOOR-{seg_idx}W", "DOOR", "ContainmentDoor",
                xa + 30.0, y_mid, 0.0, 60.0, 1200.0, 2000.0,
            )
            add_box(
                model, body_ctx, storey,
                "IfcDoor", f"{cac_name}-DOOR-{seg_idx}E", "DOOR", "ContainmentDoor",
                xb - 30.0, y_mid, 0.0, 60.0, 1200.0, 2000.0,
            )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79 heads)
    sp_idx = 1
    for ix in range(9):
        sx = 1500.0 + ix * 3000.0
        for iy in range(7):
            sy = 1500.0 + iy * 3000.0
            # Relocate clear of columns (1500 keep-out around column centre)
            for cx_col in COL_XS:
                for cy_col in COL_YS:
                    if abs(sx - cx_col) < 750.0 and abs(sy - cy_col) < 750.0:
                        sy = cy_col - 900.0
            add_cylinder_z(
                model, body_ctx, storey,
                "IfcFireSuppressionTerminal", f"SP-CLG-{sp_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx, sy, DEFLECTOR_Z, 25.0, SOFFIT_Z - DEFLECTOR_Z,
                pset_name="Pset_DCM_Sprinkler", pset_props={"Zone": "CEILING", "Deflector_mm": DEFLECTOR_Z},
            )
            sp_idx += 1

    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 1
    for y_aisle in [7200.0, 12600.0]:
        for sx in in_aisle_xs:
            add_cylinder_z(
                model, body_ctx, storey,
                "IfcFireSuppressionTerminal", f"SP-AISLE-{ia_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx, y_aisle, IN_AISLE_DEFLECTOR_Z, 25.0, 2000.0 - IN_AISLE_DEFLECTOR_Z,
                pset_name="Pset_DCM_Sprinkler", pset_props={"Zone": "IN_AISLE", "Deflector_mm": IN_AISLE_DEFLECTOR_Z},
            )
            ia_idx += 1

    # 8. MEP Routing (butt-jointed segments: 0 mm overlap, 0 mm gap)
    # 3 shared row headers at Y = 4500 (A+B), Y = 9900 (C+D), Y = 15300 (E+F)
    # Entry at (0, 9900).
    #
    # BW-1 (Power Busway, 128 W x 147 H): OVERHEAD at z_center = 2700 (z = 2626.5..2773.5)
    bw_w, bw_h, bw_z = 128.0, 147.0, 2700.0
    bw_tx = 900.0
    # Entry stub: X = 0 .. bw_tx - bw_w/2 at Y = 9900
    add_segment(model, body_ctx, storey, "IfcCableSegment", "BW_ENTRY", "BUSBARSEGMENT", "BW-1",
                0.0, 9900.0, bw_tx - bw_w / 2.0, 9900.0, bw_z, bw_w, bw_h, "BW", "OVERHEAD")
    # N-S trunk: Y = 4500 - bw_w/2 .. 15300 + bw_w/2 at X = bw_tx
    add_segment(model, body_ctx, storey, "IfcCableSegment", "BW_TRUNK", "BUSBARSEGMENT", "BW-1",
                bw_tx, 4500.0 - bw_w / 2.0, bw_tx, 15300.0 + bw_w / 2.0, bw_z, bw_w, bw_h, "BW", "OVERHEAD")
    # 3 E-W row headers: X = bw_tx + bw_w/2 .. hx_end
    hdr_specs = [(4500.0, 18600.0), (9900.0, 18600.0), (15300.0, 19800.0)]
    for idx, (hy, hx_end) in enumerate(hdr_specs, start=1):
        add_segment(model, body_ctx, storey, "IfcCableSegment", f"BW_HDR_{idx}", "BUSBARSEGMENT", "BW-1",
                    bw_tx + bw_w / 2.0, hy, hx_end, hy, bw_z, bw_w, bw_h, "BW", "OVERHEAD")

    # CT-1 (Telecom Cable Tray, 683 W x 127 H): UNDER-FLOOR PLENUM at z_center = -250 (z = -313.5..-186.5)
    ct_w, ct_h, ct_z = 683.0, 127.0, -250.0
    ct_tx = 900.0
    add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", "CT_ENTRY", "CABLELADDERSEGMENT", "CT-1",
                0.0, 9900.0, ct_tx - ct_w / 2.0, 9900.0, ct_z, ct_w, ct_h, "CT", "PLENUM")
    add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", "CT_TRUNK", "CABLELADDERSEGMENT", "CT-1",
                ct_tx, 4500.0 - ct_w / 2.0, ct_tx, 15300.0 + ct_w / 2.0, ct_z, ct_w, ct_h, "CT", "PLENUM")
    for idx, (hy, hx_end) in enumerate(hdr_specs, start=1):
        add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", f"CT_HDR_{idx}", "CABLELADDERSEGMENT", "CT-1",
                    ct_tx + ct_w / 2.0, hy, hx_end, hy, ct_z, ct_w, ct_h, "CT", "PLENUM")

    # CHW-1 (Chilled Water Pipe, insulated OD 168.3 mm): UNDER-FLOOR PLENUM at z_center = -700 (z = -784.15..-615.85)
    chw_d, chw_z = 168.3, -700.0
    chw_tx = 900.0
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW_ENTRY", "RIGIDSEGMENT", "CHW-1",
                0.0, 9900.0, chw_tx - chw_d / 2.0, 9900.0, chw_z, chw_d, chw_d, "CHW", "PLENUM")
    # N-S trunk extends south to Y = 2000 to serve perimeter CRAHs
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW_TRUNK", "RIGIDSEGMENT", "CHW-1",
                chw_tx, 2000.0 - chw_d / 2.0, chw_tx, 15300.0 + chw_d / 2.0, chw_z, chw_d, chw_d, "CHW", "PLENUM")
    # Perimeter CRAH header at Y = 2000: X = chw_tx + chw_d/2 .. 25200
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW_PERIM", "RIGIDSEGMENT", "CHW-1",
                chw_tx + chw_d / 2.0, 2000.0, 25200.0, 2000.0, chw_z, chw_d, chw_d, "CHW", "PLENUM")
    # 3 E-W row headers: X = chw_tx + chw_d/2 .. hx_end
    for idx, (hy, hx_end) in enumerate(hdr_specs, start=1):
        add_segment(model, body_ctx, storey, "IfcPipeSegment", f"CHW_HDR_{idx}", "RIGIDSEGMENT", "CHW-1",
                    chw_tx + chw_d / 2.0, hy, hx_end, hy, chw_z, chw_d, chw_d, "CHW", "PLENUM")

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)


if __name__ == "__main__":
    build_model()
