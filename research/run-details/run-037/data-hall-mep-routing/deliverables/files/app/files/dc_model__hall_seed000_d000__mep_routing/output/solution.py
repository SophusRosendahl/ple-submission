"""Coordinated 3D BIM/MEP model for data hall dc_model hall_seed000_d000.

Builds the room, fit-out, and three clash-free MEP services (telecom cable tray,
power busway, chilled-water pipe) in IFC4 using ifcopenshell==0.8.4 and numpy.

Usage:
    python3 output/solution.py [out_path.ifc]
"""
import json
import math
import os
import sys
import numpy as np


# ---------------------------------------------------------------------------
# Drawing-extracted constants (all dimensions in millimetres)
# ---------------------------------------------------------------------------
ROOM_X = 27000.0
ROOM_Y = 21000.0
SOFFIT_Z = 3600.0
SLAB_Z = -900.0
ACCESS_FLOOR_THK = 35.0
CABINET_DEPTH = 1200.0
CABINET_HEIGHT = 2000.0
CA_EAST_X = 11200.0  # Common east edge of cross-aisle per A-101 Note 5
ROW_START_X = 1800.0  # Tile D (3 * 600 mm)

# Row definitions: (row_id, y_centre, facing, bay_tokens)
# Bay tokens: ("C1", n), ("N1", n), ("CU", 1), ("SP", 1), ("CA", 0), ("OMIT", width_mm)
ROW_SPECS = [
    ("A", 3000.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
        ("CA", 0),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("B", 6000.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
        ("CA", 0),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("C", 8400.0, "SOUTH", [
        ("C1", 3), ("CU", 1), ("C1", 6), ("OMIT", 1200.0), ("CU", 1),
        ("CA", 0),
        ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("OMIT", 1200.0), ("C1", 3),
    ]),
    ("D", 11400.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
        ("CA", 0),
        ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("E", 13800.0, "SOUTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
        ("CA", 0),
        ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
    ]),
    ("F", 16800.0, "NORTH", [
        ("C1", 4), ("CU", 1), ("C1", 5), ("OMIT", 1200.0), ("CU", 1),
        ("CA", 0),
        ("N1", 2), ("C1", 5), ("SP", 1), ("OMIT", 600.0), ("CU", 1), ("C1", 4),
    ]),
]

# Structural columns: 600 x 600 mm, full clear height (0 to 3600 mm)
COLUMN_COORDS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Perimeter CRAHs: 1200 W x 900 D x 2000 H, facing NORTH
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs: 762 W x 813 D x 1959 H, front flush with served row front face
PDU_SPECS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - 813.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - 813.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - 813.0, "NORTH"),
]


def _box_item(name, x0, y0, z0, x1, y1, z1, facing="NORTH", **meta):
    return {
        "name": name,
        "aabb": (float(x0), float(y0), float(z0), float(x1), float(y1), float(z1)),
        "cx": 0.5 * (x0 + x1),
        "cy": 0.5 * (y0 + y1),
        "z0": float(z0),
        "dx": float(x1 - x0),
        "dy": float(y1 - y0),
        "dz": float(z1 - z0),
        "facing": facing,
        "meta": meta,
    }


def _seg_rect(name, p0, p1, width, height, z_bot, **meta):
    """Axis-aligned rectangular MEP segment from p0=(x0,y0) to p1=(x1,y1)."""
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    if abs(x1 - x0) >= abs(y1 - y0):
        # X-aligned
        ax0, ax1 = min(x0, x1), max(x0, x1)
        ay0, ay1 = y0 - 0.5 * width, y0 + 0.5 * width
        length = ax1 - ax0
        axis = "X"
    else:
        # Y-aligned
        ax0, ax1 = x0 - 0.5 * width, x0 + 0.5 * width
        ay0, ay1 = min(y0, y1), max(y0, y1)
        length = ay1 - ay0
        axis = "Y"
    return {
        "name": name,
        "shape": "rect",
        "axis": axis,
        "p0": (x0, y0, z_bot + 0.5 * height),
        "p1": (x1, y1, z_bot + 0.5 * height),
        "length": float(length),
        "width": float(width),
        "height": float(height),
        "aabb": (ax0, ay0, float(z_bot), ax1, ay1, float(z_bot + height)),
        "meta": meta,
    }


