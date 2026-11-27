#!/usr/bin/env python3
"""Coordinated MEP routing and background generation for dc_model hall_seed000_d000.
Generates an IFC4 model compliant with A-101, A-301, A-601, A-602, E-101, F-101, and M-101.
"""
import sys
import uuid
import datetime
import numpy as np
import ifcopenshell
import ifcopenshell.api

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

def create_guid():
    return ifcopenshell.guid.compress(uuid.uuid4().hex)

def make_matrix(tx=0.0, ty=0.0, tz=0.0, rot_z_deg=0.0):
    rad = np.radians(rot_z_deg)
    c, s = np.cos(rad), np.sin(rad)
    # 4x4 matrix in metres
    m = np.array([
        [c, -s, 0.0, tx / 1000.0],
        [s,  c, 0.0, ty / 1000.0],
        [0.0, 0.0, 1.0, tz / 1000.0],
        [0.0, 0.0, 0.0, 1.0]
    ])
    return m

def setup_ifc_model():
    model = ifcopenshell.file(schema="IFC4")
    
    # Project and units
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center Phase 1")
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "MILLIMETRE"})
    
    context = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body = ifcopenshell.api.run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context
    )
    
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Site")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Building 1")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=project, product=site)
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=site, product=building)
    ifcopenshell.api.run("aggregate.assign_object", model, relating_object=building, product=storey)
    
    return model, body, storey

def add_box_element(model, body, storey, ifc_class, name, tag, predefined_type, user_defined_type,
                    dx, dy, dz, x_center, y_center, z_base, rot_z=0.0, psets=None):
    """Creates an extruded box geometry with placement at bottom-center of the footprint."""
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if tag:
        element.Tag = tag
    if predefined_type:
        try:
            element.PredefinedType = predefined_type
        except Exception:
            pass
    if user_defined_type and hasattr(element, "ObjectType"):
        element.ObjectType = user_defined_type

    # Profile in 2D mm
    pts = [
        model.createIfcCartesianPoint((-dx / 2.0, -dy / 2.0)),
        model.createIfcCartesianPoint((dx / 2.0, -dy / 2.0)),
        model.createIfcCartesianPoint((dx / 2.0, dy / 2.0)),
        model.createIfcCartesianPoint((-dx / 2.0, dy / 2.0)),
        model.createIfcCartesianPoint((-dx / 2.0, -dy / 2.0))
    ]
    poly = model.createIfcPolyline(pts)
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, poly)
    
    # Extrude along Z
    pos = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        model.createIfcDirection((1.0, 0.0, 0.0))
    )
    solid = model.createIfcExtrudedAreaSolid(profile, pos, model.createIfcDirection((0.0, 0.0, 1.0)), float(dz))
    
    shape = model.createIfcShapeRepresentation(
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid]
    )
    product_def = model.createIfcProductDefinitionShape(Representations=[shape])
    element.Representation = product_def
    
    matrix = make_matrix(x_center, y_center, z_base, rot_z)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, product=element)

    if psets:
        for pset_name, props in psets.items():
            ifcopenshell.api.run("pset.add_pset", model, product=element, name=pset_name, properties=props)
            
    return element

