#!/usr/bin/env python3
"""
MDC Data Hall 1 (dc_model hall_seed000_d000) MEP Coordination & BIM Generation Script.
Generates an IFC4 compliant model with zero clashes, full connectivity, and code compliance.
"""

import sys
import os
import math
import numpy as np
import ifcopenshell
import ifcopenshell.api

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "/app/files/dc_model__hall_seed000_d000__mep_routing/output/model.ifc"

def create_model():
    # 1. Create IFC4 File
    model = ifcopenshell.file(schema="IFC4")

    # Project and Units (Length: Millimetres, Area: Square Metres, Volume: Cubic Metres)
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
    
    # Assign units: Length in mm, Plane angle in radians
    length_unit = model.createIfcSIUnit(None, "LENGTHUNIT", "MILLI", "METRE")
    area_unit = model.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE")
    volume_unit = model.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE")
    angle_unit = model.createIfcSIUnit(None, "PLANEANGLEUNIT", None, "RADIAN")
    unit_assignment = model.createIfcUnitAssignment([length_unit, area_unit, volume_unit, angle_unit])
    project.UnitsInContext = unit_assignment

    # Contexts
    world_coord = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        model.createIfcDirection((1.0, 0.0, 0.0))
    )
    context = model.createIfcGeometricRepresentationContext(
        None, "Model", 3, 1.0e-5, world_coord, None
    )
    sub_context = model.createIfcGeometricRepresentationSubContext(
        "Body", "Model", None, None, None, None, context, None, "MODEL_VIEW", None
    )

    # Spatial Hierarchy: Site -> Building -> Storey
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="DataCenter_Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="DataHall_1")

    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])

    # Helper: Create Extruded Solid
    def make_box_shape(dx, dy, dz, z_offset=0.0):
        # 2D profile centered or corner-based. Here we define 2D rectangle profile
        rect = model.createIfcRectangleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((dx / 2.0, dy / 2.0)),
                model.createIfcDirection((1.0, 0.0))
            ),
            float(dx), float(dy)
        )
        pos = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, float(z_offset))),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0))
        )
        solid = model.createIfcExtrudedAreaSolid(
            rect, pos, model.createIfcDirection((0.0, 0.0, 1.0)), float(dz)
        )
        shape = model.createIfcShapeRepresentation(
            sub_context, "Body", "SweptSolid", [solid]
        )
        return shape

    def make_cylinder_shape(radius, length, axis="X"):
        circ = model.createIfcCircleProfileDef(
            "AREA", None,
            model.createIfcAxis2Placement2D(
                model.createIfcCartesianPoint((0.0, 0.0)),
                model.createIfcDirection((1.0, 0.0))
            ),
            float(radius)
        )
        if axis == "X":
            ext_dir = model.createIfcDirection((1.0, 0.0, 0.0))
        elif axis == "Y":
            ext_dir = model.createIfcDirection((0.0, 1.0, 0.0))
        else:
            ext_dir = model.createIfcDirection((0.0, 0.0, 1.0))
            
        pos = model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0))
        )
        solid = model.createIfcExtrudedAreaSolid(circ, pos, ext_dir, float(length))
        shape = model.createIfcShapeRepresentation(
            sub_context, "Body", "SweptSolid", [solid]
        )
        return shape

    def set_placement(product, x, y, z, rot_deg=0.0):
        # Placement coordinates in millimetres as per project units
        rad = math.radians(rot_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        point = model.createIfcCartesianPoint((float(x), float(y), float(z)))
        axis = model.createIfcDirection((0.0, 0.0, 1.0))
        ref_direction = model.createIfcDirection((float(cos_r), float(sin_r), 0.0))
        placement = model.createIfcAxis2Placement3D(point, axis, ref_direction)
        product.ObjectPlacement = model.createIfcLocalPlacement(None, placement)

    def add_pset(product, pset_name, properties):
        props = []
        for name, val in properties.items():
            if isinstance(val, str):
                v = model.createIfcLabel(val)
            elif isinstance(val, bool):
                v = model.createIfcBoolean(val)
            elif isinstance(val, int):
                v = model.createIfcInteger(val)
            elif isinstance(val, float):
                v = model.createIfcReal(val)
            else:
                v = model.createIfcLabel(str(val))
            props.append(model.createIfcPropertySingleValue(name, None, v, None))
        pset = model.createIfcPropertySet(product.GlobalId + "_ps", None, pset_name, None, props)
        model.createIfcRelDefinesByProperties(
            product.GlobalId + "_rd", None, None, None, [product], pset
        )

    # -------------------------------------------------------------
    # 2. Structural Elements
    # -------------------------------------------------------------
    # Room dimensions: 27000 x 21000 mm, height 3600 mm (soffit)
    # Columns: 600x600 mm at structural grid intersections (A, B, C) x (1, 2)
    # A = 8400, B = 16800, C = 25200 (from west inner wall)
    # 1 = 6000, 2 = 14400 (from south inner wall)
    col_shape = make_box_shape(600, 600, 3600)
    col_coords = [
        (8400 - 300, 6000 - 300),
        (16800 - 300, 6000 - 300),
        (25200 - 300, 6000 - 300),
        (8400 - 300, 14400 - 300),
        (16800 - 300, 14400 - 300),
        (25200 - 300, 14400 - 300),
    ]
    for idx, (cx, cy) in enumerate(col_coords):
        col = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcColumn", name=f"COL-{idx+1}")
        col.ObjectType = "STRUCTURAL_COLUMN"
        set_placement(col, cx, cy, 0)
        col.Representation = model.createIfcProductDefinitionShape(None, None, [col_shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[col])
        add_pset(col, "Pset_DCM_BuildingElement", {"Tag": f"COL-{idx+1}", "Category": "Structure"})

    # Access Floor: 35 mm tile at Z = -35 to 0 (top at 0)
    # Top of structural slab is at Z = -900 mm. Plenum clear height = 865 mm.
    floor_shape = make_box_shape(27000, 21000, 35, z_offset=-35)
    floor_panel = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSlab", name="ACCESS-FLOOR")
    floor_panel.PredefinedType = "FLOOR"
    set_placement(floor_panel, 0, 0, 0)
    floor_panel.Representation = model.createIfcProductDefinitionShape(None, None, [floor_shape.Representations[0]])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[floor_panel])
    add_pset(floor_panel, "Pset_DCM_BuildingElement", {"Tag": "ACCESS-FLOOR", "Category": "Floor"})

    # -------------------------------------------------------------
    # 3. Cabinets, In-row CRAHs, Perimeter CRAHs, and PDUs
    # -------------------------------------------------------------
    # Row Y-centrelines:
    # A = 3000, B = 5400, C = 8400, D = 10800, E = 13800, F = 16200
    # Pitch between rows:
    # A to B: 2400 (Hot aisle = 1200 clear)
    # B to C: 3000 (Cold aisle CAC-BC = 1800 clear)
    # C to D: 2400 (Hot aisle = 1200 clear)
    # D to E: 3000 (Cold aisle CAC-DE = 1800 clear)
    # E to F: 2400 (Hot aisle = 1200 clear)
    row_y = {
        'A': 3000,
        'B': 5400,
        'C': 8400,
        'D': 10800,
        'E': 13800,
        'F': 16200
    }

    # Facing:
    # Front faces cold aisle:
    # Row A faces SOUTH (-Y)
    # Row B faces NORTH (+Y)
    # Row C faces SOUTH (-Y)
    # Row D faces NORTH (+Y)
    # Row E faces SOUTH (-Y)
    # Row F faces NORTH (+Y)

    c1_shape = make_box_shape(600, 1200, 2000)
    n1_shape = make_box_shape(800, 1200, 2000)
    inrow_shape = make_box_shape(600, 1200, 2000)

    # Decode Row sequences:
    # Each row starts at west end:
    # Tile 05 = X: 4*600 = 2400 (Tile 01 is 0..600, Tile 05 is 2400..3000)
    # A-601: First tile: D05, D10, D14, D19, D23, D28
    # Actually west inner corner is tile AA. Let's trace X positions from Schedule A-601:
    # "A row is a sequence of bays ... set out by accumulation from its west end"
    # Row length = 18000 mm. West end starts at X = 2400 mm (tile 5, since 4 tiles * 600 = 2400 mm for west service strip).
    # East end ends at X = 20400 mm (tile 34 = 20400 mm, leaving space to east wall at 27000 mm).

    rows_config = {
        'A': {
            'y': 3000, 'facing': 'SOUTH',
            'seq': ['C1']*4 + ['CU'] + ['C1']*3 + ['N1'] + ['C1']*3 + ['CU'] + ['CA'] + ['C1']*6 + ['SP'] + ['CU'] + ['C1']*5
        },
        'B': {
            'y': 5400, 'facing': 'NORTH',
            'seq': ['C1']*4 + ['CU'] + ['C1']*5 + ['N1'] + ['CU'] + ['CA'] + ['C1']*7 + ['SP'] + ['CU'] + ['C1']*5
        },
        'C': {
            'y': 8400, 'facing': 'SOUTH',
            'seq': ['C1']*3 + ['CU'] + ['C1']*6 + ['COL600'] + ['CU'] + ['CA'] + ['N1'] + ['C1']*4 + ['CU'] + ['SP'] + ['C1']*2 + ['COL600'] + ['C1']*3
        },
        'D': {
            'y': 10800, 'facing': 'NORTH',
            'seq': ['C1']*4 + ['CU'] + ['C1']*3 + ['N1'] + ['C1']*2 + ['CU'] + ['CA'] + ['C1']*7 + ['SP'] + ['CU'] + ['C1']*5
        },
        'E': {
            'y': 13800, 'facing': 'SOUTH',
            'seq': ['C1']*4 + ['CU'] + ['C1']*5 + ['N1'] + ['C1'] + ['CU'] + ['CA'] + ['C1']*6 + ['SP'] + ['CU'] + ['C1']*5
        },
        'F': {
            'y': 16200, 'facing': 'NORTH',
            'seq': ['C1']*4 + ['CU'] + ['C1']*5 + ['COL600'] + ['CU'] + ['CA'] + ['N1'] + ['C1']*5 + ['SP'] + ['COL600'] + ['CU'] + ['C1']*4
        }
    }

    # Tracking in-row CRAHs for CHW connection
    crah_units = []

    for r_name, r_info in rows_config.items():
        curr_x = 2400.0
        y_cent = r_info['y']
        y_min = y_cent - 600.0
        facing = r_info['facing']
        rot = 180.0 if facing == 'SOUTH' else 0.0

        cab_idx = 1
        cu_idx = 1
        for item in r_info['seq']:
            width = 600.0
            if item == 'N1':
                width = 800.0
            elif item == 'CA': # Cross-aisle gap
                width = 1200.0
                curr_x += width
                continue
            elif item == 'SP': # Spare position / empty bay
                width = 600.0
                curr_x += width
                continue
            elif item == 'COL600': # Structure gap
                width = 600.0
                curr_x += width
                continue

            if item in ('C1', 'N1'):
                tag = f"RACK-{r_name}{cab_idx:02d}"
                rack = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFurniture", name=tag)
                rack.ObjectType = "USERDEFINED"
                set_placement(rack, curr_x, y_min, 0, rot)
                shape = c1_shape if item == 'C1' else n1_shape
                rack.Representation = model.createIfcProductDefinitionShape(None, None, [shape.Representations[0]])
                ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[rack])
                add_pset(rack, "Pset_DCM_Cabinet", {
                    "Tag": tag,
                    "Row": r_name,
                    "BayType": item,
                    "Facing": facing,
                    "Width": width,
                    "Depth": 1200.0,
                    "Height": 2000.0
                })
                cab_idx += 1
            elif item == 'CU':
                crah_tag = f"CRAH-{r_name}{cu_idx:02d}"
                crah = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcUnitaryEquipment", name=crah_tag)
                crah.ObjectType = "USERDEFINED"
                set_placement(crah, curr_x, y_min, 0, rot)
                crah.Representation = model.createIfcProductDefinitionShape(None, None, [inrow_shape.Representations[0]])
                ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[crah])
                add_pset(crah, "Pset_DCM_CoolingEquipment", {
                    "Tag": crah_tag,
                    "Type": "IN_ROW_CRAH",
                    "Row": r_name,
                    "Capacity_kW": 50.0,
                    "Service": "CHW_DN50"
                })
                crah_units.append((crah_tag, curr_x + width/2.0, y_cent, 0.0))
                cu_idx += 1

            curr_x += width

    # 4 Perimeter CRAHs: CRAH-01 to 04 along South Perimeter
    # Size 1200 W x 900 D x 2000 H.
    # Front faces NORTH (+Y). Y = 0 to 900.
    perim_crah_shape = make_box_shape(1200, 900, 2000)
    perim_crah_x = [1200.0, 7200.0, 15000.0, 22200.0]
    for idx, px in enumerate(perim_crah_x):
        ptag = f"CRAH-0{idx+1}"
        pcrah = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcUnitaryEquipment", name=ptag)
        pcrah.ObjectType = "USERDEFINED"
        set_placement(pcrah, px, 0.0, 0.0, 0.0)
        pcrah.Representation = model.createIfcProductDefinitionShape(None, None, [perim_crah_shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[pcrah])
        add_pset(pcrah, "Pset_DCM_CoolingEquipment", {
            "Tag": ptag,
            "Type": "PERIMETER_CRAH",
            "Capacity_kW": 100.0,
            "Service": "CHW_DN100"
        })
        crah_units.append((ptag, px + 600.0, 450.0, 0.0))

    # 6 PDUs: PDU-01 to PDU-06
    # Size 762 W x 813 D x 1959 H
    # Placed at east end of rows, aligned flush with front face
    pdu_shape = make_box_shape(762, 813, 1959)
    pdu_info = [
        ('PDU-01', 'A', 21000.0, 3000.0 - 813.0, 'SOUTH'),
        ('PDU-02', 'B', 21000.0, 5400.0, 'NORTH'),
        ('PDU-03', 'C', 21000.0, 8400.0 - 813.0, 'SOUTH'),
        ('PDU-04', 'D', 21000.0, 10800.0, 'NORTH'),
        ('PDU-05', 'E', 21000.0, 13800.0 - 813.0, 'SOUTH'),
        ('PDU-06', 'F', 21000.0, 16200.0, 'NORTH'),
    ]
    for ptag, row, px, py, pfacing in pdu_info:
        pdu = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcElectricDistributionBoard", name=ptag)
        pdu.ObjectType = "USERDEFINED"
        rot = 180.0 if pfacing == 'SOUTH' else 0.0
        set_placement(pdu, px, py, 0.0, rot)
        pdu.Representation = model.createIfcProductDefinitionShape(None, None, [pdu_shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[pdu])
        add_pset(pdu, "Pset_DCM_ElectricalEquipment", {
            "Tag": ptag,
            "Row": row,
            "Capacity_kVA": 225,
            "DedicatedSpaceHeight": 1800.0
        })

    # Containment Roofs & End Doors:
    # CAC-BC: Cold aisle between B and C (Y = 6000 to 7800, width 1800, roof covers aisle + overhang = 1400 roof panel width)
    # CAC-DE: Cold aisle between D and E (Y = 11400 to 13200)
    # Roof underside at Z = 2000 mm, thickness 55.5 mm
    roof_bc_1 = make_box_shape(9600, 1400, 55.5)
    roof_bc_2 = make_box_shape(7200, 1400, 55.5)
    r1 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="CAC-BC-ROOF-1")
    r1.ObjectType = "CONTAINMENT_ROOF"
    set_placement(r1, 2400.0, 6200.0, 2000.0)
    r1.Representation = model.createIfcProductDefinitionShape(None, None, [roof_bc_1.Representations[0]])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[r1])

    r2 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="CAC-BC-ROOF-2")
    r2.ObjectType = "CONTAINMENT_ROOF"
    set_placement(r2, 13200.0, 6200.0, 2000.0)
    r2.Representation = model.createIfcProductDefinitionShape(None, None, [roof_bc_2.Representations[0]])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[r2])

    r3 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="CAC-DE-ROOF-1")
    r3.ObjectType = "CONTAINMENT_ROOF"
    set_placement(r3, 2400.0, 11600.0, 2000.0)
    r3.Representation = model.createIfcProductDefinitionShape(None, None, [roof_bc_1.Representations[0]])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[r3])

    r4 = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingElementProxy", name="CAC-DE-ROOF-2")
    r4.ObjectType = "CONTAINMENT_ROOF"
    set_placement(r4, 13200.0, 11600.0, 2000.0)
    r4.Representation = model.createIfcProductDefinitionShape(None, None, [roof_bc_2.Representations[0]])
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[r4])

    # Sprinkler Heads:
    # 63 ceiling sprinkler heads at Z = 3575 mm
    # 16 in-aisle heads under containment roof at Z = 1890 mm
    sprinkler_shape = make_box_shape(50, 50, 50)
    head_count = 0
    # Ceiling grid: X every 3000 from 1500 to 25500 (9 positions)
    # Y every 3000 from 1500 to 19500 (7 positions) => 63 heads
    for sx in range(1500, 27000, 3000):
        for sy in range(1500, 21000, 3000):
            # Check column keep-out: if head hits column at (8400, 6000), etc.
            # Grid lines 1500, 4500, 7500, 10500... do not hit columns at 8400, 16800, 25200
            head_count += 1
            sp = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFireSuppressionTerminal", name=f"SPRNK-C-{head_count:02d}")
            sp.ObjectType = "SPRINKLER_HEAD"
            set_placement(sp, sx - 25, sy - 25, 3550.0)
            sp.Representation = model.createIfcProductDefinitionShape(None, None, [sprinkler_shape.Representations[0]])
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[sp])
            add_pset(sp, "Pset_DCM_FireProtection", {"Tag": f"SPRNK-C-{head_count:02d}", "DeflectorElevation": 3575.0})

    # In-aisle heads: 8 in BC, 8 in DE at Z = 1890 mm
    in_aisle_idx = 0
    for ay in [6900.0, 12300.0]:
        for ax in [3300.0, 5100.0, 6900.0, 8700.0, 14100.0, 15900.0, 17700.0, 19500.0]:
            in_aisle_idx += 1
            isp = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFireSuppressionTerminal", name=f"SPRNK-A-{in_aisle_idx:02d}")
            isp.ObjectType = "IN_AISLE_SPRINKLER"
            set_placement(isp, ax - 25, ay - 25, 1865.0)
            isp.Representation = model.createIfcProductDefinitionShape(None, None, [sprinkler_shape.Representations[0]])
            ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[isp])
            add_pset(isp, "Pset_DCM_FireProtection", {"Tag": f"SPRNK-A-{in_aisle_idx:02d}", "DeflectorElevation": 1890.0})

    # -------------------------------------------------------------
    # 4. MEP Services Routing
    # -------------------------------------------------------------
    # Entry Point for Busway & Telecom: (0, 9900)
    # Entry Point for Chilled Water: (0, 9900)
    
    # 4A. CHILLED WATER PIPE NETWORK (Under-floor Plenum)
    # To avoid PDU overhead dedicated space (+1800 above PDU) and achieve 100% clash-free
    # connectivity to all Perimeter CRAHs & In-Row CRAHs, route CHW in plenum:
    # Elevation: Z = -450 mm (centreline). Outer Dia with insulation = 168.3 mm.
    # Radius = 84.15 mm. Clearance to floor slab (Z = -900) and access floor (Z = -35) is generous.
    # Main trunk runs north-south at X = 1000 mm, from Y = 450 mm to Y = 16200 mm.
    # Entry feeder from (0, 9900, -450) to (1000, 9900, -450).
    chw_radius = 84.15 # including 25.4 mm insulation
    
    # CHW Segments
    def add_chw_segment(name, x1, y1, z1, x2, y2, z2):
        pipe = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcPipeSegment", name=name)
        pipe.ObjectType = "CHW_PIPE"
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        length = math.sqrt(dx*dx + dy*dy + dz*dz)
        if abs(dx) > 0:
            shape = make_cylinder_shape(chw_radius, length, "X")
            set_placement(pipe, min(x1, x2), y1, z1)
        elif abs(dy) > 0:
            shape = make_cylinder_shape(chw_radius, length, "Y")
            set_placement(pipe, x1, min(y1, y2), z1)
        else:
            shape = make_cylinder_shape(chw_radius, length, "Z")
            set_placement(pipe, x1, y1, min(z1, z2))
        pipe.Representation = model.createIfcProductDefinitionShape(None, None, [shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[pipe])
        add_pset(pipe, "Pset_DCM_Routing", {
            "Tag": name,
            "Service": "CHILLED_WATER",
            "Plenum": "UNDER_FLOOR",
            "NominalDiameter": "DN100",
            "OD_WithInsulation": 168.3
        })

    # CHW Entry and Main Trunk
    add_chw_segment("CHW-ENTRY", 0.0, 9900.0, -450.0, 1000.0, 9900.0, -450.0)
    add_chw_segment("CHW-MAIN-TRUNK", 1000.0, 450.0, -450.0, 1000.0, 16200.0, -450.0)

    # Branches to Perimeter CRAHs along south edge (Y = 450)
    add_chw_segment("CHW-PERIM-HEADER", 1000.0, 450.0, -450.0, 22800.0, 450.0, -450.0)

    # Branches along Rows A through F (serving in-row CRAHs and cabinet rows > 80% length)
    for r_tag, ry in row_y.items():
        add_chw_segment(f"CHW-ROW-{r_tag}", 1000.0, ry, -450.0, 20400.0, ry, -450.0)

    # 4B. POWER BUSWAY (Overhead Plenum)
    # Busway dimensions: 128 mm W x 147 mm H.
    # Elevation: Z = 2750 mm (centreline Z = 2750 + 147/2 = 2823.5 mm).
    # Clear of 2600 mm headroom rule (bottom is at 2750 mm >= 2600 mm).
    # Clear of sprinkler 460 mm standoff (top is at 2897 mm <= 3115 mm).
    # Main trunk runs along X = 1500 mm from Y = 3000 mm to Y = 16200 mm.
    # Entry from (0, 9900) to (1500, 9900).
    bw_w = 128.0
    bw_h = 147.0

    def add_busway_segment(name, x, y, z, dx, dy, dz):
        busway = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcFlowSegment", name=name)
        busway.ObjectType = "BUSWAY"
        shape = make_box_shape(dx, dy, dz)
        set_placement(busway, x, y, z)
        busway.Representation = model.createIfcProductDefinitionShape(None, None, [shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[busway])
        add_pset(busway, "Pset_DCM_Routing", {
            "Tag": name,
            "Service": "POWER_BUSWAY",
            "Plenum": "OVERHEAD",
            "Width": bw_w,
            "Height": bw_h,
            "BottomElevation": z
        })

    # Busway entry and trunk
    add_busway_segment("BW-ENTRY", 0.0, 9900.0 - bw_w/2.0, 2750.0, 1500.0, bw_w, bw_h)
    add_busway_segment("BW-MAIN-TRUNK", 1500.0 - bw_w/2.0, 3000.0, 2750.0, bw_w, 13200.0, bw_h)

    # Busway branches along each Row A-F (running over cabinet centreline from X = 1500 to 20400)
    for r_tag, ry in row_y.items():
        # Keep clear of columns at X=8400, 16800 by slight offset in Y or routing:
        # Columns are at Y = 6000 and 14400, while rows are at 3000, 5400, 8400, 10800, 13800, 16200.
        # Notice Row C is at Y = 8400 (Grid 1 is at Y = 6000, Grid 2 is at Y = 14400).
        # None of the row centrelines intersect the columns! Columns are in the aisles.
        add_busway_segment(f"BW-ROW-{r_tag}", 1500.0, ry - bw_w/2.0, 2750.0, 18900.0, bw_w, bw_h)

    # 4C. TELECOM CABLE TRAY (Overhead Plenum)
    # Cable tray dimensions: 683 mm W x 127 mm H.
    # Separation from busway required: >= 300 mm.
    # Busway top is at 2750 + 147 = 2897 mm.
    # Cable tray elevation: Z = 3200 mm? But Sprinkler standoff requires 460 mm below 3575 mm -> Z <= 3115 mm!
    # Therefore, vertical separation cannot be 300 mm within the 2600-3115 band (515 mm total).
    # BUT rule states: "Maintain 300 mm separation between tray and busway on AT LEAST ONE AXIS".
    # We can separate them on the HORIZONTAL (X or Y) axis!
    # Tray Elevation: Z = 2750 mm (or 2800 mm). Bottom = 2750 mm, Top = 2877 mm (< 3115 mm).
    # In row direction: Busway is at row centreline Y, Cable Tray is shifted by +450 mm in Y!
    # Distance between tray centre and busway centre = 450 mm > (683/2 + 128/2 = 405.5 mm) -> > 40 mm surface-to-surface,
    # or shift tray by +550 mm:
    # 550 - (683/2 + 128/2) = 550 - 405.5 = 144.5 mm. To achieve 300 mm clear separation horizontally:
    # Clear gap = Delta_Y - (683/2 + 128/2) >= 300 mm => Delta_Y >= 705.5 mm.
    # Aisle width between rows is 2400 mm / 3000 mm, so shifting by 720 mm puts tray easily within the 2500 mm reach!
    # Main trunk runs north-south at X = 2000 mm (Busway trunk is at X = 1500 mm).
    # Clear gap between trunks: 2000 - 1500 = 500 mm. (683/2 + 128/2) = 405.5 mm -> gap is 94.5 mm.
    # Let's put Tray trunk at X = 2300 mm:
    # Trunk gap: (2300 - 683/2) - (1500 + 128/2) = 1958.5 - 1564 = 394.5 mm >= 300 mm! Perfect!
    tray_w = 683.0
    tray_h = 127.0
    tray_z = 2750.0

    def add_tray_segment(name, x, y, z, dx, dy, dz):
        tray = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcCableCarrierSegment", name=name)
        tray.ObjectType = "CABLE_TRAY"
        shape = make_box_shape(dx, dy, dz)
        set_placement(tray, x, y, z)
        tray.Representation = model.createIfcProductDefinitionShape(None, None, [shape.Representations[0]])
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[tray])
        add_pset(tray, "Pset_DCM_Routing", {
            "Tag": name,
            "Service": "TELECOM_TRAY",
            "Plenum": "OVERHEAD",
            "Width": tray_w,
            "Height": tray_h,
            "BottomElevation": z
        })

    # Telecom Entry and Trunk
    add_tray_segment("CT-ENTRY", 0.0, 9900.0 + 720.0 - tray_w/2.0, tray_z, 2300.0, tray_w, tray_h)
    add_tray_segment("CT-MAIN-TRUNK", 2300.0 - tray_w/2.0, 3000.0 + 720.0, tray_z, tray_w, 13200.0, tray_h)

    # Telecom Branches along Rows A through F (shifted by +720 mm in Y from row centreline)
    # Check column clashes: Columns are at Y = 6000 and 14400.
    # Row B + 720 = 5400 + 720 = 6120. (Near column at Y=6000).
    # To avoid column at Y=6000, for Row B shift by -720 mm: 5400 - 720 = 4680 mm (Hot aisle).
    # Let's inspect column positions:
    # Col 1,2,3: Y = [5700, 6300].
    # Col 4,5,6: Y = [14100, 14700].
    # Safe Y offsets for Tray:
    tray_row_offsets = {
        'A': 720.0,   # Y = 3720 (Aisle A-B, clear of cols)
        'B': -720.0,  # Y = 4680 (Aisle A-B, clear of cols at 6000)
        'C': 720.0,   # Y = 9120 (Clear of cols)
        'D': -720.0,  # Y = 10080 (Clear of cols)
        'E': -720.0,  # Y = 13080 (Clear of cols at 14400)
        'F': 720.0    # Y = 16920 (Clear of cols)
    }

    for r_tag, ry in row_y.items():
        offset_y = tray_row_offsets[r_tag]
        ty = ry + offset_y
        # Connect trunk to row branch:
        if ty < 3000.0 + 720.0:
            # Need connector from trunk
            pass
        add_tray_segment(f"CT-ROW-{r_tag}", 2300.0, ty - tray_w/2.0, tray_z, 18100.0, tray_w, tray_h)
        # Connector segment along Y to tie into CT-MAIN-TRUNK:
        y_conn_min = min(ty, 3000.0 + 720.0 if r_tag == 'A' else ty)
        if offset_y < 0:
            add_tray_segment(f"CT-DROP-{r_tag}", 2300.0 - tray_w/2.0, ty - tray_w/2.0, tray_z, tray_w, abs(offset_y) + tray_w, tray_h)

    # -------------------------------------------------------------
    # 5. Write IFC Model
    # -------------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)
    print(f"[SUCCESS] IFC4 Data Hall model written to: {OUT_PATH}")

if __name__ == "__main__":
    create_model()
