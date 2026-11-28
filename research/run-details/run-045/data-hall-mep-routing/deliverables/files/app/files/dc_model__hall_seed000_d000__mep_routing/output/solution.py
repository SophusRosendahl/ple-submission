"""Coordinated 3D IFC4 model and clash-free MEP routing for Data Hall 1 (hall_seed000_d000).

Builds the hall background (128 racks, 6 structural columns, 22 CRAHs, 6 PDUs,
access floor, cold-aisle containment, 79 sprinkler heads) and routes three
connected services (telecom cable tray CT-1, power busway BW-1, chilled-water
pipe CHW-1) from the west-wall service entry at (0, 9900) mm.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
import math
import sys
from pathlib import Path
import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else str(
    Path(__file__).resolve().parent / "model.ifc"
)

# ---------------------------------------------------------------------------
# Baked architectural & MEP data from drawing sheets A-101..F-101
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
SOFFIT_Z = 3600.0
SLAB_Z = -900.0
FLOOR_THK = 35.0
CLEAR_HEIGHT_Z = 2600.0
CEIL_DEFLECTOR_Z = 3574.6
SPRINKLER_STANDOFF = 460.0
OVERHEAD_MAX_Z = CEIL_DEFLECTOR_Z - SPRINKLER_STANDOFF  # 3114.6 mm

COL_SIZE = 600.0
COL_XS = (8400.0, 16800.0, 25200.0)
COL_YS = (8400.0, 16800.0)

CA_EAST_X = 11400.0  # Common cross-aisle east edge (tile column T)

# Row definitions: (row_id, y_centre, facing, bay_sequence)
# Facing: "SOUTH" (-Y, rot=pi) or "NORTH" (+Y, rot=0)
ROW_DEFS = [
    ("A", 3000.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
      ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
      ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH",
     [("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1),
      ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
      ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
      ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1),
      ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4)]),
]

BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

# Perimeter CRAHs: B01 (600), P01 (9000), AC01 (16800), AQ01 (25200)
PERIM_CRAH_XS = (600.0, 9000.0, 16800.0, 25200.0)
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0

# PDUs: (tag, row, x_sw, y_front_of_row, facing)
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDU_DEFS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21000.0, 12000.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0, "NORTH"),
]

# Pathway section dimensions (mm)
TRAY_W, TRAY_H = 683.0, 127.0
BUS_W, BUS_H = 128.0, 147.0
CHW_BARE_OD = 114.3
CHW_INS_OD = 168.3  # 25.4 mm insulation + ASTM C585 jacket


def _seg_record(tag, service, pathway_tag, zone, p0, p1, w, h, is_pipe=False):
    """Build an axis-aligned service segment record from centreline p0->p1."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx, dy, dz = abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if dx >= dy and dx >= dz:
        axis = "X"
        aabb = (min(x0, x1), y0 - w / 2.0, z0 - h / 2.0,
                max(x0, x1), y0 + w / 2.0, z0 + h / 2.0)
    elif dy >= dx and dy >= dz:
        axis = "Y"
        aabb = (x0 - w / 2.0, min(y0, y1), z0 - h / 2.0,
                x0 + w / 2.0, max(y0, y1), z0 + h / 2.0)
    else:
        axis = "Z"
        aabb = (x0 - w / 2.0, y0 - w / 2.0, min(z0, z1),
                x0 + w / 2.0, y0 + w / 2.0, max(z0, z1))
    return {
        "tag": tag,
        "service": service,
        "pathway_tag": pathway_tag,
        "zone": zone,
        "p0": p0,
        "p1": p1,
        "axis": axis,
        "length": length,
        "w": w,
        "h": h,
        "is_pipe": is_pipe,
        "elevation": (z0 + z1) / 2.0,
        "aabb": aabb,
    }


