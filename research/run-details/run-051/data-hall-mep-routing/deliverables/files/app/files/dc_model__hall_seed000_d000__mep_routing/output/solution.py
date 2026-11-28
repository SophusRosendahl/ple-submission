"""Data Hall MEP Coordination Model — hall_seed000_d000.

Builds the complete IFC4 coordination model (architecture, structure,
equipment, containment, sprinklers, and coordinated MEP routes for
telecom cable tray, power busway, and chilled-water piping) in
millimetres using ifcopenshell==0.8.4 and numpy.
"""
import json
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid
import ifcopenshell.validate

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# ---------------------------------------------------------------------------
# Hall & Datum Constants (mm) — from A-101, A-301, A-601, A-602, E-101, F-101, M-101
# ---------------------------------------------------------------------------
HALL_X = 27000.0
HALL_Y = 21000.0
FLOOR_THK = 35.0        # Access floor panel: Z = -35..0
SOFFIT_Z = 3600.0       # Ceiling slab soffit
CEIL_DEFL_Z = 3574.6    # 25.4 mm below soffit
INAISLE_DEFL_Z = 1890.0 # 110 mm below containment roof underside (2000)

# Structural columns: 600 x 600 x 3600 mm, centered on grid intersections
COL_SIZE = 600.0
COL_CENTERS = [
    (8400.0, 8400.0), (16800.0, 8400.0), (25200.0, 8400.0),
    (8400.0, 16800.0), (16800.0, 16800.0), (25200.0, 16800.0),
]

# Cabinet rows (A-601): start X = 1800, cross-aisle east edge = 11400
ROW_START_X = 1800.0
CA_EAST_X = 11400.0
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

