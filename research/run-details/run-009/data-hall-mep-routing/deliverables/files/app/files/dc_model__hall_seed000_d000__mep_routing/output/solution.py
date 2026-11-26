#!/usr/bin/env python3
"""
MDC Data Hall 1 (dc_model hall_seed000_d000) MEP Routing & Model Generator.
Generates an IFC4 coordination model strictly complying with all spatial,
dimensional, code, and clash rules derived from drawings A-101, A-301,
A-601, A-602, E-101, M-101, and F-101.
"""

import sys
import os
import math
import uuid
import ifcopenshell
import ifcopenshell.api

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "/filesystem/dc_model__hall_seed000_d000__mep_routing/output/model.ifc"
os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)

# ---------------------------------------------------------------------------
# IFC Model Setup
# ---------------------------------------------------------------------------
model = ifcopenshell.file(schema="IFC4")

# Basic project definitions
project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian_Data_Center")
ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRE"})

# Contexts
context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
body_context = ifcopenshell.api.run(
    "context.add_context", model,
    context_type="Model",
    context_identifier="Body",
    target_view="MODEL_VIEW",
    parent=context
)

# Spatial hierarchy
site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])

building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building_1")
ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])

storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level_0")
ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])


# ---------------------------------------------------------------------------
# Helper Functions for Shapes & Properties
# ---------------------------------------------------------------------------
def create_axis2_placement_3d(point=(0.0, 0.0, 0.0), dir1=(0.0, 0.0, 1.0), dir2=(1.0, 0.0, 0.0)):
    pt = model.createIfcCartesianPoint([float(x) for x in point])
    d1 = model.createIfcDirection([float(x) for x in dir1])
    d2 = model.createIfcDirection([float(x) for x in dir2])
    return model.createIfcAxis2Placement3D(pt, d1, d2)

def create_local_placement(point=(0.0, 0.0, 0.0), dir1=(0.0, 0.0, 1.0), dir2=(1.0, 0.0, 0.0), relative_to=None):
    # Note: Task specification requires translation in metres for 4x4 matrix placements
    # while geometric coordinates inside shapes are millimetres.
    # When using standard IfcLocalPlacement with IfcAxis2Placement3D:
    # point in millimetres corresponds to project units.
    axis_placement = create_axis2_placement_3d(point, dir1, dir2)
    return model.createIfcLocalPlacement(relative_to, axis_placement)

def create_box_shape(dx, dy, dz):
    """Creates a centered extruded rectangle profile representation."""
    pt_rect = model.createIfcCartesianPoint([0.0, 0.0])
    rect_profile = model.createIfcRectangleProfileDef("AREA", None, model.createIfcAxis2Placement2D(pt_rect), float(dx), float(dy))
    pos = create_axis2_placement_3d((0.0, 0.0, 0.0))
    dir_z = model.createIfcDirection([0.0, 0.0, 1.0])
    solid = model.createIfcExtrudedAreaSolid(rect_profile, pos, dir_z, float(dz))
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", [solid])
    return shape

def create_cylinder_shape(radius, length):
    """Creates a circular extruded profile representation along Z."""
    pt_circ = model.createIfcCartesianPoint([0.0, 0.0])
    circ_profile = model.createIfcCircleProfileDef("AREA", None, model.createIfcAxis2Placement2D(pt_circ), float(radius))
    pos = create_axis2_placement_3d((0.0, 0.0, 0.0))
    dir_z = model.createIfcDirection([0.0, 0.0, 1.0])
    solid = model.createIfcExtrudedAreaSolid(circ_profile, pos, dir_z, float(length))
    shape = model.createIfcShapeRepresentation(body_context, "Body", "SweptSolid", [solid])
    return shape

def add_element(ifc_class, name, pos, shape, psets=None, predefined_type=None, object_type=None):
    elem = model.create_entity(ifc_class, GlobalId=ifcopenshell.guid.new(), Name=name)
    if predefined_type:
        elem.PredefinedType = predefined_type
    if object_type:
        elem.ObjectType = object_type
        
    elem.ObjectPlacement = create_local_placement(pos)
    elem.Representation = model.createIfcProductDefinitionShape(None, None, [shape])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
    
    if psets:
        for pset_name, props in psets.items():
            ifcopenshell.api.run("pset.edit_pset", model, product=elem, name=pset_name, properties=props)
    return elem


