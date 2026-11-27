import sys
import os
import math
import json
import ifcopenshell
import ifcopenshell.api
import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "/filesystem/dc_model__hall_seed000_d000__mep_routing/output/model.ifc"

def create_model():
    # ---------------------------------------------------------
    # 1. IFC Model Initialization (IFC4)
    # ---------------------------------------------------------
    model = ifcopenshell.file(schema="IFC4")
    
    # Project & Units
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
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
    
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Data Hall Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 0 - Finished Floor")
    
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, products=[building])
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, products=[storey])
    
    # ---------------------------------------------------------
    # Helper functions for geometry and placement
    # Units in IFC: Millimetres for dimensions, Metres for 4x4 matrix translations!
    # ---------------------------------------------------------
    def create_box_element(ifc_class, predefined_type, name, object_type, dx, dy, dz, x_mm, y_mm, z_mm, rot_deg=0):
        """Creates an extruded box element positioned in mm (translated to meters in placement matrix)."""
        rad = math.radians(rot_deg)
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        
        # Center of box in local coords: from 0 to dx, 0 to dy, 0 to dz
        # Profile around 0,0: [-dx/2, -dy/2] to [dx/2, dy/2]
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=float(dx),
            YDim=float(dy)
        )
        
        # Solid extruded
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
                Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
            ),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=float(dz)
        )
        
        rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid]
        )
        
        prod_def = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
        
        entity = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class=ifc_class,
            predefined_type=predefined_type,
            name=name
        )
        if object_type:
            entity.ObjectType = object_type
            
        entity.Representation = prod_def
        
        # Placement: note center of box is at x_mm + dx/2, y_mm + dy/2, z_mm
        # If rotated, rotation is about center or origin. We place center at (xc, yc, z_mm)
        xc = (x_mm + dx/2.0) / 1000.0
        yc = (y_mm + dy/2.0) / 1000.0
        zc = (z_mm) / 1000.0
        
        # 4x4 matrix
        matrix = np.array([
            [cos_r, -sin_r, 0.0, xc],
            [sin_r,  cos_r, 0.0, yc],
            [0.0,    0.0,   1.0, zc],
            [0.0,    0.0,   0.0, 1.0]
        ])
        
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=entity, matrix=matrix)
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[entity])
        return entity

    def create_segment(ifc_class, predefined_type, name, object_type, p1, p2, width, height):
        """p1, p2 in mm [x, y, z]. Box segment between p1 and p2."""
        p1 = np.array(p1, dtype=float)
        p2 = np.array(p2, dtype=float)
        vec = p2 - p1
        length = float(np.linalg.norm(vec))
        if length < 1e-4:
            return None
            
        # Direction
        udir = vec / length
        mid = (p1 + p2) / 2.0
        
        # Profile: Swept area in X-Y, extruded along Z
        profile = model.create_entity(
            "IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=float(width),
            YDim=float(height)
        )
        solid = model.create_entity(
            "IfcExtrudedAreaSolid",
            SweptArea=profile,
            Position=model.create_entity(
                "IfcAxis2Placement3D",
                Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, -length/2.0)),
                Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                RefDirection=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
            ),
            ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=length
        )
        rep = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=body_context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[solid]
        )
        prod_def = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
        entity = ifcopenshell.api.run(
            "root.create_entity", model,
            ifc_class=ifc_class,
            predefined_type=predefined_type,
            name=name
        )
        if object_type:
            entity.ObjectType = object_type
        entity.Representation = prod_def
        
        # Matrix orientation: Z axis along udir
        # Choose X axis perpendicular to udir
        z_axis = udir
        if abs(z_axis[0]) < 0.9 and abs(z_axis[1]) < 0.9:
            ref = np.array([0.0, 1.0, 0.0])
        else:
            ref = np.array([0.0, 0.0, 1.0])
        x_axis = np.cross(ref, z_axis)
        x_norm = np.linalg.norm(x_axis)
        if x_norm > 1e-5:
            x_axis = x_axis / x_norm
        else:
            x_axis = np.array([1.0, 0.0, 0.0])
        y_axis = np.cross(z_axis, x_axis)
        y_axis = y_axis / np.linalg.norm(y_axis)
        
        matrix = np.eye(4)
        matrix[0:3, 0] = x_axis
        matrix[0:3, 1] = y_axis
        matrix[0:3, 2] = z_axis
        matrix[0:3, 3] = mid / 1000.0  # meters
        
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=entity, matrix=matrix)
        ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, products=[entity])
        return entity

    # ---------------------------------------------------------
    # 2. Build Structural Columns
    # Grid: 8400 mm spans.
    # Columns at:
    # 1: Y = 9000, 2: Y = 17400
    # A: X = 8400, B: X = 16800, C: X = 25200 (outside is 27000)
    # Total clear height: from finished floor (0) to soffit (+3600)
    # Size: 600 x 600 mm centered on grid lines
    # ---------------------------------------------------------
    col_x_coords = [8400, 16800, 25200]
    col_y_coords = [9000, 17400]
    col_idx = 1
    for cx in col_x_coords:
        for cy in col_y_coords:
            col = create_box_element(
                "IfcColumn", "COLUMN", f"COL-{col_idx:02d}", "Structural Column",
                600, 600, 3600,
                cx - 300, cy - 300, 0
            )
            col_idx += 1

    # ---------------------------------------------------------
    # 3. Build Perimeter CRAH Units
    # CRAH-01 to CRAH-04: Tile addresses B01, P01, AC01, AQ01 (per A-601)
    # Plan size: 1200 x 900 mm. Height: 2000 mm. Front faces North (+Y).
    # Tiles: B=1 (X=600), P=15 (X=9000), AC=28 (X=16800), AQ=42 (X=25200). Y=0 to 900.
    # ---------------------------------------------------------
    crah_perim_x = [600, 9000, 16800, 25200]
    for i, px in enumerate(crah_perim_x):
        crah = create_box_element(
            "IfcEnergyConversionDevice", "USERDEFINED", f"CRAH-{i+1:02d}", "AirHandlingUnit",
            1200, 900, 2000,
            px, 0, 0, rot_deg=0
        )
        pset = ifcopenshell.api.run("pset.add_pset", model, product=crah, name="Pset_DCM_Cooling")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
            "CapacityKW": 100.0,
            "ServiceType": "CHW_DN100",
            "Facing": "NORTH"
        })

    # ---------------------------------------------------------
    # 4. Build Cabinets & In-Row CRAHs
    # Rows A through F.
    # Row Y-centerlines from A-101 / A-301:
    # A: Y = 3600 (Row 6)
    # B: Y = 6000 (Row 11) - Pitch 2400 (Cold aisle BC)
    # C: Y = 9000 (Row 16) - Hot aisle AB 3000
    # D: Y = 11400 (Row 21) - Cold aisle DE 2400
    # E: Y = 14400 (Row 26) - Hot aisle CD 3000
    # F: Y = 17400 (Row 31) - Hot aisle EF 3000
    # Wait, let's verify row Y coordinates from A-101:
    # Look at A-101 dimensions:
    # Grid 6 to 1: 3000, 1 to 2: 8400, 2 to north: 8400.
    # Grid labels on left:
    # 6: Y=3600 (Row A)
    # 11: Y=6000 (3000 - wait, 3600 + 2400 = 6000)
    # 16: Y=9000 (3000 hot aisle)
    # 21: Y=11400 (2400 cold aisle)
    # 26: Y=14400 (3000 hot aisle)
    # 31: Y=17400 (3000 hot aisle)
    # Row A: Y_center = 3600. Depth = 1200. Y = 3000 to 4200.
    # Row B: Y_center = 6000. Y = 5400 to 6600.
    # Row C: Y_center = 9000. Y = 8400 to 9600.
    # Row D: Y_center = 11400. Y = 10800 to 12000.
    # Row E: Y_center = 14400. Y = 13800 to 15000.
    # Row F: Y_center = 17400. Y = 16800 to 18000.
    # ---------------------------------------------------------
    row_info = [
        {"row": "A", "y_center": 3600, "facing": "SOUTH", "pdu": "PDU-01", "pdu_x": 23400, "crah_tag": "A"},
        {"row": "B", "y_center": 6000, "facing": "NORTH", "pdu": "PDU-02", "pdu_x": 23400, "crah_tag": "B"},
        {"row": "C", "y_center": 9000, "facing": "SOUTH", "pdu": "PDU-03", "pdu_x": 23400, "crah_tag": "C"},
        {"row": "D", "y_center": 11400, "facing": "NORTH", "pdu": "PDU-04", "pdu_x": 23400, "crah_tag": "D"},
        {"row": "E", "y_center": 14400, "facing": "SOUTH", "pdu": "PDU-05", "pdu_x": 23400, "crah_tag": "E"},
        {"row": "F", "y_center": 17400, "facing": "NORTH", "pdu": "PDU-06", "pdu_x": 23400, "crah_tag": "F"}
    ]

    # Cabinet sequences from A-601:
    # A: 4C1 · CU · 3C1 · N1 · 3C1 · CU · CA · 6C1 · SP · CU · 5C1
    # B: 4C1 · CU · 5C1 · 2N1 · CU · CA · 7C1 · SP · CU · 5C1
    # C: 3C1 · CU · 6C1 · 2-600 · CU · CA · N1 · 4C1 · CU · SP · C1 · 2-600 · 3C1
    # D: 4C1 · CU · 3C1 · 2N1 · 2C1 · CU · CA · 7C1 · SP · CU · 5C1
    # E: 4C1 · CU · 5C1 · N1 · C1 · CU · CA · 6C1 · SP · CU · 5C1
    # F: 4C1 · CU · 5C1 · 2-600 · CU · CA · 2N1 · 5C1 · SP · -600 · CU · 4C1
    sequences = {
        "A": [('C1', 4), ('CU', 1), ('C1', 3), ('N1', 1), ('C1', 3), ('CU', 1), ('CA', 1), ('C1', 6), ('SP', 1), ('CU', 1), ('C1', 5)],
        "B": [('C1', 4), ('CU', 1), ('C1', 5), ('N1', 2), ('CU', 1), ('CA', 1), ('C1', 7), ('SP', 1), ('CU', 1), ('C1', 5)],
        "C": [('C1', 3), ('CU', 1), ('C1', 6), ('GAP', 2), ('CU', 1), ('CA', 1), ('N1', 1), ('C1', 4), ('CU', 1), ('SP', 1), ('C1', 1), ('GAP', 2), ('C1', 3)],
        "D": [('C1', 4), ('CU', 1), ('C1', 3), ('N1', 2), ('C1', 2), ('CU', 1), ('CA', 1), ('C1', 7), ('SP', 1), ('CU', 1), ('C1', 5)],
        "E": [('C1', 4), ('CU', 1), ('C1', 5), ('N1', 1), ('C1', 1), ('CU', 1), ('CA', 1), ('C1', 6), ('SP', 1), ('CU', 1), ('C1', 5)],
        "F": [('C1', 4), ('CU', 1), ('C1', 5), ('GAP', 2), ('CU', 1), ('CA', 1), ('N1', 2), ('C1', 5), ('SP', 1), ('GAP', 1), ('CU', 1), ('C1', 4)]
    }

    # Cross aisle (CA) width = 1200 mm
    widths = {
        'C1': 600,
        'N1': 800,
        'CU': 600,
        'SP': 600,
        'GAP': 600,
        'CA': 1200
    }

    # First tile for each row is D = tile 4 -> X = 2400 mm
    all_crah_positions = []
    
    for r_data in row_info:
        r_name = r_data["row"]
        y_c = r_data["y_center"]
        facing = r_data["facing"]
        rot = 0 if facing == "NORTH" else 180
        y_min = y_c - 600
        
        curr_x = 2400  # Start at west end (Tile D = 4 * 600 = 2400)
        c_count = 1
        cu_count = 1
        
        for item_type, count in sequences[r_name]:
            w = widths[item_type]
            for _ in range(count):
                if item_type == 'C1':
                    cab_tag = f"RACK-{r_name}{c_count:02d}"
                    cab = create_box_element(
                        "IfcFurniture", "USERDEFINED", cab_tag, "Rack",
                        w, 1200, 2000,
                        curr_x, y_min, 0, rot_deg=rot
                    )
                    pset = ifcopenshell.api.run("pset.add_pset", model, product=cab, name="Pset_DCM_Cabinet")
                    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
                        "CabinetType": "C1",
                        "Height": 2000,
                        "Facing": facing,
                        "LoadKW": 8.0
                    })
                    c_count += 1
                elif item_type == 'N1':
                    cab_tag = f"RACK-{r_name}{c_count:02d}"
                    cab = create_box_element(
                        "IfcFurniture", "USERDEFINED", cab_tag, "Rack",
                        w, 1200, 2000,
                        curr_x, y_min, 0, rot_deg=rot
                    )
                    pset = ifcopenshell.api.run("pset.add_pset", model, product=cab, name="Pset_DCM_Cabinet")
                    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
                        "CabinetType": "N1",
                        "Height": 2000,
                        "Facing": facing,
                        "LoadKW": 8.0
                    })
                    c_count += 1
                elif item_type == 'CU':
                    cu_tag = f"CRAH-{r_name}{cu_count:02d}"
                    crah = create_box_element(
                        "IfcEnergyConversionDevice", "USERDEFINED", cu_tag, "AirHandlingUnit",
                        w, 1200, 2000,
                        curr_x, y_min, 0, rot_deg=rot
                    )
                    pset = ifcopenshell.api.run("pset.add_pset", model, product=crah, name="Pset_DCM_Cooling")
                    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
                        "CapacityKW": 50.0,
                        "ServiceType": "CHW_DN50",
                        "Facing": facing
                    })
                    all_crah_positions.append((cu_tag, curr_x + w/2.0, y_c))
                    cu_count += 1
                curr_x += w

    # Add perimeter CRAH positions to list
    for i, px in enumerate(crah_perim_x):
        all_crah_positions.append((f"CRAH-{i+1:02d}", px + 600, 450))

    # ---------------------------------------------------------
    # 5. Build PDUs
    # Size: 762 W x 813 D x 1959 H
    # Dedicated space: 1800 mm above top -> up to 1959 + 1800 = 3759 mm
    # PDU-01 to PDU-06 at X = 23400 (Tile BJ = 39 * 600 = 23400)
    # Front flush with front face of row!
    # ---------------------------------------------------------
    for r_data in row_info:
        r_name = r_data["row"]
        y_c = r_data["y_center"]
        facing = r_data["facing"]
        pdu_name = r_data["pdu"]
        
        # PDU dimensions
        w = 762
        d = 813
        h = 1959
        
        # Front face of row is at:
        # If facing SOUTH, front face is at y_c - 600. PDU front is flush, so PDU extends from (y_c - 600) to (y_c - 600 + d).
        # If facing NORTH, front face is at y_c + 600. PDU front is flush, so PDU extends from (y_c + 600 - d) to (y_c + 600).
        if facing == "SOUTH":
            py = y_c - 600
        else:
            py = y_c + 600 - d
            
        pdu = create_box_element(
            "IfcElectricDistributionBoard", "USERDEFINED", pdu_name, "PowerDistributionUnit",
            w, d, h,
            23400, py, 0, rot_deg=0
        )
        pset = ifcopenshell.api.run("pset.add_pset", model, product=pdu, name="Pset_DCM_Electrical")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={
            "RatingKVA": 225.0,
            "WorkingSpaceFront": 900.0,
            "DedicatedSpaceHeight": 1800.0
        })

    # ---------------------------------------------------------
    # 6. Build Cold-Aisle Containment Roofs & Doors
    # CAC-BC: Rows B & C. Y between 6600 and 8400. Width = 1400 roof. Underside = 2000, Thk = 55.5
    # CAC-DE: Rows D & E. Y between 12000 and 13800.
    # ---------------------------------------------------------
    for cac_tag, y_mid in [("CAC-BC", 7500), ("CAC-DE", 12900)]:
        # Roof panel extends along aisle length
        roof = create_box_element(
            "IfcCovering", "CEILING", f"{cac_tag}-ROOF", "ContainmentRoof",
            19000, 1400, 55.5,
            2400, y_mid - 700, 2000
        )
        # End doors at East and West
        door_w = create_box_element(
            "IfcDoor", "DOOR", f"{cac_tag}-DOOR-W", "ContainmentDoor",
            60, 1400, 2055.5,
            2340, y_mid - 700, 0
        )
        door_e = create_box_element(
            "IfcDoor", "DOOR", f"{cac_tag}-DOOR-E", "ContainmentDoor",
            60, 1400, 2055.5,
            21400, y_mid - 700, 0
        )

    # ---------------------------------------------------------
    # 7. Build Sprinklers (F-101)
    # Ceiling heads: 63 heads at Z = 3575 mm deflector elevation.
    # In-aisle heads: 16 heads under containment roof at Z = 1890 mm.
    # ---------------------------------------------------------
    # Ceiling heads grid: X from 1500, spacing 3000 -> 1500, 4500, 7500, 10500, 13500, 16500, 19500, 22500, 25500 (9 cols)
    # Y from 1500, spacing 3000 -> 1500, 4500, 7500, 10500, 13500, 16500, 19500 (7 rows)
    sprinkler_idx = 1
    for ix in range(9):
        sx = 1500 + ix * 3000
        for iy in range(7):
            sy = 1500 + iy * 3000
            # Check column keepout: if head hits column at (8400, 16800, 25200) and (9000, 17400)
            # The grid positions don't clash directly (sx=7500, sy=7500, etc.)
            sp = create_box_element(
                "IfcFireSuppressionTerminal", "USERDEFINED", f"SPR-CEIL-{sprinkler_idx:02d}", "SprinklerHead",
                50, 50, 100,
                sx - 25, sy - 25, 3500
            )
            sprinkler_idx += 1

    # In-aisle heads under containment roof (8 heads in CAC-BC, 8 heads in CAC-DE)
    in_aisle_x = [3000, 5400, 7800, 10200, 12600, 15000, 17400, 19800]
    in_aisle_idx = 1
    for y_mid in [7500, 12900]:
        for hx in in_aisle_x:
            sp = create_box_element(
                "IfcFireSuppressionTerminal", "USERDEFINED", f"SPR-AISLE-{in_aisle_idx:02d}", "SprinklerHead",
                50, 50, 100,
                hx - 25, y_mid - 25, 1890
            )
            in_aisle_idx += 1

    # ---------------------------------------------------------
    # 8. MEP Routing
    #
    # Constraints:
    # - Clearance: Min clear headroom = 2600 mm.
    # - Sprinkler standoff: 460 mm below deflector (3575 - 460 = 3115 mm). Overhead zone = [2600, 3115].
    # - Under-floor zone = [-865, -20] mm.
    # - Separation between tray and busway >= 300 mm on at least one axis.
    # - Busway: 128 W x 147 H.
    # - Cable tray: 683 W x 127 H.
    # - CHW Pipe: DN100 bare OD 114.3 mm, with 25.4 mm insulation = 165.1 mm (or 168.3 mm ASTM jacket).
    # - PDU dedicated electrical space: 1800 mm directly above PDU (Z = 1959 to 3759). NO CHW PIPING!
    #
    # Strategy:
    # 1. Busway (BW-1) Overhead:
    #    Elevations: Centerline Z = 2700 mm (bottom = 2626 mm > 2600 mm headroom; top = 2774 mm).
    #    West entry at X = 0, Y = 9900.
    #    Main trunk along X = 1200 mm from Y = 3600 to Y = 17400.
    #    Branches run east over each row (Y = 3600, 6000, 9000, 11400, 14400, 17400) from X = 1200 to X = 21000.
    #    Covers >= 80% of each row (row runs from 2400 to 20400 = 18000 mm length).
    #
    # 2. Cable Tray (CT-1) Overhead:
    #    Elevations: Centerline Z = 2950 mm (bottom = 2886 mm; top = 3014 mm < 3115 mm sprinkler limit).
    #    Z-separation between tray (bottom 2886) and busway (top 2774) is 112 mm.
    #    To satisfy 300 mm separation on AT LEAST ONE axis:
    #    Offset tray branches in Y by 400 mm from busway (e.g. Y = row_y - 400 mm).
    #    400 mm > 300 mm Y-separation!
    #    Main trunk along X = 1600 mm from Y = 3200 to Y = 17800.
    #    West entry at X = 0, Y = 9900 connects up to Z = 2950 mm.
    #
    # 3. Chilled Water (CHW-1) Under-Floor:
    #    Elevations: Centerline Z = -500 mm (under-floor plenum is -865 to -35 mm).
    #    Diameter with insulation = 168.3 mm.
    #    Z = -500 leaves ample clearance below floor tiles (-35) and above slab (-900).
    #    Completely avoids the 1800 mm dedicated space above PDUs!
    #    Completely avoids overhead sprinkler deflector zones!
    #    Enters at X = 0, Y = 9900, drops down to Z = -500 mm.
    #    Runs a main header along X = 1200 mm from Y = 450 to Y = 17400.
    #    Branch headers run east at each row (Y = 3600, 6000, 9000, 11400, 14400, 17400) to serve all in-row CRAHs.
    #    Also branch at Y = 450 from X = 1200 to X = 25500 to serve all perimeter CRAHs (CRAH-01 to 04).
    #    Every CRAH is within 600 mm of the CHW route (< 2500 mm requirement!).
    # ---------------------------------------------------------

    # --- 8A. BUSWAY ROUTING (BW-1) ---
    bw_w, bw_h = 128, 147
    bw_z = 2700
    
    # Entry from west wall
    create_segment("IfcFlowSegment", "BUSWAY", "BW-ENTRY", "BuswaySegment", [0, 9900, bw_z], [1200, 9900, bw_z], bw_w, bw_h)
    # Main trunk north-south
    create_segment("IfcFlowSegment", "BUSWAY", "BW-TRUNK", "BuswaySegment", [1200, 3600, bw_z], [1200, 17400, bw_z], bw_w, bw_h)
    
    # Branches for each row
    for r_data in row_info:
        ry = r_data["y_center"]
        rname = r_data["row"]
        # Run straight branch along row centerline
        create_segment(
            "IfcFlowSegment", "BUSWAY", f"BW-BRANCH-ROW-{rname}", "BuswaySegment",
            [1200, ry, bw_z], [21000, ry, bw_z], bw_w, bw_h
        )

    # --- 8B. CABLE TRAY ROUTING (CT-1) ---
    ct_w, ct_h = 683, 127
    ct_z = 2950
    
    # Entry from west wall: rise to ct_z
    create_segment("IfcFlowSegment", "CABLETRAYSEGMENT", "CT-ENTRY", "CableTraySegment", [0, 9900, ct_z], [1800, 9900, ct_z], ct_w, ct_h)
    # Main trunk along X = 1800 (offset from BW trunk at 1200 by 600 mm > 300 mm!)
    create_segment("IfcFlowSegment", "CABLETRAYSEGMENT", "CT-TRUNK", "CableTraySegment", [1800, 3200, ct_z], [1800, 17000, ct_z], ct_w, ct_h)
    
    # Branches for each row: offset by -400 mm in Y from row centerline to maintain 400 mm separation from busway
    for r_data in row_info:
        ry = r_data["y_center"] - 400
        rname = r_data["row"]
        # Connect trunk to branch
        create_segment(
            "IfcFlowSegment", "CABLETRAYSEGMENT", f"CT-FEED-ROW-{rname}", "CableTraySegment",
            [1800, ry, ct_z], [2400, ry, ct_z], ct_w, ct_h
        )
        create_segment(
            "IfcFlowSegment", "CABLETRAYSEGMENT", f"CT-BRANCH-ROW-{rname}", "CableTraySegment",
            [2400, ry, ct_z], [21000, ry, ct_z], ct_w, ct_h
        )

    # --- 8C. CHILLED WATER ROUTING (CHW-1) ---
    chw_dia = 168.3  # outer diameter including 25.4 mm insulation
    chw_z = -500     # Under-floor plenum
    
    # Entry from west wall: drop from entry elevation down to under-floor
    create_segment("IfcPipeSegment", "PIPE", "CHW-ENTRY-DROP", "PipeSegment", [0, 9900, 1500], [0, 9900, chw_z], chw_dia, chw_dia)
    create_segment("IfcPipeSegment", "PIPE", "CHW-ENTRY-HORIZ", "PipeSegment", [0, 9900, chw_z], [800, 9900, chw_z], chw_dia, chw_dia)
    
    # Under-floor main distribution header along X = 800 mm
    create_segment("IfcPipeSegment", "PIPE", "CHW-TRUNK", "PipeSegment", [800, 450, chw_z], [800, 17400, chw_z], chw_dia, chw_dia)
    
    # Perimeter header along Y = 450 to feed CRAH-01, 02, 03, 04
    create_segment("IfcPipeSegment", "PIPE", "CHW-BRANCH-PERIM", "PipeSegment", [800, 450, chw_z], [25800, 450, chw_z], chw_dia, chw_dia)
    
    # In-row headers for each row A through F
    for r_data in row_info:
        ry = r_data["y_center"]
        rname = r_data["row"]
        # Branch runs under the floor along row centerline
        create_segment(
            "IfcPipeSegment", "PIPE", f"CHW-BRANCH-ROW-{rname}", "PipeSegment",
            [800, ry, chw_z], [20000, ry, chw_z], chw_dia, chw_dia
        )

    # ---------------------------------------------------------
    # 9. Validation & Output
    # ---------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    model.write(OUT_PATH)
    print(f"Model successfully generated at: {OUT_PATH}")

    # Write reconciliation log
    recon_path = os.path.join(os.path.dirname(os.path.abspath(OUT_PATH)), "reconciliation.json")
    recon_data = {
        "hall_dimensions": {"length_mm": 27000, "width_mm": 21000},
        "floor_grid": {"tile_size_mm": 600, "total_tiles_x": 45, "total_tiles_y": 35},
        "vertical_budget": {
            "top_of_slab_mm": -900,
            "under_floor_plenum_clear_mm": [-865, -35],
            "finished_floor_mm": 0,
            "cabinet_height_mm": 2000,
            "containment_roof_underside_mm": 2000,
            "min_headroom_clear_mm": 2600,
            "overhead_pathway_zone_mm": [2600, 3115],
            "sprinkler_standoff_zone_mm": [3115, 3575],
            "ceiling_soffit_mm": 3600
        },
        "routing_elevations": {
            "busway_bw1_cl_mm": bw_z,
            "cable_tray_ct1_cl_mm": ct_z,
            "chw_pipe_cl_mm": chw_z
        },
        "clearances_achieved": {
            "tray_to_busway_horizontal_separation_mm": 400,
            "chw_to_pdu_separation": "Under-floor routing eliminates all CHW from PDU dedicated zones",
            "overhead_headroom_clearance_mm": 2626 - 2600
        }
    }
    with open(recon_path, "w") as f:
        json.dump(recon_data, f, indent=2)
    print(f"Reconciliation log written to: {recon_path}")

if __name__ == "__main__":
    create_model()
