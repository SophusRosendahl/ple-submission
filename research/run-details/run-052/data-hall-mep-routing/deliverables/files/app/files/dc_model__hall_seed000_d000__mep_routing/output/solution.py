"""Coordinated 3D IFC4 model and overhead/under-floor MEP routing for hall_seed000_d000.

Self-contained deterministic script using ifcopenshell==0.8.4 and numpy only.
All coordinates and specifications are baked in from drawing sheets
A-101, A-301, A-601, A-602, E-101, F-101, and M-101.
"""
import json
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
import ifcopenshell.validate

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/app/files/dc_model__hall_seed000_d000__mep_routing/output/model.ifc"
)

# ---------------------------------------------------------------------------
# Baked-in hall geometry & equipment schedule (mm)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
SLAB_THK = 35.0
SOFFIT_Z = 3600.0

COL_SIZE = 400.0
COL_POSITIONS = [
    (8400.0, 8400.0),
    (16800.0, 8400.0),
    (25200.0, 8400.0),
    (8400.0, 16800.0),
    (16800.0, 16800.0),
    (25200.0, 16800.0),
]

# Cabinet rows: (name, y_center, facing, west_tokens, east_tokens)
# West half starts at x = 1800 (tile D); East half starts at x = 11400 (common east edge of cross-aisle)
ROW_DEFS = [
    (
        "A",
        3000.0,
        "SOUTH",
        ["4C1", "CU", "3C1", "N1", "3C1", "CU"],
        ["6C1", "SP", "CU", "5C1"],
    ),
    (
        "B",
        6000.0,
        "NORTH",
        ["4C1", "CU", "5C1", "2N1", "CU"],
        ["7C1", "SP", "CU", "5C1"],
    ),
    (
        "C",
        8400.0,
        "SOUTH",
        ["3C1", "CU", "6C1", "2-600", "CU"],
        ["N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"],
    ),
    (
        "D",
        11400.0,
        "NORTH",
        ["4C1", "CU", "3C1", "2N1", "2C1", "CU"],
        ["7C1", "SP", "CU", "5C1"],
    ),
    (
        "E",
        13800.0,
        "SOUTH",
        ["4C1", "CU", "5C1", "N1", "C1", "CU"],
        ["6C1", "SP", "CU", "5C1"],
    ),
    (
        "F",
        16800.0,
        "NORTH",
        ["4C1", "CU", "5C1", "2-600", "CU"],
        ["2N1", "5C1", "SP", "-600", "CU", "4C1"],
    ),
]

CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Perimeter CRAHs: (name, x0, y0, w, d, h, facing)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs: (name, serves_row, x0, y0, w, d, h, facing)
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 5787.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 11187.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 16587.0, 762.0, 813.0, 1959.0, "NORTH"),
]

# Cold-aisle containment: CAC-BC (y_aisle=6600..7800), CAC-DE (y_aisle=12000..13200)
CONTAINMENT_AISLES = [
    ("CAC-BC", 7200.0, (1800.0, 9600.0), (11400.0, 19400.0)),
    ("CAC-DE", 12600.0, (1800.0, 9800.0), (11400.0, 19200.0)),
]


def parse_tokens(tokens):
    out = []
    for tok in tokens:
        if tok.startswith("-"):
            out.append(("OMIT", float(tok[1:])))
        elif "-" in tok:
            cnt_s, w_s = tok.split("-")
            for _ in range(int(cnt_s)):
                out.append(("OMIT", float(w_s)))
        elif tok in ("CU", "SP"):
            out.append((tok, 600.0))
        elif tok == "C1":
            out.append(("C1", 600.0))
        elif tok == "N1":
            out.append(("N1", 800.0))
        else:
            # leading count
            i = 0
            while i < len(tok) and tok[i].isdigit():
                i += 1
            cnt = int(tok[:i])
            kind = tok[i:]
            w = 800.0 if kind == "N1" else 600.0
            for _ in range(cnt):
                out.append((kind, w))
    return out