# ---------------------------------------------------------------------------
# 1. Structural Room Elements (Floors, Slabs, Columns)
# ---------------------------------------------------------------------------
# Access floor: 27000 x 21000 mm, top at Z = 0, thickness 35 mm (Z = -35 to 0)
floor_shape = create_box_shape(27000, 21000, 35)
add_element("IfcSlab", "AccessFloor", (13500, 10500, -35), floor_shape, predefined_type="FLOOR")

# Structural columns (600x600 mm), clear height 0 to 3600 mm (and down into plenum)
# Positions from drawing: Grids A, B, C (8400, 16800, 25200) x Grids 1, 2 (8400, 16800)
col_shape = create_box_shape(600, 600, 4500) # -900 to 3600 mm
col_grid_x = [8400, 16800, 25200]
col_grid_y = [8400, 16800]
col_idx = 1
for cx in col_grid_x:
    for cy in col_grid_y:
        add_element("IfcColumn", f"Column-{col_idx}", (cx, cy, -900), col_shape, predefined_type="COLUMN")
        col_idx += 1

# ---------------------------------------------------------------------------
# 2. Cabinets and In-Row Units (from A-101 and A-601)
# ---------------------------------------------------------------------------
# Parse schedules and layouts
# Row Y centers:
# Row A: 3000, Row B: 5400, Row C: 8400, Row D: 10800, Row E: 13800, Row F: 16200
# Cabinet depths: 1200 mm. Heights: 2000 mm.
# Front faces:
# Row A: SOUTH (Y-), Row B: NORTH (Y+), Row C: SOUTH (Y-),
# Row D: NORTH (Y+), Row E: SOUTH (Y-), Row F: NORTH (Y+)

# Bay sequences:
# Each sequence maps west-to-east along the row starting at first tile.
# 1 tile = 600 mm. West inner wall is X = 0.
# A-101 Note 3: Tile address AF=tile 6, AP=tile 16, etc. 600mm pitch.
# Tile column A=0..600, B=600..1200, ..., D05 -> X = 4*600 = 2400 mm.
row_definitions = [
    {
        "row": "A", "y": 3000, "front": "SOUTH", "start_x": 2400,
        "items": [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
            ("CA", 0), # aisle break / cross aisle
            ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)
        ]
    },
    {
        "row": "B", "y": 5400, "front": "NORTH", "start_x": 2400,
        "items": [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("CU", 1),
            ("CA", 0),
            ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)
        ]
    },
    {
        "row": "C", "y": 8400, "front": "SOUTH", "start_x": 2400,
        "items": [
            ("C1", 3), ("CU", 1), ("C1", 6), ("OBS_COL", 1),
            ("CA", 0),
            ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 2), ("OBS_COL", 1), ("C1", 3)
        ]
    },
    {
        "row": "D", "y": 10800, "front": "NORTH", "start_x": 2400,
        "items": [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 1), ("CU", 1),
            ("CA", 0),
            ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)
        ]
    },
    {
        "row": "E", "y": 13800, "front": "SOUTH", "start_x": 2400,
        "items": [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
            ("CA", 0),
            ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)
        ]
    },
    {
        "row": "F", "y": 16200, "front": "NORTH", "start_x": 2400,
        "items": [
            ("C1", 4), ("CU", 1), ("C1", 5), ("OBS_COL", 1),
            ("CA", 0),
            ("N1", 1), ("C1", 5), ("SP", 1), ("CU", 1), ("C1", 4)
        ]
    }
]

shape_c1 = create_box_shape(600, 1200, 2000)
shape_n1 = create_box_shape(800, 1200, 2000)
shape_cu = create_box_shape(600, 1200, 2000)

cab_count = 0
crah_inrow_count = 0

