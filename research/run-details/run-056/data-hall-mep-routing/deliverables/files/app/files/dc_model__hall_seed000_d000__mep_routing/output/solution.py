"""Coordinated IFC4 model generator for Data Hall 1 (hall_seed000_d000).

Builds the hall fit-out (racks, CRAHs, PDUs, columns, access floor, cold-aisle
containment, sprinklers) and clash-free MEP routes (telecom cable tray, power
busway, chilled-water piping) from the seven-sheet drawing set.
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
import ifcopenshell.guid

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
PARAMS_FILE = "/tmp/scratch/params.json"

# Default routing parameters (can be overridden via PARAMS_FILE for optimization)
DEFAULT_PARAMS = {
    "ct_trunk_x": 5000.0,
    "bw_trunk_x": 5000.0,
    "chw_trunk_x": 3710.0,
    "ct_hdr_x_end": 16652.0,
    "bw_hdr_x_end": 16643.0,
    "chw_hdr_x_end": 15401.0,
    "chw_south_y": 2140.0,
    "chw_south_x_end": 23676.0,
}


def load_params():
    p = dict(DEFAULT_PARAMS)
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE, "r") as f:
            p.update(json.load(f))
    return p


def make_matrix(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    """4x4 placement matrix with translations in metres, rotation about Z."""
    c, s = math.cos(yaw_rad), math.sin(yaw_rad)
    return np.array([
        [c, -s, 0.0, cx_mm / 1000.0],
        [s,  c, 0.0, cy_mm / 1000.0],
        [0.0, 0.0, 1.0, z0_mm / 1000.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=float)


def add_box(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
            cx, cy, z0, sx, sy, sz, yaw_rad=0.0, pset_name=None, pset_props=None):
    """Create an extruded rectangular solid element centered at (cx, cy), bottom at z0."""
    elem = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name
    )
    if predefined_type and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(sx),
        YDim=float(sy),
    )
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
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
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=elem, matrix=make_matrix(cx, cy, z0, yaw_rad), is_si=True
    )
    ifcopenshell.api.spatial.assign_container(model, products=[elem], relating_structure=storey)

    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=pset_props)
    return elem


def add_cylinder_z(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                   cx, cy, z0, radius, height, pset_name=None, pset_props=None):
    """Create a vertical circular cylinder (e.g. sprinkler head)."""
    elem = ifcopenshell.api.root.create_entity(model, ifc_class=ifc_class, name=name)
    if predefined_type and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
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
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=elem, matrix=make_matrix(cx, cy, z0, 0.0), is_si=True
    )
    ifcopenshell.api.spatial.assign_container(model, products=[elem], relating_structure=storey)
    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=pset_props)
    return elem


def add_segment(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
                x0, y0, x1, y1, z0, width, height, pset_name=None, pset_props=None):
    """Create an axis-aligned horizontal route segment from (x0, y0) to (x1, y1), bottom at z0."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    if dx >= dy:
        sx, sy = dx, width
    else:
        sx, sy = width, dy
    if sx < 1.0 or sy < 1.0:
        return None
    return add_box(
        model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
        cx, cy, z0, sx, sy, height, 0.0, pset_name, pset_props
    )