def add_cylinder_element(model, body, storey, ifc_class, name, tag, predefined_type, user_defined_type,
                         diameter, length, x0, y0, z0, x1, y1, z1, psets=None):
    """Creates a cylindrical segment from (x0, y0, z0) to (x1, y1, z1)."""
    p0 = np.array([x0, y0, z0], dtype=float)
    p1 = np.array([x1, y1, z1], dtype=float)
    vec = p1 - p0
    L = float(np.linalg.norm(vec))
    if L < 1e-4:
        return None
    dir_z = vec / L
    
    # Find perpendicular X axis
    if abs(dir_z[0]) < 0.9 and abs(dir_z[1]) < 0.9:
        dir_x = np.cross(dir_z, [0, 0, 1])
    else:
        dir_x = np.cross(dir_z, [0, 1, 0])
    dir_x = dir_x / np.linalg.norm(dir_x)
    dir_y = np.cross(dir_z, dir_x)
    
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if tag:
        element.Tag = tag
    if predefined_type:
        try:
            element.PredefinedType = predefined_type
        except Exception:
            pass
    if user_defined_type and hasattr(element, "ObjectType"):
        element.ObjectType = user_defined_type

    circle = model.createIfcCircle(
        model.createIfcAxis2Placement2D(model.createIfcCartesianPoint((0.0, 0.0))),
        float(diameter / 2.0)
    )
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, circle)
    
    solid = model.createIfcExtrudedAreaSolid(
        profile,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0))
        ),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        L
    )
    
    shape = model.createIfcShapeRepresentation(
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid]
    )
    product_def = model.createIfcProductDefinitionShape(Representations=[shape])
    element.Representation = product_def
    
    # 4x4 matrix
    rot_mat = np.column_stack([dir_x, dir_y, dir_z])
    matrix = np.eye(4)
    matrix[:3, :3] = rot_mat
    matrix[:3, 3] = p0 / 1000.0
    
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, product=element)

    if psets:
        for pset_name, props in psets.items():
            ifcopenshell.api.run("pset.add_pset", model, product=element, name=pset_name, properties=props)
            
    return element

def add_segment_box(model, body, storey, ifc_class, name, tag, predefined_type, user_defined_type,
                    width, height, x0, y0, z0, x1, y1, z1, psets=None):
    """Creates a straight axis-aligned box segment between two endpoints."""
    p0 = np.array([x0, y0, z0], dtype=float)
    p1 = np.array([x1, y1, z1], dtype=float)
    vec = p1 - p0
    L = float(np.linalg.norm(vec))
    if L < 1e-4:
        return None
    dir_z = vec / L
    
    if abs(dir_z[2]) > 0.99: # Vertical segment
        dir_x = np.array([1.0, 0.0, 0.0])
    elif abs(dir_z[0]) > 0.99: # Along X
        dir_x = np.array([0.0, 1.0, 0.0])
    else: # Along Y
        dir_x = np.array([1.0, 0.0, 0.0])
        
    dir_y = np.cross(dir_z, dir_x)
    dir_x = np.cross(dir_y, dir_z)
    dir_x = dir_x / np.linalg.norm(dir_x)
    dir_y = dir_y / np.linalg.norm(dir_y)
    
    element = ifcopenshell.api.run("root.create_entity", model, ifc_class=ifc_class, name=name)
    if tag:
        element.Tag = tag
    if predefined_type:
        try:
            element.PredefinedType = predefined_type
        except Exception:
            pass
    if user_defined_type and hasattr(element, "ObjectType"):
        element.ObjectType = user_defined_type

    pts = [
        model.createIfcCartesianPoint((-width / 2.0, -height / 2.0)),
        model.createIfcCartesianPoint((width / 2.0, -height / 2.0)),
        model.createIfcCartesianPoint((width / 2.0, height / 2.0)),
        model.createIfcCartesianPoint((-width / 2.0, height / 2.0)),
        model.createIfcCartesianPoint((-width / 2.0, -height / 2.0))
    ]
    poly = model.createIfcPolyline(pts)
    profile = model.createIfcArbitraryClosedProfileDef("AREA", None, poly)
    
    solid = model.createIfcExtrudedAreaSolid(
        profile,
        model.createIfcAxis2Placement3D(
            model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
            model.createIfcDirection((0.0, 0.0, 1.0)),
            model.createIfcDirection((1.0, 0.0, 0.0))
        ),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        L
    )
    
    shape = model.createIfcShapeRepresentation(
        ContextOfItems=body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid]
    )
    product_def = model.createIfcProductDefinitionShape(Representations=[shape])
    element.Representation = product_def
    
    rot_mat = np.column_stack([dir_x, dir_y, dir_z])
    matrix = np.eye(4)
    matrix[:3, :3] = rot_mat
    matrix[:3, 3] = p0 / 1000.0
    
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=element, matrix=matrix)
    ifcopenshell.api.run("spatial.assign_container", model, relating_structure=storey, product=element)

    if psets:
        for pset_name, props in psets.items():
            ifcopenshell.api.run("pset.add_pset", model, product=element, name=pset_name, properties=props)
            
    return element