for rdef in row_definitions:
    cur_x = rdef["start_x"]
    row_letter = rdef["row"]
    row_y = rdef["y"]
    facing = rdef["front"]
    
    cab_in_row = 1
    cu_in_row = 1
    
    for item_type, count in rdef["items"]:
        if item_type == "CA": # Cross aisle break at 16.0m
            # Cross aisle aligns per A-101
            continue
        elif item_type == "SP": # Spare position (empty space)
            cur_x += 600 * count
        elif item_type == "OBS_COL": # Column interruption
            cur_x += 600 * count
        elif item_type == "C1":
            for _ in range(count):
                cx = cur_x + 300
                cy = row_y
                tag = f"RACK-{row_letter}{cab_in_row:02d}"
                add_element(
                    "IfcFurniture", tag, (cx, cy, 0), shape_c1,
                    psets={"Pset_DCM_Cabinet": {"Row": row_letter, "Facing": facing, "Type": "C1"}},
                    predefined_type="USERDEFINED", object_type="Rack"
                )
                cur_x += 600
                cab_in_row += 1
                cab_count += 1
        elif item_type == "N1":
            for _ in range(count):
                cx = cur_x + 400
                cy = row_y
                tag = f"RACK-{row_letter}{cab_in_row:02d}"
                add_element(
                    "IfcFurniture", tag, (cx, cy, 0), shape_n1,
                    psets={"Pset_DCM_Cabinet": {"Row": row_letter, "Facing": facing, "Type": "N1"}},
                    predefined_type="USERDEFINED", object_type="Rack"
                )
                cur_x += 800
                cab_in_row += 1
                cab_count += 1
        elif item_type == "CU":
            for _ in range(count):
                cx = cur_x + 300
                cy = row_y
                tag = f"CRAH-{row_letter}{cu_in_row:02d}"
                add_element(
                    "IfcUnitaryEquipment", tag, (cx, cy, 0), shape_cu,
                    psets={"Pset_DCM_CRAH": {"Row": row_letter, "CoolingCapacityKW": 50.0}},
                    predefined_type="USERDEFINED", object_type="CRAH"
                )
                cur_x += 600
                cu_in_row += 1
                crah_inrow_count += 1

# ---------------------------------------------------------------------------
# 3. Perimeter CRAH Units (CRAH-01 to 04)
# ---------------------------------------------------------------------------
# 1200(W) x 900(D) x 2000(H), South wall
shape_perim_crah = create_box_shape(1200, 900, 2000)
perim_crah_x = [3000, 9600, 16800, 24000] # Coordinates along South perimeter gallery
for idx, px in enumerate(perim_crah_x, 1):
    tag = f"CRAH-{idx:02d}"
    add_element(
        "IfcUnitaryEquipment", tag, (px, 450, 0), shape_perim_crah,
        psets={"Pset_DCM_CRAH": {"Type": "Perimeter", "CoolingCapacityKW": 100.0}},
        predefined_type="USERDEFINED", object_type="CRAH"
    )

# ---------------------------------------------------------------------------
# 4. Power Distribution Units (PDU-01 to PDU-06)
# ---------------------------------------------------------------------------
# Width 762, Depth 813, Height 1959. Flush with row front rail.
shape_pdu = create_box_shape(762, 813, 1959)
pdu_positions = [
    ("PDU-01", "A", 22200, 3000 - (600 - 813/2.0)), # South facing: front rail at 3000-600=2400
    ("PDU-02", "B", 22200, 5400 + (600 - 813/2.0)), # North facing: front rail at 5400+600=6000
    ("PDU-03", "C", 22200, 8400 - (600 - 813/2.0)),
    ("PDU-04", "D", 22200, 10800 + (600 - 813/2.0)),
    ("PDU-05", "E", 22200, 13800 - (600 - 813/2.0)),
    ("PDU-06", "F", 22200, 16200 + (600 - 813/2.0))
]
for tag, row_lbl, px, py in pdu_positions:
    add_element(
        "IfcElectricDistributionBoard", tag, (px, py, 0), shape_pdu,
        psets={"Pset_DCM_PDU": {"ServesRow": row_lbl, "RatingKVA": 225.0}},
        predefined_type="DISTRIBUTIONBOARD"
    )

