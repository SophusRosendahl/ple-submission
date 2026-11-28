"""Meridian Data Center — Data Hall 1 (hall_seed000_d000) coordinated MEP IFC4 model.

Self-contained deterministic builder using ifcopenshell==0.8.4 + numpy only.
Writes IFC4 model (millimetre project units) to sys.argv[1] (default output/model.ifc).
"""
import json
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
# Hall constants (mm) — extracted from sheets A-101, A-301, A-601, A-602, E-101, F-101, M-101
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0
FLOOR_TOP_Z = 0.0
SOFFIT_Z = 3600.0
MIN_CLEAR_Z = 2600.0
CEIL_DEFLECTOR_Z = 3574.6
SPRINKLER_STANDOFF = 460.0
IN_AISLE_DEFLECTOR_Z = 1890.0

ROW_START_X = 1800.0
CROSS_AISLE_EAST_X = 11400.0
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Structural columns: 600 x 600 mm, Z = 0..3600
COL_SIZE = 600.0
COL_CENTRES = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Cabinet rows: (name, cl_y, facing, west_bays, east_bays)
# Bay tokens: ("C1", 600), ("N1", 800), ("CU", 600), ("SP", 600), ("GAP", 600)
ROWS = [
    ("A", 3000.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
     [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH",
     [("C1", 3), ("CU", 1), ("C1", 6), ("GAP", 2), ("CU", 1)],
     [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("GAP", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
     [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("GAP", 2), ("CU", 1)],
     [("N1", 2), ("C1", 5), ("SP", 1), ("GAP", 1), ("CU", 1), ("C1", 4)]),
]

BAY_WIDTH = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "GAP": 600.0}

# Perimeter CRAHs: 1200 x 900 x 2000 mm, facing NORTH, Y = 0..900
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs: 762 x 813 x 1959 mm, front flush with served row front face
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", "SOUTH", 21000.0, 2400.0),
    ("PDU-02", "B", "NORTH", 21600.0, 6600.0 - PDU_D),
    ("PDU-03", "C", "SOUTH", 21000.0, 7800.0),
    ("PDU-04", "D", "NORTH", 21000.0, 12000.0 - PDU_D),
    ("PDU-05", "E", "SOUTH", 21000.0, 13200.0),
    ("PDU-06", "F", "NORTH", 21600.0, 17400.0 - PDU_D),
]

# MEP pathway section dimensions (mm)
TRAY_W, TRAY_H = 683.0, 127.0
BUSWAY_W, BUSWAY_H = 128.0, 147.0
CHW_OD = 168.3  # insulated OD per M-101 Note 4


# ---------------------------------------------------------------------------
# IFC4 geometry helpers (placement translations in METRES, geometry in MM)
# ---------------------------------------------------------------------------
def make_matrix(cx_mm, cy_mm, z0_mm, yaw_deg=0.0):
    rad = math.radians(yaw_deg)
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


def add_box(f, ctx, storey, ifc_class, name, predefined_type, object_type,
            x0, y0, z0, dx, dy, dz, yaw_deg=0.0, pset_name=None, pset_props=None):
    elem = ifcopenshell.api.run(
        "root.create_entity", f, ifc_class=ifc_class, name=name,
        predefined_type=predefined_type,
    )
    elem.ObjectType = object_type
    ifcopenshell.api.run("spatial.assign_container", f, products=[elem], relating_structure=storey)

    cx = x0 + dx / 2.0
    cy = y0 + dy / 2.0
    ifcopenshell.api.run(
        "geometry.edit_object_placement", f, product=elem,
        matrix=make_matrix(cx, cy, z0, yaw_deg=yaw_deg),
    )

    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    z_dir = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=z_dir,
        Depth=float(dz),
    )
    rep = f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    elem.Representation = f.create_entity("IfcProductDefinitionShape", Representations=[rep])

    if pset_name and pset_props:
        pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
    return elem


def add_mep_segment(f, ctx, storey, ifc_class, name, predefined_type, object_type,
                    x0, y0, z0, x1, y1, z1, service, zone):
    dx = x1 - x0
    dy = y1 - y0
    dz = z1 - z0
    length = max(dx, dy)
    return add_box(
        f, ctx, storey, ifc_class, name, predefined_type, object_type,
        x0, y0, z0, dx, dy, dz, yaw_deg=0.0,
        pset_name="Pset_DCM_MEP",
        pset_props={
            "Service": service,
            "Zone": zone,
            "Elevation_mm": float(z0),
            "Length_mm": float(length),
        },
    )