def _seg_pipe(name, p0, p1, outer_od, z_center, **meta):
    """Axis-aligned circular pipe segment (using insulated OD for clash AABB)."""
    x0, y0 = float(p0[0]), float(p0[1])
    x1, y1 = float(p1[0]), float(p1[1])
    r = 0.5 * outer_od
    if abs(x1 - x0) >= abs(y1 - y0):
        ax0, ax1 = min(x0, x1), max(x0, x1)
        ay0, ay1 = y0 - r, y0 + r
        length = ax1 - ax0
        axis = "X"
    else:
        ax0, ax1 = x0 - r, x0 + r
        ay0, ay1 = min(y0, y1), max(y0, y1)
        length = ay1 - ay0
        axis = "Y"
    return {
        "name": name,
        "shape": "pipe",
        "axis": axis,
        "p0": (x0, y0, float(z_center)),
        "p1": (x1, y1, float(z_center)),
        "length": float(length),
        "outer_od": float(outer_od),
        "aabb": (ax0, ay0, float(z_center - r), ax1, ay1, float(z_center + r)),
        "meta": meta,
    }


def build_model_data():
    """Construct all background and MEP geometry data deterministically."""
    racks = []
    crahs_inrow = []
    rows_info = {}

    for row_id, yc, facing, tokens in ROW_SPECS:
        x = ROW_START_X
        y0 = yc - 0.5 * CABINET_DEPTH
        y1 = yc + 0.5 * CABINET_DEPTH
        rack_idx = 0
        crah_idx = 0
        ca_west_x = None

        for kind, val in tokens:
            if kind == "C1":
                for _ in range(val):
                    rack_idx += 1
                    racks.append(_box_item(
                        f"RACK-{row_id}{rack_idx:02d}",
                        x, y0, 0.0, x + 600.0, y1, CABINET_HEIGHT,
                        facing=facing, row=row_id, rack_type="C1", ru=42,
                        power_kw=8.0, load_kg=1363.0,
                    ))
                    x += 600.0
            elif kind == "N1":
                for _ in range(val):
                    rack_idx += 1
                    racks.append(_box_item(
                        f"RACK-{row_id}{rack_idx:02d}",
                        x, y0, 0.0, x + 800.0, y1, CABINET_HEIGHT,
                        facing=facing, row=row_id, rack_type="N1", ru=42,
                        power_kw=8.0, load_kg=1363.0,
                    ))
                    x += 800.0
            elif kind == "CU":
                crah_idx += 1
                crahs_inrow.append(_box_item(
                    f"CRAH-{row_id}{crah_idx:02d}",
                    x, y0, 0.0, x + 600.0, y1, CABINET_HEIGHT,
                    facing=facing, row=row_id, placement="IN-ROW",
                    capacity_kw=50.0, airflow_m3h=9000.0, service="CHW DN50",
                ))
                x += 600.0
            elif kind == "SP":
                x += 600.0 * val
            elif kind == "OMIT":
                x += float(val)
            elif kind == "CA":
                ca_west_x = x
                x = CA_EAST_X

        rows_info[row_id] = {
            "yc": yc,
            "facing": facing,
            "x_min": ROW_START_X,
            "x_max": x,
            "ca_west_x": ca_west_x,
            "ca_east_x": CA_EAST_X,
        }

    # Structural columns (400 x 400 mm, 0 to 3600 mm)
    columns = [
        _box_item(name, cx - 200.0, cy - 200.0, 0.0, cx + 200.0, cy + 200.0, SOFFIT_Z)
        for name, cx, cy in COLUMN_COORDS
    ]

    # Perimeter CRAHs
    crahs_perimeter = [
        _box_item(
            name, x0, y0, 0.0, x0 + 1200.0, y0 + 900.0, 2000.0,
            facing="NORTH", placement="PERIMETER",
            capacity_kw=100.0, airflow_m3h=20000.0, service="CHW DN100",
        )
        for name, x0, y0 in PERIMETER_CRAHS
    ]

    # PDUs
    pdus = [
        _box_item(
            name, x0, y0, 0.0, x0 + 762.0, y0 + 813.0, 1959.0,
            facing=facing, serves_row=row_id, rating_kva=225.0, working_space_mm=900.0,
        )
        for name, row_id, x0, y0, facing in PDU_SPECS
    ]

    # Access floor panel: 35 mm thick (-35 to 0 mm)
    access_floor = [
        _box_item("ACCESS-FLOOR", 0.0, 0.0, -ACCESS_FLOOR_THK, ROOM_X, ROOM_Y, 0.0)
    ]

    # Cold-aisle containment: CAC-BC (y=6600..7800) and CAC-DE (y=12000..13200)
    containment_roofs = []
    containment_doors = []
    for tag, r_south, r_north, ay0, ay1 in [
        ("CAC-BC", "B", "C", 6600.0, 7800.0),
        ("CAC-DE", "D", "E", 12000.0, 13200.0),
    ]:
        west_end = min(rows_info[r_south]["ca_west_x"], rows_info[r_north]["ca_west_x"])
        east_end = max(rows_info[r_south]["x_max"], rows_info[r_north]["x_max"])
        # 2 roof panels per aisle (west half, east half), width 1400 (overhangs 100 mm each side)
        containment_roofs.append(_box_item(
            f"{tag}-ROOF-W", ROW_START_X, ay0 - 100.0, 2000.0, west_end, ay1 + 100.0, 2055.5,
            aisle=tag,
        ))
        containment_roofs.append(_box_item(
            f"{tag}-ROOF-E", CA_EAST_X, ay0 - 100.0, 2000.0, east_end, ay1 + 100.0, 2055.5,
            aisle=tag,
        ))
        # 4 end doors per aisle (60 mm thick x 2055.5 mm high, spanning 1200 mm aisle)
        for idx, dx_pos in enumerate([ROW_START_X, west_end - 60.0, CA_EAST_X, east_end - 60.0], 1):
            containment_doors.append(_box_item(
                f"{tag}-DOOR-{idx}", dx_pos, ay0, 0.0, dx_pos + 60.0, ay1, 2055.5,
                aisle=tag,
            ))

    # Sprinklers: 63 ceiling heads (9 x 7 grid, relocated clear of columns)
    sprinklers_ceiling = []
    xs = [1500.0 + 3000.0 * i for i in range(9)]
    ys = [1500.0 + 3000.0 * j for j in range(7)]
    h_idx = 0
    for sy in ys:
        for sx in xs:
            h_idx += 1
            rx, ry = sx, sy
            # Relocate heads inside 750 mm keep-out of any column
            for _, cx, cy in COLUMN_COORDS:
                if abs(rx - cx) < 750.0 and abs(ry - cy) < 750.0:
                    rx = cx - 900.0 if rx <= cx else cx + 900.0
                    ry = cy - 900.0 if ry <= cy else cy + 900.0
            sprinklers_ceiling.append({
                "name": f"SPR-CLG-{h_idx:02d}",
                "x": rx, "y": ry, "z": 3574.6,
                "location": "CEILING", "standoff_mm": 460.0,
            })

    # 16 in-aisle sprinkler heads (8 in CAC-BC at y=7200, 8 in CAC-DE at y=12600)
    sprinklers_inaisle = []
    in_idx = 0
    for tag, ay in [("CAC-BC", 7200.0), ("CAC-DE", 12600.0)]:
        for hx in [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]:
            in_idx += 1
            sprinklers_inaisle.append({
                "name": f"SPR-AISLE-{in_idx:02d}",
                "x": hx, "y": ay, "z": 1890.0,
                "location": tag, "standoff_mm": 460.0,
            })

    # -----------------------------------------------------------------------
    # MEP Routing (axis-aligned, clash-free, connected, code-compliant)
    # -----------------------------------------------------------------------
    # 1. Telecom Cable Tray (CT-1: 683 W x 127 H, overhead z = 2970..3097 mm)
    tray_z = 2970.0
    tray_w, tray_h = 683.0, 127.0
    tray_y_map = {
        "A": 2750.0, "B": 5750.0, "C": 7500.0,
        "D": 11150.0, "E": 13550.0, "F": 15900.0,
    }
    tray_segs = [
        _seg_rect("CT-ENTRY", (0.0, 9900.0), (500.0, 9900.0), tray_w, tray_h, tray_z, zone="Overhead"),
        _seg_rect("CT-TRUNK-W", (500.0, 2750.0), (500.0, 15900.0), tray_w, tray_h, tray_z, zone="Overhead"),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = tray_y_map[row_id]
        rx_max = rows_info[row_id]["x_max"]
        tray_segs.append(_seg_rect(
            f"CT-ROW-{row_id}", (500.0, ry), (rx_max, ry), tray_w, tray_h, tray_z,
            zone="Overhead", row=row_id,
        ))

    # 2. Power Busway (BW-1: 128 W x 147 H, under-floor plenum z = -250..-103 mm)
    bw_z = -250.0
    bw_w, bw_h = 128.0, 147.0
    bw_y_map = {
        "A": 3000.0, "B": 6000.0, "C": 9000.0,
        "D": 11400.0, "E": 13800.0, "F": 17400.0,
    }
    bw_segs = [
        _seg_rect("BW-ENTRY", (0.0, 9900.0), (1300.0, 9900.0), bw_w, bw_h, bw_z, zone="Plenum"),
        _seg_rect("BW-TRUNK-W", (1300.0, 3000.0), (1300.0, 17400.0), bw_w, bw_h, bw_z, zone="Plenum"),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = bw_y_map[row_id]
        rx_max = rows_info[row_id]["x_max"]
        bw_segs.append(_seg_rect(
            f"BW-ROW-{row_id}", (1300.0, ry), (rx_max, ry), bw_w, bw_h, bw_z,
            zone="Plenum", row=row_id,
        ))

    # 3. Chilled Water Pipe (CHW-1: DN100, insulated OD 168.3 mm, under-floor plenum z_c = -515.85 mm)
    chw_zc = -515.85
    chw_od = 168.3
    chw_y_map = {
        "A": 3000.0, "B": 6000.0, "C": 9200.0,
        "D": 11400.0, "E": 13800.0, "F": 16000.0,
    }
    chw_segs = [
        _seg_pipe("CHW-ENTRY", (0.0, 9900.0), (1000.0, 9900.0), chw_od, chw_zc, zone="Plenum"),
        _seg_pipe("CHW-TRUNK-W", (1000.0, 450.0), (1000.0, 16000.0), chw_od, chw_zc, zone="Plenum"),
        _seg_pipe("CHW-PERIM-CRAH", (1000.0, 450.0), (25800.0, 450.0), chw_od, chw_zc, zone="Plenum"),
    ]
    for row_id in ["A", "B", "C", "D", "E", "F"]:
        ry = chw_y_map[row_id]
        rx_max = rows_info[row_id]["x_max"]
        chw_segs.append(_seg_pipe(
            f"CHW-ROW-{row_id}", (1000.0, ry), (rx_max, ry), chw_od, chw_zc,
            zone="Plenum", row=row_id,
        ))

    return {
        "rows": rows_info,
        "racks": racks,
        "columns": columns,
        "crahs_perimeter": crahs_perimeter,
        "crahs_inrow": crahs_inrow,
        "pdus": pdus,
        "access_floor": access_floor,
        "containment_roofs": containment_roofs,
        "containment_doors": containment_doors,
        "sprinklers_ceiling": sprinklers_ceiling,
        "sprinklers_inaisle": sprinklers_inaisle,
        "services": {
            "tray": tray_segs,
            "busway": bw_segs,
            "chw": chw_segs,
        },
    }


def _placement_matrix(cx_mm, cy_mm, z0_mm, facing="NORTH"):
    """4x4 placement matrix with translations in METRES and Z-rotation about footprint centre."""
    theta = math.pi if facing == "SOUTH" else 0.0
    c, s = math.cos(theta), math.sin(theta)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def _make_rect_extrusion(f, context, dx_mm, dy_mm, dz_mm):
    """Create a 2D IfcRectangleProfileDef extruded along +Z by dz_mm."""
    profile = f.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx_mm),
        YDim=float(dy_mm),
    )
    dir_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=dir_z,
        Depth=float(dz_mm),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _make_cyl_extrusion(f, context, radius_mm, length_mm):
    """Create a 2D IfcCircleProfileDef extruded along +Z by length_mm."""
    profile = f.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius_mm),
    )
    dir_z = f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = f.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=dir_z,
        Depth=float(length_mm),
    )
    return f.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=context,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _pipe_placement_matrix(seg):
    """4x4 placement matrix (metres) orienting local +Z along the pipe axis."""
    x0, y0, z0 = seg["p0"]
    x1, y1, z1 = seg["p1"]
    m = np.eye(4, dtype=float)
    if seg["axis"] == "X":
        sx = min(x0, x1)
        # Local +Z -> World +X: col0=(0,1,0), col1=(0,0,1), col2=(1,0,0)
        m[:3, 0] = [0.0, 1.0, 0.0]
        m[:3, 1] = [0.0, 0.0, 1.0]
        m[:3, 2] = [1.0, 0.0, 0.0]
        m[0, 3], m[1, 3], m[2, 3] = sx / 1000.0, y0 / 1000.0, z0 / 1000.0
    else:
        sy = min(y0, y1)
        # Local +Z -> World +Y: col0=(0,0,1), col1=(1,0,0), col2=(0,1,0)
        m[:3, 0] = [0.0, 0.0, 1.0]
        m[:3, 1] = [1.0, 0.0, 0.0]
        m[:3, 2] = [0.0, 1.0, 0.0]
        m[0, 3], m[1, 3], m[2, 3] = x0 / 1000.0, sy / 1000.0, z0 / 1000.0
    return m