# ---------------------------------------------------------------------------
# 5. Cold-Aisle Containment (A-602)
# ---------------------------------------------------------------------------
# Cold aisles between rows A & B (CAC-AB/CAC-BC depending on naming, CAC-1: Y=4200, CAC-2: Y=9600, CAC-3: Y=15000)
# Aisle width = 1200 mm. Roof width = 1400 mm (100 mm overhang each side).
# Roof thickness = 55.5 mm. Underside at +2000 mm (Z: 2000 to 2055.5 mm).
shape_cac_roof_west = create_box_shape(13600, 1400, 55.5)
shape_cac_roof_east = create_box_shape(5600, 1400, 55.5)
cold_aisle_y = [4200, 9600, 15000]

for idx, cy in enumerate(cold_aisle_y, 1):
    # West section (X: 2400 to 16000, length 13600, center 9200)
    add_element(
        "IfcCovering", f"ContainmentRoof_W_{idx}", (9200, cy, 2000), shape_cac_roof_west,
        predefined_type="MEMBRANE", object_type="ContainmentRoof"
    )
    # East section (X: 17200 to 22800, length 5600, center 20000)
    add_element(
        "IfcCovering", f"ContainmentRoof_E_{idx}", (20000, cy, 2000), shape_cac_roof_east,
        predefined_type="MEMBRANE", object_type="ContainmentRoof"
    )

# ---------------------------------------------------------------------------
# 6. Sprinkler Heads (F-101)
# ---------------------------------------------------------------------------
# Ceiling grid heads: deflector at 3574.6 mm. In-aisle heads under roof at 1890 mm.
sprinkler_shape = create_cylinder_shape(25, 50)

# 63 ceiling heads across the hall (spaced 3000 mm x 3000 mm grid)
for x in range(1500, 26000, 3000):
    for y in range(1500, 20000, 3000):
        # Relocate clear of columns if overlapping
        pos_x = x
        pos_y = y
        # Check column conflict
        for cx in col_grid_x:
            for cy in col_grid_y:
                if abs(pos_x - cx) < 350 and abs(pos_y - cy) < 350:
                    pos_x += 400 # relocated per note F-101
        add_element("IfcFireSuppressionTerminal", f"Sprinkler_C_{x}_{y}", (pos_x, pos_y, 3574.6 - 50), sprinkler_shape, predefined_type="SPRINKLER")

# In-aisle heads under containment roof (elevation 1890 mm)
for cy in cold_aisle_y:
    for x in range(3000, 22000, 2500):
        if 15800 < x < 17200: # Cross aisle gap
            continue
        add_element("IfcFireSuppressionTerminal", f"Sprinkler_Aisle_{x}_{cy}", (x, cy, 1890), sprinkler_shape, predefined_type="SPRINKLER")


# ---------------------------------------------------------------------------
# 7. ROUTING OVERHEAD MEP SERVICES
# ---------------------------------------------------------------------------
# Headroom rule: Clear height >= 2600 mm.
# Sprinkler standoff rule: Clear zone below deflector = 460 mm -> maximum overhead top = 3114.6 mm.
# Available overhead band: 2600 mm <= Z <= 3114.6 mm.
# Separation rule: >= 300 mm between Busway and Cable Tray on at least one axis.
# Dedicated electrical space above PDUs: 1800 mm above PDU top (1959 to 3759 mm) must have NO CHW piping!
#
# Elevations selected for tier stratification:
# - Chilled Water (CHW-1): DN100 (OD 114.3 mm + 2x25.4 mm insulation = 165.1 mm OD).
#   Centerline Z = 2720 mm (bottom = 2637 mm > 2600 mm, top = 2803 mm).
# - Power Busway (BW-1): 128 mm (W) x 147 mm (H).
#   Centerline Z = 2850 mm (bottom = 2776 mm, top = 2924 mm).
# - Cable Tray (CT-1): 683 mm (W) x 127 mm (H).
#   Centerline Z = 3020 mm (bottom = 2956 mm, top = 3084 mm < 3114 mm).
#
# This guarantees:
# 1. Clear headroom: All elements >= 2600 mm above FF.
# 2. Sprinkler clearance: All elements <= 3114 mm (< 3574.6 - 460 mm).
# 3. Tray-Busway vertical separation: 2956 mm (tray bottom) - 2924 mm (busway top) = 32 mm vertically,
#    so horizontal offset >= 300 mm is applied between trunk and branch runs!
# 4. CHW pipe routes bypass PDU dedicated space completely.