def build_scene():
    """Construct all background and MEP geometry in millimetres."""
    racks = []
    crahs = []
    row_extents = {}

    # 1. Racks & In-Row CRAHs
    for row_id, yc, facing, seq in ROW_DEFS:
        x = 1800.0  # Tile column D
        y0 = yc - CAB_DEPTH / 2.0
        y1 = yc + CAB_DEPTH / 2.0
        cab_idx = 0
        cu_idx = 0
        west_end = 0.0
        east_end = 0.0
        for typ, cnt in seq:
            for _ in range(cnt):
                if typ == "CA":
                    west_end = x
                    x = CA_EAST_X
                    continue
                w = BAY_WIDTHS[typ]
                if typ in ("C1", "N1"):
                    cab_idx += 1
                    racks.append({
                        "tag": f"RACK-{row_id}{cab_idx:02d}",
                        "row": row_id,
                        "bay": cab_idx,
                        "type": typ,
                        "facing": facing,
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                    })
                elif typ == "CU":
                    cu_idx += 1
                    crahs.append({
                        "tag": f"CRAH-{row_id}{cu_idx:02d}",
                        "placement": "IN_ROW",
                        "row": row_id,
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "airflow_m3h": 9000.0,
                        "branch": "DN50",
                        "w": w,
                        "d": CAB_DEPTH,
                        "h": CAB_HEIGHT,
                        "aabb": (x, y0, 0.0, x + w, y1, CAB_HEIGHT),
                    })
                x += w
        east_end = x
        row_extents[row_id] = (1800.0, west_end, CA_EAST_X, east_end, yc)

    # 2. Perimeter CRAHs (south wall, facing NORTH)
    for idx, x0 in enumerate(PERIM_CRAH_XS, start=1):
        crahs.append({
            "tag": f"CRAH-{idx:02d}",
            "placement": "PERIMETER",
            "row": "PERIMETER",
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
            "branch": "DN100",
            "w": PERIM_CRAH_W,
            "d": PERIM_CRAH_D,
            "h": PERIM_CRAH_H,
            "aabb": (x0, 0.0, 0.0, x0 + PERIM_CRAH_W, PERIM_CRAH_D, PERIM_CRAH_H),
        })

    # 3. Structural Columns (0 to +3600)
    columns = []
    col_letters = ("A", "B", "C")
    for ci, cx in enumerate(COL_XS):
        for ri, cy in enumerate(COL_YS, start=1):
            columns.append({
                "tag": f"COL-{col_letters[ci]}{ri}",
                "w": COL_SIZE,
                "d": COL_SIZE,
                "h": SOFFIT_Z,
                "aabb": (cx - COL_SIZE / 2.0, cy - COL_SIZE / 2.0, 0.0,
                         cx + COL_SIZE / 2.0, cy + COL_SIZE / 2.0, SOFFIT_Z),
            })

    # 4. PDUs (front flush with front face of served row)
    pdus = []
    for tag, row_id, x0, y_front, facing in PDU_DEFS:
        if facing == "SOUTH":
            y0, y1 = y_front, y_front + PDU_D
        else:
            y0, y1 = y_front - PDU_D, y_front
        pdus.append({
            "tag": tag,
            "row": row_id,
            "facing": facing,
            "rating_kva": 225.0,
            "w": PDU_W,
            "d": PDU_D,
            "h": PDU_H,
            "aabb": (x0, y0, 0.0, x0 + PDU_W, y1, PDU_H),
        })

    # 5. Access Floor Slab (-35 to 0)
    floor = {
        "tag": "ACCESS-FLOOR",
        "aabb": (0.0, 0.0, -FLOOR_THK, ROOM_X, ROOM_Y, 0.0),
    }

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE)
    containment = []
    cac_specs = [
        ("CAC-BC", 7200.0, 1800.0, 9600.0, CA_EAST_X, 19200.0),
        ("CAC-DE", 12600.0, 1800.0, 9800.0, CA_EAST_X, 19200.0),
    ]
    for cac_tag, ayc, wx0, wx1, ex0, ex1 in cac_specs:
        # 2 roof panels (1400 wide, 55.5 thick, underside at 2000)
        for side, rx0, rx1 in (("W", wx0, wx1), ("E", ex0, ex1)):
            containment.append({
                "tag": f"{cac_tag}-ROOF-{side}",
                "kind": "ROOF",
                "aabb": (rx0, ayc - 700.0, 2000.0, rx1, ayc + 700.0, 2055.5),
            })
        # 4 end doors (60 thick, 1200 wide, 2055.5 high)
        for d_idx, dx in enumerate((wx0 - 60.0, wx1, ex0 - 60.0, ex1), start=1):
            containment.append({
                "tag": f"{cac_tag}-DOOR-{d_idx}",
                "kind": "DOOR",
                "aabb": (dx, ayc - 600.0, 0.0, dx + 60.0, ayc + 600.0, 2055.5),
            })

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle)
    sprinklers = []
    idx = 0
    for gx in range(1500, 27000, 3000):
        for gy in range(1500, 21000, 3000):
            idx += 1
            hx, hy = float(gx), float(gy)
            # Relocate heads inside 1500x1500 column keep-out
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                        hy = cy - 900.0
            sprinklers.append({
                "tag": f"SPR-C{idx:02d}",
                "mount": "Ceiling",
                "x": hx,
                "y": hy,
                "z": CEIL_DEFLECTOR_Z,
                "standoff": SPRINKLER_STANDOFF,
            })

    aisle_xs = (2400.0, 4800.0, 7200.0, 9000.0, 12000.0, 14400.0, 16800.0, 18600.0)
    a_idx = 0
    for ayc in (7200.0, 12600.0):
        for ax in aisle_xs:
            a_idx += 1
            sprinklers.append({
                "tag": f"SPR-A{a_idx:02d}",
                "mount": "InAisle",
                "x": ax,
                "y": ayc,
                "z": 1890.0,
                "standoff": SPRINKLER_STANDOFF,
            })

    # 8. MEP Routing — Three connected, clash-free, code-compliant networks
    segments = []

    # 8a. Telecom Cable Tray (CT-1): Overhead at Z = 2713.5 (Z in [2650, 2777])
    # Spine at X = 900; row branches at Y = Y_row + 700 (clear of all columns)
    z_tray = 2713.5
    x_tray_spine = 900.0
    tray_row_ys = [yc + 700.0 for _, yc, _, _ in ROW_DEFS]
    segments.append(_seg_record(
        "CT-ENTRY", "Telecom", "CT-1", "Overhead",
        (0.0, 9900.0, z_tray), (x_tray_spine, 9900.0, z_tray), TRAY_W, TRAY_H
    ))
    segments.append(_seg_record(
        "CT-SPINE", "Telecom", "CT-1", "Overhead",
        (x_tray_spine, min(tray_row_ys), z_tray),
        (x_tray_spine, max(tray_row_ys), z_tray), TRAY_W, TRAY_H
    ))
    for (row_id, yc, _, _), ty in zip(ROW_DEFS, tray_row_ys):
        rx_end = 17800.0  # > 88% of every row
        segments.append(_seg_record(
            f"CT-ROW-{row_id}", "Telecom", "CT-1", "Overhead",
            (x_tray_spine, ty, z_tray), (rx_end, ty, z_tray), TRAY_W, TRAY_H
        ))

    # 8b. Power Busway (BW-1): Under-Floor Plenum at Z = -300 (Z in [-373.5, -226.5])
    # Completely clear of access floor (-35..0), > 2876 mm vertical separation from tray
    z_bus = -300.0
    x_bus_spine = 600.0
    bus_row_ys = [yc - 450.0 for _, yc, _, _ in ROW_DEFS]
    segments.append(_seg_record(
        "BW-ENTRY", "Power", "BW-1", "UnderFloor",
        (0.0, 9900.0, z_bus), (x_bus_spine, 9900.0, z_bus), BUS_W, BUS_H
    ))
    segments.append(_seg_record(
        "BW-SPINE", "Power", "BW-1", "UnderFloor",
        (x_bus_spine, min(bus_row_ys), z_bus),
        (x_bus_spine, max(bus_row_ys), z_bus), BUS_W, BUS_H
    ))
    for (row_id, yc, _, _), by in zip(ROW_DEFS, bus_row_ys):
        rx_end = 17800.0
        segments.append(_seg_record(
            f"BW-ROW-{row_id}", "Power", "BW-1", "UnderFloor",
            (x_bus_spine, by, z_bus), (rx_end, by, z_bus), BUS_W, BUS_H
        ))

    # 8c. Chilled Water Pipe (CHW-1): Overhead at Z = 2950 (Z in [2865.85, 3034.15])
    # Above tray (2777) by 88.85 mm, below sprinkler standoff (3114.6) by 80.45 mm
    # Spine at X = 1200; row headers at Y = Y_row + 450 (clear of columns);
    # perimeter CRAH header at Y = 1200 from X = 1200 to X = 25200 (clear of PDUs)
    z_chw = 2950.0
    x_chw_spine = 1200.0
    chw_row_ys = [yc + 450.0 for _, yc, _, _ in ROW_DEFS]
    y_perim_chw = 1200.0
    segments.append(_seg_record(
        "CHW-ENTRY", "ChilledWater", "CHW-1", "Overhead",
        (0.0, 9900.0, z_chw), (x_chw_spine, 9900.0, z_chw),
        CHW_INS_OD, CHW_INS_OD, is_pipe=True
    ))
    segments.append(_seg_record(
        "CHW-SPINE", "ChilledWater", "CHW-1", "Overhead",
        (x_chw_spine, y_perim_chw, z_chw),
        (x_chw_spine, max(chw_row_ys), z_chw),
        CHW_INS_OD, CHW_INS_OD, is_pipe=True
    ))
    segments.append(_seg_record(
        "CHW-PERIM", "ChilledWater", "CHW-1", "Overhead",
        (x_chw_spine, y_perim_chw, z_chw), (25200.0, y_perim_chw, z_chw),
        CHW_INS_OD, CHW_INS_OD, is_pipe=True
    ))
    for (row_id, yc, _, _), cy in zip(ROW_DEFS, chw_row_ys):
        rx_end = 17800.0
        segments.append(_seg_record(
            f"CHW-ROW-{row_id}", "ChilledWater", "CHW-1", "Overhead",
            (x_chw_spine, cy, z_chw), (rx_end, cy, z_chw),
            CHW_INS_OD, CHW_INS_OD, is_pipe=True
        ))

    return {
        "racks": racks,
        "columns": columns,
        "crahs": crahs,
        "pdus": pdus,
        "floor": floor,
        "containment": containment,
        "sprinklers": sprinklers,
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# IFC4 Writer (uses ifcopenshell==0.8.4 + numpy only)
# ---------------------------------------------------------------------------
def _make_matrix(tx_mm, ty_mm, tz_mm, rot_z=0.0):
    """Return 4x4 placement matrix with translations in METRES."""
    c, s = math.cos(rot_z), math.sin(rot_z)
    m = np.eye(4, dtype=np.float64)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = tx_mm / 1000.0
    m[1, 3] = ty_mm / 1000.0
    m[2, 3] = tz_mm / 1000.0
    return m


def _make_pipe_matrix(p0, p1):
    """Return 4x4 placement matrix (translations in metres) with local +Z along p0->p1."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    v = np.array([x1 - x0, y1 - y0, z1 - z0], dtype=np.float64)
    L = float(np.linalg.norm(v))
    z_axis = v / L
    ref = np.array([0.0, 0.0, 1.0]) if abs(z_axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x_axis = np.cross(ref, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)
    m = np.eye(4, dtype=np.float64)
    m[:3, 0] = x_axis
    m[:3, 1] = y_axis
    m[:3, 2] = z_axis
    m[0, 3] = x0 / 1000.0
    m[1, 3] = y0 / 1000.0
    m[2, 3] = z0 / 1000.0
    return m


def _add_box_rep(model, body_ctx, w, d, h):
    """Create a centred 2D-profile box extrusion in millimetres."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        XDim=float(w),
        YDim=float(d),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    z_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=z_dir,
        Depth=float(h),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _add_cyl_rep(model, body_ctx, radius, length):
    """Create a 2D-circle-profile cylinder extrusion along +Z in millimetres."""
    pt2d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    pos2d = model.create_entity("IfcAxis2Placement2D", Location=pt2d)
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=pos2d,
        Radius=float(radius),
    )
    pt3d = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    pos3d = model.create_entity("IfcAxis2Placement3D", Location=pt3d)
    z_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos3d,
        ExtrudedDirection=z_dir,
        Depth=float(length),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def write_ifc(scene, out_path):
    import ifcopenshell
    import ifcopenshell.api

    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRES"})

    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    bldg = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[bldg], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=bldg)

    def place_box(ifc_class, name, aabb, predefined_type=None, object_type=None, facing="NORTH", pset_name=None, props=None):
        kw = {"ifc_class": ifc_class, "name": name}
        if predefined_type:
            kw["predefined_type"] = predefined_type
        el = ifcopenshell.api.run("root.create_entity", model, **kw)
        if object_type:
            el.ObjectType = object_type
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        x0, y0, z0, x1, y1, z1 = aabb
        w, d, h = x1 - x0, y1 - y0, z1 - z0
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rot_z = math.pi if facing == "SOUTH" else 0.0
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=_make_matrix(cx, cy, z0, rot_z))
        rep = _add_box_rep(model, body, w, d, h)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        if pset_name and props:
            ps = ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)
        return el

    # 1. Racks
    for r in scene["racks"]:
        place_box(
            "IfcFurniture", r["tag"], r["aabb"],
            predefined_type="USERDEFINED", object_type="Rack", facing=r["facing"],
            pset_name="Pset_DCM_Rack",
            props={
                "Row": r["row"], "Bay": r["bay"], "CabinetType": r["type"],
                "RU": 42, "Facing": r["facing"],
                "Width_mm": r["w"], "Depth_mm": r["d"], "Height_mm": r["h"],
            },
        )

    # 2. Structural Columns
    for c in scene["columns"]:
        place_box("IfcColumn", c["tag"], c["aabb"], predefined_type="COLUMN")

    # 3. CRAHs
    for c in scene["crahs"]:
        place_box(
            "IfcUnitaryEquipment", c["tag"], c["aabb"],
            predefined_type="AIRHANDLER", object_type="CRAH", facing=c["facing"],
            pset_name="Pset_DCM_CRAH",
            props={
                "Placement": c["placement"], "Capacity_kW": c["capacity_kw"],
                "Airflow_m3h": c["airflow_m3h"], "Facing": c["facing"],
                "BranchSize": c["branch"],
            },
        )

    # 4. PDUs
    for p in scene["pdus"]:
        place_box(
            "IfcElectricDistributionBoard", p["tag"], p["aabb"],
            predefined_type="DISTRIBUTIONBOARD", object_type="PDU", facing=p["facing"],
            pset_name="Pset_DCM_PDU",
            props={
                "ServesRow": p["row"], "Rating_kVA": p["rating_kva"],
                "Facing": p["facing"], "WorkingSpace_mm": 900.0,
            },
        )

    # 5. Access Floor
    place_box("IfcSlab", scene["floor"]["tag"], scene["floor"]["aabb"], predefined_type="FLOOR")

    # 6. Containment
    for ct in scene["containment"]:
        if ct["kind"] == "ROOF":
            place_box("IfcCovering", ct["tag"], ct["aabb"], predefined_type="CEILING", object_type="ContainmentRoof")
        else:
            place_box("IfcDoor", ct["tag"], ct["aabb"], predefined_type="DOOR", object_type="ContainmentDoor")

    # 7. Sprinklers (small 50x50x50 mm body at deflector elevation)
    for s in scene["sprinklers"]:
        el = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class="IfcFireSuppressionTerminal", name=s["tag"], predefined_type="SPRINKLER",
        )
        ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=el, matrix=_make_matrix(s["x"], s["y"], s["z"]))
        rep = _add_cyl_rep(model, body, 25.0, 25.0)
        ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
        ps = ifcopenshell.api.run("pset.add_pset", model, product=el, name="Pset_DCM_Sprinkler")
        ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={
            "MountType": s["mount"],
            "DeflectorElevation_mm": s["z"],
            "Standoff_mm": s["standoff"],
        })

    # 8. MEP Service Segments
    for seg in scene["segments"]:
        props = {
            "Service": seg["service"],
            "PathwayTag": seg["pathway_tag"],
            "Zone": seg["zone"],
            "Elevation_mm": seg["elevation"],
            "Length_mm": seg["length"],
        }
        if seg["is_pipe"]:
            props["BareOD_mm"] = CHW_BARE_OD
            props["InsulatedOD_mm"] = CHW_INS_OD
            el = ifcopenshell.api.run(
                "root.create_entity", model,
                ifc_class="IfcPipeSegment", name=seg["tag"], predefined_type="RIGIDSEGMENT",
            )
            ifcopenshell.api.run("spatial.assign_container", model, products=[el], relating_structure=storey)
            ifcopenshell.api.run(
                "geometry.edit_object_placement", model, product=el,
                matrix=_make_pipe_matrix(seg["p0"], seg["p1"]),
            )
            rep = _add_cyl_rep(model, body, seg["w"] / 2.0, seg["length"])
            ifcopenshell.api.run("geometry.assign_representation", model, product=el, representation=rep)
            ps = ifcopenshell.api.run("pset.add_pset", model, product=el, name="Pset_DCM_ServiceSegment")
            ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)
        elif seg["service"] == "Telecom":
            place_box(
                "IfcCableCarrierSegment", seg["tag"], seg["aabb"],
                predefined_type="CABLETRAYSEGMENT", object_type="CableTray",
                pset_name="Pset_DCM_ServiceSegment", props=props,
            )
        else:
            place_box(
                "IfcCableSegment", seg["tag"], seg["aabb"],
                predefined_type="BUSBARSEGMENT", object_type="Busway",
                pset_name="Pset_DCM_ServiceSegment", props=props,
            )

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out_path))


if __name__ == "__main__":
    scene_data = build_scene()
    write_ifc(scene_data, OUT_PATH)