def write_ifc(model, out_path):
    """Build and write the IFC4 file using ifcopenshell==0.8.4."""
    import ifcopenshell
    import ifcopenshell.api

    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcProject", name="Meridian Data Center")
    ifcopenshell.api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETRE"})

    ctx_model = ifcopenshell.api.run("context.add_context", f, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", f,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx_model,
    )

    site = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcSite", name="Phase 1")
    building = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 1")
    ifcopenshell.api.run("aggregate.assign_object", f, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", f, products=[storey], relating_object=building)

    def add_box_element(ifc_class, predefined_type, object_type, item, pset_name=None, pset_props=None):
        elem = ifcopenshell.api.run(
            "root.create_entity", f,
            ifc_class=ifc_class, predefined_type=predefined_type, name=item["name"],
        )
        if object_type is not None:
            elem.ObjectType = object_type
        ifcopenshell.api.run("spatial.assign_container", f, products=[elem], relating_structure=storey)
        rep = _make_rect_extrusion(f, body, item["dx"], item["dy"], item["dz"])
        ifcopenshell.api.run("geometry.assign_representation", f, product=elem, representation=rep)
        mat = _placement_matrix(item["cx"], item["cy"], item["z0"], item["facing"])
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=elem, matrix=mat)
        if pset_name and pset_props:
            pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name=pset_name)
            ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties=pset_props)
        return elem

    # 1. Racks
    for r in model["racks"]:
        add_box_element(
            "IfcFurniture", "USERDEFINED", "Rack", r,
            pset_name="Pset_DCM_Rack",
            pset_props={
                "Row": r["meta"]["row"],
                "RackType": r["meta"]["rack_type"],
                "Width_mm": r["dx"],
                "Depth_mm": r["dy"],
                "Height_mm": r["dz"],
                "RU": r["meta"]["ru"],
                "Facing": r["facing"],
                "Power_kW": r["meta"]["power_kw"],
                "Load_kg": r["meta"]["load_kg"],
            },
        )

    # 2. Structural columns
    for col in model["columns"]:
        add_box_element("IfcColumn", "COLUMN", None, col)

    # 3. CRAHs (perimeter + in-row)
    for crah in model["crahs_perimeter"] + model["crahs_inrow"]:
        add_box_element(
            "IfcUnitaryEquipment", "AIRCONDITIONINGUNIT", "CRAH", crah,
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": crah["meta"]["placement"],
                "Capacity_kW": crah["meta"]["capacity_kw"],
                "Airflow_m3h": crah["meta"]["airflow_m3h"],
                "Facing": crah["facing"],
                "Service": crah["meta"]["service"],
            },
        )

    # 4. PDUs
    for pdu in model["pdus"]:
        add_box_element(
            "IfcElectricDistributionBoard", "DISTRIBUTIONBOARD", "PDU", pdu,
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": pdu["meta"]["serves_row"],
                "Rating_kVA": pdu["meta"]["rating_kva"],
                "Facing": pdu["facing"],
                "WorkingSpace_mm": pdu["meta"]["working_space_mm"],
            },
        )

    # 5. Access floor
    for af in model["access_floor"]:
        add_box_element("IfcSlab", "FLOOR", "AccessFloor", af)

    # 6. Containment roofs & doors
    for roof in model["containment_roofs"]:
        add_box_element(
            "IfcCovering", "CEILING", "ContainmentRoof", roof,
            pset_name="Pset_DCM_Containment",
            pset_props={"Aisle": roof["meta"]["aisle"], "Thickness_mm": 55.5},
        )
    for door in model["containment_doors"]:
        add_box_element("IfcDoor", "DOOR", "ContainmentDoor", door)

    # 7. Sprinklers (63 ceiling + 16 in-aisle)
    for spr in model["sprinklers_ceiling"] + model["sprinklers_inaisle"]:
        elem = ifcopenshell.api.run(
            "root.create_entity", f,
            ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=spr["name"],
        )
        elem.ObjectType = "SprinklerHead"
        ifcopenshell.api.run("spatial.assign_container", f, products=[elem], relating_structure=storey)
        rep = _make_cyl_extrusion(f, body, 25.0, 25.4)
        ifcopenshell.api.run("geometry.assign_representation", f, product=elem, representation=rep)
        mat = _placement_matrix(spr["x"], spr["y"], spr["z"], "NORTH")
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=elem, matrix=mat)
        pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name="Pset_DCM_Sprinkler")
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={
            "Location": spr["location"],
            "DeflectorElevation_mm": spr["z"],
            "Standoff_mm": spr["standoff_mm"],
        })

    # 8. MEP Services: Cable Tray, Busway, Chilled Water Pipe
    for seg in model["services"]["tray"]:
        b = seg["aabb"]
        item = _box_item(seg["name"], *b)
        add_box_element(
            "IfcCableCarrierSegment", "CABLELADDERSEGMENT", "CableTray", item,
            pset_name="Pset_DCM_Pathway",
            pset_props={
                "Service": "Telecom", "Tag": "CT-1",
                "Width_mm": 683.0, "Height_mm": 127.0,
                "Zone": seg["meta"].get("zone", "Overhead"),
                "Elevation_mm": b[2],
            },
        )

    for seg in model["services"]["busway"]:
        b = seg["aabb"]
        item = _box_item(seg["name"], *b)
        add_box_element(
            "IfcCableSegment", "BUSBARSEGMENT", "Busway", item,
            pset_name="Pset_DCM_Pathway",
            pset_props={
                "Service": "Power", "Tag": "BW-1",
                "Width_mm": 128.0, "Height_mm": 147.0,
                "Zone": seg["meta"].get("zone", "Plenum"),
                "Elevation_mm": b[2],
            },
        )

    for seg in model["services"]["chw"]:
        elem = ifcopenshell.api.run(
            "root.create_entity", f,
            ifc_class="IfcPipeSegment", predefined_type="RIGIDSEGMENT", name=seg["name"],
        )
        elem.ObjectType = "ChilledWaterPipe"
        ifcopenshell.api.run("spatial.assign_container", f, products=[elem], relating_structure=storey)
        rep = _make_cyl_extrusion(f, body, 0.5 * seg["outer_od"], seg["length"])
        ifcopenshell.api.run("geometry.assign_representation", f, product=elem, representation=rep)
        mat = _pipe_placement_matrix(seg)
        ifcopenshell.api.run("geometry.edit_object_placement", f, product=elem, matrix=mat)
        pset = ifcopenshell.api.run("pset.add_pset", f, product=elem, name="Pset_DCM_Pathway")
        ifcopenshell.api.run("pset.edit_pset", f, pset=pset, properties={
            "Service": "ChilledWater", "Tag": "CHW-1",
            "BareOD_mm": 114.3, "InsulatedOD_mm": 168.3, "Insulation_mm": 25.4,
            "Zone": seg["meta"].get("zone", "Plenum"),
            "Elevation_mm": seg["p0"][2],
        })

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    f.write(out_path)


if __name__ == "__main__":
    out_ifc = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    model_data = build_model_data()
    write_ifc(model_data, out_ifc)