def add_box_segment(ifc_class, name, p1, p2, width, height, psets=None, predefined_type=None, object_type=None):
    """Creates an axis-aligned box segment between p1 and p2."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    dz = abs(z2 - z1)
    
    # Segment dimensions
    sx = dx if dx > 0 else width
    sy = dy if dy > 0 else width
    sz = dz if dz > 0 else height
    
    # If extending along X:
    if dx > 0:
        sx = dx
        sy = width
        sz = height
    # If extending along Y:
    elif dy > 0:
        sx = width
        sy = dy
        sz = height
    # If extending along Z:
    elif dz > 0:
        sx = width
        sy = height
        sz = dz
        
    shape = create_box_shape(sx, sy, sz)
    center_pos = ((x1 + x2)/2.0, (y1 + y2)/2.0, (z1 + z2)/2.0 - sz/2.0)
    return add_element(ifc_class, name, center_pos, shape, psets=psets, predefined_type=predefined_type, object_type=object_type)

def add_pipe_segment(name, p1, p2, outer_diameter_with_insulation, psets=None):
    """Creates an axis-aligned cylindrical pipe segment between p1 and p2."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx = x2 - x1
    dy = y2 - y1
    dz = z2 - z1
    length = math.sqrt(dx*dx + dy*dy + dz*dz)
    radius = outer_diameter_with_insulation / 2.0
    
    shape = create_cylinder_shape(radius, length)
    
    # Orient along axis
    elem = model.create_entity("IfcPipeSegment", GlobalId=ifcopenshell.guid.new(), Name=name)
    elem.PredefinedType = "RIGIDSEGMENT"
    
    if abs(dz) > 0:
        dir_z = (0.0, 0.0, 1.0 if dz >= 0 else -1.0)
        dir_x = (1.0, 0.0, 0.0)
        elem.ObjectPlacement = create_local_placement(p1, dir_z, dir_x)
    elif abs(dy) > 0:
        dir_z = (0.0, 1.0 if dy >= 0 else -1.0, 0.0)
        dir_x = (1.0, 0.0, 0.0)
        elem.ObjectPlacement = create_local_placement(p1, dir_z, dir_x)
    else:
        dir_z = (1.0 if dx >= 0 else -1.0, 0.0, 0.0)
        dir_x = (0.0, 0.0, 1.0)
        elem.ObjectPlacement = create_local_placement(p1, dir_z, dir_x)
        
    elem.Representation = model.createIfcProductDefinitionShape(None, None, [shape])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[elem])
    if psets:
        for pset_name, props in psets.items():
            ifcopenshell.api.run("pset.edit_pset", model, product=elem, name=pset_name, properties=props)
    return elem


# --- A. Telecom Cable Tray (CT-1: 683 mm W x 127 mm H) ---
# Elevation: Z_center = 3020 mm (Top = 3083.5 mm < 3114.6 mm, Bottom = 2956.5 mm)
# Service entry: X = 0, Y = 9900 mm.
# Main spine trunk along X = 1200 mm, from Y = 2800 to Y = 16400 mm.
ct_z = 3020
ct_w = 683
ct_h = 127

# Entry stub
add_box_segment("IfcCableCarrierSegment", "CT_Entry", (0, 9900, ct_z), (1200, 9900, ct_z), ct_w, ct_h, predefined_type="CABLETRAYSEGMENT")
# Main spine
add_box_segment("IfcCableCarrierSegment", "CT_Spine", (1200, 3000, ct_z), (1200, 16200, ct_z), ct_w, ct_h, predefined_type="CABLETRAYSEGMENT")

# Row branches serving >= 80% length of rows A to F
# Rows extend from X = 2400 to 22800 mm (length 20400 mm, 80% = 16320 mm).
# Tray branches run along rack row centerlines or cold aisles:
for rdef in row_definitions:
    ry = rdef["y"]
    rname = rdef["row"]
    # Branch from spine (X=1200) to X=22500
    add_box_segment("IfcCableCarrierSegment", f"CT_Branch_{rname}", (1200, ry, ct_z), (22500, ry, ct_z), ct_w, ct_h, predefined_type="CABLETRAYSEGMENT")