def build_model():
    params = load_params()

    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Data Hall Building")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.spatial.assign_container(model, products=[], relating_structure=storey)
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor (35 mm panel, Z = [-35, 0], 27000 x 21000)
    add_box(
        model, body_ctx, storey, "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        13500.0, 10500.0, -35.0, 27000.0, 21000.0, 35.0
    )

    # 2. Structural Columns (6 total, 600 x 600, Z = [0, 3600])
    col_xs = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
    col_ys = [("1", 8400.0), ("2", 16800.0)]
    for cx_lbl, cx in col_xs:
        for cy_lbl, cy in col_ys:
            add_box(
                model, body_ctx, storey, "IfcColumn", f"COL-{cx_lbl}{cy_lbl}",
                "COLUMN", "StructuralColumn", cx, cy, 0.0, 600.0, 600.0, 3600.0
            )

    # 3. Cabinet Rows (128 racks) & In-Row CRAHs (18 units)
    # Bay sequences: list of (west_tokens, east_tokens)
    rows_spec = [
        ("A", 3000.0, "SOUTH",
         [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
         [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("B", 6000.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
         [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("C", 8400.0, "SOUTH",
         [("C1", 3), ("CU", 1), ("C1", 6), ("OM", 2), ("CU", 1)],
         [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OM", 2), ("C1", 3)]),
        ("D", 11400.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
         [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("E", 13800.0, "SOUTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
         [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("F", 16800.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("OM", 2), ("CU", 1)],
         [("N1", 2), ("C1", 5), ("SP", 1), ("OM", 1), ("CU", 1), ("C1", 4)]),
    ]
    bay_widths = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "OM": 600.0}

    for row_id, yc, facing, west_seq, east_seq in rows_spec:
        yaw = 0.0 if facing == "NORTH" else math.pi
        rack_idx = 0
        crah_idx = 0
        for start_x, seq in [(1800.0, west_seq), (11400.0, east_seq)]:
            x = start_x
            for tok, cnt in seq:
                w = bay_widths[tok]
                for _ in range(cnt):
                    cx = x + 0.5 * w
                    if tok in ("C1", "N1"):
                        rack_idx += 1
                        add_box(
                            model, body_ctx, storey, "IfcFurniture",
                            f"RACK-{row_id}{rack_idx:02d}", "USERDEFINED", "Rack",
                            cx, yc, 0.0, w, 1200.0, 2000.0, yaw,
                            "Pset_DCM_Rack",
                            {"Row": row_id, "Type": tok, "Width_mm": w, "Depth_mm": 1200.0,
                             "Height_mm": 2000.0, "RU": 42, "Facing": facing, "Power_kW": 8.0, "Load_kg": 1363.0}
                        )
                    elif tok == "CU":
                        crah_idx += 1
                        add_box(
                            model, body_ctx, storey, "IfcUnitaryEquipment",
                            f"CRAH-{row_id}{crah_idx:02d}", "AIRHANDLER", "CRAH",
                            cx, yc, 0.0, 600.0, 1200.0, 2000.0, yaw,
                            "Pset_DCM_CRAH",
                            {"Placement": f"ROW_{row_id}", "Capacity_kW": 50.0,
                             "Airflow_m3h": 9000.0, "Facing": facing, "Service": "CHW_DN50"}
                        )
                    x += w

    # 4. Perimeter CRAHs (4 units, 1200 x 900 x 2000, NORTH)
    perim_crahs = [
        ("CRAH-01", 600.0),
        ("CRAH-02", 9000.0),
        ("CRAH-03", 16800.0),
        ("CRAH-04", 25200.0),
    ]
    for name, x0 in perim_crahs:
        add_box(
            model, body_ctx, storey, "IfcUnitaryEquipment", name, "AIRHANDLER", "CRAH",
            x0 + 600.0, 450.0, 0.0, 1200.0, 900.0, 2000.0, 0.0,
            "Pset_DCM_CRAH",
            {"Placement": "PERIMETER", "Capacity_kW": 100.0,
             "Airflow_m3h": 20000.0, "Facing": "NORTH", "Service": "CHW_DN100"}
        )

    # 5. PDUs (6 units, 762 x 813 x 1959)
    pdus = [
        ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
        ("PDU-02", "B", 21600.0, 6600.0 - 813.0, "NORTH"),
        ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
        ("PDU-04", "D", 21600.0, 12000.0 - 813.0, "NORTH"),
        ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
        ("PDU-06", "F", 21600.0, 17400.0 - 813.0, "NORTH"),
    ]
    for name, row_id, x0, y0, facing in pdus:
        yaw = 0.0 if facing == "NORTH" else math.pi
        add_box(
            model, body_ctx, storey, "IfcElectricDistributionBoard", name,
            "DISTRIBUTIONBOARD", "PDU",
            x0 + 381.0, y0 + 406.5, 0.0, 762.0, 813.0, 1959.0, yaw,
            "Pset_DCM_PDU",
            {"ServesRow": row_id, "Rating_kVA": 225.0, "Facing": facing, "WorkingSpace_mm": 900.0}
        )

    # 6. Cold-Aisle Containment (CAC-BC at Y=7200, CAC-DE at Y=12600)
    # West panels: X=[1800, 9600], East panels: X=[11400, 19400] (clear of columns & cross aisle)
    for tag, yc in [("CAC-BC", 7200.0), ("CAC-DE", 12600.0)]:
        for side, x0, x1 in [("W", 1800.0, 9600.0), ("E", 11400.0, 19400.0)]:
            add_box(
                model, body_ctx, storey, "IfcCovering", f"{tag}-ROOF-{side}",
                "CEILING", "ContainmentRoof",
                0.5 * (x0 + x1), yc, 2000.0, x1 - x0, 1400.0, 55.5
            )
            # End doors (60 mm thick x 1200 wide x 2055.5 high, flush outside panel ends)
            add_box(
                model, body_ctx, storey, "IfcDoor", f"{tag}-DOOR-{side}W",
                "DOOR", "ContainmentDoor",
                x0 - 30.0, yc, 0.0, 60.0, 1200.0, 2055.5
            )
            add_box(
                model, body_ctx, storey, "IfcDoor", f"{tag}-DOOR-{side}E",
                "DOOR", "ContainmentDoor",
                x1 + 30.0, yc, 0.0, 60.0, 1200.0, 2055.5
            )

    # 7. Sprinklers (63 ceiling + 16 in-aisle = 79 heads)
    spr_idx = 0
    col_pts = [(8400.0, 8400.0), (16800.0, 8400.0), (25200.0, 8400.0),
               (8400.0, 16800.0), (16800.0, 16800.0), (25200.0, 16800.0)]
    for ix in range(9):
        for iy in range(7):
            spr_idx += 1
            sx = 1500.0 + 3000.0 * ix
            sy = 1500.0 + 3000.0 * iy
            # Relocate clear of any 600x600 column
            for cx, cy in col_pts:
                if abs(sx - cx) < 400.0 and abs(sy - cy) < 400.0:
                    sy = cy - 600.0
            add_cylinder_z(
                model, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPR-C{spr_idx:02d}",
                "SPRINKLER", "SprinklerHead", sx, sy, 3574.6, 25.0, 25.4,
                "Pset_DCM_Sprinkler",
                {"Location": "CEILING", "DeflectorElevation_mm": 3574.6, "Standoff_mm": 460.0}
            )
    aisle_idx = 0
    for yc in (7200.0, 12600.0):
        for sx in (3000.0, 5400.0, 7800.0, 9000.0, 12600.0, 15000.0, 17400.0, 18600.0):
            aisle_idx += 1
            add_cylinder_z(
                model, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPR-A{aisle_idx:02d}",
                "SPRINKLER", "SprinklerHead", sx, yc, 1890.0, 25.0, 110.0,
                "Pset_DCM_Sprinkler",
                {"Location": "IN_AISLE", "DeflectorElevation_mm": 1890.0, "Standoff_mm": 460.0}
            )

    # 8. MEP Routes (3 services, all butt-joined with 0 mm overlap)
    hdr_ys = [4500.0, 9900.0, 15300.0]

    # 8a. Telecom Cable Tray (CT-1: 683 W x 127 H, Overhead Z = [2610, 2737])
    ct_w, ct_h, ct_z0 = 683.0, 127.0, 2610.0
    ct_tx = params["ct_trunk_x"]
    ct_xe = params["ct_hdr_x_end"]
    ct_ps = {"Service": "TELECOM", "Tag": "CT-1", "Width_mm": ct_w, "Height_mm": ct_h, "Zone": "OVERHEAD"}
    add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", "CT-ENTRY",
                "CABLETRAYSEGMENT", "CT", 0.0, 9900.0, ct_tx - 0.5 * ct_w, 9900.0, ct_z0, ct_w, ct_h, "Pset_DCM_Pathway", ct_ps)
    add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", "CT-TRUNK",
                "CABLETRAYSEGMENT", "CT", ct_tx, hdr_ys[0] - 0.5 * ct_w, ct_tx, hdr_ys[-1] + 0.5 * ct_w, ct_z0, ct_w, ct_h, "Pset_DCM_Pathway", ct_ps)
    for i, hy in enumerate(hdr_ys, 1):
        add_segment(model, body_ctx, storey, "IfcCableCarrierSegment", f"CT-HDR-{i}",
                    "CABLETRAYSEGMENT", "CT", ct_tx + 0.5 * ct_w, hy, ct_xe, hy, ct_z0, ct_w, ct_h, "Pset_DCM_Pathway", ct_ps)

    # 8b. Power Busway (BW-1: 128 W x 147 H, Under-Floor Z = [-250, -103])
    bw_w, bw_h, bw_z0 = 128.0, 147.0, -250.0
    bw_tx = params["bw_trunk_x"]
    bw_xe = params["bw_hdr_x_end"]
    bw_ps = {"Service": "POWER", "Tag": "BW-1", "Width_mm": bw_w, "Height_mm": bw_h, "Zone": "UNDERFLOOR"}
    add_segment(model, body_ctx, storey, "IfcCableSegment", "BW-ENTRY",
                "BUSBARSEGMENT", "BW", 0.0, 9900.0, bw_tx - 0.5 * bw_w, 9900.0, bw_z0, bw_w, bw_h, "Pset_DCM_Pathway", bw_ps)
    add_segment(model, body_ctx, storey, "IfcCableSegment", "BW-TRUNK",
                "BUSBARSEGMENT", "BW", bw_tx, hdr_ys[0] - 0.5 * bw_w, bw_tx, hdr_ys[-1] + 0.5 * bw_w, bw_z0, bw_w, bw_h, "Pset_DCM_Pathway", bw_ps)
    for i, hy in enumerate(hdr_ys, 1):
        add_segment(model, body_ctx, storey, "IfcCableSegment", f"BW-HDR-{i}",
                    "BUSBARSEGMENT", "BW", bw_tx + 0.5 * bw_w, hy, bw_xe, hy, bw_z0, bw_w, bw_h, "Pset_DCM_Pathway", bw_ps)

    # 8c. Chilled Water Pipe (CHW-1: OD 168.3 mm incl. 25.4 mm insulation, Overhead Z = [2920, 3088.3])
    chw_od, chw_z0 = 168.3, 2920.0
    chw_tx = params["chw_trunk_x"]
    chw_xe = params["chw_hdr_x_end"]
    chw_sy = params["chw_south_y"]
    chw_sxe = params["chw_south_x_end"]
    chw_ps = {"Service": "CHW", "Tag": "CHW-1", "BareOD_mm": 114.3, "InsulatedOD_mm": chw_od, "Insulation_mm": 25.4, "Zone": "OVERHEAD"}
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW-ENTRY",
                "RIGIDSEGMENT", "CHW", 0.0, 9900.0, chw_tx - 0.5 * chw_od, 9900.0, chw_z0, chw_od, chw_od, "Pset_DCM_Pathway", chw_ps)
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW-TRUNK",
                "RIGIDSEGMENT", "CHW", chw_tx, chw_sy - 0.5 * chw_od, chw_tx, hdr_ys[-1] + 0.5 * chw_od, chw_z0, chw_od, chw_od, "Pset_DCM_Pathway", chw_ps)
    for i, hy in enumerate(hdr_ys, 1):
        add_segment(model, body_ctx, storey, "IfcPipeSegment", f"CHW-HDR-{i}",
                    "RIGIDSEGMENT", "CHW", chw_tx + 0.5 * chw_od, hy, chw_xe, hy, chw_z0, chw_od, chw_od, "Pset_DCM_Pathway", chw_ps)
    add_segment(model, body_ctx, storey, "IfcPipeSegment", "CHW-PERIM",
                "RIGIDSEGMENT", "CHW", chw_tx + 0.5 * chw_od, chw_sy, chw_sxe, chw_sy, chw_z0, chw_od, chw_od, "Pset_DCM_Pathway", chw_ps)

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)


if __name__ == "__main__":
    build_model()