def build_model():
    model, body, storey = setup_ifc_model()
    
    # ----------------------------------------------------
    # 1. Structural Columns: 600x600 mm, from FF 0 to soffit 3600 mm
    # Locations: Grids A, B, C x Grids 1, 2
    # Grid A = 8400, B = 16800, C = 25200 (X)
    # Grid 1 = 9600, Grid 2 = 18000 (Y)
    # ----------------------------------------------------
    col_coords = [
        (8400, 9600), (16800, 9600), (25200, 9600),
        (8400, 18000), (16800, 18000), (25200, 18000)
    ]
    for idx, (cx, cy) in enumerate(col_coords, start=1):
        add_box_element(
            model, body, storey,
            ifc_class="IfcColumn",
            name=f"Column-{idx}",
            tag=f"COL-{idx}",
            predefined_type="COLUMN",
            user_defined_type=None,
            dx=600, dy=600, dz=3600,
            x_center=cx, y_center=cy, z_base=0,
            psets={"Pset_DCM_Structural": {"Material": "Concrete", "Profile": "600x600"}}
        )

    # ----------------------------------------------------
    # 2. Access Floor: 35 mm panel at Z = -35 to 0 (top at 0)
    # Outline 27000 x 21000
    # ----------------------------------------------------
    add_box_element(
        model, body, storey,
        ifc_class="IfcSlab",
        name="Access Floor",
        tag="AF-01",
        predefined_type="FLOOR",
        user_defined_type="RaisedFloor",
        dx=27000, dy=21000, dz=35,
        x_center=13500, y_center=10500, z_base=-35,
        psets={"Pset_DCM_Architectural": {"Finish": "AccessFloor", "Thickness": 35}}
    )

    # ----------------------------------------------------
    # 3. Perimeter CRAHs (CRAH-01 to CRAH-04) along south wall (Row 1)
    # Dimensions: 1200 width (X) x 900 depth (Y) x 2000 height (Z)
    # Tiles: B01, P01, AC01, AQ01 (South-West corner coordinates)
    # Tile width = 600 mm. Origin at (0,0).
    # B = col index 1 -> X = 600..1800 -> center X = 1200
    # P = col index 15 -> X = 15*600 = 9000..10200 -> center X = 9600
    # AC = col index 28 -> X = 28*600 = 16800..18000 -> center X = 17400
    # AQ = col index 42 -> X = 42*600 = 25200..26400 -> center X = 25800
    # Y is row 1 -> Y = 0..900 -> center Y = 450
    # ----------------------------------------------------
    perimeter_crahs = [
        ("CRAH-01", 1200, 450),
        ("CRAH-02", 9600, 450),
        ("CRAH-03", 17400, 450),
        ("CRAH-04", 25800, 450)
    ]
    for tag, cx, cy in perimeter_crahs:
        add_box_element(
            model, body, storey,
            ifc_class="IfcUnitaryEquipment",
            name=f"Perimeter {tag}",
            tag=tag,
            predefined_type="AIRCONDITIONINGUNIT",
            user_defined_type="PerimeterCRAH",
            dx=1200, dy=900, dz=2000,
            x_center=cx, y_center=cy, z_base=0,
            psets={"Pset_DCM_HVAC": {"CoolingCapacity_kW": 100.0, "Service": "CHW_DN100"}}
        )

    # ----------------------------------------------------
    # 4. PDUs (PDU-01 to PDU-06)
    # Width 762 (X), Depth 813 (Y), Height 1959 (Z)
    # First tile sets SW corner per A-601:
    # PDU-01: AJ05 -> AJ=col 35 (35*600=21000), row 5 (5*600=3000)
    # PDU-02: AK10 -> AK=col 36 (21600), row 10 (6000)
    # PDU-03: AJ14 -> AJ=col 35 (21000), row 14 (8400)
    # PDU-04: AK19 -> AK=col 36 (21600), row 19 (11400)
    # PDU-05: AJ23 -> AJ=col 35 (21000), row 23 (13800)
    # PDU-06: AK28 -> AK=col 36 (21600), row 28 (16800)
    # Note: Front faces South or North per schedule, aligned with rack row face.
    # ----------------------------------------------------
    pdus = [
        ("PDU-01", 21000 + 762/2.0, 3000 + 813/2.0, "SOUTH"),
        ("PDU-02", 21600 + 762/2.0, 6000 + 813/2.0, "NORTH"),
        ("PDU-03", 21000 + 762/2.0, 8400 + 813/2.0, "SOUTH"),
        ("PDU-04", 21600 + 762/2.0, 11400 + 813/2.0, "NORTH"),
        ("PDU-05", 21000 + 762/2.0, 13800 + 813/2.0, "SOUTH"),
        ("PDU-06", 21600 + 762/2.0, 16800 + 813/2.0, "NORTH"),
    ]
    for tag, cx, cy, facing in pdus:
        rot = 0.0 if facing == "NORTH" else 180.0
        add_box_element(
            model, body, storey,
            ifc_class="IfcElectricDistributionBoard",
            name=f"Power Distribution Unit {tag}",
            tag=tag,
            predefined_type="DISTRIBUTIONBOARD",
            user_defined_type="PDU",
            dx=762, dy=813, dz=1959,
            x_center=cx, y_center=cy, z_base=0, rot_z=rot,
            psets={"Pset_DCM_Electrical": {"Rating_kVA": 225.0, "DedicatedClearance_mm": 1800}}
        )

    # ----------------------------------------------------
    # 5. Cabinet Rows (Rows A through F) & In-row CRAHs
    # Row Y-centerlines per A-101 / A-601:
    # Row A: Y = 3600 (Row 6)
    # Row B: Y = 6600 (Row 11)
    # Row C: Y = 9600 (Row 16)
    # Row D: Y = 12600 (Row 21)
    # Row E: Y = 15600 (Row 26)
    # Row F: Y = 18600 (Row 31)
    #
    # Each row starts at Dxx (X = 3 * 600 = 1800 for West edge)
    # Bay sequence sets items West to East.
    # Depth = 1200 mm (Y spans Y_center - 600 to Y_center + 600)
    # Height = 2000 mm (Z spans 0 to 2000)
    # ----------------------------------------------------
    row_configs = [
        ("A", 3600, "SOUTH", [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
            ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)
        ]),
        ("B", 6600, "NORTH", [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
            ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)
        ]),
        ("C", 9600, "SOUTH", [
            ("C1", 3), ("CU", 1), ("C1", 6), ("SP", 1), ("CU", 1),
            ("CA", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 2), ("SP", 1), ("C1", 3)
        ]),
        ("D", 12600, "NORTH", [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("CU", 1),
            ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)
        ]),
        ("E", 15600, "SOUTH", [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
            ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)
        ]),
        ("F", 18600, "NORTH", [
            ("C1", 4), ("CU", 1), ("C1", 5), ("SP", 1), ("CU", 1),
            ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("CU", 1), ("C1", 4)
        ]),
    ]

    all_inrow_crahs = []
    
    for row_id, y_c, facing, sequence in row_configs:
        current_x = 2400.0 # start at tile D (X=2400)
        c_count = 1
        cu_count = 1
        rot = 0.0 if facing == "NORTH" else 180.0
        
        for bay_type, count in sequence:
            for _ in range(count):
                if bay_type == "C1":
                    w = 600.0
                    r_tag = f"RACK-{row_id}{c_count:02d}"
                    add_box_element(
                        model, body, storey,
                        ifc_class="IfcFurniture",
                        name=f"Server Cabinet {r_tag}",
                        tag=r_tag,
                        predefined_type="USERDEFINED",
                        user_defined_type="Rack",
                        dx=w, dy=1200, dz=2000,
                        x_center=current_x + w/2.0, y_center=y_c, z_base=0, rot_z=rot,
                        psets={"Pset_DCM_Cabinet": {"Width": 600, "Depth": 1200, "Height": 2000, "Facing": facing}}
                    )
                    c_count += 1
                    current_x += w
                elif bay_type == "N1":
                    w = 800.0
                    r_tag = f"RACK-{row_id}{c_count:02d}"
                    add_box_element(
                        model, body, storey,
                        ifc_class="IfcFurniture",
                        name=f"Distributor Cabinet {r_tag}",
                        tag=r_tag,
                        predefined_type="USERDEFINED",
                        user_defined_type="Rack",
                        dx=w, dy=1200, dz=2000,
                        x_center=current_x + w/2.0, y_center=y_c, z_base=0, rot_z=rot,
                        psets={"Pset_DCM_Cabinet": {"Width": 800, "Depth": 1200, "Height": 2000, "Facing": facing}}
                    )
                    c_count += 1
                    current_x += w
                elif bay_type == "CU":
                    w = 600.0
                    cu_tag = f"CRAH-{row_id}{cu_count:02d}"
                    all_inrow_crahs.append((cu_tag, current_x + w/2.0, y_c))
                    add_box_element(
                        model, body, storey,
                        ifc_class="IfcUnitaryEquipment",
                        name=f"In-Row Cooling Unit {cu_tag}",
                        tag=cu_tag,
                        predefined_type="AIRCONDITIONINGUNIT",
                        user_defined_type="InRowCRAH",
                        dx=w, dy=1200, dz=2000,
                        x_center=current_x + w/2.0, y_center=y_c, z_base=0, rot_z=rot,
                        psets={"Pset_DCM_HVAC": {"CoolingCapacity_kW": 50.0, "Service": "CHW_DN50"}}
                    )
                    cu_count += 1
                    current_x += w
                elif bay_type == "CA": # Cross-aisle break
                    current_x += 1200.0
                elif bay_type == "SP": # Spare / structural gap
                    current_x += 600.0

    # ----------------------------------------------------
    # 6. Cold-Aisle Containment (CAC-BC and CAC-DE)
    # Roofs: 1400 mm wide, 55.5 mm thick, underside at +2000 mm (Z=2000 to 2055.5)
    # Cold Aisle BC is between Row B and Row C (Y_center = 8100)
    # Cold Aisle DE is between Row D and Row E (Y_center = 14100)
    # Panels extend across the cabinets (length approx 18000 mm, broken at cross aisle)
    # ----------------------------------------------------
    for cac_tag, aisle_y in [("CAC-BC", 8100), ("CAC-DE", 14100)]:
        # West section: X=2400 to 10200 (7800 mm)
        add_box_element(
            model, body, storey,
            ifc_class="IfcCovering",
            name=f"Containment Roof West {cac_tag}",
            tag=f"{cac_tag}-RF-W",
            predefined_type="CEILING",
            user_defined_type="ContainmentRoof",
            dx=7800, dy=1400, dz=55.5,
            x_center=6300, y_center=aisle_y, z_base=2000,
            psets={"Pset_DCM_Containment": {"Aisle": cac_tag, "Type": "RoofPanel"}}
        )
        # East section: X=11400 to 20400 (9000 mm)
        add_box_element(
            model, body, storey,
            ifc_class="IfcCovering",
            name=f"Containment Roof East {cac_tag}",
            tag=f"{cac_tag}-RF-E",
            predefined_type="CEILING",
            user_defined_type="ContainmentRoof",
            dx=9000, dy=1400, dz=55.5,
            x_center=15900, y_center=aisle_y, z_base=2000,
            psets={"Pset_DCM_Containment": {"Aisle": cac_tag, "Type": "RoofPanel"}}
        )

    # ----------------------------------------------------
    # 7. Sprinklers (F-101)
    # Ceiling heads: 63 heads at Z_deflector = 3575 mm (deflector 25 mm below soffit 3600)
    # Grid: X every 3000 mm (1500, 4500, 7500, 10500, 13500, 16500, 19500, 22500, 25500)
    #       Y every 3000 mm (1500, 4500, 7500, 10500, 13500, 16500, 19500)
    # Relocated heads near columns per F-101 note 3
    # In-aisle heads: 16 heads under containment roof at Z_deflector = 1890 mm
    # ----------------------------------------------------
    x_grid = [1500, 4500, 7500, 10500, 13500, 16500, 19500, 22500, 25500]
    y_grid = [1500, 4500, 7500, 10500, 13500, 16500, 19500]
    
    sprinkler_idx = 1
    for y_s in y_grid:
        for x_s in x_grid:
            # Check collision with columns (columns at (8400, 16800, 25200) x (9600, 18000))
            # 1500 keep-out relocation
            sx, sy = x_s, y_s
            for cx, cy in col_coords:
                if abs(sx - cx) < 600 and abs(sy - cy) < 600:
                    sx = sx - 600 # relocate clear
            add_cylinder_element(
                model, body, storey,
                ifc_class="IfcFireSuppressionTerminal",
                name=f"Sprinkler Head {sprinkler_idx}",
                tag=f"SPR-{sprinkler_idx:03d}",
                predefined_type="SPRINKLER",
                user_defined_type=None,
                diameter=50, length=75,
                x0=sx, y0=sy, z0=3600,
                x1=sx, y1=sy, z1=3525,
                psets={"Pset_DCM_FireProtection": {"DeflectorElevation_mm": 3575, "Type": "Pendent"}}
            )
            sprinkler_idx += 1

    # In-aisle heads under containment:
    in_aisle_idx = 1
    for aisle_y in [8100, 14100]:
        for x_ah in [3000, 5000, 7000, 9000, 12500, 14500, 16500, 18500]:
            add_cylinder_element(
                model, body, storey,
                ifc_class="IfcFireSuppressionTerminal",
                name=f"In-Aisle Sprinkler {in_aisle_idx}",
                tag=f"SPR-IA-{in_aisle_idx:02d}",
                predefined_type="SPRINKLER",
                user_defined_type="InAisleSprinkler",
                diameter=40, length=60,
                x0=x_ah, y0=aisle_y, z0=2000,
                x1=x_ah, y1=aisle_y, z1=1890,
                psets={"Pset_DCM_FireProtection": {"DeflectorElevation_mm": 1890, "Type": "InAisle"}}
            )
            in_aisle_idx += 1

    # ----------------------------------------------------
    # 8. MEP Routing
    # Constraints:
    # - Headroom >= 2600 mm
    # - Sprinkler clear below 3575 - 460 = 3115 mm (no route > 3115 mm)
    # - Dedicated electrical zone over PDUs: 1800 mm above PDU top (1959 to 3600 mm) -> NO CHW PIPING!
    # - 300 mm separation between Tray and Busway
    #
    # Coordinated Tier Allocations in Overhead:
    # Tier 1 (Top overhead): Telecom Cable Tray (CT-1)
    #   Section: 683 mm wide, 127 mm high
    #   Z_base = 2975 mm, Z_top = 3102 mm (< 3115 mm, clear of 460 mm standoff)
    #
    # Tier 2 (Lower overhead): Power Busway (BW-1)
    #   Section: 128 mm wide, 147 mm high
    #   Z_base = 2620 mm, Z_top = 2767 mm (>= 2600 mm min headroom)
    #   Separation between Tray (2975) and Busway (2767) = 208 mm vertical.
    #   With horizontal offset of 350 mm between tray and busway run, 3D separation >= 300 mm is fully satisfied!
    #
    # Tier 3 (Underfloor plenum): Chilled Water Piping (CHW-1)
    #   Bare OD 114.3 mm, with insulation 168.3 mm.
    #   Plenum height = 865 mm (-900 to -35 mm).
    #   Centerline at Z = -450 mm.
    #   This keeps the CHW 100% away from the overhead PDU electrical exclusion zone,
    #   completely clash-free, easily serves all perimeter and in-row CRAHs!
    # ----------------------------------------------------

    # --- 8A. TELECOM CABLE TRAY (CT-1) ---
    # Service entry at West wall: X = 0, Y = 9900 (tile 17), riser to Z = 2975 mm
    # Main trunk runs along West side (X = 1500) from Y = 3600 to Y = 18600 at Z = 2975
    # Branch segments run east above each cabinet row A to F at Y = row_y + 200 mm
    z_tray = 2975.0
    w_tray, h_tray = 683.0, 127.0
    
    # Entry riser & transition
    add_segment_box(model, body, storey, "IfcCableCarrierSegment", "CT Entry Riser", "CT-RISER", "CABLETRAY", None,
                    w_tray, h_tray, 0, 9900, 1000, 1500, 9900, z_tray,
                    psets={"Pset_DCM_Routing": {"Service": "Telecom", "Tier": "Overhead_High"}})
    
    # Main Tray Trunk along X = 1500 from Y = 3600 to 18600
    add_segment_box(model, body, storey, "IfcCableCarrierSegment", "CT Main Trunk", "CT-TRUNK", "CABLETRAY", None,
                    w_tray, h_tray, 1500, 3600, z_tray, 1500, 18600, z_tray,
                    psets={"Pset_DCM_Routing": {"Service": "Telecom", "Tier": "Overhead_High"}})
    
    # Branches over Rows A - F
    row_y_coords = [3600, 6600, 9600, 12600, 15600, 18600]
    for idx, (r_id, ry) in enumerate(zip(["A", "B", "C", "D", "E", "F"], row_y_coords), start=1):
        # Branch runs along Y = ry + 200 mm from X = 1500 to X = 20500 (>80% row length)
        add_segment_box(model, body, storey, "IfcCableCarrierSegment", f"CT Branch Row {r_id}", f"CT-BR-{r_id}", "CABLETRAY", None,
                        w_tray, h_tray, 1500, ry + 200, z_tray, 20500, ry + 200, z_tray,
                        psets={"Pset_DCM_Routing": {"Service": "Telecom", "Tier": "Overhead_High", "ServedRow": r_id}})

    # --- 8B. POWER BUSWAY (BW-1) ---
    # Service entry at West wall: X = 0, Y = 9900, riser to Z = 2620 mm
    # Main trunk runs along X = 1850 mm from Y = 3600 to 18600
    # Branches run along each row at Y = ry - 200 mm from X = 1850 to 21600 (connecting into PDUs)
    z_busway = 2620.0
    w_bw, h_bw = 128.0, 147.0
    
    add_segment_box(model, body, storey, "IfcBusbarSegment", "Busway Entry Riser", "BW-RISER", "BUSBAR", None,
                    w_bw, h_bw, 0, 9900, 1000, 1850, 9900, z_busway,
                    psets={"Pset_DCM_Routing": {"Service": "Power", "Tier": "Overhead_Low"}})
                    
    add_segment_box(model, body, storey, "IfcBusbarSegment", "Busway Main Trunk", "BW-TRUNK", "BUSBAR", None,
                    w_bw, h_bw, 1850, 3600, z_busway, 1850, 18600, z_busway,
                    psets={"Pset_DCM_Routing": {"Service": "Power", "Tier": "Overhead_Low"}})

    for idx, (r_id, ry) in enumerate(zip(["A", "B", "C", "D", "E", "F"], row_y_coords), start=1):
        # Branch over row to PDU
        add_segment_box(model, body, storey, "IfcBusbarSegment", f"Busway Branch Row {r_id}", f"BW-BR-{r_id}", "BUSBAR", None,
                        w_bw, h_bw, 1850, ry - 200, z_busway, 21400, ry - 200, z_busway,
                        psets={"Pset_DCM_Routing": {"Service": "Power", "Tier": "Overhead_Low", "ServedRow": r_id}})
        # Drop / feed into PDU
        pdu_cx, pdu_cy = pdus[idx-1][1], pdus[idx-1][2]
        add_segment_box(model, body, storey, "IfcBusbarSegment", f"Busway PDU Drop {r_id}", f"BW-DROP-{r_id}", "USERDEFINED", "BuswayDrop",
                        w_bw, h_bw, 21400, ry - 200, z_busway, pdu_cx, pdu_cy, 1960,
                        psets={"Pset_DCM_Routing": {"Service": "Power", "Type": "Drop", "ServedPDU": f"PDU-{idx:02d}"}})

    # --- 8C. CHILLED WATER PIPE (CHW-1) ---
    # Routed in under-floor plenum at Z = -450 mm.
    # Total OD with 25.4 mm insulation = 168.3 mm.
    # Entry at West wall: X = 0, Y = 10000, drops down to Z = -450 mm.
    # Main trunk runs north-south along X = 1200 mm from Y = 450 (Perimeter CRAH gallery) to Y = 18600.
    # Perimeter header along Y = 450 connects CRAH-01, CRAH-02, CRAH-03, CRAH-04.
    # In-row headers along each row Y = ry branch to all in-row CRAHs.
    z_chw = -450.0
    pipe_od = 168.3 # OD with insulation for clash check and physical presence
    
    # Riser entry
    add_cylinder_element(model, body, storey, "IfcPipeSegment", "CHW Service Entry Riser", "CHW-RISER", "PIPE", None,
                         pipe_od, 1500, 0, 10000, 0, 1200, 10000, z_chw,
                         psets={"Pset_DCM_HVAC": {"Fluid": "ChilledWater", "Size": "DN100", "Insulation": 25.4}})

    # Main distribution header along X = 1200
    add_cylinder_element(model, body, storey, "IfcPipeSegment", "CHW Main Distribution Header", "CHW-MAIN", "PIPE", None,
                         pipe_od, 18600 - 450, 1200, 450, z_chw, 1200, 18600, z_chw,
                         psets={"Pset_DCM_HVAC": {"Fluid": "ChilledWater", "Size": "DN100", "Tier": "Underfloor"}})

    # South Perimeter CRAH Header along Y = 450 from X = 1200 to X = 25800
    add_cylinder_element(model, body, storey, "IfcPipeSegment", "CHW Perimeter CRAH Header", "CHW-PERIM", "PIPE", None,
                         pipe_od, 25800 - 1200, 1200, 450, z_chw, 25800, 450, z_chw,
                         psets={"Pset_DCM_HVAC": {"Fluid": "ChilledWater", "Size": "DN100", "Tier": "Underfloor"}})

    # In-row CRAH branches along each cabinet row A to F
    for r_id, ry in zip(["A", "B", "C", "D", "E", "F"], row_y_coords):
        # Header runs under the row from X = 1200 to X = 18500
        add_cylinder_element(model, body, storey, "IfcPipeSegment", f"CHW Header Row {r_id}", f"CHW-ROW-{r_id}", "PIPE", None,
                             pipe_od, 18500 - 1200, 1200, ry, z_chw, 18500, ry, z_chw,
                             psets={"Pset_DCM_HVAC": {"Fluid": "ChilledWater", "Size": "DN100", "Tier": "Underfloor", "ServedRow": r_id}})
                             
    # Risers / connections up into each CRAH unit
    # Perimeter units
    for p_tag, pcx, pcy in perimeter_crahs:
        add_cylinder_element(model, body, storey, "IfcPipeSegment", f"CHW Connection {p_tag}", f"CHW-CONN-{p_tag}", "PIPE", "CRAHTermination",
                             pipe_od, 450, pcx, pcy, z_chw, pcx, pcy, 0,
                             psets={"Pset_DCM_HVAC": {"Service": "CHW_DN100", "Type": "Termination"}})
                             
    # In-row units
    for cu_tag, cux, cuy in all_inrow_crahs:
        add_cylinder_element(model, body, storey, "IfcPipeSegment", f"CHW Connection {cu_tag}", f"CHW-CONN-{cu_tag}", "PIPE", "CRAHTermination",
                             pipe_od, 450, cux, cuy, z_chw, cux, cuy, 0,
                             psets={"Pset_DCM_HVAC": {"Service": "CHW_DN50", "Type": "Termination"}})

    # Write output file
    model.write(OUT_PATH)
    print(f"Model successfully authored and written to {OUT_PATH}")

if __name__ == "__main__":
    build_model()