def build_model():
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETRE"})

    model_ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context", f, context_type="Model",
        context_identifier="Body", target_view="MODEL_VIEW", parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[storey], relating_object=building)

    # 1. Access floor panel (Z = -35..0)
    add_box(
        f, body_ctx, storey, "IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor",
        0.0, 0.0, -FLOOR_THK, HALL_W, HALL_D, FLOOR_THK,
        pset_name="Pset_DCM_Floor",
        pset_props={"Thickness_mm": FLOOR_THK, "PlenumDepth_mm": 865.0},
    )

    # 2. Structural columns (Z = 0..3600)
    for cname, cx, cy in COL_CENTRES:
        add_box(
            f, body_ctx, storey, "IfcColumn", cname, "COLUMN", "Column",
            cx - COL_SIZE / 2.0, cy - COL_SIZE / 2.0, 0.0,
            COL_SIZE, COL_SIZE, SOFFIT_Z,
            pset_name="Pset_DCM_Structure",
            pset_props={"Width_mm": COL_SIZE, "Depth_mm": COL_SIZE, "Height_mm": SOFFIT_Z},
        )

    # 3. Cabinet rows & in-row CRAHs
    for row_name, cl_y, facing, west_bays, east_bays in ROWS:
        y0 = cl_y - CAB_DEPTH / 2.0
        yaw = 0.0 if facing == "NORTH" else 180.0
        rack_idx = 0
        crah_idx = 0
        for start_x, bays in ((ROW_START_X, west_bays), (CROSS_AISLE_EAST_X, east_bays)):
            x = start_x
            for btype, count in bays:
                w = BAY_WIDTH[btype]
                for _ in range(count):
                    if btype in ("C1", "N1"):
                        rack_idx += 1
                        tag = f"RACK-{row_name}{rack_idx:02d}"
                        add_box(
                            f, body_ctx, storey, "IfcFurniture", tag, "USERDEFINED", "Rack",
                            x, y0, 0.0, w, CAB_DEPTH, CAB_HEIGHT, yaw_deg=yaw,
                            pset_name="Pset_DCM_Rack",
                            pset_props={
                                "Row": row_name, "BayType": btype,
                                "Width_mm": w, "Depth_mm": CAB_DEPTH,
                                "Height_mm": CAB_HEIGHT, "RU": 42,
                                "Facing": facing, "Power_kW": 8.0, "Load_kg": 1363.0,
                            },
                        )
                    elif btype == "CU":
                        crah_idx += 1
                        tag = f"CRAH-{row_name}{crah_idx:02d}"
                        add_box(
                            f, body_ctx, storey, "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
                            x, y0, 0.0, w, CAB_DEPTH, CAB_HEIGHT, yaw_deg=yaw,
                            pset_name="Pset_DCM_CRAH",
                            pset_props={
                                "Placement": f"IN_ROW_{row_name}",
                                "Capacity_kW": 50.0, "Airflow_m3h": 9000.0,
                                "Facing": facing, "Service": "CHW_DN50",
                            },
                        )
                    x += w

    # 4. Perimeter CRAHs
    for tag, x0, y0 in PERIM_CRAHS:
        add_box(
            f, body_ctx, storey, "IfcUnitaryEquipment", tag, "AIRHANDLER", "CRAH",
            x0, y0, 0.0, 1200.0, 900.0, 2000.0, yaw_deg=0.0,
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "PERIMETER",
                "Capacity_kW": 100.0, "Airflow_m3h": 20000.0,
                "Facing": "NORTH", "Service": "CHW_DN100",
            },
        )

    # 5. PDUs
    for tag, served_row, facing, x0, y0 in PDUS:
        yaw = 0.0 if facing == "NORTH" else 180.0
        add_box(
            f, body_ctx, storey, "IfcElectricDistributionBoard", tag, "DISTRIBUTIONBOARD", "PDU",
            x0, y0, 0.0, PDU_W, PDU_D, PDU_H, yaw_deg=yaw,
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServedRow": served_row, "Rating_kVA": 225.0,
                "Facing": facing, "WorkingSpace_mm": 900.0,
            },
        )

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE)
    # Roof panels: Z = 2000..2055.5, width 1400 mm; End doors: 60 mm thick x 1200 wide x 2055.5 high
    # Place doors just outside the roof panel ends so they do not overlap the roof panels or cabinets.
    for cac_name, aisle_y0, west_x1, east_x1 in (
        ("CAC-BC", 6600.0, 9600.0, 19400.0),
        ("CAC-DE", 12000.0, 9800.0, 19200.0),
    ):
        roof_y0 = aisle_y0 - 100.0
        add_box(
            f, body_ctx, storey, "IfcCovering", f"{cac_name}-ROOF-W", "CEILING", "ContainmentRoof",
            ROW_START_X, roof_y0, 2000.0, west_x1 - ROW_START_X, 1400.0, 55.5,
        )
        add_box(
            f, body_ctx, storey, "IfcCovering", f"{cac_name}-ROOF-E", "CEILING", "ContainmentRoof",
            CROSS_AISLE_EAST_X, roof_y0, 2000.0, east_x1 - CROSS_AISLE_EAST_X, 1400.0, 55.5,
        )
        for d_idx, dx0 in enumerate((ROW_START_X - 60.0, west_x1, CROSS_AISLE_EAST_X - 60.0, east_x1), 1):
            add_box(
                f, body_ctx, storey, "IfcDoor", f"{cac_name}-DOOR-{d_idx}", "DOOR", "ContainmentDoor",
                dx0, aisle_y0, 0.0, 60.0, 1200.0, 2055.5,
            )

    # 7. Sprinkler heads: 63 ceiling + 16 in-aisle = 79 total
    ceil_idx = 0
    for ix in range(9):
        sx = 1500.0 + ix * 3000.0
        for iy in range(7):
            sy = 1500.0 + iy * 3000.0
            # Relocate clear of structural columns (1500 mm keep-out)
            for _, colx, coly in COL_CENTRES:
                if abs(sx - colx) < 1000.0 and abs(sy - coly) < 1000.0:
                    sy = coly - 1200.0
            ceil_idx += 1
            add_box(
                f, body_ctx, storey, "IfcFireSuppressionTerminal",
                f"SPR-CEIL-{ceil_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx - 25.0, sy - 25.0, CEIL_DEFLECTOR_Z, 50.0, 50.0, 25.4,
            )

    aisle_idx = 0
    for cac_y in (7200.0, 12600.0):
        for sx in (3000.0, 5400.0, 7800.0, 10200.0, 12600.0, 15000.0, 17400.0, 19000.0):
            aisle_idx += 1
            add_box(
                f, body_ctx, storey, "IfcFireSuppressionTerminal",
                f"SPR-AISLE-{aisle_idx:02d}", "SPRINKLER", "SprinklerHead",
                sx - 25.0, cac_y - 25.0, IN_AISLE_DEFLECTOR_Z, 50.0, 50.0, 110.0,
            )

    # -----------------------------------------------------------------------
    # 8. MEP ROUTING — 3 services, all starting at West entry (0, 9900)
    #    - Busway (BW): Overhead zone Z = 2800..2947 (H = 147, W = 128)
    #    - Cable Tray (CT): Under-floor plenum Z = -300..-173 (H = 127, W = 683)
    #    - Chilled Water (CHW): Under-floor plenum Z = -700..-531.7 (OD = 168.3)
    #    All segments cleanly butted (0 mm overlap, 0 mm gap).
    # -----------------------------------------------------------------------

    # --- 8a. Power Busway (Overhead Z = 2800..2947) ---
    bw_z0, bw_z1 = 2800.0, 2800.0 + BUSWAY_H
    bw_xc = 1800.0
    bw_hw = BUSWAY_W / 2.0
    # Entry stub from X=0 to trunk west face
    add_mep_segment(
        f, body_ctx, storey, "IfcCableSegment", "BW-ENTRY", "BUSBARSEGMENT", "Busway",
        0.0, 9900.0 - bw_hw, bw_z0, bw_xc - bw_hw, 9900.0 + bw_hw, bw_z1, "Power", "OVERHEAD",
    )
    # N-S trunk at X=1800 from Y=4500-hw to Y=15300+hw
    add_mep_segment(
        f, body_ctx, storey, "IfcCableSegment", "BW-TRUNK", "BUSBARSEGMENT", "Busway",
        bw_xc - bw_hw, 4500.0 - bw_hw, bw_z0, bw_xc + bw_hw, 15300.0 + bw_hw, bw_z1, "Power", "OVERHEAD",
    )
    # 3 E-W headers in the hot aisles (Y=4500 serves A+B, Y=9900 serves C+D, Y=15300 serves E+F)
    for h_idx, (hy, hx1) in enumerate(((4500.0, 16600.0), (9900.0, 16600.0), (15300.0, 17000.0)), 1):
        add_mep_segment(
            f, body_ctx, storey, "IfcCableSegment", f"BW-HDR-{h_idx}", "BUSBARSEGMENT", "Busway",
            bw_xc + bw_hw, hy - bw_hw, bw_z0, hx1, hy + bw_hw, bw_z1, "Power", "OVERHEAD",
        )

    # --- 8b. Telecom Cable Tray (Under-floor plenum Z = -300..-173) ---
    ct_z0, ct_z1 = -300.0, -300.0 + TRAY_H
    ct_xc = 1800.0
    ct_hw = TRAY_W / 2.0
    add_mep_segment(
        f, body_ctx, storey, "IfcCableCarrierSegment", "CT-ENTRY", "CABLETRAYSEGMENT", "CableTray",
        0.0, 9900.0 - ct_hw, ct_z0, ct_xc - ct_hw, 9900.0 + ct_hw, ct_z1, "Telecom", "PLENUM",
    )
    add_mep_segment(
        f, body_ctx, storey, "IfcCableCarrierSegment", "CT-TRUNK", "CABLETRAYSEGMENT", "CableTray",
        ct_xc - ct_hw, 4500.0 - ct_hw, ct_z0, ct_xc + ct_hw, 15300.0 + ct_hw, ct_z1, "Telecom", "PLENUM",
    )
    for h_idx, (hy, hx1) in enumerate(((4500.0, 16600.0), (9900.0, 16600.0), (15300.0, 17000.0)), 1):
        add_mep_segment(
            f, body_ctx, storey, "IfcCableCarrierSegment", f"CT-HDR-{h_idx}", "CABLETRAYSEGMENT", "CableTray",
            ct_xc + ct_hw, hy - ct_hw, ct_z0, hx1, hy + ct_hw, ct_z1, "Telecom", "PLENUM",
        )

    # --- 8c. Chilled Water Pipe (Under-floor plenum Z = -700..-531.7) ---
    chw_z0, chw_z1 = -700.0, -700.0 + CHW_OD
    chw_xc = 1800.0
    chw_hw = CHW_OD / 2.0
    add_mep_segment(
        f, body_ctx, storey, "IfcPipeSegment", "CHW-ENTRY", "RIGIDSEGMENT", "CHW",
        0.0, 9900.0 - chw_hw, chw_z0, chw_xc - chw_hw, 9900.0 + chw_hw, chw_z1, "CHW", "PLENUM",
    )
    add_mep_segment(
        f, body_ctx, storey, "IfcPipeSegment", "CHW-TRUNK", "RIGIDSEGMENT", "CHW",
        chw_xc - chw_hw, 3100.0 - chw_hw, chw_z0, chw_xc + chw_hw, 15300.0 + chw_hw, chw_z1, "CHW", "PLENUM",
    )
    # 3 E-W headers: Y=3100 (perimeter CRAHs + Rows A & B), Y=9900 (Rows C+D), Y=15300 (Rows E+F)
    for h_idx, (hy, hx1) in enumerate((
        (3100.0, 24500.0),
        (9900.0, 16600.0),
        (15300.0, 17000.0),
    ), 1):
        add_mep_segment(
            f, body_ctx, storey, "IfcPipeSegment", f"CHW-HDR-{h_idx}", "RIGIDSEGMENT", "CHW",
            chw_xc + chw_hw, hy - chw_hw, chw_z0, hx1, hy + chw_hw, chw_z1, "CHW", "PLENUM",
        )

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    f.write(OUT_PATH)
    return f


if __name__ == "__main__":
    build_model()
    print(f"Wrote {OUT_PATH}")
