"""Meridian Data Center Phase 1 — Data Hall 1 (hall_seed000_d000)
Coordinated IFC4 model with overhead & under-floor MEP routing.
"""
import json
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.pset

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
PARAMS_FILE = "/tmp/scratch/params.json"

DEFAULT_PARAMS = {
    "trunk_x": 1637.64,
    "y_ab": 5200.0,
    "y_cd": 9900.0,
    "y_ef": 14574.7,
    "chw_y_ab": 2841.73,
    "branch_x_end": 16539.8,
    "chw_south_x_end": 23858.1,
}

def load_params():
    p = dict(DEFAULT_PARAMS)
    if os.path.exists(PARAMS_FILE):
        with open(PARAMS_FILE, "r", encoding="utf-8") as fh:
            p.update(json.load(fh))
    return p


def make_matrix(x_mm, y_mm, z_mm, rot_deg=0.0):
    """4x4 placement matrix with translations in METRES (ifcopenshell SI)."""
    rad = np.radians(rot_deg)
    c, s = float(np.cos(rad)), float(np.sin(rad))
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def add_box(f, body, storey, ifc_class, name, x0, y0, z0, x1, y1, z1,
            predefined=None, obj_type=None, rot_deg=0.0, pset_name=None, pset_props=None):
    """Create an extruded rectangular solid centred in XY at ((x0+x1)/2, (y0+y1)/2), z from z0 to z1."""
    dx = float(x1 - x0)
    dy = float(y1 - y0)
    dz = float(z1 - z0)
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)

    kwargs = {"ifc_class": ifc_class, "name": name}
    if predefined is not None:
        kwargs["predefined_type"] = predefined
    elem = ifcopenshell.api.root.create_entity(f, **kwargs)
    if obj_type is not None:
        elem.ObjectType = obj_type

    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[elem])

    # 2D rectangle profile centred at (0, 0) in mm
    profile = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=dx, YDim=dy)
    direction = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, ExtrudedDirection=direction, Depth=dz)
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(f, product=elem, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(f, product=elem, matrix=make_matrix(cx, cy, z0, rot_deg))

    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(f, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=ps, properties=pset_props)
    return elem


def add_cylinder_z(f, body, storey, ifc_class, name, cx, cy, z0, z1, radius,
                   predefined=None, obj_type=None, pset_name=None, pset_props=None):
    dz = float(z1 - z0)
    kwargs = {"ifc_class": ifc_class, "name": name}
    if predefined is not None:
        kwargs["predefined_type"] = predefined
    elem = ifcopenshell.api.root.create_entity(f, **kwargs)
    if obj_type is not None:
        elem.ObjectType = obj_type
    ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[elem])

    profile = f.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
    direction = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, ExtrudedDirection=direction, Depth=dz)
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(f, product=elem, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(f, product=elem, matrix=make_matrix(cx, cy, z0, 0.0))

    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(f, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(f, pset=ps, properties=pset_props)
    return elem


def add_mep_segment(f, body, storey, service, idx, x0, y0, z0, x1, y1, z1):
    """Add an axis-aligned rectangular MEP segment (butt-jointed, no overlap)."""
    if service == "CT":
        ifc_class, predefined, obj_type = "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1"
        name = f"CT-{idx:02d}"
    elif service == "BW":
        ifc_class, predefined, obj_type = "IfcCableSegment", "BUSBARSEGMENT", "BW-1"
        name = f"BW-{idx:02d}"
    elif service == "CHW":
        ifc_class, predefined, obj_type = "IfcPipeSegment", "RIGIDSEGMENT", "CHW-1"
        name = f"CHW-{idx:02d}"
    else:
        raise ValueError(service)
    return add_box(
        f, body, storey, ifc_class, name,
        x0, y0, z0, x1, y1, z1,
        predefined=predefined, obj_type=obj_type,
        pset_name="Pset_DCM_Route",
        pset_props={"Service": service, "Elevation_mm": float(z0)},
    )


def build_model():
    params = load_params()

    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
    ifcopenshell.api.unit.assign_unit(f, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = ifcopenshell.api.context.add_context(f, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx
    )

    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Meridian Campus")
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Data Hall Building")
    storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=building, products=[storey])

    # 1. Access Floor Panel (27000 x 21000 x 35 mm, z = -35..0)
    add_box(
        f, body, storey, "IfcSlab", "ACCESS-FLOOR",
        0.0, 0.0, -35.0, 27000.0, 21000.0, 0.0,
        predefined="FLOOR", obj_type="AccessFloor",
    )

    # 2. Structural Columns (6 columns, 400 x 400 x 3600 mm, z = 0..3600)
    col_xs = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
    col_ys = [("1", 8400.0), ("2", 16800.0)]
    for cx_lbl, cx in col_xs:
        for cy_lbl, cy in col_ys:
            add_box(
                f, body, storey, "IfcColumn", f"COL-{cx_lbl}{cy_lbl}",
                cx - 200.0, cy - 200.0, 0.0, cx + 200.0, cy + 200.0, 3600.0,
                predefined="COLUMN", obj_type="Column",
            )

    # 3. Cabinet Rows & In-Row CRAHs (A-101, A-601)
    rows_spec = [
        ("A", 3000.0, "SOUTH", "4C1 CU 3C1 N1 3C1 CU CA 6C1 SP CU 5C1"),
        ("B", 6000.0, "NORTH", "4C1 CU 5C1 2N1 CU CA 7C1 SP CU 5C1"),
        ("C", 8400.0, "SOUTH", "3C1 CU 6C1 2-600 CU CA N1 4C1 CU SP C1 2-600 3C1"),
        ("D", 11400.0, "NORTH", "4C1 CU 3C1 2N1 2C1 CU CA 7C1 SP CU 5C1"),
        ("E", 13800.0, "SOUTH", "4C1 CU 5C1 N1 C1 CU CA 6C1 SP CU 5C1"),
        ("F", 16800.0, "NORTH", "4C1 CU 5C1 2-600 CU CA 2N1 5C1 SP -600 CU 4C1"),
    ]
    for row_id, y_cl, facing, seq in rows_spec:
        y0, y1 = y_cl - 600.0, y_cl + 600.0
        rot = 0.0 if facing == "NORTH" else 180.0
        x = 1800.0
        rack_idx = 0
        crah_idx = 0
        for tok in seq.split():
            if tok == "CA":
                x = 11400.0
            elif tok == "SP":
                x += 600.0
            elif tok == "CU":
                crah_idx += 1
                add_box(
                    f, body, storey, "IfcUnitaryEquipment", f"CRAH-{row_id}{crah_idx:02d}",
                    x, y0, 0.0, x + 600.0, y1, 2000.0,
                    predefined="AIRHANDLER", obj_type="CRAH", rot_deg=rot,
                    pset_name="Pset_DCM_CRAH",
                    pset_props={"Placement": "IN-ROW", "Row": row_id, "Capacity_kW": 50.0, "Airflow_m3h": 9000.0, "Facing": facing},
                )
                x += 600.0
            elif tok.endswith("-600"):
                n = int(tok[:-4]) if tok[:-4] else 1
                x += n * 600.0
            else:
                if tok.endswith("C1"):
                    n = int(tok[:-2]) if tok[:-2] else 1
                    w, ctype = 600.0, "C1"
                elif tok.endswith("N1"):
                    n = int(tok[:-2]) if tok[:-2] else 1
                    w, ctype = 800.0, "N1"
                else:
                    raise ValueError(tok)
                for _ in range(n):
                    rack_idx += 1
                    add_box(
                        f, body, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                        x, y0, 0.0, x + w, y1, 2000.0,
                        predefined="USERDEFINED", obj_type="Rack", rot_deg=rot,
                        pset_name="Pset_DCM_Cabinet",
                        pset_props={
                            "Row": row_id, "Type": ctype, "Width_mm": w, "Depth_mm": 1200.0,
                            "Height_mm": 2000.0, "RU": 42, "Facing": facing, "Power_kW": 8.0, "Load_kg": 1363.0,
                        },
                    )
                    x += w

    # 4. Perimeter CRAHs (CRAH-01..04, 1200 x 900 x 2000, faces NORTH)
    perim_crahs = [
        ("CRAH-01", 600.0),
        ("CRAH-02", 9000.0),
        ("CRAH-03", 16800.0),
        ("CRAH-04", 25200.0),
    ]
    for name, x0 in perim_crahs:
        add_box(
            f, body, storey, "IfcUnitaryEquipment", name,
            x0, 0.0, 0.0, x0 + 1200.0, 900.0, 2000.0,
            predefined="AIRHANDLER", obj_type="CRAH", rot_deg=0.0,
            pset_name="Pset_DCM_CRAH",
            pset_props={"Placement": "PERIMETER", "Capacity_kW": 100.0, "Airflow_m3h": 20000.0, "Facing": "NORTH"},
        )

    # 5. PDUs (PDU-01..06, 762 x 813 x 1959, front flush with row front)
    pdus = [
        ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
        ("PDU-02", "B", 21600.0, 5787.0, "NORTH"),
        ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
        ("PDU-04", "D", 21600.0, 11187.0, "NORTH"),
        ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
        ("PDU-06", "F", 21600.0, 16587.0, "NORTH"),
    ]
    for name, row_id, x0, y0, facing in pdus:
        rot = 0.0 if facing == "NORTH" else 180.0
        add_box(
            f, body, storey, "IfcElectricDistributionBoard", name,
            x0, y0, 0.0, x0 + 762.0, y0 + 813.0, 1959.0,
            predefined="DISTRIBUTIONBOARD", obj_type="PDU", rot_deg=rot,
            pset_name="Pset_DCM_PDU",
            pset_props={"ServesRow": row_id, "Rating_kVA": 225.0, "Facing": facing, "WorkingSpace_mm": 900.0},
        )

    # 6. Cold-Aisle Containment (CAC-BC, CAC-DE)
    containment_aisles = [
        ("CAC-BC", 6600.0, 7800.0, 1800.0, 9600.0, 11400.0, 19200.0),
        ("CAC-DE", 12000.0, 13200.0, 1800.0, 9800.0, 11400.0, 19200.0),
    ]
    for tag, ay0, ay1, wx0, wx1, ex0, ex1 in containment_aisles:
        # Roof panels (z = 2000..2055.5, width = 1400 mm overhanging 100 mm each side)
        add_box(f, body, storey, "IfcBuildingElementProxy", f"{tag}-ROOF-W",
                wx0, ay0 - 100.0, 2000.0, wx1, ay1 + 100.0, 2055.5, obj_type="ContainmentRoof")
        add_box(f, body, storey, "IfcBuildingElementProxy", f"{tag}-ROOF-E",
                ex0, ay0 - 100.0, 2000.0, ex1, ay1 + 100.0, 2055.5, obj_type="ContainmentRoof")
        # 4 End doors (60 mm thick, z = 0..2000, inside roof ends so zero overlap)
        add_box(f, body, storey, "IfcDoor", f"{tag}-DOOR-WW",
                wx0, ay0, 0.0, wx0 + 60.0, ay1, 2000.0, obj_type="ContainmentDoor")
        add_box(f, body, storey, "IfcDoor", f"{tag}-DOOR-WE",
                wx1 - 60.0, ay0, 0.0, wx1, ay1, 2000.0, obj_type="ContainmentDoor")
        add_box(f, body, storey, "IfcDoor", f"{tag}-DOOR-EW",
                ex0, ay0, 0.0, ex0 + 60.0, ay1, 2000.0, obj_type="ContainmentDoor")
        add_box(f, body, storey, "IfcDoor", f"{tag}-DOOR-EE",
                ex1 - 60.0, ay0, 0.0, ex1, ay1, 2000.0, obj_type="ContainmentDoor")

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79)
    spr_idx = 0
    for j in range(7):
        sy = 1500.0 + 3000.0 * j
        for i in range(9):
            sx = 1500.0 + 3000.0 * i
            spr_idx += 1
            add_cylinder_z(
                f, body, storey, "IfcFireSuppressionTerminal", f"SPR-C{spr_idx:02d}",
                sx, sy, 3574.6, 3600.0, 25.0,
                predefined="SPRINKLER", obj_type="SprinklerHead",
            )
    in_aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]
    aisle_idx = 0
    for sy in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            aisle_idx += 1
            add_cylinder_z(
                f, body, storey, "IfcFireSuppressionTerminal", f"SPR-A{aisle_idx:02d}",
                sx, sy, 1890.0, 1998.0, 25.0,
                predefined="SPRINKLER", obj_type="SprinklerHead",
            )

    # 8. MEP Routing (3 services, butt-jointed, zero overlap, connected to (0, 9900))
    tx = float(params["trunk_x"])
    y_ab = float(params["y_ab"])
    y_cd = float(params["y_cd"])
    y_ef = float(params["y_ef"])
    chw_y_ab = float(params["chw_y_ab"])
    bx_end = float(params["branch_x_end"])
    chw_sx_end = float(params["chw_south_x_end"])

    def route_tree(service, width, z0, z1, y_south, y_mid, y_north, x_end_south, x_end_mid, x_end_north):
        hw = width / 2.0
        idx = 0
        # Entry stub from x=0 to trunk west face (tx - hw) at y = 9900
        if tx - hw > 1.0:
            idx += 1
            add_mep_segment(f, body, storey, service, idx, 0.0, 9900.0 - hw, z0, tx - hw, 9900.0 + hw, z1)
        # Main N-S trunk at x = tx, spanning y_south - hw to y_north + hw
        idx += 1
        add_mep_segment(f, body, storey, service, idx, tx - hw, y_south - hw, z0, tx + hw, y_north + hw, z1)
        # 3 E-W branches starting at trunk east face (tx + hw)
        for yb, xe in ((y_south, x_end_south), (y_mid, x_end_mid), (y_north, x_end_north)):
            idx += 1
            add_mep_segment(f, body, storey, service, idx, tx + hw, yb - hw, z0, xe, yb + hw, z1)

    # CT-1: Overhead (z = 2620..2747, width = 683 mm, height = 127 mm)
    route_tree("CT", 683.0, 2620.0, 2747.0, y_ab, y_cd, y_ef, bx_end, bx_end, bx_end)

    # BW-1: Under-floor plenum (z = -247..-100, width = 128 mm, height = 147 mm)
    route_tree("BW", 128.0, -247.0, -100.0, y_ab, y_cd, y_ef, bx_end, bx_end, bx_end)

    # CHW-1: Under-floor plenum (z = -550..-381.7, insulated OD = 168.3 mm)
    route_tree("CHW", 168.3, -550.0, -381.7, chw_y_ab, y_cd, y_ef, chw_sx_end, bx_end, bx_end)

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    f.write(OUT_PATH)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build_model()