def make_placement_matrix(cx_mm, cy_mm, z_mm, rot_deg=0.0):
    """4x4 placement matrix with translations in METRES (is_si=True)."""
    rad = math.radians(rot_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def add_box(model, body_ctx, element, w, d, h, cx, cy, z0, rot_deg=0.0):
    """Create a centered rectangular extrusion [w x d x h] with bottom at z0."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w),
        YDim=float(d),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(h),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    element.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[rep]
    )
    ifcopenshell.api.geometry.edit_object_placement(
        model,
        product=element,
        matrix=make_placement_matrix(cx, cy, z0, rot_deg),
        is_si=True,
    )


def add_cylinder_z(model, body_ctx, element, radius, h, cx, cy, z0):
    profile = model.create_entity(
        "IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius)
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(h),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    element.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[rep]
    )
    ifcopenshell.api.geometry.edit_object_placement(
        model,
        product=element,
        matrix=make_placement_matrix(cx, cy, z0, 0.0),
        is_si=True,
    )


def add_pset(model, element, pset_name, props):
    pset = ifcopenshell.api.pset.add_pset(model, product=element, name=pset_name)
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)


def add_mep_segment(
    model, storey, body_ctx, ifc_class, predefined_type, obj_type, name, x0, y0, z0, x1, y1, z1, extra_props=None
):
    """Add an axis-aligned MEP segment filling the exact AABB [x0..x1, y0..y1, z0..z1]."""
    el = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, predefined_type=predefined_type, name=name
    )
    el.ObjectType = obj_type
    ifcopenshell.api.spatial.assign_container(model, products=[el], relating_structure=storey)
    w = abs(x1 - x0)
    d = abs(y1 - y0)
    h = abs(z1 - z0)
    cx = 0.5 * (x0 + x1)
    cy = 0.5 * (y0 + y1)
    add_box(model, body_ctx, el, w, d, h, cx, cy, min(z0, z1), 0.0)
    props = {
        "Service": obj_type,
        "Elevation_mm": float(min(z0, z1)),
        "TopElevation_mm": float(max(z0, z1)),
        "Zone": "UnderFloor" if max(z0, z1) <= 0.0 else "Overhead",
    }
    if extra_props:
        props.update(extra_props)
    add_pset(model, el, "Pset_DCM_Pathway", props)
    return el


def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center")
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor Panel (-35 to 0 mm)
    floor = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcSlab", predefined_type="FLOOR", name="ACCESS-FLOOR-01"
    )
    floor.ObjectType = "AccessFloor"
    ifcopenshell.api.spatial.assign_container(model, products=[floor], relating_structure=storey)
    add_box(model, body_ctx, floor, ROOM_W, ROOM_D, SLAB_THK, ROOM_W / 2.0, ROOM_D / 2.0, -SLAB_THK)

    # 2. Structural Columns (0 to 3600 mm)
    for idx, (cx, cy) in enumerate(COL_POSITIONS, start=1):
        col = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcColumn", predefined_type="COLUMN", name=f"COL-{idx:02d}"
        )
        col.ObjectType = "Column"
        ifcopenshell.api.spatial.assign_container(model, products=[col], relating_structure=storey)
        add_box(model, body_ctx, col, COL_SIZE, COL_SIZE, SOFFIT_Z, cx, cy, 0.0)

    # 3. Cabinet Rows & In-Row CRAHs
    for row_name, y_c, facing, west_toks, east_toks in ROW_DEFS:
        rot_deg = 0.0 if facing == "NORTH" else 180.0
        cab_idx = 0
        crah_idx = 0
        for start_x, toks in ((1800.0, west_toks), (11400.0, east_toks)):
            x = start_x
            for kind, w in parse_tokens(toks):
                cx = x + w / 2.0
                if kind in ("C1", "N1"):
                    cab_idx += 1
                    rack = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcFurniture",
                        predefined_type="USERDEFINED",
                        name=f"RACK-{row_name}{cab_idx:02d}",
                    )
                    rack.ObjectType = "Rack"
                    ifcopenshell.api.spatial.assign_container(
                        model, products=[rack], relating_structure=storey
                    )
                    add_box(model, body_ctx, rack, w, CAB_DEPTH, CAB_HEIGHT, cx, y_c, 0.0, rot_deg)
                    add_pset(
                        model,
                        rack,
                        "Pset_DCM_Rack",
                        {
                            "Row": row_name,
                            "CabinetType": kind,
                            "Facing": facing,
                            "RU": 42,
                            "Power_kW": 8.0,
                            "Load_kg": 1363.0,
                        },
                    )
                elif kind == "CU":
                    crah_idx += 1
                    crah = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcUnitaryEquipment",
                        predefined_type="AIRHANDLER",
                        name=f"CRAH-{row_name}{crah_idx:02d}",
                    )
                    crah.ObjectType = "CRAH"
                    ifcopenshell.api.spatial.assign_container(
                        model, products=[crah], relating_structure=storey
                    )
                    add_box(model, body_ctx, crah, w, CAB_DEPTH, CAB_HEIGHT, cx, y_c, 0.0, rot_deg)
                    add_pset(
                        model,
                        crah,
                        "Pset_DCM_CRAH",
                        {
                            "Placement": f"Row {row_name}",
                            "Facing": facing,
                            "Capacity_kW": 50.0,
                            "Airflow_m3h": 9000.0,
                        },
                    )
                x += w

    # 4. Perimeter CRAHs
    for name, x0, y0, w, d, h, facing in PERIMETER_CRAHS:
        crah = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRHANDLER", name=name
        )
        crah.ObjectType = "CRAH"
        ifcopenshell.api.spatial.assign_container(model, products=[crah], relating_structure=storey)
        add_box(model, body_ctx, crah, w, d, h, x0 + w / 2.0, y0 + d / 2.0, 0.0, 0.0)
        add_pset(
            model,
            crah,
            "Pset_DCM_CRAH",
            {
                "Placement": "Perimeter",
                "Facing": facing,
                "Capacity_kW": 100.0,
                "Airflow_m3h": 20000.0,
            },
        )

    # 5. PDUs
    for name, serves_row, x0, y0, w, d, h, facing in PDUS:
        rot_deg = 0.0 if facing == "NORTH" else 180.0
        pdu = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcElectricDistributionBoard", predefined_type="DISTRIBUTIONBOARD", name=name
        )
        pdu.ObjectType = "PDU"
        ifcopenshell.api.spatial.assign_container(model, products=[pdu], relating_structure=storey)
        add_box(model, body_ctx, pdu, w, d, h, x0 + w / 2.0, y0 + d / 2.0, 0.0, rot_deg)
        add_pset(
            model,
            pdu,
            "Pset_DCM_PDU",
            {
                "ServesRow": serves_row,
                "Facing": facing,
                "Rating_kVA": 225.0,
                "DedicatedSpaceAbove_mm": 1800.0,
            },
        )

    # 6. Cold-Aisle Containment (Roofs & End Doors)
    for cac_name, y_c, (wx0, wx1), (ex0, ex1) in CONTAINMENT_AISLES:
        for half_idx, (hx0, hx1) in enumerate(((wx0, wx1), (ex0, ex1)), start=1):
            roof = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcBuildingElementProxy",
                predefined_type="USERDEFINED",
                name=f"{cac_name}-ROOF-{half_idx}",
            )
            roof.ObjectType = "ContainmentRoof"
            ifcopenshell.api.spatial.assign_container(model, products=[roof], relating_structure=storey)
            add_box(model, body_ctx, roof, hx1 - hx0, 1400.0, 55.5, 0.5 * (hx0 + hx1), y_c, 2000.0)

            for end_idx, dx in enumerate((hx0 - 30.0, hx1 + 30.0), start=1):
                door = ifcopenshell.api.root.create_entity(
                    model,
                    ifc_class="IfcBuildingElementProxy",
                    predefined_type="USERDEFINED",
                    name=f"{cac_name}-DOOR-{half_idx}-{end_idx}",
                )
                door.ObjectType = "ContainmentDoor"
                ifcopenshell.api.spatial.assign_container(
                    model, products=[door], relating_structure=storey
                )
                add_box(model, body_ctx, door, 60.0, 1200.0, 2055.5, dx, y_c, 0.0)

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle = 79)
    sp_idx = 0
    for j in range(7):
        ny = 1500.0 + j * 3000.0
        for i in range(9):
            nx = 1500.0 + i * 3000.0
            # Relocate outside 1500x1500 keep-out around columns
            sx, sy = nx, ny
            for cx, cy in COL_POSITIONS:
                if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                    sy = cy - 900.0
            sp_idx += 1
            sp = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SP-CEIL-{sp_idx:02d}",
            )
            sp.ObjectType = "SprinklerHead"
            ifcopenshell.api.spatial.assign_container(model, products=[sp], relating_structure=storey)
            # Deflector at z = 3575 mm (body 3575..3600 mm)
            add_cylinder_z(model, body_ctx, sp, 25.0, 25.0, sx, sy, 3575.0)
            add_pset(
                model,
                sp,
                "Pset_DCM_Sprinkler",
                {"Zone": "Ceiling", "DeflectorElevation_mm": 3575.0, "Standoff_mm": 460.0},
            )

    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 0
    for y_aisle in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            sp = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SP-AISLE-{ia_idx:02d}",
            )
            sp.ObjectType = "SprinklerHead"
            ifcopenshell.api.spatial.assign_container(model, products=[sp], relating_structure=storey)
            # Deflector at z = 1890 mm (body 1890..2000 mm)
            add_cylinder_z(model, body_ctx, sp, 25.0, 110.0, sx, y_aisle, 1890.0)
            add_pset(
                model,
                sp,
                "Pset_DCM_Sprinkler",
                {"Zone": "InAisle", "DeflectorElevation_mm": 1890.0},
            )

    # -----------------------------------------------------------------------
    # 8. MEP Routing (All butt-jointed, 0 mm overlap, 100% connected to (0, 9900))
    # -----------------------------------------------------------------------
    # Common hot-aisle header Y coordinates: 4500 (Rows A/B), 9900 (Rows C/D), 15300 (Rows E/F)
    # Spine at x = 2400 mm, headers from x = 2400 to 17400 mm (> 81% coverage on every row).
    SPINE_X = 2400.0
    HEADER_X_END = 17400.0

    # --- 8A. Cable Tray CT-1 (683 W x 127 H) in under-floor plenum z = -250..-123 ---
    ct_z0, ct_z1 = -250.0, -123.0
    ct_w = 683.0
    ct_hw = ct_w / 2.0
    ct_spine_x = SPINE_X

    # Entry stub from West wall (x=0) to spine west face at y=9900
    add_mep_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLELADDERSEGMENT", "CableTray",
        "CT-ENTRY", 0.0, 9900.0 - ct_hw, ct_z0, ct_spine_x - ct_hw, 9900.0 + ct_hw, ct_z1
    )
    # N-S Spine from y=4500-hw to y=15300+hw
    add_mep_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLELADDERSEGMENT", "CableTray",
        "CT-SPINE", ct_spine_x - ct_hw, 4500.0 - ct_hw, ct_z0, ct_spine_x + ct_hw, 15300.0 + ct_hw, ct_z1
    )
    # 3 E-W Headers from spine east face to HEADER_X_END
    for h_name, hy in (("AB", 4500.0), ("CD", 9900.0), ("EF", 15300.0)):
        add_mep_segment(
            model, storey, body_ctx, "IfcCableCarrierSegment", "CABLELADDERSEGMENT", "CableTray",
            f"CT-HDR-{h_name}", ct_spine_x + ct_hw, hy - ct_hw, ct_z0, HEADER_X_END, hy + ct_hw, ct_z1
        )

    # --- 8B. Power Busway BW-1 (128 W x 147 H) overhead z = 2950..3097 ---
    bw_z0, bw_z1 = 2950.0, 3097.0
    bw_w = 128.0
    bw_hw = bw_w / 2.0
    bw_spine_x = SPINE_X

    add_mep_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "Busway",
        "BW-ENTRY", 0.0, 9900.0 - bw_hw, bw_z0, bw_spine_x - bw_hw, 9900.0 + bw_hw, bw_z1
    )
    add_mep_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "Busway",
        "BW-SPINE", bw_spine_x - bw_hw, 4500.0 - bw_hw, bw_z0, bw_spine_x + bw_hw, 15300.0 + bw_hw, bw_z1
    )
    for h_name, hy in (("AB", 4500.0), ("CD", 9900.0), ("EF", 15300.0)):
        add_mep_segment(
            model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "Busway",
            f"BW-HDR-{h_name}", bw_spine_x + bw_hw, hy - bw_hw, bw_z0, HEADER_X_END, hy + bw_hw, bw_z1
        )

    # --- 8C. Chilled Water CHW-1 (OD 168.3 mm over insulation) overhead z = 2650..2818.3 ---
    chw_z0, chw_z1 = 2650.0, 2818.3
    chw_od = 168.3
    chw_hr = chw_od / 2.0
    chw_spine_x = SPINE_X

    # Entry stub
    add_mep_segment(
        model, storey, body_ctx, "IfcPipeSegment", "RIGIDSEGMENT", "CHW",
        "CHW-ENTRY", 0.0, 9900.0 - chw_hr, chw_z0, chw_spine_x - chw_hr, 9900.0 + chw_hr, chw_z1
    )
    # N-S Spine from perimeter branch y=1500-hr to y=15300+hr
    add_mep_segment(
        model, storey, body_ctx, "IfcPipeSegment", "RIGIDSEGMENT", "CHW",
        "CHW-SPINE", chw_spine_x - chw_hr, 1500.0 - chw_hr, chw_z0, chw_spine_x + chw_hr, 15300.0 + chw_hr, chw_z1
    )
    # 3 E-W Row Headers
    for h_name, hy in (("AB", 4500.0), ("CD", 9900.0), ("EF", 15300.0)):
        add_mep_segment(
            model, storey, body_ctx, "IfcPipeSegment", "RIGIDSEGMENT", "CHW",
            f"CHW-HDR-{h_name}", chw_spine_x + chw_hr, hy - chw_hr, chw_z0, HEADER_X_END, hy + chw_hr, chw_z1
        )
    # Perimeter CRAH gallery header at y = 1500 (serves CRAH-01..04, south of PDU-01)
    add_mep_segment(
        model, storey, body_ctx, "IfcPipeSegment", "RIGIDSEGMENT", "CHW",
        "CHW-PERIM", chw_spine_x + chw_hr, 1500.0 - chw_hr, chw_z0, 23200.0, 1500.0 + chw_hr, chw_z1
    )

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)

    # Optional diagnostic reconciliation log
    recon_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)), "reconciliation.json")
    recon = {
        "sheets": ["A-101", "A-301", "A-601", "A-602", "E-101", "F-101", "M-101"],
        "datums_mm": {
            "finished_floor": 0.0,
            "access_floor_panel": [-35.0, 0.0],
            "under_floor_zone": [-900.0, -55.0],
            "overhead_zone": [2600.0, 3115.0],
            "ceiling_sprinkler_deflector": 3575.0,
            "soffit": 3600.0,
        },
        "service_tiers_mm": {
            "CT-1": {"zone": "UnderFloor", "z": [ct_z0, ct_z1], "width": ct_w, "height": 127.0},
            "CHW-1": {"zone": "Overhead", "z": [chw_z0, chw_z1], "od_insulated": chw_od},
            "BW-1": {"zone": "Overhead", "z": [bw_z0, bw_z1], "width": bw_w, "height": 147.0},
        },
        "clearances_mm": {
            "tray_to_busway_vertical": bw_z0 - ct_z1,
            "overhead_headroom_min": chw_z0,
            "sprinkler_standoff_achieved": 3575.0 - bw_z1,
            "under_floor_below_panel": -35.0 - ct_z1,
        },
    }
    with open(recon_path, "w", encoding="utf-8") as f:
        json.dump(recon, f, indent=2)


if __name__ == "__main__":
    build_model()
