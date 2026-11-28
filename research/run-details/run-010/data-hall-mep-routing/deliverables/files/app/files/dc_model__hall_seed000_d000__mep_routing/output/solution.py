"""Coordinated IFC4 3D model generator for Data Hall 1 (hall_seed000_d000).

Rebuilds the architectural/structural/equipment background from sheets A-101,
A-301, A-601, A-602, E-101, F-101, and M-101, and routes three clash-free,
code-compliant MEP networks (telecom cable tray CT-1, power busway BW-1,
chilled-water pipe CHW-1).

Usage:
    python output/solution.py [output/model.ifc]
"""

import math
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


OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# ---------------------------------------------------------------------------
# Hall constants (mm) reconciled from A-101, A-301, A-601, A-602, E-101, F-101, M-101
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
TILE_SIZE = 600.0

Z_SLAB_TOP = -900.0
Z_FF = 0.0
FLOOR_PANEL_THK = 35.0
Z_SOFFIT = 3600.0
Z_MIN_CLEAR = 2600.0
Z_SPRINKLER_CEILING = 3600.0 - 25.4  # 3574.6 mm
SPRINKLER_STANDOFF = 460.0           # clear below deflector -> 3114.6 mm
Z_SPRINKLER_AISLE = 1890.0

COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

ROW_SPECS = [
    # (name, y_center, facing_deg, bay_sequence)
    # facing_deg: 0 = +Y (North), 180 = -Y (South)
    ("A", 3000.0, 180.0, "4C1·CU·3C1·N1·3C1·CU·CA·6C1·SP·CU·5C1"),
    ("B", 6000.0, 0.0,   "4C1·CU·5C1·2N1·CU·CA·7C1·SP·CU·5C1"),
    ("C", 8400.0, 180.0, "3C1·CU·6C1·2-600·CU·CA·N1·4C1·CU·SP·C1·2-600·3C1"),
    ("D", 11400.0, 0.0,  "4C1·CU·3C1·2N1·2C1·CU·CA·7C1·SP·CU·5C1"),
    ("E", 13800.0, 180.0,"4C1·CU·5C1·N1·C1·CU·CA·6C1·SP·CU·5C1"),
    ("F", 16800.0, 0.0,  "4C1·CU·5C1·2-600·CU·CA·2N1·5C1·SP·-600·CU·4C1"),
]

ROW_X_START = 1800.0        # Tile D (index 3 * 600)
CROSS_AISLE_X_EAST = 11400.0  # Common east edge of cross aisle (tile T)

PERIMETER_CRAHS = [
    # (tag, x_sw, y_sw)  1200 x 900 x 2000, facing North (+Y)
    ("CRAH-01", 600.0,   0.0),   # B01
    ("CRAH-02", 9000.0,  0.0),   # P01
    ("CRAH-03", 16800.0, 0.0),   # AC01
    ("CRAH-04", 25200.0, 0.0),   # AQ01
]

PDU_SPECS = [
    # (tag, row, x_sw, y_sw, facing_deg)  762 x 813 x 1959
    ("PDU-01", "A", 21000.0, 2400.0,          180.0),  # AJ05, front flush at Y=2400
    ("PDU-02", "B", 21600.0, 6600.0 - 813.0,  0.0),    # AK10, front flush at Y=6600
    ("PDU-03", "C", 21000.0, 7800.0,          180.0),  # AJ14, front flush at Y=7800
    ("PDU-04", "D", 21600.0, 12000.0 - 813.0, 0.0),    # AK19, front flush at Y=12000
    ("PDU-05", "E", 21000.0, 13200.0,         180.0),  # AJ23, front flush at Y=13200
    ("PDU-06", "F", 21600.0, 17400.0 - 813.0, 0.0),    # AK28, front flush at Y=17400
]

# MEP Section sizes (mm)
CT_W, CT_H = 683.0, 127.0       # Telecom cable tray
BW_W, BW_H = 128.0, 147.0       # Power busway
CHW_OD = 168.3                  # DN100 steel pipe + 25.4mm insulation jacket