ROWS = [
    ("A", 3000.0, "SOUTH", ["4C1", "CU", "3C1", "N1", "3C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("B", 6000.0, "NORTH", ["4C1", "CU", "5C1", "2N1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("C", 8400.0, "SOUTH", ["3C1", "CU", "6C1", "2-600", "CU", "CA", "N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"]),
    ("D", 11400.0, "NORTH", ["4C1", "CU", "3C1", "2N1", "2C1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("E", 13800.0, "SOUTH", ["4C1", "CU", "5C1", "N1", "C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("F", 16800.0, "NORTH", ["4C1", "CU", "5C1", "2-600", "CU", "CA", "2N1", "5C1", "SP", "-600", "CU", "4C1"]),
]

# Perimeter CRAHs (A-601, M-101): 1200 W x 900 D x 2000 H, facing NORTH
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, E-101): 762 W x 813 D x 1959 H, front flush with row front
PDU_W, PDU_D, PDU_H = 762.0, 813.0, 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Containment (A-602, A-301): CAC-BC (Y=6600..7800), CAC-DE (Y=12000..13200)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_W = 1200.0
CAC_DOOR_H = 2055.5


def det_guid(seed_str: str) -> str:
    """Deterministic IFC GUID from a string key."""
    import hashlib
    h = hashlib.md5(seed_str.encode("utf-8")).digest()
    return ifcopenshell.guid.compress(h.hex())


def make_placement_matrix(cx: float, cy: float, z0: float, yaw_deg: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for is_si=True)."""
    rad = math.radians(yaw_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx / 1000.0
    m[1, 3] = cy / 1000.0
    m[2, 3] = z0 / 1000.0
    return m


def add_box(model, body_ctx, storey, ifc_class, name, predefined_type, object_type,
            x0, y0, z0, dx, dy, dz, yaw_deg=0.0, psets=None):
    """Create an extruded rectangular solid centered at (x0+dx/2, y0+dy/2) in XY, base at z0."""
    elem = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class=ifc_class, name=name
    )
    elem.GlobalId = det_guid(f"{ifc_class}:{name}")
    if predefined_type and hasattr(elem, "PredefinedType"):
        elem.PredefinedType = predefined_type
    if object_type and hasattr(elem, "ObjectType"):
        elem.ObjectType = object_type

    cx = x0 + dx / 2.0
    cy = y0 + dy / 2.0
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=elem,
        matrix=make_placement_matrix(cx, cy, z0, yaw_deg),
        is_si=True,
    )

    # 2D profile points only, in millimetres (project units)
    hx, hy = dx / 2.0, dy / 2.0
    pts = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy), (-hx, -hy)]
    polyline = model.create_entity(
        "IfcPolyline",
        Points=[model.create_entity("IfcCartesianPoint", Coordinates=(float(px), float(py))) for px, py in pts],
    )
    profile = model.create_entity(
        "IfcArbitraryClosedProfileDef", ProfileType="AREA", OuterCurve=polyline
    )
    pos = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    z_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
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
    elem.Representation = model.create_entity(
        "IfcProductDefinitionShape", Representations=[rep]
    )

    ifcopenshell.api.run(
        "spatial.assign_container", model, relating_structure=storey, products=[elem]
    )

    if psets:
        for pset_name, props in psets.items():
            pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)

    return elem


def parse_row_bays(seq):
    """Expand bay sequence into list of (kind, x0, width)."""
    out = []
    x = ROW_START_X
    for tok in seq:
        if tok == "CA":
            x = CA_EAST_X
            continue
        if tok == "CU":
            out.append(("CU", x, 600.0))
            x += 600.0
        elif tok == "SP":
            x += 600.0
        elif tok == "-600":
            x += 600.0
        elif tok == "2-600":
            x += 1200.0
        elif tok.endswith("C1"):
            n = int(tok[:-2]) if len(tok) > 2 else 1
            for _ in range(n):
                out.append(("C1", x, 600.0))
                x += 600.0
        elif tok.endswith("N1"):
            n = int(tok[:-2]) if len(tok) > 2 else 1
            for _ in range(n):
                out.append(("N1", x, 800.0))
                x += 800.0
        else:
            raise ValueError(f"Unknown bay token: {tok}")
    return out


def build_model(out_path: str):
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center")
    project.GlobalId = det_guid("Project:Meridian")

    # Millimetre project units
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRE"})

    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    site.GlobalId = det_guid("Site")
    bldg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    bldg.GlobalId = det_guid("Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.GlobalId = det_guid("Storey:DH1")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[bldg])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=bldg, products=[storey])

    # 1. Access Floor Panel (Z = -35..0)
    add_box(
        model, body_ctx, storey, "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        0.0, 0.0, -FLOOR_THK, HALL_X, HALL_Y, FLOOR_THK,
        psets={"Pset_DCM_Floor": {"Thickness_mm": FLOOR_THK, "PlenumDepth_mm": 865.0}},
    )

    # 2. Structural Columns (6 units, 600 x 600 x 3600, Z = 0..3600)
    for idx, (cx, cy) in enumerate(COL_CENTERS, 1):
        add_box(
            model, body_ctx, storey, "IfcColumn", f"COL-{idx:02d}", "COLUMN", "Column",
            cx - COL_SIZE / 2.0, cy - COL_SIZE / 2.0, 0.0, COL_SIZE, COL_SIZE, SOFFIT_Z,
            psets={"Pset_DCM_Structure": {"GridCenterX_mm": cx, "GridCenterY_mm": cy}},
        )

    # 3. Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_id, y_cl, facing, seq in ROWS:
        y0 = y_cl - CAB_DEPTH / 2.0
        yaw = 0.0 if facing == "NORTH" else 180.0
        bays = parse_row_bays(seq)
        rack_idx = 0
        cu_idx = 0
        west_end = 0.0
        east_end = 0.0
        for kind, x0, w in bays:
            if x0 < CA_EAST_X:
                west_end = max(west_end, x0 + w)
            else:
                east_end = max(east_end, x0 + w)
            if kind in ("C1", "N1"):
                rack_idx += 1
                add_box(
                    model, body_ctx, storey, "IfcFurniture", f"RACK-{row_id}{rack_idx:02d}",
                    "USERDEFINED", "Rack",
                    x0, y0, 0.0, w, CAB_DEPTH, CAB_HEIGHT, yaw_deg=yaw,
                    psets={
                        "Pset_DCM_Rack": {
                            "Row": row_id,
                            "Type": kind,
                            "Facing": facing,
                            "Width_mm": w,
                            "Depth_mm": CAB_DEPTH,
                            "Height_mm": CAB_HEIGHT,
                            "RU": 42,
                            "Power_kW": 8.0,
                        }
                    },
                )
            elif kind == "CU":
                cu_idx += 1
                add_box(
                    model, body_ctx, storey, "IfcUnitaryEquipment", f"CRAH-{row_id}{cu_idx:02d}",
                    "AIRCONDITIONINGUNIT", "CRAH",
                    x0, y0, 0.0, w, CAB_DEPTH, CAB_HEIGHT, yaw_deg=yaw,
                    psets={
                        "Pset_DCM_CRAH": {
                            "Placement": f"InRow-{row_id}",
                            "Facing": facing,
                            "Capacity_kW": 50.0,
                            "Airflow_m3h": 9000.0,
                        }
                    },
                )
        row_extents[row_id] = (ROW_START_X, west_end, CA_EAST_X, east_end)

    # 4. Perimeter CRAHs (4 units)
    for tag, x0, y0 in PERIM_CRAHS:
        add_box(
            model, body_ctx, storey, "IfcUnitaryEquipment", tag,
            "AIRCONDITIONINGUNIT", "CRAH",
            x0, y0, 0.0, 1200.0, 900.0, 2000.0, yaw_deg=0.0,
            psets={
                "Pset_DCM_CRAH": {
                    "Placement": "Perimeter",
                    "Facing": "NORTH",
                    "Capacity_kW": 100.0,
                    "Airflow_m3h": 20000.0,
                }
            },
        )

    # 5. PDUs (6 units)
    for tag, row_id, x0, y0, facing in PDUS:
        yaw = 0.0 if facing == "NORTH" else 180.0
        add_box(
            model, body_ctx, storey, "IfcElectricDistributionBoard", tag,
            "DISTRIBUTIONBOARD", "PDU",
            x0, y0, 0.0, PDU_W, PDU_D, PDU_H, yaw_deg=yaw,
            psets={
                "Pset_DCM_PDU": {
                    "ServesRow": row_id,
                    "Facing": facing,
                    "Rating_kVA": 225.0,
                    "DedicatedSpaceHeight_mm": 1800.0,
                }
            },
        )

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE: 2 roof panels + 4 end doors each)
    cac_specs = [
        ("CAC-BC", 7200.0, "B", "C"),
        ("CAC-DE", 12600.0, "D", "E"),
    ]
    for cac_tag, y_mid, r1, r2 in cac_specs:
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_end = min(row_extents[r1][3], row_extents[r2][3])
        # West & East roof panels (Z = 2000..2055.5, Y = y_mid - 700 .. y_mid + 700)
        for side, sx0, sx1 in [("W", ROW_START_X, w_end), ("E", CA_EAST_X, e_end)]:
            add_box(
                model, body_ctx, storey, "IfcCovering", f"{cac_tag}-ROOF-{side}",
                "CEILING", "ContainmentRoof",
                sx0, y_mid - CAC_ROOF_W / 2.0, CAC_ROOF_Z, sx1 - sx0, CAC_ROOF_W, CAC_ROOF_THK,
                psets={"Pset_DCM_Containment": {"Aisle": cac_tag, "Component": "Roof"}},
            )
            # 2 end doors per panel (outside panel ends so zero overlap with cabinets/roof)
            add_box(
                model, body_ctx, storey, "IfcDoor", f"{cac_tag}-DOOR-{side}1",
                "DOOR", "ContainmentDoor",
                sx0 - CAC_DOOR_THK, y_mid - CAC_DOOR_W / 2.0, 0.0,
                CAC_DOOR_THK, CAC_DOOR_W, CAC_DOOR_H,
            )
            add_box(
                model, body_ctx, storey, "IfcDoor", f"{cac_tag}-DOOR-{side}2",
                "DOOR", "ContainmentDoor",
                sx1, y_mid - CAC_DOOR_W / 2.0, 0.0,
                CAC_DOOR_THK, CAC_DOOR_W, CAC_DOOR_H,
            )

    # 7. Sprinklers (63 ceiling heads + 16 in-aisle heads = 79)
    spr_idx = 0
    for iy in range(7):
        sy = 1500.0 + 3000.0 * iy
        for ix in range(9):
            sx = 1500.0 + 3000.0 * ix
            # Relocate heads inside 1500 mm column keep-out (750 mm half-width)
            for cx, cy in COL_CENTERS:
                if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                    sy_adj = cy - 900.0
                    sx_adj = cx - 900.0 if sx < cx else cx + 300.0
                    sx, sy = sx_adj, sy_adj
            spr_idx += 1
            add_box(
                model, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPR-C{spr_idx:02d}",
                "SPRINKLER", "SprinklerHead",
                sx - 25.0, sy - 25.0, CEIL_DEFL_Z, 50.0, 50.0, SOFFIT_Z - CEIL_DEFL_Z,
                psets={"Pset_DCM_Sprinkler": {"Type": "Ceiling", "DeflectorElevation_mm": CEIL_DEFL_Z}},
            )

    in_aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]
    ia_idx = 0
    for y_mid in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            ia_idx += 1
            add_box(
                model, body_ctx, storey, "IfcFireSuppressionTerminal", f"SPR-IA{ia_idx:02d}",
                "SPRINKLER", "SprinklerHead",
                sx - 25.0, y_mid - 25.0, INAISLE_DEFL_Z, 50.0, 50.0, CAC_ROOF_Z - INAISLE_DEFL_Z,
                psets={"Pset_DCM_Sprinkler": {"Type": "InAisle", "DeflectorElevation_mm": INAISLE_DEFL_Z}},
            )

    # -----------------------------------------------------------------------
    # 8. Coordinated MEP Routing (3 services, butt-jointed, zero clashes)
    # -----------------------------------------------------------------------
    # Shared comb topology:
    #   - Middle header at Y = 9900 (from entry X = 0 to X = 17500) serves Rows C & D
    #   - Spine at X = 1200 connects Y = 9900 to Y = 4500 (Rows A & B) and Y = 15300 (Rows E & F)
    #   - CHW spine also extends South to Y = 1500 and runs East to X = 25200 for Perimeter CRAHs 01..04
    # Vertical tiers:
    #   - Busway (BW-1, 128 W x 147 H): Overhead Z = 2650..2797 (in [2600, 3114.6])
    #   - Cable Tray (CT-1, 683 W x 127 H): Under-floor Z = -220..-93 (in [-900, -55], >2700 mm from BW)
    #   - CHW Pipe (CHW-1, 168.3 OD insul): Under-floor Z = -600..-431.7 (in [-900, -55], 211 mm below CT)
    SPINE_X = 2400.0
    END_AB = 17000.0
    END_CD = 16600.0
    END_EF = 17400.0
    PERIM_END_X = 23500.0

    def add_route_seg(ifc_class, ptype, otype, name, x0, y0, x1, y1, z0, h, service, tier):
        add_box(
            model, body_ctx, storey, ifc_class, name, ptype, otype,
            min(x0, x1), min(y0, y1), z0, abs(x1 - x0), abs(y1 - y0), h,
            psets={
                "Pset_DCM_Pathway": {
                    "Service": service,
                    "Tier": tier,
                    "BottomElevation_mm": z0,
                    "TopElevation_mm": z0 + h,
                }
            },
        )

    # 8a. Power Busway (BW-1: 128 W x 147 H, Overhead Z = 2650..2797)
    bw_w, bw_h, bw_z = 128.0, 147.0, 2650.0
    bw_hw = bw_w / 2.0
    bw_segs = [
        ("BW-MAIN-CD", 0.0, 9900.0 - bw_hw, END_CD, 9900.0 + bw_hw),
        ("BW-SPINE-S", SPINE_X - bw_hw, 4500.0 - bw_hw, SPINE_X + bw_hw, 9900.0 - bw_hw),
        ("BW-SPINE-N", SPINE_X - bw_hw, 9900.0 + bw_hw, SPINE_X + bw_hw, 15300.0 + bw_hw),
        ("BW-MAIN-AB", SPINE_X + bw_hw, 4500.0 - bw_hw, END_AB, 4500.0 + bw_hw),
        ("BW-MAIN-EF", SPINE_X + bw_hw, 15300.0 - bw_hw, END_EF, 15300.0 + bw_hw),
    ]
    for name, x0, y0, x1, y1 in bw_segs:
        add_route_seg(
            "IfcCableSegment", "BUSBARSEGMENT", "BW", name,
            x0, y0, x1, y1, bw_z, bw_h, "Power", "Overhead",
        )

    # 8b. Telecom Cable Tray (CT-1: 683 W x 127 H, Under-Floor Z = -220..-93)
    ct_w, ct_h, ct_z = 683.0, 127.0, -220.0
    ct_hw = ct_w / 2.0
    ct_segs = [
        ("CT-MAIN-CD", 0.0, 9900.0 - ct_hw, END_CD, 9900.0 + ct_hw),
        ("CT-SPINE-S", SPINE_X - ct_hw, 4500.0 - ct_hw, SPINE_X + ct_hw, 9900.0 - ct_hw),
        ("CT-SPINE-N", SPINE_X - ct_hw, 9900.0 + ct_hw, SPINE_X + ct_hw, 15300.0 + ct_hw),
        ("CT-MAIN-AB", SPINE_X + ct_hw, 4500.0 - ct_hw, END_AB, 4500.0 + ct_hw),
        ("CT-MAIN-EF", SPINE_X + ct_hw, 15300.0 - ct_hw, END_EF, 15300.0 + ct_hw),
    ]
    for name, x0, y0, x1, y1 in ct_segs:
        add_route_seg(
            "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT", name,
            x0, y0, x1, y1, ct_z, ct_h, "Telecom", "UnderFloor",
        )

    # 8c. Chilled Water Pipe (CHW-1: 168.3 OD insulated, Under-Floor Z = -600..-431.7)
    ch_d, ch_z = 168.3, -600.0
    ch_r = ch_d / 2.0
    ch_segs = [
        ("CHW-MAIN-CD", 0.0, 9900.0 - ch_r, END_CD, 9900.0 + ch_r),
        ("CHW-SPINE-S", SPINE_X - ch_r, 1500.0 - ch_r, SPINE_X + ch_r, 9900.0 - ch_r),
        ("CHW-SPINE-N", SPINE_X - ch_r, 9900.0 + ch_r, SPINE_X + ch_r, 15300.0 + ch_r),
        ("CHW-MAIN-AB", SPINE_X + ch_r, 4500.0 - ch_r, END_AB, 4500.0 + ch_r),
        ("CHW-MAIN-EF", SPINE_X + ch_r, 15300.0 - ch_r, END_EF, 15300.0 + ch_r),
        ("CHW-PERIM-CRAH", SPINE_X + ch_r, 1500.0 - ch_r, PERIM_END_X, 1500.0 + ch_r),
    ]
    for name, x0, y0, x1, y1 in ch_segs:
        add_route_seg(
            "IfcPipeSegment", "RIGIDSEGMENT", "CHW", name,
            x0, y0, x1, y1, ch_z, ch_d, "ChilledWater", "UnderFloor",
        )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)
    return model


def write_reconciliation_log(out_dir: str):
    log = {
        "hall": {"width_mm": HALL_X, "depth_mm": HALL_Y, "tile_mm": 600.0},
        "vertical_datums_mm": {
            "top_of_structural_slab": -900.0,
            "access_floor_underside": -35.0,
            "underfloor_pathway_max_top": -55.0,
            "finished_floor": 0.0,
            "min_clear_height": 2600.0,
            "overhead_pathway_max_top": 3114.6,
            "ceiling_sprinkler_deflector": CEIL_DEFL_Z,
            "ceiling_slab_soffit": SOFFIT_Z,
        },
        "services": {
            "BW-1": {"section_mm": "128x147", "tier": "Overhead", "z_mm": [2650.0, 2797.0]},
            "CT-1": {"section_mm": "683x127", "tier": "UnderFloor", "z_mm": [-220.0, -93.0]},
            "CHW-1": {"od_insulated_mm": 168.3, "tier": "UnderFloor", "z_mm": [-600.0, -431.7]},
        },
        "clearances_applied": {
            "tray_busway_separation_mm": 2743.0,
            "sprinkler_standoff_mm": 777.6,
            "pdu_dedicated_space_chw": "CHW routed under-floor, 0 intrusion",
        },
    }
    rec_path = os.path.join(out_dir, "reconciliation.json")
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


if __name__ == "__main__":
    build_model(OUT_PATH)
    write_reconciliation_log(os.path.dirname(os.path.abspath(OUT_PATH)))
    print(f"Wrote IFC4 model to {OUT_PATH}")
