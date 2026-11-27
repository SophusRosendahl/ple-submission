"""Coordinated 3D IFC4 model builder for Meridian Data Center — Data Hall 1 (hall_seed000_d000).

Rebuilds the hall architecture, fit-out, containment, and sprinkler grid from the
seven-sheet drawing set (A-101, A-301, A-601, A-602, M-101, E-101, F-101) and routes
three clash-free, code-compliant MEP services (Telecom Cable Tray, Power Busway,
Chilled-Water Pipe) from their west-wall service entries.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
import math
import sys
from pathlib import Path

import numpy as np

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else str(Path(__file__).resolve().parent / "model.ifc")
)

# ---------------------------------------------------------------------------
# Hall constants (all dimensions in millimetres, baked from drawings)
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
FLOOR_THK = 35.0
PLENUM_BOTTOM = -900.0
SOFFIT_Z = 3600.0
DEFLECTOR_CEIL_Z = 3574.6
DEFLECTOR_AISLE_Z = 1890.0

# Pathway section dimensions (mm)
TRAY_W, TRAY_H = 683.0, 127.0       # CT-1
BUSWAY_W, BUSWAY_H = 128.0, 147.0   # BW-1
CHW_BARE_OD = 114.3                 # DN100
CHW_INSUL_THK = 25.4
CHW_OD = 168.3                      # ASTM C585 jacket OD over insulation

# Service elevations (centreline Z in mm relative to Finished Floor = 0)
# Three non-overlapping vertical tiers:
#   Power Busway  : Overhead   z_c = +2850.0 -> [2776.5, 2923.5] (>=2600 headroom, 651.1 below deflector)
#   Telecom Tray  : UnderFloor z_c =  -200.0 -> [-263.5, -136.5] (101.5 below -35 floor underside >= 20 mm)
#   Chilled Water : UnderFloor z_c =  -600.0 -> [-684.15, -515.85] (252.35 below tray, 215.85 above -900 slab)
BUSWAY_Z = 2850.0
TRAY_Z = -200.0
CHW_Z = -600.0


def _make_box_aabb(cx, cy, z0, dx, dy, dz):
    return (cx - dx / 2.0, cy - dy / 2.0, z0, cx + dx / 2.0, cy + dy / 2.0, z0 + dz)


def build_scene_data():
    """Return all background and MEP geometry in pure Python/mm for IFC build & verification."""
    # 1. Access floor (27000 x 21000 x 35 mm, top at z = 0)
    access_floor = {
        "name": "AccessFloor-Hall1",
        "cx": HALL_W / 2.0,
        "cy": HALL_D / 2.0,
        "z0": -FLOOR_THK,
        "dx": HALL_W,
        "dy": HALL_D,
        "dz": FLOOR_THK,
        "aabb": (0.0, 0.0, -FLOOR_THK, HALL_W, HALL_D, 0.0),
    }

    # 2. Structural columns (6 columns, 600 x 600 mm, z = 0..3600)
    col_xs = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
    col_ys = [("1", 8400.0), ("2", 16800.0)]
    columns = []
    for gx, cx in col_xs:
        for gy, cy in col_ys:
            columns.append({
                "name": f"COL-{gx}{gy}",
                "cx": cx,
                "cy": cy,
                "z0": 0.0,
                "dx": 600.0,
                "dy": 600.0,
                "dz": SOFFIT_Z,
                "aabb": _make_box_aabb(cx, cy, 0.0, 600.0, 600.0, SOFFIT_Z),
            })

    # 3. Cabinet rows & in-row CRAHs (A-101, A-601, M-101)
    # West half starts at x = 1800 (tile D); east half starts at x = 11400 (common CA east edge).
    row_specs = [
        ("A", 3000.0, "SOUTH",
         [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
         [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("B", 6000.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
         [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("C", 8400.0, "SOUTH",
         [("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1)],
         [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3)]),
        ("D", 11400.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
         [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("E", 13800.0, "SOUTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
         [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
        ("F", 16800.0, "NORTH",
         [("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1)],
         [("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4)]),
    ]
    bay_w = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}
    racks = []
    crahs = []
    for row_id, yc, facing, west_seq, east_seq in row_specs:
        rot_z = 0.0 if facing == "NORTH" else math.pi
        rack_idx = 0
        crah_idx = 0
        for x_start, seq in ((1800.0, west_seq), (11400.0, east_seq)):
            x = x_start
            for kind, count in seq:
                w = bay_w[kind]
                for _ in range(count):
                    cx = x + w / 2.0
                    if kind in ("C1", "N1"):
                        rack_idx += 1
                        racks.append({
                            "name": f"RACK-{row_id}{rack_idx:02d}",
                            "row": row_id,
                            "type": kind,
                            "cx": cx,
                            "cy": yc,
                            "z0": 0.0,
                            "dx": w,
                            "dy": 1200.0,
                            "dz": 2000.0,
                            "facing": facing,
                            "rot_z": rot_z,
                            "aabb": _make_box_aabb(cx, yc, 0.0, w, 1200.0, 2000.0),
                        })
                    elif kind == "CU":
                        crah_idx += 1
                        crahs.append({
                            "name": f"CRAH-{row_id}{crah_idx:02d}",
                            "placement": f"IN-ROW {row_id}",
                            "cx": cx,
                            "cy": yc,
                            "z0": 0.0,
                            "dx": 600.0,
                            "dy": 1200.0,
                            "dz": 2000.0,
                            "capacity_kw": 50.0,
                            "airflow_m3h": 9000.0,
                            "facing": facing,
                            "rot_z": rot_z,
                            "service": "CHILLED WATER, DN50",
                            "aabb": _make_box_aabb(cx, yc, 0.0, 600.0, 1200.0, 2000.0),
                        })
                    x += w

    # 4. Perimeter CRAHs (4 units: B01, P01, AC01, AQ01 -> 1200 x 900 x 2000, facing NORTH)
    perim_crahs = [
        ("CRAH-01", 600.0),
        ("CRAH-02", 9000.0),
        ("CRAH-03", 16800.0),
        ("CRAH-04", 25200.0),
    ]
    for name, x0 in perim_crahs:
        cx = x0 + 600.0
        cy = 450.0
        crahs.append({
            "name": name,
            "placement": "PERIMETER",
            "cx": cx,
            "cy": cy,
            "z0": 0.0,
            "dx": 1200.0,
            "dy": 900.0,
            "dz": 2000.0,
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
            "facing": "NORTH",
            "rot_z": 0.0,
            "service": "CHILLED WATER, DN100",
            "aabb": _make_box_aabb(cx, cy, 0.0, 1200.0, 900.0, 2000.0),
        })

    # 5. PDUs (6 units: 762 W x 813 D x 1959 H, front flush with served row front)
    pdu_specs = [
        ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
        ("PDU-02", "B", 21600.0, 6600.0 - 813.0, "NORTH"),
        ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
        ("PDU-04", "D", 21000.0, 12000.0 - 813.0, "NORTH"),
        ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
        ("PDU-06", "F", 21600.0, 17400.0 - 813.0, "NORTH"),
    ]
    pdus = []
    for name, row_id, x0, y0, facing in pdu_specs:
        cx = x0 + 762.0 / 2.0
        cy = y0 + 813.0 / 2.0
        pdus.append({
            "name": name,
            "serves_row": row_id,
            "cx": cx,
            "cy": cy,
            "z0": 0.0,
            "dx": 762.0,
            "dy": 813.0,
            "dz": 1959.0,
            "facing": facing,
            "rot_z": 0.0 if facing == "NORTH" else math.pi,
            "aabb": _make_box_aabb(cx, cy, 0.0, 762.0, 813.0, 1959.0),
        })

    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE: 2 roof panels + 4 end doors each)
    containment_roofs = []
    containment_doors = []
    cac_specs = [
        ("CAC-BC", 7200.0, (1800.0, 9600.0), (11400.0, 19400.0)),
        ("CAC-DE", 12600.0, (1800.0, 9800.0), (11400.0, 19200.0)),
    ]
    for tag, yc, (wx0, wx1), (ex0, ex1) in cac_specs:
        for side, (x0, x1) in (("W", (wx0, wx1)), ("E", (ex0, ex1))):
            w = x1 - x0
            cx = (x0 + x1) / 2.0
            containment_roofs.append({
                "name": f"{tag}-ROOF-{side}",
                "tag": tag,
                "cx": cx,
                "cy": yc,
                "z0": 2000.0,
                "dx": w,
                "dy": 1400.0,
                "dz": 55.5,
                "aabb": _make_box_aabb(cx, yc, 2000.0, w, 1400.0, 55.5),
            })
        # 4 end doors per aisle (60 mm thick x 1200 mm wide x 2055.5 mm high, placed outside roof ends)
        door_xs = [
            (f"{tag}-DOOR-W1", wx0 - 30.0),
            (f"{tag}-DOOR-W2", wx1 + 30.0),
            (f"{tag}-DOOR-E1", ex0 - 30.0),
            (f"{tag}-DOOR-E2", ex1 + 30.0),
        ]
        for dname, dxc in door_xs:
            containment_doors.append({
                "name": dname,
                "tag": tag,
                "cx": dxc,
                "cy": yc,
                "z0": 0.0,
                "dx": 60.0,
                "dy": 1200.0,
                "dz": 2055.5,
                "aabb": _make_box_aabb(dxc, yc, 0.0, 60.0, 1200.0, 2055.5),
            })

    # 7. Sprinklers (63 ceiling heads + 16 in-aisle heads per F-101)
    sprinklers = []
    col_centers = [(c["cx"], c["cy"]) for c in columns]
    idx = 0
    for iy in range(7):
        ny = 1500.0 + iy * 3000.0
        for ix in range(9):
            nx = 1500.0 + ix * 3000.0
            # Relocate clear of 1500 mm column keep-out (+-750 mm from column centre)
            hx, hy = nx, ny
            for ccx, ccy in col_centers:
                if abs(hx - ccx) < 750.0 and abs(hy - ccy) < 750.0:
                    hy = ccy - 900.0  # shift south clear of column keep-out
            idx += 1
            sprinklers.append({
                "name": f"SPR-CEIL-{idx:02d}",
                "head_type": "Ceiling",
                "cx": hx,
                "cy": hy,
                "z_deflector": DEFLECTOR_CEIL_Z,
                "radius": 25.0,
                "height": 25.4,
            })

    aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    aidx = 0
    for tag, yc in (("CAC-BC", 7200.0), ("CAC-DE", 12600.0)):
        for ax in aisle_xs:
            aidx += 1
            sprinklers.append({
                "name": f"SPR-AISLE-{aidx:02d}",
                "head_type": "InAisle",
                "aisle": tag,
                "cx": ax,
                "cy": yc,
                "z_deflector": DEFLECTOR_AISLE_Z,
                "radius": 25.0,
                "height": 110.0,
            })

    # 8. MEP Routes (straight axis-aligned segments)
    mep_segments = []

    def add_rect_seg(service, tag, name, zone, axis, p0, p1, w, h):
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        if axis == "X":
            xmin, xmax = min(x0, x1), max(x0, x1)
            length = xmax - xmin
            aabb = (xmin, y0 - w / 2.0, z0 - h / 2.0, xmax, y0 + w / 2.0, z0 + h / 2.0)
        else:  # "Y"
            ymin, ymax = min(y0, y1), max(y0, y1)
            length = ymax - ymin
            aabb = (x0 - w / 2.0, ymin, z0 - h / 2.0, x0 + w / 2.0, ymax, z0 + h / 2.0)
        mep_segments.append({
            "service": service,
            "tag": tag,
            "name": name,
            "zone": zone,
            "shape": "rect",
            "axis": axis,
            "p0": (min(x0, x1), min(y0, y1), z0),
            "length": length,
            "w": w,
            "h": h,
            "z_center": z0,
            "aabb": aabb,
        })

    def add_pipe_seg(name, zone, axis, p0, p1, od):
        x0, y0, z0 = p0
        x1, y1, z1 = p1
        r = od / 2.0
        if axis == "X":
            xmin, xmax = min(x0, x1), max(x0, x1)
            length = xmax - xmin
            aabb = (xmin, y0 - r, z0 - r, xmax, y0 + r, z0 + r)
        else:  # "Y"
            ymin, ymax = min(y0, y1), max(y0, y1)
            length = ymax - ymin
            aabb = (x0 - r, ymin, z0 - r, x0 + r, ymax, z0 + r)
        mep_segments.append({
            "service": "ChilledWater",
            "tag": "CHW-1",
            "name": name,
            "zone": zone,
            "shape": "pipe",
            "axis": axis,
            "p0": (min(x0, x1), min(y0, y1), z0),
            "length": length,
            "od": od,
            "z_center": z0,
            "aabb": aabb,
        })

    # Shared trunk X = 900 mm (inside west service strip, clear of columns & racks)
    trunk_x = 900.0

    # --- Power Busway (BW-1, Overhead z = 2850 mm) ---
    add_rect_seg("Power", "BW-1", "BW-ENTRY", "Overhead", "X", (0.0, 9900.0, BUSWAY_Z), (trunk_x, 9900.0, BUSWAY_Z), BUSWAY_W, BUSWAY_H)
    add_rect_seg("Power", "BW-1", "BW-TRUNK", "Overhead", "Y", (trunk_x, 4500.0, BUSWAY_Z), (trunk_x, 15300.0, BUSWAY_Z), BUSWAY_W, BUSWAY_H)
    add_rect_seg("Power", "BW-1", "BW-HDR-AB", "Overhead", "X", (trunk_x, 4500.0, BUSWAY_Z), (19800.0, 4500.0, BUSWAY_Z), BUSWAY_W, BUSWAY_H)
    add_rect_seg("Power", "BW-1", "BW-HDR-CD", "Overhead", "X", (trunk_x, 9900.0, BUSWAY_Z), (19800.0, 9900.0, BUSWAY_Z), BUSWAY_W, BUSWAY_H)
    add_rect_seg("Power", "BW-1", "BW-HDR-EF", "Overhead", "X", (trunk_x, 15300.0, BUSWAY_Z), (20200.0, 15300.0, BUSWAY_Z), BUSWAY_W, BUSWAY_H)

    # --- Telecom Cable Tray (CT-1, UnderFloor z = -200 mm) ---
    add_rect_seg("Telecom", "CT-1", "CT-ENTRY", "UnderFloor", "X", (0.0, 9900.0, TRAY_Z), (trunk_x, 9900.0, TRAY_Z), TRAY_W, TRAY_H)
    add_rect_seg("Telecom", "CT-1", "CT-TRUNK", "UnderFloor", "Y", (trunk_x, 4500.0, TRAY_Z), (trunk_x, 15300.0, TRAY_Z), TRAY_W, TRAY_H)
    add_rect_seg("Telecom", "CT-1", "CT-HDR-AB", "UnderFloor", "X", (trunk_x, 4500.0, TRAY_Z), (19800.0, 4500.0, TRAY_Z), TRAY_W, TRAY_H)
    add_rect_seg("Telecom", "CT-1", "CT-HDR-CD", "UnderFloor", "X", (trunk_x, 9900.0, TRAY_Z), (19800.0, 9900.0, TRAY_Z), TRAY_W, TRAY_H)
    add_rect_seg("Telecom", "CT-1", "CT-HDR-EF", "UnderFloor", "X", (trunk_x, 15300.0, TRAY_Z), (20200.0, 15300.0, TRAY_Z), TRAY_W, TRAY_H)

    # --- Chilled Water Pipe (CHW-1, UnderFloor z = -600 mm, OD = 168.3 mm incl. insulation) ---
    add_pipe_seg("CHW-ENTRY", "UnderFloor", "X", (0.0, 9900.0, CHW_Z), (trunk_x, 9900.0, CHW_Z), CHW_OD)
    add_pipe_seg("CHW-TRUNK", "UnderFloor", "Y", (trunk_x, 1500.0, CHW_Z), (trunk_x, 15300.0, CHW_Z), CHW_OD)
    add_pipe_seg("CHW-HDR-PERIM", "UnderFloor", "X", (trunk_x, 1500.0, CHW_Z), (25800.0, 1500.0, CHW_Z), CHW_OD)
    add_pipe_seg("CHW-HDR-AB", "UnderFloor", "X", (trunk_x, 4500.0, CHW_Z), (19800.0, 4500.0, CHW_Z), CHW_OD)
    add_pipe_seg("CHW-HDR-CD", "UnderFloor", "X", (trunk_x, 9900.0, CHW_Z), (19800.0, 9900.0, CHW_Z), CHW_OD)
    add_pipe_seg("CHW-HDR-EF", "UnderFloor", "X", (trunk_x, 15300.0, CHW_Z), (20200.0, 15300.0, CHW_Z), CHW_OD)

    return {
        "access_floor": access_floor,
        "columns": columns,
        "racks": racks,
        "crahs": crahs,
        "pdus": pdus,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "sprinklers": sprinklers,
        "mep_segments": mep_segments,
    }


def _mat_z_rot(x_mm, y_mm, z_mm, rot_z=0.0):
    """4x4 placement matrix with Z rotation and translation in METRES."""
    c, s = math.cos(rot_z), math.sin(rot_z)
    m = np.eye(4, dtype=np.float64)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def _mat_mep_axis(axis, p0_mm):
    """4x4 placement matrix orienting local +Z along world +X or +Y, translation in METRES."""
    x_mm, y_mm, z_mm = p0_mm
    m = np.eye(4, dtype=np.float64)
    if axis == "X":
        # local +X -> world +Y, local +Y -> world +Z, local +Z -> world +X (det = +1)
        m[0:3, 0:3] = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    elif axis == "Y":
        # local +X -> world -X, local +Y -> world +Z, local +Z -> world +Y (det = +1)
        m[0:3, 0:3] = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def build_ifc(out_path):
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.project
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    scene = build_scene_data()

    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1"
    )
    ifcopenshell.api.unit.assign_unit(
        model, length={"is_metric": True, "raw": "MILLIMETRE"}
    )

    ctx_model = ifcopenshell.api.context.add_context(model, context_type="Model")
    ctx_body = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx_model,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Phase 1")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Finished Floor")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))

    def attach_box(elem, dx, dy, dz, matrix):
        profile = model.create_entity(
            "IfcRectangleProfileDef", ProfileType="AREA", XDim=float(dx), YDim=float(dy)
        )
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            ExtrudedDirection=extrude_dir,
            Depth=float(dz),
        )
        rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=ctx_body,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=matrix)

    def attach_cyl(elem, radius, depth, matrix):
        profile = model.create_entity(
            "IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius)
        )
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            ExtrudedDirection=extrude_dir,
            Depth=float(depth),
        )
        rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=ctx_body,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid],
        )
        elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=matrix)

    def add_pset(elem, pset_name, props):
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)

    products = []

    # Access floor
    af = scene["access_floor"]
    e_af = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcSlab", predefined_type="FLOOR", name=af["name"]
    )
    e_af.ObjectType = "AccessFloor"
    attach_box(e_af, af["dx"], af["dy"], af["dz"], _mat_z_rot(af["cx"], af["cy"], af["z0"]))
    products.append(e_af)

    # Structural columns
    for c in scene["columns"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcColumn", predefined_type="COLUMN", name=c["name"]
        )
        attach_box(e, c["dx"], c["dy"], c["dz"], _mat_z_rot(c["cx"], c["cy"], c["z0"]))
        products.append(e)

    # Racks (IfcFurniture / USERDEFINED / "Rack")
    for r in scene["racks"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcFurniture", predefined_type="USERDEFINED", name=r["name"]
        )
        e.ObjectType = "Rack"
        attach_box(e, r["dx"], r["dy"], r["dz"], _mat_z_rot(r["cx"], r["cy"], r["z0"], r["rot_z"]))
        add_pset(e, "Pset_DCM_Rack", {
            "Row": r["row"],
            "CabinetType": r["type"],
            "Width_mm": float(r["dx"]),
            "Depth_mm": float(r["dy"]),
            "Height_mm": float(r["dz"]),
            "RU": 42,
            "Facing": r["facing"],
            "Power_kW": 8.0,
            "Load_kg": 1363.0,
        })
        products.append(e)

    # CRAHs
    for c in scene["crahs"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRHANDLER", name=c["name"]
        )
        e.ObjectType = "CRAH"
        attach_box(e, c["dx"], c["dy"], c["dz"], _mat_z_rot(c["cx"], c["cy"], c["z0"], c["rot_z"]))
        add_pset(e, "Pset_DCM_Equipment", {
            "EquipmentType": "CRAH",
            "Placement": c["placement"],
            "Capacity_kW": float(c["capacity_kw"]),
            "Airflow_m3h": float(c["airflow_m3h"]),
            "Facing": c["facing"],
            "Service": c["service"],
        })
        products.append(e)

    # PDUs
    for p in scene["pdus"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcElectricDistributionBoard", predefined_type="DISTRIBUTIONBOARD", name=p["name"]
        )
        e.ObjectType = "PDU"
        attach_box(e, p["dx"], p["dy"], p["dz"], _mat_z_rot(p["cx"], p["cy"], p["z0"], p["rot_z"]))
        add_pset(e, "Pset_DCM_Equipment", {
            "EquipmentType": "PDU",
            "ServesRow": p["serves_row"],
            "Rating_kVA": 225.0,
            "Facing": p["facing"],
            "WorkingSpace_mm": 900.0,
            "DedicatedSpaceAbove_mm": 1800.0,
        })
        products.append(e)

    # Containment roofs & doors
    for rf in scene["containment_roofs"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcCovering", predefined_type="CEILING", name=rf["name"]
        )
        e.ObjectType = "ContainmentRoof"
        attach_box(e, rf["dx"], rf["dy"], rf["dz"], _mat_z_rot(rf["cx"], rf["cy"], rf["z0"]))
        products.append(e)

    for dr in scene["containment_doors"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcDoor", predefined_type="DOOR", name=dr["name"]
        )
        e.ObjectType = "ContainmentDoor"
        attach_box(e, dr["dx"], dr["dy"], dr["dz"], _mat_z_rot(dr["cx"], dr["cy"], dr["z0"]))
        products.append(e)

    # Sprinklers
    for s in scene["sprinklers"]:
        e = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=s["name"]
        )
        e.ObjectType = "SprinklerHead"
        attach_cyl(e, s["radius"], s["height"], _mat_z_rot(s["cx"], s["cy"], s["z_deflector"]))
        add_pset(e, "Pset_DCM_Sprinkler", {
            "HeadType": s["head_type"],
            "DeflectorElevation_mm": float(s["z_deflector"]),
            "Standoff_mm": 460.0,
        })
        products.append(e)

    # MEP segments
    for m in scene["mep_segments"]:
        if m["service"] == "Telecom":
            e = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcCableCarrierSegment", predefined_type="CABLETRAYSEGMENT", name=m["name"]
            )
            e.ObjectType = "CableTray"
            attach_box(e, m["w"], m["h"], m["length"], _mat_mep_axis(m["axis"], m["p0"]))
            add_pset(e, "Pset_DCM_MEP", {
                "Service": "Telecom",
                "Tag": m["tag"],
                "Zone": m["zone"],
                "Elevation_mm": float(m["z_center"]),
                "Width_mm": float(m["w"]),
                "Height_mm": float(m["h"]),
            })
        elif m["service"] == "Power":
            e = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcCableCarrierSegment", predefined_type="USERDEFINED", name=m["name"]
            )
            e.ObjectType = "Busway"
            attach_box(e, m["w"], m["h"], m["length"], _mat_mep_axis(m["axis"], m["p0"]))
            add_pset(e, "Pset_DCM_MEP", {
                "Service": "Power",
                "Tag": m["tag"],
                "Zone": m["zone"],
                "Elevation_mm": float(m["z_center"]),
                "Width_mm": float(m["w"]),
                "Height_mm": float(m["h"]),
                "MaxSupportSpacing_mm": 1500.0,
            })
        else:  # ChilledWater
            e = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcPipeSegment", predefined_type="RIGIDSEGMENT", name=m["name"]
            )
            e.ObjectType = "ChilledWaterPipe"
            attach_cyl(e, m["od"] / 2.0, m["length"], _mat_mep_axis(m["axis"], m["p0"]))
            add_pset(e, "Pset_DCM_MEP", {
                "Service": "ChilledWater",
                "Tag": m["tag"],
                "Zone": m["zone"],
                "Elevation_mm": float(m["z_center"]),
                "BareOD_mm": CHW_BARE_OD,
                "Insulation_mm": CHW_INSUL_THK,
                "InsulatedOD_mm": float(m["od"]),
            })
        products.append(e)

    ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=products)

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out_file))


if __name__ == "__main__":
    build_ifc(OUT_PATH)
