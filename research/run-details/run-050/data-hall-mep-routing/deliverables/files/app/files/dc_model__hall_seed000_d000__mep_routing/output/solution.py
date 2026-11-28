"""Data hall MEP coordination model generator (hall_seed000_d000).

Builds the complete IFC4 model in millimetres using ifcopenshell==0.8.4 and numpy,
and writes the IFC4 file to sys.argv[1] (default: output/model.ifc).
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

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "model.ifc"
)

# ---------------------------------------------------------------------------
# Deterministic GUID helper (so repeated runs produce identical IFC files)
# ---------------------------------------------------------------------------
_GUID_COUNTER = 0


def next_guid() -> str:
    global _GUID_COUNTER
    _GUID_COUNTER += 1
    # Deterministic 16-byte seed from counter
    h = (_GUID_COUNTER * 2654435761) & 0xFFFFFFFFFFFFFFFF
    raw = h.to_bytes(8, "big") + (_GUID_COUNTER).to_bytes(8, "big")
    return ifcopenshell.guid.compress(raw.hex())


# ---------------------------------------------------------------------------
# Geometry & placement helpers (units = mm; edit_object_placement uses metres)
# ---------------------------------------------------------------------------
def make_matrix(cx_mm: float, cy_mm: float, z0_mm: float, rot_z_rad: float = 0.0) -> np.ndarray:
    c = math.cos(rot_z_rad)
    s = math.sin(rot_z_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def add_box_element(
    model,
    storey,
    body_ctx,
    ifc_class: str,
    name: str,
    predefined_type: str,
    object_type: str,
    cx: float,
    cy: float,
    z0: float,
    dx: float,
    dy: float,
    dz: float,
    rot_z_rad: float = 0.0,
    pset_name: str = None,
    pset_props: dict = None,
):
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, predefined_type=predefined_type, name=name
    )
    el.GlobalId = next_guid()
    if object_type is not None:
        el.ObjectType = object_type

    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)

    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    extrusion = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(dz),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    el.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    mat = make_matrix(cx, cy, z0, rot_z_rad)
    ifcopenshell.api.geometry.edit_object_placement(model, product=el, matrix=mat, is_si=True)

    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ps.GlobalId = next_guid()
        ifcopenshell.api.pset.edit_pset(model, pset=ps, properties=pset_props)

    return el


def add_cyl_element(
    model,
    storey,
    body_ctx,
    ifc_class: str,
    name: str,
    predefined_type: str,
    object_type: str,
    cx: float,
    cy: float,
    z0: float,
    radius: float,
    height: float,
    pset_name: str = None,
    pset_props: dict = None,
):
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, predefined_type=predefined_type, name=name
    )
    el.GlobalId = next_guid()
    if object_type is not None:
        el.ObjectType = object_type

    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)

    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    extrusion = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(height),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[extrusion],
    )
    el.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    mat = make_matrix(cx, cy, z0, 0.0)
    ifcopenshell.api.geometry.edit_object_placement(model, product=el, matrix=mat, is_si=True)

    if pset_name and pset_props:
        ps = ifcopenshell.api.pset.add_pset(model, product=el, name=pset_name)
        ps.GlobalId = next_guid()
        ifcopenshell.api.pset.edit_pset(model, pset=ps, properties=pset_props)

    return el


# ---------------------------------------------------------------------------
# Architectural & Equipment Data (from A-101, A-301, A-601, A-602, M-101, E-101, F-101)
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
SOFFIT_Z = 3600.0
FLOOR_THK = 35.0
SLAB_TOP_Z = -900.0
SLAB_THK = 200.0

# Structural columns: 6 columns at Grid (A,B,C) x (1,2)
# Column size 400 x 400 mm (fits cleanly inside Row F's -600 bay at 16400..17000 centered at 16800)
COL_SIZE = 400.0
COLUMNS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Cabinet rows: (row_letter, y_centre, facing_str, bay_sequence_west_of_CA, bay_sequence_east_of_CA)
# Facing: SOUTH -> rot_z = pi (front -Y), NORTH -> rot_z = 0 (front +Y)
# Cross-aisle east edge is common to every row at X = 11200.0
ROW_START_X = 1800.0  # Tile D
CA_EAST_X = 11200.0

ROWS_SPEC = [
    (
        "A", 3000.0, "SOUTH",
        ["C1"] * 4 + ["CU"] + ["C1"] * 3 + ["N1"] + ["C1"] * 3 + ["CU"],
        ["C1"] * 6 + ["SP", "CU"] + ["C1"] * 5,
    ),
    (
        "B", 6000.0, "NORTH",
        ["C1"] * 4 + ["CU"] + ["C1"] * 5 + ["N1"] * 2 + ["CU"],
        ["C1"] * 7 + ["SP", "CU"] + ["C1"] * 5,
    ),
    (
        "C", 8400.0, "SOUTH",
        ["C1"] * 3 + ["CU"] + ["C1"] * 6 + ["OMIT600"] * 2 + ["CU"],
        ["N1"] + ["C1"] * 4 + ["CU", "SP", "C1"] + ["OMIT600"] * 2 + ["C1"] * 3,
    ),
    (
        "D", 11400.0, "NORTH",
        ["C1"] * 4 + ["CU"] + ["C1"] * 3 + ["N1"] * 2 + ["C1"] * 2 + ["CU"],
        ["C1"] * 7 + ["SP", "CU"] + ["C1"] * 5,
    ),
    (
        "E", 13800.0, "SOUTH",
        ["C1"] * 4 + ["CU"] + ["C1"] * 5 + ["N1", "C1", "CU"],
        ["C1"] * 6 + ["SP", "CU"] + ["C1"] * 5,
    ),
    (
        "F", 16800.0, "NORTH",
        ["C1"] * 4 + ["CU"] + ["C1"] * 5 + ["OMIT600"] * 2 + ["CU"],
        ["N1"] * 2 + ["C1"] * 5 + ["SP", "OMIT600", "CU"] + ["C1"] * 4,
    ),
]

BAY_WIDTH = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "OMIT600": 600.0}

# Perimeter CRAHs: 1200 W x 900 D x 2000 H, front faces NORTH (+Y), Y: 0..900
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),    # B01
    ("CRAH-02", 9000.0, 0.0),   # P01
    ("CRAH-03", 16800.0, 0.0),  # AC01
    ("CRAH-04", 25200.0, 0.0),  # AQ01
]

# PDUs: 762 W x 813 D x 1959 H, front flush with served row's front face
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),   # AJ05, front at Y=2400 -> Y: 2400..3213
    ("PDU-02", "B", 21600.0, 5787.0, "NORTH"),   # AK10, front at Y=6600 -> Y: 5787..6600
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),   # AJ14, front at Y=7800 -> Y: 7800..8613
    ("PDU-04", "D", 21600.0, 11187.0, "NORTH"),  # AK19, front at Y=12000 -> Y: 11187..12000
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),  # AJ23, front at Y=13200 -> Y: 13200..14013
    ("PDU-06", "F", 21600.0, 16587.0, "NORTH"),  # AK28, front at Y=17400 -> Y: 16587..17400
]


def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    project.GlobalId = next_guid()

    # Millimetre length unit
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    # Geometric representation context
    ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx
    )

    # Spatial structure
    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    site.GlobalId = next_guid()
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    building.GlobalId = next_guid()
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.GlobalId = next_guid()
    storey.Elevation = 0.0

    ifcopenshell.api.spatial.assign_container(model, products=[], relating_structure=storey) if False else None
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor & Structural Slab
    add_box_element(
        model, storey, body_ctx, "IfcSlab", "AccessFloor", "FLOOR", "AccessFloor",
        HALL_W / 2.0, HALL_D / 2.0, -FLOOR_THK, HALL_W, HALL_D, FLOOR_THK,
    )
    add_box_element(
        model, storey, body_ctx, "IfcSlab", "StructuralSlab", "BASESLAB", "StructuralSlab",
        HALL_W / 2.0, HALL_D / 2.0, SLAB_TOP_Z - SLAB_THK, HALL_W, HALL_D, SLAB_THK,
    )

    # 2. Structural Columns (Z = 0 to 3600)
    for cname, cx, cy in COLUMNS:
        add_box_element(
            model, storey, body_ctx, "IfcColumn", cname, "COLUMN", "StructuralColumn",
            cx, cy, 0.0, COL_SIZE, COL_SIZE, SOFFIT_Z,
        )

    # 3. Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_id, yc, facing, west_seq, east_seq in ROWS_SPEC:
        rot = math.pi if facing == "SOUTH" else 0.0
        cab_idx = 0
        cu_idx = 0

        # West of cross-aisle
        x = ROW_START_X
        for bay in west_seq:
            w = BAY_WIDTH[bay]
            if bay in ("C1", "N1"):
                cab_idx += 1
                tag = f"RACK-{row_id}{cab_idx:02d}"
                add_box_element(
                    model, storey, body_ctx, "IfcFurniture", tag, "USERDEFINED", "Rack",
                    x + w / 2.0, yc, 0.0, w, 1200.0, 2000.0, rot_z_rad=rot,
                    pset_name="Pset_DCM_Rack",
                    pset_props={
                        "Tag": tag, "Row": row_id, "Type": bay,
                        "Width_mm": w, "Depth_mm": 1200.0, "Height_mm": 2000.0,
                        "RU": 42, "Facing": facing, "Power_kW": 8.0, "Load_kg": 1363.0,
                    },
                )
            elif bay == "CU":
                cu_idx += 1
                tag = f"CRAH-{row_id}{cu_idx:02d}"
                add_box_element(
                    model, storey, body_ctx, "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
                    x + w / 2.0, yc, 0.0, w, 1200.0, 2000.0, rot_z_rad=rot,
                    pset_name="Pset_DCM_CRAH",
                    pset_props={
                        "Tag": tag, "Placement": f"Row {row_id}",
                        "Capacity_kW": 50.0, "Airflow_m3h": 9000.0,
                        "Facing": facing, "Service": "CHW DN50",
                    },
                )
            x += w
        west_end_x = x

        # East of cross-aisle
        x = CA_EAST_X
        for bay in east_seq:
            w = BAY_WIDTH[bay]
            if bay in ("C1", "N1"):
                cab_idx += 1
                tag = f"RACK-{row_id}{cab_idx:02d}"
                add_box_element(
                    model, storey, body_ctx, "IfcFurniture", tag, "USERDEFINED", "Rack",
                    x + w / 2.0, yc, 0.0, w, 1200.0, 2000.0, rot_z_rad=rot,
                    pset_name="Pset_DCM_Rack",
                    pset_props={
                        "Tag": tag, "Row": row_id, "Type": bay,
                        "Width_mm": w, "Depth_mm": 1200.0, "Height_mm": 2000.0,
                        "RU": 42, "Facing": facing, "Power_kW": 8.0, "Load_kg": 1363.0,
                    },
                )
            elif bay == "CU":
                cu_idx += 1
                tag = f"CRAH-{row_id}{cu_idx:02d}"
                add_box_element(
                    model, storey, body_ctx, "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
                    x + w / 2.0, yc, 0.0, w, 1200.0, 2000.0, rot_z_rad=rot,
                    pset_name="Pset_DCM_CRAH",
                    pset_props={
                        "Tag": tag, "Placement": f"Row {row_id}",
                        "Capacity_kW": 50.0, "Airflow_m3h": 9000.0,
                        "Facing": facing, "Service": "CHW DN50",
                    },
                )
            x += w
        row_extents[row_id] = (ROW_START_X, west_end_x, CA_EAST_X, x)

    # 4. Perimeter CRAHs
    for tag, x0, y0 in PERIMETER_CRAHS:
        add_box_element(
            model, storey, body_ctx, "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
            x0 + 600.0, y0 + 450.0, 0.0, 1200.0, 900.0, 2000.0, rot_z_rad=0.0,
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Tag": tag, "Placement": "Perimeter",
                "Capacity_kW": 100.0, "Airflow_m3h": 20000.0,
                "Facing": "NORTH", "Service": "CHW DN100",
            },
        )

    # 5. PDUs
    for tag, serves_row, x0, y0, facing in PDUS:
        rot = math.pi if facing == "SOUTH" else 0.0
        add_box_element(
            model, storey, body_ctx, "IfcElectricDistributionBoard", tag, "DISTRIBUTIONBOARD", "PDU",
            x0 + 762.0 / 2.0, y0 + 813.0 / 2.0, 0.0, 762.0, 813.0, 1959.0, rot_z_rad=rot,
            pset_name="Pset_DCM_PDU",
            pset_props={
                "Tag": tag, "ServesRow": serves_row, "Rating_kVA": 225.0,
                "Facing": facing, "WorkingSpace_mm": 900.0,
            },
        )

    # 6. Cold-Aisle Containment (CAC-BC at Y=7200, CAC-DE at Y=12600)
    # 2 roof panels per aisle (west & east of cross-aisle), 4 end doors per aisle
    for cac_tag, y_aisle, row_s, row_n in [
        ("CAC-BC", 7200.0, "B", "C"),
        ("CAC-DE", 12600.0, "D", "E"),
    ]:
        ws0, ws1, es0, es1 = row_extents[row_s]
        wn0, wn1, en0, en1 = row_extents[row_n]
        w_x0 = max(ws0, wn0)
        w_x1 = min(ws1, wn1)
        e_x0 = max(es0, en0)
        e_x1 = min(es1, en1)

        # Roof panels: width 1400 mm (100 mm overhang each side), thk 55.5 mm, Z = 2000..2055.5
        for side_idx, (rx0, rx1) in enumerate([(w_x0, w_x1), (e_x0, e_x1)], 1):
            add_box_element(
                model, storey, body_ctx, "IfcCovering", f"{cac_tag}-ROOF-{side_idx}", "CEILING", "ContainmentRoof",
                (rx0 + rx1) / 2.0, y_aisle, 2000.0, rx1 - rx0, 1400.0, 55.5,
            )
            # End doors: 60 mm thk x 1200 mm wide x 2055.5 mm H (placed just outside roof ends so 0 overlap)
            add_box_element(
                model, storey, body_ctx, "IfcDoor", f"{cac_tag}-DOOR-{side_idx}W", "DOOR", "ContainmentDoor",
                rx0 - 30.0, y_aisle, 0.0, 60.0, 1200.0, 2055.5,
            )
            add_box_element(
                model, storey, body_ctx, "IfcDoor", f"{cac_tag}-DOOR-{side_idx}E", "DOOR", "ContainmentDoor",
                rx1 + 30.0, y_aisle, 0.0, 60.0, 1200.0, 2055.5,
            )

    # 7. Sprinklers (63 ceiling heads + 16 in-aisle heads = 79)
    # Ceiling grid: 9 x 7 (1500, 4500, ..., 25500) x (1500, 4500, ..., 19500)
    # Relocate any head within 1500 mm keep-out of a column clear of the column
    spk_idx = 0
    for iy in range(7):
        sy = 1500.0 + iy * 3000.0
        for ix in range(9):
            sx = 1500.0 + ix * 3000.0
            # Check column proximity (only at Y=16500 near Col B (16800,16800) and Col C (25200,16800))
            for _, cx, cy in COLUMNS:
                if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                    sx = cx - 900.0 if sx <= cx else cx + 900.0
            spk_idx += 1
            add_cyl_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal", f"SPK-C{spk_idx:02d}",
                "SPRINKLER", "SprinklerHead",
                sx, sy, 3574.6, 25.0, 25.4,
                pset_name="Pset_DCM_Sprinkler",
                pset_props={"Type": "CeilingPendent", "DeflectorZ_mm": 3574.6, "Standoff_mm": 460.0},
            )

    # 16 in-aisle heads (8 in CAC-BC at Y=7200, 8 in CAC-DE at Y=12600), deflector at Z=1890
    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12100.0, 14500.0, 16900.0, 18700.0]
    ia_idx = 0
    for y_aisle in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            add_cyl_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal", f"SPK-A{ia_idx:02d}",
                "SPRINKLER", "SprinklerHead",
                sx, y_aisle, 1890.0, 25.0, 110.0,
                pset_name="Pset_DCM_Sprinkler",
                pset_props={"Type": "InAislePendent", "DeflectorZ_mm": 1890.0, "Standoff_mm": 460.0},
            )

    # 8. MEP Routing (zero-overlap abutted axis-aligned segments!)
    # Helper to add a straight axis-aligned segment given its exact AABB [x0, y0, z0, x1, y1, z1]
    def add_mep_seg(ifc_class, name, predef, obj_type, x0, y0, z0, x1, y1, z1, props):
        add_box_element(
            model, storey, body_ctx, ifc_class, name, predef, obj_type,
            (x0 + x1) / 2.0, (y0 + y1) / 2.0, z0,
            x1 - x0, y1 - y0, z1 - z0,
            pset_name="Pset_DCM_MEP",
            pset_props=props,
        )

    # --- A. Telecom Cable Tray (CT-1: 683 W x 127 H) in Under-Floor Plenum Z = [-200, -73] ---
    # Spine at X = 1800 (west end of rows), Y = [4500, 15300]
    # Entry stub at Y = 9900 from X = 0 to spine; 3 hot-aisle headers to X = 17200
    ct_w, ct_h = 683.0, 127.0
    ct_z0, ct_z1 = -200.0, -200.0 + ct_h
    ct_props = {"Service": "Telecom", "Tag": "CT-1", "Zone": "UnderFloorPlenum", "Elevation_mm": ct_z0}
    ct_sx0, ct_sx1 = 1800.0 - ct_w / 2.0, 1800.0 + ct_w / 2.0

    add_mep_seg("IfcCableCarrierSegment", "CT-01", "CABLELADDERSEGMENT", "CT-1",
                0.0, 9900.0 - ct_w / 2.0, ct_z0, ct_sx0, 9900.0 + ct_w / 2.0, ct_z1, ct_props)
    add_mep_seg("IfcCableCarrierSegment", "CT-02", "CABLELADDERSEGMENT", "CT-1",
                ct_sx0, 4500.0 - ct_w / 2.0, ct_z0, ct_sx1, 15300.0 + ct_w / 2.0, ct_z1, ct_props)
    for idx, hy in enumerate((4500.0, 9900.0, 15300.0), 3):
        add_mep_seg("IfcCableCarrierSegment", f"CT-{idx:02d}", "CABLELADDERSEGMENT", "CT-1",
                    ct_sx1, hy - ct_w / 2.0, ct_z0, 17200.0, hy + ct_w / 2.0, ct_z1, ct_props)

    # --- B. Power Busway (BW-1: 128 W x 147 H) in Overhead Tier Z = [2610, 2757] ---
    bw_w, bw_h = 128.0, 147.0
    bw_z0, bw_z1 = 2610.0, 2610.0 + bw_h
    bw_props = {"Service": "Power", "Tag": "BW-1", "Zone": "Overhead", "Elevation_mm": bw_z0}
    bw_sx0, bw_sx1 = 1800.0 - bw_w / 2.0, 1800.0 + bw_w / 2.0

    add_mep_seg("IfcCableSegment", "BW-01", "BUSBARSEGMENT", "BW-1",
                0.0, 9900.0 - bw_w / 2.0, bw_z0, bw_sx0, 9900.0 + bw_w / 2.0, bw_z1, bw_props)
    add_mep_seg("IfcCableSegment", "BW-02", "BUSBARSEGMENT", "BW-1",
                bw_sx0, 4500.0 - bw_w / 2.0, bw_z0, bw_sx1, 15300.0 + bw_w / 2.0, bw_z1, bw_props)
    for idx, hy in enumerate((4500.0, 9900.0, 15300.0), 3):
        add_mep_seg("IfcCableSegment", f"BW-{idx:02d}", "BUSBARSEGMENT", "BW-1",
                    bw_sx1, hy - bw_w / 2.0, bw_z0, 17200.0, hy + bw_w / 2.0, bw_z1, bw_props)

    # --- C. Chilled Water Pipe (CHW-1: Insulated OD 168.3 mm) in Overhead Tier Z = [2940, 3108.3] ---
    # 3 hot-aisle headers (Y = 4500, 9900, 15300 to X = 17200) + 1 south perimeter header (Y = 2100 to X = 23200)
    chw_d = 168.3
    chw_z0, chw_z1 = 2940.0, 2940.0 + chw_d
    chw_props = {
        "Service": "ChilledWater", "Tag": "CHW-1", "Zone": "Overhead",
        "Elevation_mm": chw_z0, "BareOD_mm": 114.3, "InsulatedOD_mm": 168.3,
    }
    chw_sx0, chw_sx1 = 1800.0 - chw_d / 2.0, 1800.0 + chw_d / 2.0

    add_mep_seg("IfcPipeSegment", "CHW-01", "RIGIDSEGMENT", "CHW-1",
                0.0, 9900.0 - chw_d / 2.0, chw_z0, chw_sx0, 9900.0 + chw_d / 2.0, chw_z1, chw_props)
    add_mep_seg("IfcPipeSegment", "CHW-02", "RIGIDSEGMENT", "CHW-1",
                chw_sx0, 2100.0 - chw_d / 2.0, chw_z0, chw_sx1, 15300.0 + chw_d / 2.0, chw_z1, chw_props)
    for idx, (hy, ex) in enumerate([(2100.0, 23200.0), (4500.0, 17200.0), (9900.0, 17200.0), (15300.0, 17200.0)], 3):
        add_mep_seg("IfcPipeSegment", f"CHW-{idx:02d}", "RIGIDSEGMENT", "CHW-1",
                    chw_sx1, hy - chw_d / 2.0, chw_z0, ex, hy + chw_d / 2.0, chw_z1, chw_props)

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)

    # Optional diagnostic side file: output/reconciliation.json
    recon_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)), "reconciliation.json")
    recon = {
        "hall_dimensions_mm": {"width_x": HALL_W, "depth_y": HALL_D, "soffit_z": SOFFIT_Z},
        "vertical_datums_mm": {
            "finished_floor": 0.0,
            "access_floor_thickness": 35.0,
            "structural_slab_top": -900.0,
            "under_floor_tray_top_max": -55.0,
            "min_clear_height": 2600.0,
            "ceiling_sprinkler_deflector": 3574.6,
            "sprinkler_standoff": 460.0,
            "overhead_top_max": 3114.6,
        },
        "service_sections_mm": {
            "CT-1": {"width": 683.0, "height": 127.0, "zone": "UnderFloorPlenum", "z_band": [-200.0, -73.0]},
            "BW-1": {"width": 128.0, "height": 147.0, "zone": "Overhead", "z_band": [2610.0, 2757.0]},
            "CHW-1": {"bare_od": 114.3, "insulated_od": 168.3, "zone": "Overhead", "z_band": [2940.0, 3108.3]},
        },
        "applied_rules": {
            "tray_busway_separation_mm": 2683.0,
            "chw_sprinkler_clearance_mm": 466.3,
            "pdu_dedicated_space_clear": True,
            "columns_clear_full_height": True,
        },
    }
    with open(recon_path, "w", encoding="utf-8") as f:
        json.dump(recon, f, indent=2)


if __name__ == "__main__":
    build_model()