# MEP Elevations (mm relative to FF = 0)
# - BW-1 overhead: Z = 2800..2947 (centre 2873.5) -> >2600 headroom, <3114.6 sprinkler standoff
# - CT-1 under-floor plenum: Z = -250..-123 (centre -186.5) -> >20mm clear below -35 panel
# - CHW-1 under-floor plenum: Z = -584.15..-415.85 (centre -500.0) -> clear of slab (-900) and CT-1
Z_BW_CENTER = 2873.5
Z_CT_CENTER = -186.5
Z_CHW_CENTER = -500.0


# ---------------------------------------------------------------------------
# Geometry & IFC helpers
# ---------------------------------------------------------------------------
def make_matrix(x_mm, y_mm, z_mm, rot_z_deg=0.0):
    """4x4 placement matrix with translations in METRES (for edit_object_placement)."""
    rad = math.radians(rot_z_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def make_box_rep(model, body_ctx, w_mm, d_mm, h_mm):
    """Extruded rectangular solid centered on XY=(0,0), Z from 0 to h_mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w_mm),
        YDim=float(d_mm),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(h_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cyl_rep(model, body_ctx, radius_mm, length_mm):
    """Extruded circular solid centered on XY=(0,0), Z from 0 to length_mm."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius_mm),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=direction,
        Depth=float(length_mm),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def add_box_element(
    model, storey, body_ctx, ifc_class, name,
    cx, cy, z_bot, w, d, h,
    rot_z_deg=0.0, predefined_type=None, object_type=None, pset_name=None, pset_props=None
):
    elem = ifcopenshell.api.root.create_entity(
        model, ifc_class=ifc_class, name=name, predefined_type=predefined_type
    )
    if object_type is not None:
        elem.ObjectType = object_type
    ifcopenshell.api.spatial.assign_container(model, products=[elem], relating_structure=storey)
    rep = make_box_rep(model, body_ctx, w, d, h)
    ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=elem, matrix=make_matrix(cx, cy, z_bot, rot_z_deg)
    )
    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=pset_props)
    return elem


def add_segment_rect(
    model, storey, body_ctx, ifc_class, name,
    p1, p2, width_mm, height_mm,
    predefined_type=None, object_type=None, pset_name=None, pset_props=None
):
    """Add an axis-aligned rectangular MEP segment from p1=(x1,y1,z1) to p2=(x2,y2,z2)."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    cx, cy = 0.5 * (x1 + x2), 0.5 * (y1 + y2)
    z_bot = min(z1, z2) - 0.5 * height_mm

    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        w, d, h = abs(dx), width_mm, height_mm
    elif abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        w, d, h = width_mm, abs(dy), height_mm
    else:
        # Vertical riser
        w, d, h = width_mm, width_mm, abs(dz)
        z_bot = min(z1, z2)

    return add_box_element(
        model, storey, body_ctx, ifc_class, name,
        cx, cy, z_bot, w, d, h,
        predefined_type=predefined_type,
        object_type=object_type,
        pset_name=pset_name,
        pset_props=pset_props,
    )


def add_pipe_segment(
    model, storey, body_ctx, name, p1, p2, od_mm,
    pset_name=None, pset_props=None
):
    """Add an axis-aligned cylindrical pipe segment from p1 to p2."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-3:
        return None

    elem = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcPipeSegment", name=name, predefined_type="RIGIDSEGMENT"
    )
    elem.ObjectType = "CHW-1"
    ifcopenshell.api.spatial.assign_container(model, products=[elem], relating_structure=storey)
    rep = make_cyl_rep(model, body_ctx, od_mm / 2.0, length)
    ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)

    # Local +Z of cylinder aligned to segment direction
    ux, uy, uz = dx / length, dy / length, dz / length
    m = np.eye(4, dtype=float)
    if abs(uz) > 0.999:
        if uz < 0:
            m[1, 1] = -1.0
            m[2, 2] = -1.0
    elif abs(ux) > 0.999:
        # Rotate +Z to +/-X
        s = 1.0 if ux > 0 else -1.0
        m[:3, 0] = [0.0, 0.0, -s]
        m[:3, 1] = [0.0, 1.0, 0.0]
        m[:3, 2] = [s, 0.0, 0.0]
    else:
        # Rotate +Z to +/-Y
        s = 1.0 if uy > 0 else -1.0
        m[:3, 0] = [1.0, 0.0, 0.0]
        m[:3, 1] = [0.0, 0.0, -s]
        m[:3, 2] = [0.0, s, 0.0]

    m[0, 3] = x1 / 1000.0
    m[1, 3] = y1 / 1000.0
    m[2, 3] = z1 / 1000.0
    ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=m)

    if pset_name and pset_props:
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=pset_props)
    return elem