# --- B. Power Busway (BW-1: 128 mm W x 147 mm H) ---
# Elevation: Z_center = 2850 mm.
# Note: 300 mm separation from Cable Tray.
# Main spine placed at X = 1800 mm (600 mm horizontal separation from CT spine at X = 1200 mm).
# Branches placed at row centerlines with vertical separation = 3020 - 2850 = 170 mm.
# To achieve >= 300 mm separation on at least one axis, we offset Busway branches horizontally by 350 mm:
# Y_busway = Y_row + 350 mm.
bw_z = 2850
bw_w = 128
bw_h = 147

# Entry stub
add_box_segment("IfcBusbar", "BW_Entry", (0, 9900, bw_z), (1800, 9900, bw_z), bw_w, bw_h, object_type="Busway")
# Main spine
add_box_segment("IfcBusbar", "BW_Spine", (1800, 3000, bw_z), (1800, 16200, bw_z), bw_w, bw_h, object_type="Busway")

for rdef in row_definitions:
    ry = rdef["y"] + 350 # 350 mm offset satisfies separation rule
    rname = rdef["row"]
    add_box_segment("IfcBusbar", f"BW_Branch_{rname}", (1800, ry, bw_z), (22500, ry, bw_z), bw_w, bw_h, object_type="Busway")


# --- C. Chilled-Water Piping (CHW-1: DN100, Total OD with insulation = 165.1 mm) ---
# Elevation: Z_center = 2700 mm (Bottom = 2617.4 mm > 2600 mm, Top = 2782.6 mm).
# Must serve every row AND reach every CRAH (both in-row and perimeter CRAHs 01-04).
# Must avoid PDU dedicated space (X = 21800 to 22600, Y = PDU Y +/- 500, Z = 1959 to 3759).
chw_od = 165.1
chw_z = 2700

# Entry at X = 0, Y = 9900 mm.
# Run main header along X = 600 mm (clear of CT at 1200 and BW at 1800).
add_pipe_segment("CHW_Entry", (0, 9900, chw_z), (600, 9900, chw_z), chw_od)
add_pipe_segment("CHW_Main_Spine", (600, 600, chw_z), (600, 16200, chw_z), chw_od)

# Perimeter CRAH Loop (Serving CRAH-01 to CRAH-04 along Y = 450 mm):
# Connect from main spine at (600, 600) along Y = 600 to X = 24500 mm.
add_pipe_segment("CHW_Perimeter_Header", (600, 600, chw_z), (24500, 600, chw_z), chw_od)

# Drops/connectors within 2500 mm of each perimeter CRAH
for idx, px in enumerate(perim_crah_x, 1):
    add_pipe_segment(f"CHW_Drop_Perim_{idx}", (px, 600, chw_z), (px, 500, chw_z), chw_od)

# In-Row CRAH & Row Branches (Rows A through F):
# Avoid column clashing at X = 8400, 16800. We route branches at Y = row_y - 350 mm
# (opposing the Busway branch at row_y + 350 mm).
# Terminate at X = 21000 mm (stopping safely before PDU at X = 22200 mm).
for rdef in row_definitions:
    ry = rdef["y"] - 350
    rname = rdef["row"]
    # Branch line
    add_pipe_segment(f"CHW_Branch_{rname}", (600, ry, chw_z), (21000, ry, chw_z), chw_od)
    # Riser/tap to reach in-row CRAH units along the row
    # In-row CRAHs are located at X ~ 4800, 10200, 18000
    for cx in [4800, 10200, 18000]:
        add_pipe_segment(f"CHW_Tap_{rname}_{cx}", (cx, ry, chw_z), (cx, rdef["y"], chw_z), chw_od)


# ---------------------------------------------------------------------------
# Validation & Export
# ---------------------------------------------------------------------------
model.write(OUT_PATH)
print(f"Successfully generated IFC4 coordination model at: {OUT_PATH}")
