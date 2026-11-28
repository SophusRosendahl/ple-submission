"""Data hall MEP coordination model generator (hall_seed000_d000).

Builds the complete IFC4 coordination model in millimetres using ifcopenshell 0.8.4
and numpy only, with all drawing data baked in as literals.
"""
import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.validate


# ---------------------------------------------------------------------------
# Drawing constants (all dimensions in mm)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
SOFFIT_Z = 3600.0
SLAB_TOP_Z = -900.0
ACCESS_FLOOR_THK = 35.0

COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

ROW_SPECS = [
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

BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
WEST_START_X = 1800.0
EAST_START_X = 11400.0

PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]
PERIM_CRAH_W = 1200.0
PERIM_CRAH_D = 900.0
PERIM_CRAH_H = 2000.0

PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 5787.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 11187.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 16587.0, "NORTH"),
]
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0

# Service section dimensions (mm)
TRAY_W = 683.0
TRAY_H = 127.0
BUS_W = 128.0
BUS_H = 147.0
CHW_OD = 168.3  # DN100 bare 114.3 + 25.4 mm insulation (ASTM C585 jacket)

ENTRY_X = 0.0
ENTRY_Y = 9900.0


# ---------------------------------------------------------------------------
# IFC helper functions
# ---------------------------------------------------------------------------
def make_matrix(x_mm, y_mm, z_mm, rot_z_deg=0.0):
    """4x4 placement matrix with translations in metres (for is_si=True)."""
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


def add_box(model, body_ctx, elem, cx, cy, z_bot, sx, sy, sz, rot_z_deg=0.0):
    """Assign an extruded rectangle solid centered at (cx, cy) with base at z_bot."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(sx),
        YDim=float(sy),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(sz),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    prod_rep = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    elem.Representation = prod_rep
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=elem,
        matrix=make_matrix(cx, cy, z_bot, rot_z_deg),
        is_si=True,
    )


def add_cyl_z(model, body_ctx, elem, cx, cy, z_bot, radius, height):
    """Assign a vertical cylinder centered at (cx, cy) from z_bot to z_bot+height."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(height),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=elem,
        matrix=make_matrix(cx, cy, z_bot, 0.0),
        is_si=True,
    )


def add_pset(model, elem, pset_name, props):
    pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=props)


def add_rect_segment(model, storey, body_ctx, ifc_class, predefined, obj_type, name,
                     p1, p2, width, height, pset_name, props):
    """Create an axis-aligned rectangular MEP segment from p1=(x1,y1,z1) to p2=(x2,y2,z2)
    where z1, z2 are segment centreline Z.
    """
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    if abs(dx) > 1e-3:
        sx = abs(dx)
        sy = width
        sz = height
        cx = 0.5 * (x1 + x2)
        cy = y1
        z_bot = z1 - 0.5 * height
    elif abs(dy) > 1e-3:
        sx = width
        sy = abs(dy)
        sz = height
        cx = x1
        cy = 0.5 * (y1 + y2)
        z_bot = z1 - 0.5 * height
    else:
        sx = width
        sy = width
        sz = abs(dz)
        cx = x1
        cy = y1
        z_bot = min(z1, z2)

    elem = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class=ifc_class, predefined_type=predefined, name=name
    )
    elem.ObjectType = obj_type
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
    add_box(model, body_ctx, elem, cx, cy, z_bot, sx, sy, sz)
    p = dict(props)
    p["Elevation_mm"] = float(z1)
    add_pset(model, elem, pset_name, p)
    return elem