def parse_row_bays(seq_str):
    """Parse A-601 bay sequence into list of (kind, width_mm) for West and East halves."""
    west_str, east_str = seq_str.split("·CA·")

    def parse_half(s):
        items = []
        for tok in s.split("·"):
            if tok.startswith("-"):
                items.append(("OMIT", float(tok[1:])))
            elif "-" in tok:
                cnt, w = tok.split("-")
                for _ in range(int(cnt)):
                    items.append(("OMIT", float(w)))
            elif tok == "CU":
                items.append(("CU", 600.0))
            elif tok == "SP":
                items.append(("SP", 600.0))
            elif tok.endswith("C1"):
                cnt = int(tok[:-2]) if tok[:-2] else 1
                for _ in range(cnt):
                    items.append(("C1", 600.0))
            elif tok.endswith("N1"):
                cnt = int(tok[:-2]) if tok[:-2] else 1
                for _ in range(cnt):
                    items.append(("N1", 800.0))
            else:
                raise ValueError(f"Unknown bay token: {tok}")
        return items

    return parse_half(west_str), parse_half(east_str)


# ---------------------------------------------------------------------------
# Main model builder
# ---------------------------------------------------------------------------
def build_model():
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1"
    )
    length_unit = ifcopenshell.api.unit.add_si_unit(
        model, unit_type="LENGTHUNIT", prefix="MILLI"
    )
    area_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit, area_unit, vol_unit])

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuilding", name="Phase 1"
    )
    storey = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Data Hall 1"
    )
    ifcopenshell.api.spatial.assign_container(model, products=[], relating_structure=storey)
    ifcopenshell.api.aggregate.assign_object(model, products=[site], relating_object=project)
    ifcopenshell.api.aggregate.assign_object(model, products=[building], relating_object=site)
    ifcopenshell.api.aggregate.assign_object(model, products=[storey], relating_object=building)

    # 1. Access Floor Panel (35 mm thick, top at Z=0) & Structural Slab (top at Z=-900)
    add_box_element(
        model, storey, body_ctx, "IfcSlab", "Access Floor",
        HALL_W / 2.0, HALL_D / 2.0, -FLOOR_PANEL_THK,
        HALL_W, HALL_D, FLOOR_PANEL_THK,
        predefined_type="FLOOR",
        object_type="AccessFloor",
    )
    add_box_element(
        model, storey, body_ctx, "IfcSlab", "Structural Floor Slab",
        HALL_W / 2.0, HALL_D / 2.0, Z_SLAB_TOP - 200.0,
        HALL_W, HALL_D, 200.0,
        predefined_type="BASESLAB",
        object_type="StructuralSlab",
    )

    # 2. Structural Columns (600 x 600, Z = 0 to 3600)
    col_idx = 1
    for cx in COL_XS:
        for cy in COL_YS:
            add_box_element(
                model, storey, body_ctx, "IfcColumn", f"COL-{col_idx:02d}",
                cx, cy, Z_FF, COL_SIZE, COL_SIZE, Z_SOFFIT,
                predefined_type="COLUMN",
                pset_name="Pset_DCM_Structure",
                pset_props={"GridX_mm": cx, "GridY_mm": cy},
            )
            col_idx += 1

    # 3. Cabinet Rows & In-Row CRAHs
    row_extents = {}
    for row_name, y_c, facing_deg, seq_str in ROW_SPECS:
        west_bays, east_bays = parse_row_bays(seq_str)
        rack_num = 1
        crah_num = 1

        def place_bays(bays, x_cursor):
            nonlocal rack_num, crah_num
            for kind, bw in bays:
                cx = x_cursor + bw / 2.0
                if kind in ("C1", "N1"):
                    add_box_element(
                        model, storey, body_ctx, "IfcFurniture",
                        f"RACK-{row_name}{rack_num:02d}",
                        cx, y_c, Z_FF, bw, 1200.0, 2000.0,
                        rot_z_deg=facing_deg,
                        predefined_type="USERDEFINED",
                        object_type="Rack",
                        pset_name="Pset_DCM_Cabinet",
                        pset_props={
                            "Row": row_name,
                            "CabinetType": kind,
                            "Power_kW": 8.0,
                            "RU": 42,
                        },
                    )
                    rack_num += 1
                elif kind == "CU":
                    add_box_element(
                        model, storey, body_ctx, "IfcUnitaryEquipment",
                        f"CRAH-{row_name}{crah_num:02d}",
                        cx, y_c, Z_FF, bw, 1200.0, 2000.0,
                        rot_z_deg=facing_deg,
                        predefined_type="AIRHANDLER",
                        object_type="CRAH",
                        pset_name="Pset_DCM_CRAH",
                        pset_props={
                            "Placement": f"ROW {row_name}",
                            "Capacity_kW": 50.0,
                            "Service": "CHW DN50",
                        },
                    )
                    crah_num += 1
                x_cursor += bw
            return x_cursor

        place_bays(west_bays, ROW_X_START)
        x_end = place_bays(east_bays, CROSS_AISLE_X_EAST)
        row_extents[row_name] = (ROW_X_START, x_end, y_c)

    # 4. Perimeter CRAHs
    for tag, x_sw, y_sw in PERIMETER_CRAHS:
        add_box_element(
            model, storey, body_ctx, "IfcUnitaryEquipment", tag,
            x_sw + 600.0, y_sw + 450.0, Z_FF, 1200.0, 900.0, 2000.0,
            rot_z_deg=0.0,
            predefined_type="AIRHANDLER",
            object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "PERIMETER",
                "Capacity_kW": 100.0,
                "Service": "CHW DN100",
            },
        )

    # 5. PDUs
    for tag, row_name, x_sw, y_sw, facing_deg in PDU_SPECS:
        add_box_element(
            model, storey, body_ctx, "IfcElectricDistributionBoard", tag,
            x_sw + 762.0 / 2.0, y_sw + 813.0 / 2.0, Z_FF,
            762.0, 813.0, 1959.0,
            rot_z_deg=facing_deg,
            predefined_type="DISTRIBUTIONBOARD",
            object_type="PDU",
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": row_name,
                "Rating_kVA": 225.0,
                "DedicatedSpaceAbove_mm": 1800.0,
            },
        )

    # 6. Cold-Aisle Containment (CAC-BC at Y=7200, CAC-DE at Y=12600)
    for cac_tag, y_aisle in [("CAC-BC", 7200.0), ("CAC-DE", 12600.0)]:
        for half_idx, (x0, x1) in enumerate([(1800.0, 9600.0), (11400.0, 19200.0)], 1):
            # Roof panel: 1400 mm wide, 55.5 mm thick, underside at Z=2000
            add_box_element(
                model, storey, body_ctx, "IfcCovering",
                f"{cac_tag}-ROOF-{half_idx}",
                0.5 * (x0 + x1), y_aisle, 2000.0,
                x1 - x0, 1400.0, 55.5,
                predefined_type="CEILING",
                object_type="ContainmentRoof",
                pset_name="Pset_DCM_Containment",
                pset_props={"Tag": cac_tag},
            )
            # End doors: 60 mm thick x 1200 mm wide x 2055.5 mm tall
            for end_idx, xd in enumerate([x0 + 30.0, x1 - 30.0], 1):
                add_box_element(
                    model, storey, body_ctx, "IfcDoor",
                    f"{cac_tag}-DOOR-{half_idx}-{end_idx}",
                    xd, y_aisle, Z_FF,
                    60.0, 1200.0, 2055.5,
                    predefined_type="DOOR",
                    object_type="ContainmentDoor",
                )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle)
    sp_idx = 1
    for ix in range(9):
        sx = 1500.0 + ix * 3000.0
        for iy in range(7):
            sy = 1500.0 + iy * 3000.0
            # Relocate heads falling inside column keep-out
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 600.0 and abs(sy - cy) < 600.0:
                        sx_adj = sx - 600.0 if sx <= cx else sx + 600.0
                        sx = sx_adj
            add_box_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal",
                f"SPK-C{sp_idx:02d}",
                sx, sy, Z_SPRINKLER_CEILING,
                50.0, 50.0, 25.4,
                predefined_type="SPRINKLER",
                object_type="CeilingSprinkler",
                pset_name="Pset_DCM_Sprinkler",
                pset_props={
                    "DeflectorElevation_mm": Z_SPRINKLER_CEILING,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )
            sp_idx += 1

    aisle_idx = 1
    for y_aisle in (7200.0, 12600.0):
        for sx in (2700.0, 4700.0, 6700.0, 8700.0, 12300.0, 14300.0, 16300.0, 18300.0):
            add_box_element(
                model, storey, body_ctx, "IfcFireSuppressionTerminal",
                f"SPK-A{aisle_idx:02d}",
                sx, y_aisle, Z_SPRINKLER_AISLE,
                50.0, 50.0, 110.0,
                predefined_type="SPRINKLER",
                object_type="InAisleSprinkler",
                pset_name="Pset_DCM_Sprinkler",
                pset_props={"DeflectorElevation_mm": Z_SPRINKLER_AISLE},
            )
            aisle_idx += 1

    # -----------------------------------------------------------------------
    # 8. MEP Routing — Three Connected, Clash-Free, Code-Compliant Networks
    # -----------------------------------------------------------------------
    # Service entry on West wall: X = 0, Y = 9900 (per E-101 & M-101)
    #
    # 8a. Power Busway (BW-1, 128 x 147) — OVERHEAD at Z_center = 2873.5
    #     Main N-S trunk at X = 900 (clear of all racks & columns).
    #     Row branches at Y = Y_row + 500 (clears columns at Y=8400, 16800).
    bw_seg = 1
    bw_x_trunk = 900.0
    bw_ys = [y_c + 500.0 for _, y_c, _, _ in ROW_SPECS]

    # Entry stub from X=0, Y=9900 to trunk X=900, Y=9900
    add_segment_rect(
        model, storey, body_ctx, "IfcCableSegment", f"BW-SEG-{bw_seg:02d}",
        (0.0, 9900.0, Z_BW_CENTER), (bw_x_trunk, 9900.0, Z_BW_CENTER),
        BW_W, BW_H, predefined_type="BUSBARSEGMENT", object_type="BW-1",
        pset_name="Pset_DCM_MEP",
        pset_props={"Service": "BW-1", "Zone": "Overhead", "ElevationFF_mm": Z_BW_CENTER},
    )
    bw_seg += 1

    # Main N-S trunk from Row A branch (3500) to Row F branch (17300)
    add_segment_rect(
        model, storey, body_ctx, "IfcCableSegment", f"BW-SEG-{bw_seg:02d}",
        (bw_x_trunk, min(bw_ys), Z_BW_CENTER), (bw_x_trunk, max(bw_ys), Z_BW_CENTER),
        BW_W, BW_H, predefined_type="BUSBARSEGMENT", object_type="BW-1",
        pset_name="Pset_DCM_MEP",
        pset_props={"Service": "BW-1", "Zone": "Overhead", "ElevationFF_mm": Z_BW_CENTER},
    )
    bw_seg += 1

    # Row branches
    for row_name, y_c, _, _ in ROW_SPECS:
        _, x_end, _ = row_extents[row_name]
        yb = y_c + 500.0
        add_segment_rect(
            model, storey, body_ctx, "IfcCableSegment", f"BW-SEG-{bw_seg:02d}",
            (bw_x_trunk, yb, Z_BW_CENTER), (x_end - 300.0, yb, Z_BW_CENTER),
            BW_W, BW_H, predefined_type="BUSBARSEGMENT", object_type="BW-1",
            pset_name="Pset_DCM_MEP",
            pset_props={"Service": "BW-1", "Zone": "Overhead", "ElevationFF_mm": Z_BW_CENTER},
        )
        bw_seg += 1

    # 8b. Telecom Cable Tray (CT-1, 683 x 127) — UNDER-FLOOR PLENUM at Z_center = -186.5
    #     Vertical separation from overhead BW-1 = 2923 mm >> 300 mm everywhere.
    #     Top at -123 mm (88 mm below -35 floor panel underside, >20 mm required).
    ct_seg = 1
    ct_x_trunk = 900.0
    ct_ys = [y_c for _, y_c, _, _ in ROW_SPECS]

    add_segment_rect(
        model, storey, body_ctx, "IfcCableCarrierSegment", f"CT-SEG-{ct_seg:02d}",
        (0.0, 9900.0, Z_CT_CENTER), (ct_x_trunk, 9900.0, Z_CT_CENTER),
        CT_W, CT_H, predefined_type="CABLETRAYSEGMENT", object_type="CT-1",
        pset_name="Pset_DCM_MEP",
        pset_props={"Service": "CT-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CT_CENTER},
    )
    ct_seg += 1

    add_segment_rect(
        model, storey, body_ctx, "IfcCableCarrierSegment", f"CT-SEG-{ct_seg:02d}",
        (ct_x_trunk, min(ct_ys), Z_CT_CENTER), (ct_x_trunk, max(ct_ys), Z_CT_CENTER),
        CT_W, CT_H, predefined_type="CABLETRAYSEGMENT", object_type="CT-1",
        pset_name="Pset_DCM_MEP",
        pset_props={"Service": "CT-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CT_CENTER},
    )
    ct_seg += 1

    for row_name, y_c, _, _ in ROW_SPECS:
        _, x_end, _ = row_extents[row_name]
        add_segment_rect(
            model, storey, body_ctx, "IfcCableCarrierSegment", f"CT-SEG-{ct_seg:02d}",
            (ct_x_trunk, y_c, Z_CT_CENTER), (x_end - 300.0, y_c, Z_CT_CENTER),
            CT_W, CT_H, predefined_type="CABLETRAYSEGMENT", object_type="CT-1",
            pset_name="Pset_DCM_MEP",
            pset_props={"Service": "CT-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CT_CENTER},
        )
        ct_seg += 1

    # 8c. Chilled-Water Pipe (CHW-1, OD 168.3 incl. insulation) — UNDER-FLOOR PLENUM at Z = -500.0
    #     Clear below CT-1 (-250) by 166 mm, clear above slab (-900) by 316 mm.
    #     Serves every cabinet row AND all 4 perimeter CRAHs (Y=1200, X=1200..25800).
    #     Never enters PDU footprints (X=21000..22362, Y>=2400).
    chw_seg = 1
    chw_x_trunk = 900.0

    # Entry stub from X=0, Y=9900 to trunk
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (0.0, 9900.0, Z_CHW_CENTER), (chw_x_trunk, 9900.0, Z_CHW_CENTER),
        CHW_OD, pset_name="Pset_DCM_MEP",
        pset_props={"Service": "CHW-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CHW_CENTER},
    )
    chw_seg += 1

    # Main N-S trunk from South perimeter gallery (Y=1200) to Row F (Y=16800)
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (chw_x_trunk, 1200.0, Z_CHW_CENTER), (chw_x_trunk, 16800.0, Z_CHW_CENTER),
        CHW_OD, pset_name="Pset_DCM_MEP",
        pset_props={"Service": "CHW-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CHW_CENTER},
    )
    chw_seg += 1

    # South perimeter CRAH header (Y=1200, X=900..25800) -> within 750 mm of CRAH-01..04
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (chw_x_trunk, 1200.0, Z_CHW_CENTER), (25800.0, 1200.0, Z_CHW_CENTER),
        CHW_OD, pset_name="Pset_DCM_MEP",
        pset_props={"Service": "CHW-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CHW_CENTER},
    )
    chw_seg += 1

    # Row headers (serving all 6 rows and their 18 in-row CRAHs)
    for row_name, y_c, _, _ in ROW_SPECS:
        _, x_end, _ = row_extents[row_name]
        add_pipe_segment(
            model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
            (chw_x_trunk, y_c, Z_CHW_CENTER), (x_end - 300.0, y_c, Z_CHW_CENTER),
            CHW_OD, pset_name="Pset_DCM_MEP",
            pset_props={"Service": "CHW-1", "Zone": "UnderFloor", "ElevationFF_mm": Z_CHW_CENTER},
        )
        chw_seg += 1

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)


if __name__ == "__main__":
    build_model()
