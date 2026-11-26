#!/usr/bin/env python3
"""Coordinated 3D MEP routing and data hall model generator for dc_model hall_seed000_d000.

Rebuilds the entire room background and coordinates the three overhead MEP services:
- Background: 128 cabinets, structural columns, CRAHs, PDUs, access floor,
              cold-aisle containment, and NFPA 13 sprinkler grid.
- MEP Services: Telecom cable tray, power busway, and insulated chilled water distribution.
- Code & Clash Compliance: Headroom >= 2600 mm, sprinkler deflector clearance >= 460 mm,
                           PDU dedicated electrical space (1800 mm clear above),
                           tray-busway separation >= 300 mm, zero hard clashes.
- IFC4 standard compliance verified with express_rules=True.
"""

import json
import math
import os
import sys
import ifcopenshell
import ifcopenshell.guid
import ifcopenshell.validate


def build_model(out_path: str):
    # Ensure destination directory exists
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # 1. IFC4 Model Initialization & Units Definition
    # -------------------------------------------------------------------------
    model = ifcopenshell.file(schema="IFC4")

    # SI Project Units (Millimetre project units)
    length_unit = model.createIfcSIUnit(
        UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE"
    )
    plane_angle_unit = model.createIfcSIUnit(
        UnitType="PLANEANGLEUNIT", Name="RADIAN"
    )
    area_unit = model.createIfcSIUnit(
        UnitType="AREAUNIT", Prefix=None, Name="SQUARE_METRE"
    )
    volume_unit = model.createIfcSIUnit(
        UnitType="VOLUMEUNIT", Prefix=None, Name="CUBIC_METRE"
    )
    unit_assignment = model.createIfcUnitAssignment(
        Units=[length_unit, plane_angle_unit, area_unit, volume_unit]
    )

    # Representation Contexts
    world_origin = model.createIfcCartesianPoint((0.0, 0.0, 0.0))
    axis_z = model.createIfcDirection((0.0, 0.0, 1.0))
    ref_dir_x = model.createIfcDirection((1.0, 0.0, 0.0))
    wcs = model.createIfcAxis2Placement3D(world_origin, axis_z, ref_dir_x)

    model_context = model.createIfcGeometricRepresentationContext(
        ContextIdentifier=None,
        ContextType="Model",
        CoordinateSpaceDimension=3,
        Precision=1.0e-5,
        WorldCoordinateSystem=wcs,
        TrueNorth=model.createIfcDirection((0.0, 1.0)),
    )

    sub_context_body = model.createIfcGeometricRepresentationSubContext(
        ContextIdentifier="Body",
        ContextType="Model",
        ParentContext=model_context,
        TargetScale=None,
        TargetView="MODEL_VIEW",
        UserDefinedTargetView=None,
    )

    # Spatial Structure Hierarchy: Project -> Site -> Building -> Storey -> Space
    project = model.createIfcProject(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="DataHall_Seed000",
        Description="Data Hall Coordinated Background and Overhead MEP Model",
        UnitsInContext=unit_assignment,
        RepresentationContexts=[model_context],
    )

    site = model.createIfcSite(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="DataCenter_Site",
        CompositionType="ELEMENT",
        ObjectPlacement=model.createIfcLocalPlacement(None, wcs),
    )

    building = model.createIfcBuilding(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="DataCenter_Building",
        CompositionType="ELEMENT",
        ObjectPlacement=model.createIfcLocalPlacement(
            site.ObjectPlacement, wcs
        ),
    )

    storey = model.createIfcBuildingStorey(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="DataHall_Level_1",
        CompositionType="ELEMENT",
        Elevation=0.0,
        ObjectPlacement=model.createIfcLocalPlacement(
            building.ObjectPlacement, wcs
        ),
    )

    space = model.createIfcSpace(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="DataHall_Seed000_Room",
        LongName="Data Hall White Space ~27x21m (128 Cabinets)",
        CompositionType="ELEMENT",
        ObjectPlacement=model.createIfcLocalPlacement(
            storey.ObjectPlacement, wcs
        ),
    )

    # Aggregate spatial structure
    model.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=project,
        RelatedObjects=[site],
    )
    model.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=site,
        RelatedObjects=[building],
    )
    model.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=building,
        RelatedObjects=[storey],
    )
    model.createIfcRelAggregates(
        GlobalId=ifcopenshell.guid.new(),
        RelatingObject=storey,
        RelatedObjects=[space],
    )

    contained_elements = []

    # -------------------------------------------------------------------------
    # Helper Functions for Geometry and Property Sets
    # -------------------------------------------------------------------------
    def attach_pset(product, pset_name: str, properties: dict):
        props = []
        for k, v in properties.items():
            if isinstance(v, bool):
                val = model.createIfcBoolean(v)
            elif isinstance(v, int):
                val = model.createIfcInteger(v)
            elif isinstance(v, float):
                val = model.createIfcReal(v)
            else:
                val = model.createIfcLabel(str(v))
            props.append(
                model.createIfcPropertySingleValue(
                    Name=k, NominalValue=val, Unit=None
                )
            )

        pset = model.createIfcPropertySet(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=None,
            Name=pset_name,
            HasProperties=props,
        )
        model.createIfcRelDefinesByProperties(
            GlobalId=ifcopenshell.guid.new(),
            OwnerHistory=None,
            RelatedObjects=[product],
            RelatingPropertyDefinition=pset,
        )

    def create_box_solid(dx: float, dy: float, dz: float):
        """Creates an extruded rectangle solid centered on the footprint (dx x dy) extruded dz along +Z."""
        pos2d = model.createIfcAxis2Placement2D(
            model.createIfcCartesianPoint((0.0, 0.0))
        )
        profile = model.createIfcRectangleProfileDef(
            ProfileType="AREA",
            ProfileName=f"Rect_{int(dx)}x{int(dy)}",
            Position=pos2d,
            XDim=float(dx),
            YDim=float(dy),
        )
        extrusion = model.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=None,
            ExtrudedDirection=axis_z,
            Depth=float(dz),
        )
        return extrusion

    def create_pipe_solid(
        radius: float, length: float, direction: tuple = (1.0, 0.0, 0.0)
    ):
        """Creates a circular swept area solid along direction."""
        pos2d = model.createIfcAxis2Placement2D(
            model.createIfcCartesianPoint((0.0, 0.0))
        )
        profile = model.createIfcCircleProfileDef(
            ProfileType="AREA",
            ProfileName=f"Pipe_R{int(radius)}",
            Position=pos2d,
            Radius=float(radius),
        )
        ext_dir = model.createIfcDirection(direction)
        extrusion = model.createIfcExtrudedAreaSolid(
            SweptArea=profile,
            Position=None,
            ExtrudedDirection=ext_dir,
            Depth=float(length),
        )
        return extrusion

    def create_placement_3d(
        x: float, y: float, z: float, yaw_rad: float = 0.0
    ):
        loc = model.createIfcCartesianPoint((float(x), float(y), float(z)))
        if abs(yaw_rad) < 1e-6:
            r_dir = ref_dir_x
        elif abs(yaw_rad - math.pi) < 1e-4 or abs(yaw_rad + math.pi) < 1e-4:
            r_dir = model.createIfcDirection((-1.0, 0.0, 0.0))
        else:
            r_dir = model.createIfcDirection(
                (math.cos(yaw_rad), math.sin(yaw_rad), 0.0)
            )
        placement = model.createIfcAxis2Placement3D(loc, axis_z, r_dir)
        return model.createIfcLocalPlacement(storey.ObjectPlacement, placement)

    # -------------------------------------------------------------------------
    # 2. Architectural Background Modelling
    # -------------------------------------------------------------------------
    # Room parameters: ~27m x 21m. FFL = 0 mm. Subfloor = -800 mm. Ceiling = 4500 mm.
    hall_length = 27000.0  # X
    hall_width = 21000.0  # Y
    ffl_elevation = 0.0
    subfloor_elevation = -800.0
    ceiling_elevation = 4500.0

    # Access Floor Slab (Raised Floor)
    floor_solid = create_box_solid(hall_length, hall_width, 38.0)
    floor_shape = model.createIfcShapeRepresentation(
        ContextOfItems=sub_context_body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[floor_solid],
    )
    floor_rep = model.createIfcProductDefinitionShape(
        Representations=[floor_shape]
    )
    access_floor = model.createIfcSlab(
        GlobalId=ifcopenshell.guid.new(),
        OwnerHistory=None,
        Name="AccessFloor_L1",
        PredefinedType="FLOOR",
        ObjectType="AccessFloor",
        ObjectPlacement=create_placement_3d(
            hall_length / 2.0, hall_width / 2.0, -38.0
        ),
        Representation=floor_rep,
    )
    attach_pset(
        access_floor,
        "Pset_DCM_AccessFloor",
        {
            "TileSize": 600,
            "FinishedFloorLevel": 0.0,
            "PlenumHeight": 800.0,
        },
    )
    contained_elements.append(access_floor)

    # Structural Columns (6 columns full clear height -800 mm to 4500 mm)
    col_size = 500.0
    col_height = ceiling_elevation - subfloor_elevation  # 5300 mm
    col_x_coords = [9000.0, 18000.0]
    col_y_coords = [1800.0, 10500.0, 19200.0]

    col_solid = create_box_solid(col_size, col_size, col_height)
    col_shape = model.createIfcShapeRepresentation(
        ContextOfItems=sub_context_body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[col_solid],
    )
    col_rep = model.createIfcProductDefinitionShape(Representations=[col_shape])

    col_idx = 1
    for cx in col_x_coords:
        for cy in col_y_coords:
            col_elem = model.createIfcColumn(
                GlobalId=ifcopenshell.guid.new(),
                OwnerHistory=None,
                Name=f"Col-{cx/1000:.0f}m-{cy/1000:.1f}m",
                PredefinedType="COLUMN",
                ObjectType="Column",
                ObjectPlacement=create_placement_3d(
                    cx, cy, subfloor_elevation, 0.0
                ),
                Representation=col_rep,
            )
            attach_pset(
                col_elem,
                "Pset_DCM_Column",
                {
                    "Width": col_size,
                    "Depth": col_size,
                    "FullHeight": col_height,
                },
            )
            contained_elements.append(col_elem)
            col_idx += 1

    # 128 Cabinets (Racks): 4 rows of 32 cabinets (600 mm W x 1200 mm D x 2000 mm H)
    # Row 1: Y = 4200 (faces North/Cold Aisle 1, yaw = 0)
    # Row 2: Y = 6600 (faces South/Cold A