def add_pipe_segment(model, storey, body_ctx, name, p1, p2, od, pset_name, props):
    """Create an axis-aligned cylindrical pipe segment from p1 to p2 (centreline)."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    r = od / 2.0
    elem = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcPipeSegment", predefined_type="RIGIDSEGMENT", name=name
    )
    elem.ObjectType = "ChilledWaterPipe"
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])

    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(r))
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(length),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    elem.Representation = model.create_entity("IfcProductDefinitionShape", Representations=[rep])

    m = np.eye(4, dtype=float)
    if abs(dx) > 1e-3:
        # Extrude along +X from min(x1,x2)
        x0 = min(x1, x2)
        m[:3, 0] = [0.0, 0.0, -1.0]
        m[:3, 1] = [0.0, 1.0, 0.0]
        m[:3, 2] = [1.0, 0.0, 0.0]
        m[0, 3] = x0 / 1000.0
        m[1, 3] = y1 / 1000.0
        m[2, 3] = z1 / 1000.0
    elif abs(dy) > 1e-3:
        # Extrude along +Y from min(y1,y2)
        y0 = min(y1, y2)
        m[:3, 0] = [1.0, 0.0, 0.0]
        m[:3, 1] = [0.0, 0.0, -1.0]
        m[:3, 2] = [0.0, 1.0, 0.0]
        m[0, 3] = x1 / 1000.0
        m[1, 3] = y0 / 1000.0
        m[2, 3] = z1 / 1000.0
    else:
        z0 = min(z1, z2)
        m[0, 3] = x1 / 1000.0
        m[1, 3] = y1 / 1000.0
        m[2, 3] = z0 / 1000.0

    ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=m, is_si=True)
    p = dict(props)
    p["Elevation_mm"] = float(z1)
    p["InsulatedOD_mm"] = float(od)
    add_pset(model, elem, pset_name, p)
    return elem


# ---------------------------------------------------------------------------
# Build model
# ---------------------------------------------------------------------------
def build_model(out_path):
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center")
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
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 1")
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    # 1. Access Floor (35 mm thick, top at z=0)
    floor = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcSlab", predefined_type="FLOOR", name="AccessFloor"
    )
    floor.ObjectType = "AccessFloor"
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[floor])
    add_box(model, body_ctx, floor, ROOM_W / 2.0, ROOM_D / 2.0, -ACCESS_FLOOR_THK, ROOM_W, ROOM_D, ACCESS_FLOOR_THK)
    add_pset(model, floor, "Pset_DCM_AccessFloor", {"Thickness_mm": ACCESS_FLOOR_THK, "PlenumDepth_mm": 865.0})

    # 2. Structural Columns (6, full height 0..3600)
    for ix, cx in enumerate(COL_XS):
        for iy, cy in enumerate(COL_YS):
            cname = f"COL-{['A','B','C'][ix]}{iy+1}"
            col = ifcopenshell.api.run(
                "root.create_entity", model, ifc_class="IfcColumn", predefined_type="COLUMN", name=cname
            )
            col.ObjectType = "StructuralColumn"
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[col])
            add_box(model, body_ctx, col, cx, cy, 0.0, COL_SIZE, COL_SIZE, SOFFIT_Z)
            add_pset(model, col, "Pset_DCM_Column", {"Grid": f"{['A','B','C'][ix]}{iy+1}", "Size_mm": COL_SIZE})

    # 3. Cabinet Rows (128 racks) & In-Row CRAHs (18 units)
    row_extents = {}
    for row_id, yc, facing, west_seq, east_seq in ROW_SPECS:
        rot = 0.0 if facing == "NORTH" else 180.0
        rack_idx = 0
        crah_idx = 0

        def place_seq(start_x, seq):
            nonlocal rack_idx, crah_idx
            x = start_x
            for btype, count in seq:
                w = BAY_WIDTHS[btype]
                for _ in range(count):
                    cx = x + w / 2.0
                    if btype in ("C1", "N1"):
                        rack_idx += 1
                        rname = f"RACK-{row_id}{rack_idx:02d}"
                        rack = ifcopenshell.api.run(
                            "root.create_entity",
                            model,
                            ifc_class="IfcFurniture",
                            predefined_type="USERDEFINED",
                            name=rname,
                        )
                        rack.ObjectType = "Rack"
                        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[rack])
                        add_box(model, body_ctx, rack, cx, yc, 0.0, w, CAB_DEPTH, CAB_HEIGHT, rot_z_deg=rot)
                        add_pset(model, rack, "Pset_DCM_Rack", {
                            "Row": row_id,
                            "CabinetType": btype,
                            "Facing": facing,
                            "RU": 42,
                            "Power_kW": 8.0,
                        })
                    elif btype == "CU":
                        crah_idx += 1
                        cname = f"CRAH-{row_id}{crah_idx:02d}"
                        crah = ifcopenshell.api.run(
                            "root.create_entity",
                            model,
                            ifc_class="IfcUnitaryEquipment",
                            predefined_type="AIRHANDLER",
                            name=cname,
                        )
                        crah.ObjectType = "CRAH"
                        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[crah])
                        add_box(model, body_ctx, crah, cx, yc, 0.0, w, CAB_DEPTH, CAB_HEIGHT, rot_z_deg=rot)
                        add_pset(model, crah, "Pset_DCM_CRAH", {
                            "Placement": "IN_ROW",
                            "Row": row_id,
                            "Facing": facing,
                            "Capacity_kW": 50.0,
                        })
                    x += w
            return x

        west_end = place_seq(WEST_START_X, west_seq)
        east_end = place_seq(EAST_START_X, east_seq)
        row_extents[row_id] = (WEST_START_X, west_end, EAST_START_X, east_end)

    # 4. Perimeter CRAHs (4 units)
    for cname, x0, y0 in PERIMETER_CRAHS:
        crah = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcUnitaryEquipment",
            predefined_type="AIRHANDLER",
            name=cname,
        )
        crah.ObjectType = "CRAH"
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[crah])
        add_box(model, body_ctx, crah, x0 + PERIM_CRAH_W / 2.0, y0 + PERIM_CRAH_D / 2.0, 0.0,
                PERIM_CRAH_W, PERIM_CRAH_D, PERIM_CRAH_H, rot_z_deg=0.0)
        add_pset(model, crah, "Pset_DCM_CRAH", {
            "Placement": "PERIMETER",
            "Facing": "NORTH",
            "Capacity_kW": 100.0,
        })

    # 5. PDUs (6 units)
    for pname, row_id, x0, y0, facing in PDUS:
        rot = 0.0 if facing == "NORTH" else 180.0
        pdu = ifcopenshell.api.run(
            "root.create_entity",
            model,
            ifc_class="IfcElectricDistributionBoard",
            predefined_type="DISTRIBUTIONBOARD",
            name=pname,
        )
        pdu.ObjectType = "PDU"
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[pdu])
        add_box(model, body_ctx, pdu, x0 + PDU_W / 2.0, y0 + PDU_D / 2.0, 0.0, PDU_W, PDU_D, PDU_H, rot_z_deg=rot)
        add_pset(model, pdu, "Pset_DCM_PDU", {
            "ServesRow": row_id,
            "Rating_kVA": 225.0,
            "Facing": facing,
        })

    # 6. Cold-Aisle Containment (CAC-BC, CAC-DE)
    for cac_name, y_center, r1, r2 in [("CAC-BC", 7200.0, "B", "C"), ("CAC-DE", 12600.0, "D", "E")]:
        w_end = min(row_extents[r1][1], row_extents[r2][1])
        e_end = min(row_extents[r1][3], row_extents[r2][3])
        for sec_name, x_start, x_end in [("W", WEST_START_X, w_end), ("E", EAST_START_X, e_end)]:
            roof = ifcopenshell.api.run(
                "root.create_entity",
                model,
                ifc_class="IfcCovering",
                predefined_type="CEILING",
                name=f"{cac_name}-ROOF-{sec_name}",
            )
            roof.ObjectType = "ContainmentRoof"
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[roof])
            add_box(model, body_ctx, roof, 0.5 * (x_start + x_end), y_center, 2000.0,
                    x_end - x_start, 1400.0, 55.5)
            add_pset(model, roof, "Pset_DCM_Containment", {"Aisle": cac_name, "Section": sec_name})

            for end_tag, dx in [("L", x_start - 30.0), ("R", x_end + 30.0)]:
                door = ifcopenshell.api.run(
                    "root.create_entity",
                    model,
                    ifc_class="IfcDoor",
                    predefined_type="DOOR",
                    name=f"{cac_name}-DOOR-{sec_name}{end_tag}",
                )
                door.ObjectType = "ContainmentDoor"
                ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[door])
                add_box(model, body_ctx, door, dx, y_center, 0.0, 60.0, 1200.0, 2055.5)
                add_pset(model, door, "Pset_DCM_Containment", {"Aisle": cac_name, "Section": sec_name})

    # 7. Sprinklers (63 ceiling + 16 in-aisle)
    ceil_idx = 0
    for gx in range(1500, 27000, 3000):
        for gy in range(1500, 21000, 3000):
            sx, sy = float(gx), float(gy)
            # Relocate clear of column keep-out (750 mm from column centre)
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sy = cy - 900.0
            ceil_idx += 1
            sp = ifcopenshell.api.run(
                "root.create_entity",
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SP-CEIL-{ceil_idx:02d}",
            )
            sp.ObjectType = "SprinklerHead"
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[sp])
            add_cyl_z(model, body_ctx, sp, sx, sy, 3574.6, 25.0, 25.4)
            add_pset(model, sp, "Pset_DCM_Sprinkler", {"Type": "CEILING", "DeflectorElevation_mm": 3574.6})

    aisle_idx = 0
    in_aisle_xs = [3000.0, 5400.0, 7800.0, 9300.0, 12600.0, 15000.0, 17400.0, 18900.0]
    for yc in (7200.0, 12600.0):
        for sx in in_aisle_xs:
            aisle_idx += 1
            sp = ifcopenshell.api.run(
                "root.create_entity",
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SP-AISLE-{aisle_idx:02d}",
            )
            sp.ObjectType = "SprinklerHead"
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[sp])
            add_cyl_z(model, body_ctx, sp, sx, yc, 1890.0, 25.0, 110.0)
            add_pset(model, sp, "Pset_DCM_Sprinkler", {"Type": "IN_AISLE", "DeflectorElevation_mm": 1890.0})

    # 8. MEP Routing (all junctions butt flush with 0.0 mm overlap for zero clashes & full connectivity)
    # -----------------------------------------------------------------------
    # A. Power Busway (BW-1: 128 W x 147 H) — OVERHEAD at z_center = 2875 (z = 2801.5..2948.5)
    bus_z = 2875.0
    bus_x_trunk = 900.0
    bus_x_end = 17500.0
    bw_half = BUS_W / 2.0
    bus_segs = [
        ("BW-ENTRY", (ENTRY_X, ENTRY_Y, bus_z), (bus_x_trunk - bw_half, ENTRY_Y, bus_z)),
        ("BW-TRUNK", (bus_x_trunk, 4500.0 - bw_half, bus_z), (bus_x_trunk, 15300.0 + bw_half, bus_z)),
        ("BW-BR-AB", (bus_x_trunk + bw_half, 4500.0, bus_z), (bus_x_end, 4500.0, bus_z)),
        ("BW-BR-CD", (bus_x_trunk + bw_half, 9900.0, bus_z), (bus_x_end, 9900.0, bus_z)),
        ("BW-BR-EF", (bus_x_trunk + bw_half, 15300.0, bus_z), (bus_x_end, 15300.0, bus_z)),
    ]
    for name, p1, p2 in bus_segs:
        add_rect_segment(
            model, storey, body_ctx,
            "IfcCableSegment", "BUSBARSEGMENT", "Busway", name,
            p1, p2, BUS_W, BUS_H,
            "Pset_DCM_MEP", {"Service": "POWER_BUSWAY", "Zone": "OVERHEAD"},
        )

    # B. Telecom Cable Tray (CT-1: 683 W x 127 H) — UNDER-FLOOR at z_center = -250 (z = -313.5..-186.5)
    tray_z = -250.0
    tray_x_trunk = 900.0
    tray_x_end = 17500.0
    tw_half = TRAY_W / 2.0
    tray_segs = [
        ("CT-ENTRY", (ENTRY_X, ENTRY_Y, tray_z), (tray_x_trunk - tw_half, ENTRY_Y, tray_z)),
        ("CT-TRUNK", (tray_x_trunk, 4500.0 - tw_half, tray_z), (tray_x_trunk, 15300.0 + tw_half, tray_z)),
        ("CT-BR-AB", (tray_x_trunk + tw_half, 4500.0, tray_z), (tray_x_end, 4500.0, tray_z)),
        ("CT-BR-CD", (tray_x_trunk + tw_half, 9900.0, tray_z), (tray_x_end, 9900.0, tray_z)),
        ("CT-BR-EF", (tray_x_trunk + tw_half, 15300.0, tray_z), (tray_x_end, 15300.0, tray_z)),
    ]
    for name, p1, p2 in tray_segs:
        add_rect_segment(
            model, storey, body_ctx,
            "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", name,
            p1, p2, TRAY_W, TRAY_H,
            "Pset_DCM_MEP", {"Service": "TELECOM_TRAY", "Zone": "UNDERFLOOR"},
        )

    # C. Chilled Water Pipe (CHW-1: OD 168.3 mm) — UNDER-FLOOR at z_center = -600 (z = -684.15..-515.85)
    chw_z = -600.0
    chw_x_trunk = 900.0
    chw_x_end = 17500.0
    chw_r = CHW_OD / 2.0
    chw_segs = [
        ("CHW-ENTRY", (ENTRY_X, ENTRY_Y, chw_z), (chw_x_trunk - chw_r, ENTRY_Y, chw_z)),
        ("CHW-TRUNK", (chw_x_trunk, 1800.0 - chw_r, chw_z), (chw_x_trunk, 16800.0 + chw_r, chw_z)),
        ("CHW-BR-A-PERIM", (chw_x_trunk + chw_r, 1800.0, chw_z), (24000.0, 1800.0, chw_z)),
        ("CHW-BR-BC", (chw_x_trunk + chw_r, 7200.0, chw_z), (chw_x_end, 7200.0, chw_z)),
        ("CHW-BR-DE", (chw_x_trunk + chw_r, 12600.0, chw_z), (chw_x_end, 12600.0, chw_z)),
        ("CHW-BR-F", (chw_x_trunk + chw_r, 16800.0, chw_z), (chw_x_end, 16800.0, chw_z)),
    ]
    for name, p1, p2 in chw_segs:
        add_pipe_segment(
            model, storey, body_ctx, name, p1, p2, CHW_OD,
            "Pset_DCM_MEP", {"Service": "CHILLED_WATER", "Zone": "UNDERFLOOR"},
        )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)
    return model


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"
    model = build_model(out_path)
    if os.environ.get("VALIDATE_IFC") == "1":
        logger = ifcopenshell.validate.json_logger()
        ifcopenshell.validate.validate(model, logger, express_rules=True)
        print("Validation issues:", len(logger.statements))
        for s in logger.statements[:10]:
            print(s)
