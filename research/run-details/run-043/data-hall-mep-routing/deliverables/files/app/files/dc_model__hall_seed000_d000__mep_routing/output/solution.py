"""Coordinated 3D IFC4 model builder for Data Hall 1 (dc_model hall_seed000_d000).

Self-contained script using only ifcopenshell==0.8.4 and numpy.
All dimensions, positions, schedules, and elevations are baked in as literals
reconciled from sheets A-101, A-301, A-601, A-602, E-101, F-101, and M-101.
"""
import math
import os
import sys
import numpy as np


# ---------------------------------------------------------------------------
# 1. Pure-Python / NumPy geometry specification (importable without ifcopenshell)
# ---------------------------------------------------------------------------

HALL_W = 27000.0
HALL_D = 21000.0
SOFFIT_Z = 3600.0
SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0

# Structural columns: 400 x 400 mm centred on Grid (A,B,C) x (1,2), Z = [0, 3600]
COL_SIZE = 400.0
COL_GRID_X = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
COL_GRID_Y = [("1", 8400.0), ("2", 16800.0)]

# Cabinet rows (A-101 & A-601): all start at X=1800, common CA east edge at X=11200
ROW_START_X = 1800.0
CA_EAST_X = 11200.0
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

ROW_SPECS = [
    ("A", 3000.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("B", 6000.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1)],
     [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("C", 8400.0, "SOUTH",
     [("C1", 3), ("CU", 1), ("C1", 6), ("GAP600", 2), ("CU", 1)],
     [("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("GAP600", 2), ("C1", 3)]),
    ("D", 11400.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1)],
     [("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("E", 13800.0, "SOUTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1)],
     [("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)]),
    ("F", 16800.0, "NORTH",
     [("C1", 4), ("CU", 1), ("C1", 5), ("GAP600", 2), ("CU", 1)],
     [("N1", 2), ("C1", 5), ("SP", 1), ("GAP600", 1), ("CU", 1), ("C1", 4)]),
]

BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "GAP600": 600.0}

# Perimeter CRAHs (A-601, A-101, M-101): 1200 x 900 x 2000, face NORTH (+Y)
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, A-101, E-101): 762 W x 813 D x 1959 H, front flush with served row
PDU_W, PDU_D, PDU_H = 762.0, 813.0, 1959.0
PDU_SPECS = [
    ("PDU-01", "A", "SOUTH", 21000.0, 2400.0),
    ("PDU-02", "B", "NORTH", 21600.0, 6600.0 - PDU_D),
    ("PDU-03", "C", "SOUTH", 21000.0, 7800.0),
    ("PDU-04", "D", "NORTH", 21600.0, 12000.0 - PDU_D),
    ("PDU-05", "E", "SOUTH", 21000.0, 13200.0),
    ("PDU-06", "F", "NORTH", 21600.0, 17400.0 - PDU_D),
]

# Pathway section dimensions (A-602, E-101, M-101)
TRAY_W, TRAY_H = 683.0, 127.0
BUS_W, BUS_H = 128.0, 147.0
CHW_OD = 168.3  # DN100 bare 114.3 mm + 25.4 mm insulation -> 168.3 mm ASTM C585 jacket

# Service elevation tiers (mm relative to Finished Floor = 0)
# Busway overhead: Z = [2800, 2947] (>= 2600 headroom, <= 3115 sprinkler standoff)
BUS_Z0 = 2800.0
BUS_ZC = BUS_Z0 + BUS_H / 2.0
# Cable tray under-floor: Z = [-250, -123] (<= -55 clearance below -35 panel)
TRAY_Z0 = -250.0
TRAY_ZC = TRAY_Z0 + TRAY_H / 2.0
# CHW under-floor: Z = [-650, -481.7] (>= -900 slab, 231.7 mm clear below tray)
CHW_ZC = -565.85


def _seg_rect(name, service, x0, y0, x1, y1, z0, w, h):
    """Build an axis-aligned rectangular route segment dict with AABB."""
    if abs(y1 - y0) < 1e-6:  # East-West along X
        xmin, xmax = min(x0, x1), max(x0, x1)
        ymin, ymax = y0 - w / 2.0, y0 + w / 2.0
        axis = "X"
        length = xmax - xmin
    else:  # North-South along Y
        xmin, xmax = x0 - w / 2.0, x0 + w / 2.0
        ymin, ymax = min(y0, y1), max(y0, y1)
        axis = "Y"
        length = ymax - ymin
    zmin, zmax = z0, z0 + h
    return {
        "name": name,
        "service": service,
        "axis": axis,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "z0": z0, "zc": z0 + h / 2.0, "w": w, "h": h, "length": length,
        "aabb": (xmin, xmax, ymin, ymax, zmin, zmax),
    }


def _seg_pipe(name, x0, y0, x1, y1, zc, od):
    """Build an axis-aligned circular pipe segment dict with AABB."""
    r = od / 2.0
    if abs(y1 - y0) < 1e-6:
        xmin, xmax = min(x0, x1), max(x0, x1)
        ymin, ymax = y0 - r, y0 + r
        axis = "X"
        length = xmax - xmin
    else:
        xmin, xmax = x0 - r, x0 + r
        ymin, ymax = min(y0, y1), max(y0, y1)
        axis = "Y"
        length = ymax - ymin
    return {
        "name": name,
        "service": "ChilledWaterPipe",
        "axis": axis,
        "x0": x0, "y0": y0, "x1": x1, "y1": y1,
        "z0": zc - r, "zc": zc, "od": od, "length": length,
        "aabb": (xmin, xmax, ymin, ymax, zc - r, zc + r),
    }


def build_geometry_spec():
    """Return all background elements and MEP routes with AABBs."""
    solids = []
    racks = []
    columns = []
    crahs = []
    pdus = []
    containments = []
    sprinklers = []
    rows = {}

    # Access floor panel: Z = [-35, 0]
    floor_aabb = (0.0, HALL_W, 0.0, HALL_D, -FLOOR_THK, 0.0)
    solids.append(("AccessFloor", "AccessFloor-1", floor_aabb))

    # Structural columns
    for gx_name, gx in COL_GRID_X:
        for gy_name, gy in COL_GRID_Y:
            cname = f"COL-{gx_name}{gy_name}"
            aabb = (gx - COL_SIZE / 2, gx + COL_SIZE / 2,
                    gy - COL_SIZE / 2, gy + COL_SIZE / 2,
                    0.0, SOFFIT_Z)
            columns.append({"name": cname, "grid": f"{gx_name}{gy_name}",
                            "cx": gx, "cy": gy, "aabb": aabb})
            solids.append(("Column", cname, aabb))

    # Cabinet rows and in-row CRAHs
    for rname, yc, facing, west_seq, east_seq in ROW_SPECS:
        cab_idx = 0
        cu_idx = 0
        x_min_row = ROW_START_X
        x_max_row = CA_EAST_X

        for start_x, seq in [(ROW_START_X, west_seq), (CA_EAST_X, east_seq)]:
            x = start_x
            for btype, count in seq:
                w = BAY_WIDTHS[btype]
                for _ in range(count):
                    if btype in ("C1", "N1"):
                        cab_idx += 1
                        name = f"RACK-{rname}{cab_idx:02d}"
                        aabb = (x, x + w, yc - CAB_DEPTH / 2, yc + CAB_DEPTH / 2, 0.0, CAB_HEIGHT)
                        racks.append({
                            "name": name, "row": rname, "type": btype,
                            "facing": facing, "w": w, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                            "cx": x + w / 2, "cy": yc, "aabb": aabb,
                        })
                        solids.append(("Rack", name, aabb))
                    elif btype == "CU":
                        cu_idx += 1
                        name = f"CRAH-{rname}{cu_idx:02d}"
                        aabb = (x, x + w, yc - CAB_DEPTH / 2, yc + CAB_DEPTH / 2, 0.0, CAB_HEIGHT)
                        crahs.append({
                            "name": name, "placement": "IN-ROW", "row": rname,
                            "facing": facing, "w": w, "d": CAB_DEPTH, "h": CAB_HEIGHT,
                            "cx": x + w / 2, "cy": yc, "capacity_kw": 50.0,
                            "airflow": 9000.0, "service": "CHILLED WATER, DN50",
                            "aabb": aabb,
                        })
                        solids.append(("CRAH", name, aabb))
                    x += w
            if start_x == CA_EAST_X:
                x_max_row = x
        rows[rname] = {"y_c": yc, "facing": facing, "x_min": x_min_row, "x_max": x_max_row}

    # Perimeter CRAHs
    for name, x0, y0 in PERIM_CRAHS:
        w, d, h = 1200.0, 900.0, 2000.0
        aabb = (x0, x0 + w, y0, y0 + d, 0.0, h)
        crahs.append({
            "name": name, "placement": "PERIMETER", "row": "PERIMETER",
            "facing": "NORTH", "w": w, "d": d, "h": h,
            "cx": x0 + w / 2, "cy": y0 + d / 2, "capacity_kw": 100.0,
            "airflow": 20000.0, "service": "CHILLED WATER, DN100",
            "aabb": aabb,
        })
        solids.append(("CRAH", name, aabb))

    # PDUs
    for name, srow, facing, x0, y0 in PDU_SPECS:
        aabb = (x0, x0 + PDU_W, y0, y0 + PDU_D, 0.0, PDU_H)
        pdus.append({
            "name": name, "serves_row": srow, "facing": facing,
            "w": PDU_W, "d": PDU_D, "h": PDU_H,
            "cx": x0 + PDU_W / 2, "cy": y0 + PDU_D / 2, "aabb": aabb,
        })
        solids.append(("PDU", name, aabb))

    # Cold-aisle containment (CAC-BC and CAC-DE): 2 roof panels + 4 end doors each
    cac_defs = [
        ("CAC-BC", 7200.0, [(1800.0, 9600.0), (11200.0, 19200.0)]),
        ("CAC-DE", 12600.0, [(1800.0, 9800.0), (11200.0, 19000.0)]),
    ]
    for aisle_name, ay, spans in cac_defs:
        for idx, (x0, x1) in enumerate(spans, 1):
            rname = f"{aisle_name}-ROOF-{idx}"
            raabb = (x0, x1, ay - 700.0, ay + 700.0, 2000.0, 2055.5)
            containments.append({"name": rname, "aisle": aisle_name, "role": "ContainmentRoof", "aabb": raabb})
            solids.append(("ContainmentRoof", rname, raabb))
            # End doors (60 mm thick x 1200 mm aisle width x 2055.5 mm height)
            for side, dx0 in [("W", x0 - 60.0), ("E", x1)]:
                dname = f"{aisle_name}-DOOR-{idx}{side}"
                daabb = (dx0, dx0 + 60.0, ay - 600.0, ay + 600.0, 0.0, 2055.5)
                containments.append({"name": dname, "aisle": aisle_name, "role": "ContainmentDoor", "aabb": daabb})
                solids.append(("ContainmentDoor", dname, daabb))

    # Sprinkler heads: 63 ceiling heads + 16 in-aisle heads
    # Ceiling 9 x 7 grid: X = 1500 + 3000i, Y = 1500 + 3000j, relocate clear of column keep-out (1500 mm)
    sp_idx = 0
    for j in range(7):
        for i in range(9):
            sp_idx += 1
            sx = 1500.0 + 3000.0 * i
            sy = 1500.0 + 3000.0 * j
            # Check 1500 mm keep-out (±750 mm) around structural columns
            for _, gx in COL_GRID_X:
                for _, gy in COL_GRID_Y:
                    if abs(sx - gx) < 750.0 and abs(sy - gy) < 750.0:
                        sx = gx - 900.0
                        sy = gy - 900.0
            sname = f"SPK-C{sp_idx:02d}"
            # Small cylinder representing head: OD 50 mm, Z = [3575, 3600]
            aabb = (sx - 25.0, sx + 25.0, sy - 25.0, sy + 25.0, 3575.0, 3600.0)
            sprinklers.append({"name": sname, "type": "CEILING", "cx": sx, "cy": sy,
                               "deflector_z": 3575.0, "standoff": 460.0, "aabb": aabb})
            solids.append(("SprinklerHead", sname, aabb))

    # 16 in-aisle heads (8 in CAC-BC at Y=7200, 8 in CAC-DE at Y=12600), deflector at +1890
    in_idx = 0
    for aisle_name, ay, spans in cac_defs:
        for x0, x1 in spans:
            for k in range(4):
                in_idx += 1
                sx = x0 + (x1 - x0) * (k + 0.5) / 4.0
                sname = f"SPK-A{in_idx:02d}"
                aabb = (sx - 25.0, sx + 25.0, ay - 25.0, ay + 25.0, 1890.0, 2000.0)
                sprinklers.append({"name": sname, "type": "IN-AISLE", "cx": sx, "cy": ay,
                                   "deflector_z": 1890.0, "standoff": 460.0, "aabb": aabb})
                solids.append(("SprinklerHead", sname, aabb))

    # -----------------------------------------------------------------------
    # MEP Routes (all 3 services connected to entry (X=0, Y=9900))
    # -----------------------------------------------------------------------
    routes = {"CableTray": [], "Busway": [], "ChilledWaterPipe": []}

    # 1. BUSWAY (overhead, Z = [2800, 2947], offset clear of columns at Y=8400, 16800)
    bus_trunk_x = 600.0
    bus_row_y = {"A": 3000.0, "B": 6000.0, "C": 9000.0, "D": 11400.0, "E": 13800.0, "F": 17400.0}
    routes["Busway"].append(_seg_rect("BW-ENTRY", "Busway", 0.0, 9900.0, bus_trunk_x, 9900.0, BUS_Z0, BUS_W, BUS_H))
    routes["Busway"].append(_seg_rect("BW-TRUNK", "Busway", bus_trunk_x, 3000.0, bus_trunk_x, 17400.0, BUS_Z0, BUS_W, BUS_H))
    for rname, rinfo in rows.items():
        ry = bus_row_y[rname]
        routes["Busway"].append(_seg_rect(f"BW-ROW-{rname}", "Busway", bus_trunk_x, ry, rinfo["x_max"], ry, BUS_Z0, BUS_W, BUS_H))

    # 2. CABLE TRAY (under-floor, Z = [-250, -123], >= 2923 mm vertical separation from Busway)
    tray_trunk_x = 600.0
    routes["CableTray"].append(_seg_rect("CT-ENTRY", "CableTray", 0.0, 9900.0, tray_trunk_x, 9900.0, TRAY_Z0, TRAY_W, TRAY_H))
    routes["CableTray"].append(_seg_rect("CT-TRUNK", "CableTray", tray_trunk_x, 3000.0, tray_trunk_x, 16800.0, TRAY_Z0, TRAY_W, TRAY_H))
    for rname, rinfo in rows.items():
        ry = rinfo["y_c"]
        routes["CableTray"].append(_seg_rect(f"CT-ROW-{rname}", "CableTray", tray_trunk_x, ry, rinfo["x_max"], ry, TRAY_Z0, TRAY_W, TRAY_H))

    # 3. CHILLED WATER PIPE (under-floor, Zc = -565.85, OD = 168.3 mm incl. 25.4 mm insulation)
    chw_trunk_x = 600.0
    routes["ChilledWaterPipe"].append(_seg_pipe("CHW-ENTRY", 0.0, 9900.0, chw_trunk_x, 9900.0, CHW_ZC, CHW_OD))
    routes["ChilledWaterPipe"].append(_seg_pipe("CHW-TRUNK", chw_trunk_x, 450.0, chw_trunk_x, 16800.0, CHW_ZC, CHW_OD))
    for rname, rinfo in rows.items():
        ry = rinfo["y_c"]
        routes["ChilledWaterPipe"].append(_seg_pipe(f"CHW-ROW-{rname}", chw_trunk_x, ry, rinfo["x_max"], ry, CHW_ZC, CHW_OD))
    # South perimeter header reaching CRAH-01..04 (Y=450, X=600..25800)
    routes["ChilledWaterPipe"].append(_seg_pipe("CHW-PERIM", chw_trunk_x, 450.0, 25800.0, 450.0, CHW_ZC, CHW_OD))

    for svc, segs in routes.items():
        for s in segs:
            solids.append((svc, s["name"], s["aabb"]))

    return {
        "solids": solids,
        "racks": racks,
        "columns": columns,
        "crahs": crahs,
        "pdus": pdus,
        "containments": containments,
        "sprinklers": sprinklers,
        "rows": rows,
        "routes": routes,
    }


# ---------------------------------------------------------------------------
# 2. IFC4 Model Builder (ifcopenshell==0.8.4 + numpy)
# ---------------------------------------------------------------------------

def _mat_translate_rot_z(x_mm, y_mm, z_mm, angle_rad=0.0):
    """4x4 placement matrix with translation in METRES and Z-rotation."""
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def _mat_pipe_axis(x_mm, y_mm, z_mm, axis):
    """4x4 placement matrix orienting local +Z along global +X or +Y (metres)."""
    m = np.eye(4, dtype=float)
    if axis == "X":
        # Local +Z -> Global +X, Local +X -> Global -Z, Local +Y -> Global +Y
        m[:3, :3] = np.array([[0.0, 0.0, 1.0],
                              [0.0, 1.0, 0.0],
                              [-1.0, 0.0, 0.0]])
    elif axis == "Y":
        # Local +Z -> Global +Y, Local +X -> Global +X, Local +Y -> Global -Z
        m[:3, :3] = np.array([[1.0, 0.0, 0.0],
                              [0.0, 0.0, 1.0],
                              [0.0, -1.0, 0.0]])
    m[0, 3] = x_mm / 1000.0
    m[1, 3] = y_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def _add_box_rep(f, body_ctx, w, d, h):
    """Create an IfcShapeRepresentation with a centred 2D rectangle extruded +Z by h (mm)."""
    profile = f.createIfcRectangleProfileDef(
        ProfileType="AREA",
        Position=f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((0.0, 0.0))),
        XDim=float(w),
        YDim=float(d),
    )
    solid = f.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))),
        ExtrudedDirection=f.createIfcDirection((0.0, 0.0, 1.0)),
        Depth=float(h),
    )
    return f.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _add_cyl_rep(f, body_ctx, radius, length):
    """Create an IfcShapeRepresentation with a 2D circle extruded +Z by length (mm)."""
    profile = f.createIfcCircleProfileDef(
        ProfileType="AREA",
        Position=f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((0.0, 0.0))),
        Radius=float(radius),
    )
    solid = f.createIfcExtrudedAreaSolid(
        SweptArea=profile,
        Position=f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))),
        ExtrudedDirection=f.createIfcDirection((0.0, 0.0, 1.0)),
        Depth=float(length),
    )
    return f.createIfcShapeRepresentation(
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def build_ifc(out_path):
    import ifcopenshell
    import ifcopenshell.api

    spec = build_geometry_spec()

    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Meridian Data Center - Phase 1")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETRES"})

    model_ctx = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context", f,
        context_type="Model", context_identifier="Body",
        target_view="MODEL_VIEW", parent=model_ctx,
    )

    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 00")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    def place_element(ifc_class, name, predefined_type, object_type, rep, matrix, pset_name=None, pset_props=None):
        elem = ifcopenshell.api.run("root.create_entity", f, ifc_class=ifc_class, name=name)
        if predefined_type is not None and hasattr(elem, "PredefinedType"):
            elem.PredefinedType = predefined_type
        if object_type is not None and hasattr(elem, "ObjectType"):
            elem.ObjectType = object_type
        ifcopenshell.api.run("spatial.assign_container", f, relating_structure=storey, products=[elem])
        ifcopenshell.api.run("geometry.assign_representation", f, product=elem, representation=rep)
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=elem, matrix=matrix)
        if pset_name and pset_props:
            pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
        return elem

    # Access floor
    place_element(
        "IfcSlab", "AccessFloor-1", "FLOOR", "AccessFloor",
        _add_box_rep(f, body_ctx, HALL_W, HALL_D, FLOOR_THK),
        _mat_translate_rot_z(HALL_W / 2.0, HALL_D / 2.0, -FLOOR_THK),
        "Pset_DCM_AccessFloor",
        {"ThicknessMM": FLOOR_THK, "TileSizeMM": 600.0, "PlenumDepthMM": 865.0},
    )

    # Structural columns
    for col in spec["columns"]:
        place_element(
            "IfcColumn", col["name"], "COLUMN", "Column",
            _add_box_rep(f, body_ctx, COL_SIZE, COL_SIZE, SOFFIT_Z),
            _mat_translate_rot_z(col["cx"], col["cy"], 0.0),
            "Pset_DCM_Column",
            {"Grid": col["grid"], "WidthMM": COL_SIZE, "DepthMM": COL_SIZE, "HeightMM": SOFFIT_Z},
        )

    # Racks (facing rotation about footprint centre: NORTH=0, SOUTH=pi)
    for r in spec["racks"]:
        ang = 0.0 if r["facing"] == "NORTH" else math.pi
        place_element(
            "IfcFurniture", r["name"], "USERDEFINED", "Rack",
            _add_box_rep(f, body_ctx, r["w"], r["d"], r["h"]),
            _mat_translate_rot_z(r["cx"], r["cy"], 0.0, ang),
            "Pset_DCM_Rack",
            {"Row": r["row"], "Type": r["type"], "Facing": r["facing"],
             "WidthMM": r["w"], "DepthMM": r["d"], "HeightMM": r["h"],
             "RackUnits": 42, "PowerKW": 8.0, "LoadKg": 1363.0},
        )

    # CRAHs
    for c in spec["crahs"]:
        ang = 0.0 if c["facing"] == "NORTH" else math.pi
        place_element(
            "IfcUnitaryEquipment", c["name"], "AIRHANDLER", "CRAH",
            _add_box_rep(f, body_ctx, c["w"], c["d"], c["h"]),
            _mat_translate_rot_z(c["cx"], c["cy"], 0.0, ang),
            "Pset_DCM_CRAH",
            {"Placement": c["placement"], "Row": c["row"], "Facing": c["facing"],
             "CapacityKW": c["capacity_kw"], "AirflowM3H": c["airflow"], "Service": c["service"]},
        )

    # PDUs
    for p in spec["pdus"]:
        ang = 0.0 if p["facing"] == "NORTH" else math.pi
        place_element(
            "IfcElectricDistributionBoard", p["name"], "DISTRIBUTIONBOARD", "PDU",
            _add_box_rep(f, body_ctx, p["w"], p["d"], p["h"]),
            _mat_translate_rot_z(p["cx"], p["cy"], 0.0, ang),
            "Pset_DCM_PDU",
            {"ServesRow": p["serves_row"], "Facing": p["facing"],
             "RatingKVA": 225.0, "WorkingSpaceMM": 900.0},
        )

    # Cold-aisle containment roofs & doors
    for cnt in spec["containments"]:
        x0, x1, y0, y1, z0, z1 = cnt["aabb"]
        place_element(
            "IfcBuildingElementProxy", cnt["name"], "USERDEFINED", cnt["role"],
            _add_box_rep(f, body_ctx, x1 - x0, y1 - y0, z1 - z0),
            _mat_translate_rot_z(0.5 * (x0 + x1), 0.5 * (y0 + y1), z0),
            "Pset_DCM_Containment",
            {"Aisle": cnt["aisle"], "ElementRole": cnt["role"]},
        )

    # Sprinkler heads
    for sp in spec["sprinklers"]:
        _, _, _, _, z0, z1 = sp["aabb"]
        place_element(
            "IfcFireSuppressionTerminal", sp["name"], "SPRINKLER", "SprinklerHead",
            _add_cyl_rep(f, body_ctx, 25.0, z1 - z0),
            _mat_translate_rot_z(sp["cx"], sp["cy"], z0),
            "Pset_DCM_Sprinkler",
            {"Type": sp["type"], "DeflectorElevationMM": sp["deflector_z"], "StandoffMM": sp["standoff"]},
        )

    # MEP Services
    for seg in spec["routes"]["CableTray"]:
        x0, x1, y0, y1, z0, z1 = seg["aabb"]
        place_element(
            "IfcCableCarrierSegment", seg["name"], "CABLETRAYSEGMENT", "CableTray",
            _add_box_rep(f, body_ctx, x1 - x0, y1 - y0, z1 - z0),
            _mat_translate_rot_z(0.5 * (x0 + x1), 0.5 * (y0 + y1), z0),
            "Pset_DCM_MEP",
            {"Service": "Telecom", "Tag": "CT-1", "WidthMM": TRAY_W, "HeightMM": TRAY_H,
             "Zone": "UnderFloor", "ElevationMM": seg["zc"]},
        )

    for seg in spec["routes"]["Busway"]:
        x0, x1, y0, y1, z0, z1 = seg["aabb"]
        place_element(
            "IfcCableSegment", seg["name"], "BUSBARSEGMENT", "Busway",
            _add_box_rep(f, body_ctx, x1 - x0, y1 - y0, z1 - z0),
            _mat_translate_rot_z(0.5 * (x0 + x1), 0.5 * (y0 + y1), z0),
            "Pset_DCM_MEP",
            {"Service": "Power", "Tag": "BW-1", "WidthMM": BUS_W, "HeightMM": BUS_H,
             "Zone": "Overhead", "ElevationMM": seg["zc"]},
        )

    for seg in spec["routes"]["ChilledWaterPipe"]:
        sx = min(seg["x0"], seg["x1"]) if seg["axis"] == "X" else seg["x0"]
        sy = seg["y0"] if seg["axis"] == "X" else min(seg["y0"], seg["y1"])
        place_element(
            "IfcPipeSegment", seg["name"], "RIGIDSEGMENT", "ChilledWaterPipe",
            _add_cyl_rep(f, body_ctx, CHW_OD / 2.0, seg["length"]),
            _mat_pipe_axis(sx, sy, seg["zc"], seg["axis"]),
            "Pset_DCM_MEP",
            {"Service": "ChilledWater", "Tag": "CHW-1", "OuterDiameterMM": CHW_OD,
             "InsulationMM": 25.4, "Zone": "UnderFloor", "ElevationMM": seg["zc"]},
        )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    f.write(out_path)


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    build_ifc(out_path)
