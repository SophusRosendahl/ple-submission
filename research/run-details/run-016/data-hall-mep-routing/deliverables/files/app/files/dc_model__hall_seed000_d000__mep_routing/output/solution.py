"""Coordinated 3D IFC4 model of Data Hall 1 (hall_seed000_d000) with clash-free MEP routing.

Rebuilds the architectural/structural/equipment background from sheets A-101, A-301,
A-601, A-602, E-101, F-101, and M-101, and routes:
  - Power busway (BW-1, 128 x 147 mm) in the overhead plenum (Z_cl = 2800 mm)
  - Telecom cable tray (CT-1, 683 x 127 mm) in the under-floor plenum (Z_cl = -200 mm)
  - Chilled-water pipe (CHW-1, 168.3 mm insulated OD) in the under-floor plenum (Z_cl = -600 mm)

Writes one IFC4 file to sys.argv[1] (default: output/model.ifc) and a drawing-note
reconciliation log to output/reconciliation.json.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Iterable

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import numpy as np

# ---------------------------------------------------------------------------
# Constants extracted from the 7-sheet drawing set (all dimensions in mm)
# ---------------------------------------------------------------------------

ROOM_W = 27000.0
ROOM_D = 21000.0
TILE_SIZE = 600.0

Z_STRUCT_SLAB_TOP = -900.0
Z_ACCESS_FLOOR_TOP = 0.0
ACCESS_FLOOR_THK = 35.0
Z_MIN_CLEAR = 2600.0
Z_SOFFIT = 3600.0
SPRINKLER_DEFLECTOR_Z = 3574.6  # 25.4 mm below soffit
SPRINKLER_STANDOFF = 460.0      # clear below deflector -> max overhead Z = 3114.6

CABINET_D = 1200.0
CABINET_H = 2000.0
CONT_ROOF_W = 1400.0
CONT_ROOF_THK = 55.5
CONT_DOOR_THK = 60.0
CONT_DOOR_H = 2055.5
IN_AISLE_DEFLECTOR_Z = 1890.0

COL_SIZE = 600.0
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]

# Row definitions from A-101 and A-601
# Bay tokens: (count, type_code) where type_code in {'C1', 'N1', 'CU', 'CA', 'SP', '-600'}
ROW_SPECS = [
    {
        "row": "A",
        "y_cl": 3000.0,
        "facing": "SOUTH",
        "x_start": 1800.0,
        "bays": [
            (4, "C1"), (1, "CU"), (3, "C1"), (1, "N1"), (3, "C1"), (1, "CU"),
            (1, "CA"), (6, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
        ],
    },
    {
        "row": "B",
        "y_cl": 6000.0,
        "facing": "NORTH",
        "x_start": 1800.0,
        "bays": [
            (4, "C1"), (1, "CU"), (5, "C1"), (2, "N1"), (1, "CU"),
            (1, "CA"), (7, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
        ],
    },
    {
        "row": "C",
        "y_cl": 8400.0,
        "facing": "SOUTH",
        "x_start": 1800.0,
        "bays": [
            (3, "C1"), (1, "CU"), (6, "C1"), (2, "-600"), (1, "CU"),
            (1, "CA"), (1, "N1"), (4, "C1"), (1, "CU"), (1, "SP"),
            (1, "C1"), (2, "-600"), (3, "C1"),
        ],
    },
    {
        "row": "D",
        "y_cl": 11400.0,
        "facing": "NORTH",
        "x_start": 1800.0,
        "bays": [
            (4, "C1"), (1, "CU"), (3, "C1"), (2, "N1"), (2, "C1"), (1, "CU"),
            (1, "CA"), (7, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
        ],
    },
    {
        "row": "E",
        "y_cl": 13800.0,
        "facing": "SOUTH",
        "x_start": 1800.0,
        "bays": [
            (4, "C1"), (1, "CU"), (5, "C1"), (1, "N1"), (1, "C1"), (1, "CU"),
            (1, "CA"), (6, "C1"), (1, "SP"), (1, "CU"), (5, "C1"),
        ],
    },
    {
        "row": "F",
        "y_cl": 16800.0,
        "facing": "NORTH",
        "x_start": 1800.0,
        "bays": [
            (4, "C1"), (1, "CU"), (5, "C1"), (2, "-600"), (1, "CU"),
            (1, "CA"), (2, "N1"), (5, "C1"), (1, "SP"), (1, "-600"),
            (1, "CU"), (4, "C1"),
        ],
    },
]

BAY_WIDTHS = {
    "C1": 600.0,
    "N1": 800.0,
    "CU": 600.0,
    "CA": 1200.0,
    "SP": 600.0,
    "-600": 600.0,
}

# Perimeter CRAHs (A-601): 1200 x 900 x 2000, facing NORTH
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, A-101 Note 8): 762 x 813 x 1959, front flush with row front face
PDU_W = 762.0
PDU_D = 813.0
PDU_H = 1959.0
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - PDU_D, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - PDU_D, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - PDU_D, "NORTH"),
]

# Pathway section dimensions (A-602, E-101, M-101)
CT_W, CT_H = 683.0, 127.0
BW_W, BW_H = 128.0, 147.0
CHW_BARE_OD = 114.3
CHW_INSUL_OD = 168.3
CHW_INSUL_THK = 25.4

# Service routing elevations (centreline Z in mm)
Z_BW = 2800.0    # Overhead plenum: 2726.5..2873.5 (clear of 2600 min & 3114.6 sprinkler standoff)
Z_CT = -200.0    # Under-floor plenum: -263.5..-136.5 (101.5 mm clear below -35 panel underside)
Z_CHW = -600.0   # Under-floor plenum: -684.15..-515.85 (215.85 mm above -900 slab, 252 mm below tray)

# Service entry (E-101 & M-101): west wall X = 0, Y = 9900
ENTRY_X = 0.0
ENTRY_Y = 9900.0
SPINE_X = 1200.0

# Row header Y coordinates (offset clear of structural columns on Rows C and F)
ROW_HEADER_YS = [3000.0, 6000.0, 7400.0, 11400.0, 13800.0, 15800.0]
ROW_HEADER_X_END = 19000.0


# ---------------------------------------------------------------------------
# Geometry & IFC helpers
# ---------------------------------------------------------------------------

def make_matrix(cx_mm: float, cy_mm: float, cz_mm: float, rot_z: float = 0.0) -> np.ndarray:
    """Return 4x4 placement matrix with translation in METRES for edit_object_placement."""
    c = math.cos(rot_z)
    s = math.sin(rot_z)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = cz_mm / 1000.0
    return m


def add_box_representation(
    model: ifcopenshell.file,
    body_ctx,
    element,
    w_mm: float,
    d_mm: float,
    h_mm: float,
    cx_mm: float,
    cy_mm: float,
    z_bot_mm: float,
    rot_z: float = 0.0,
) -> None:
    """Attach an extruded 2D rectangle solid centered in local XY, extruded +Z by h_mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(w_mm),
        YDim=float(d_mm),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(h_mm),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=element, representation=rep)
    ifcopenshell.api.geometry.edit_object_placement(
        model, product=element, matrix=make_matrix(cx_mm, cy_mm, z_bot_mm, rot_z), is_si=True
    )


def add_cylinder_representation(
    model: ifcopenshell.file,
    body_ctx,
    element,
    radius_mm: float,
    length_mm: float,
    p1: tuple[float, float, float],
    p2: tuple[float, float, float],
) -> None:
    """Attach an axis-aligned circular extrusion from p1 to p2 (in mm)."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1

    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius_mm),
    )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
        ),
        ExtrudedDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
        Depth=float(length_mm),
    )
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )
    ifcopenshell.api.geometry.assign_representation(model, product=element, representation=rep)

    # Build rotation matrix mapping local +Z to segment direction
    m = np.eye(4, dtype=float)
    if abs(dx) >= abs(dy) and abs(dx) >= abs(dz):
        if dx >= 0:
            # +Z -> +X: x'=(0,0,-1), y'=(0,1,0), z'=(1,0,0)
            m[:3, :3] = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], dtype=float)
        else:
            m[:3, :3] = np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], dtype=float)
    elif abs(dy) >= abs(dx) and abs(dy) >= abs(dz):
        if dy >= 0:
            # +Z -> +Y: x'=(1,0,0), y'=(0,0,-1), z'=(0,1,0)
            m[:3, :3] = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)
        else:
            m[:3, :3] = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=float)
    else:
        if dz < 0:
            m[:3, :3] = np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], dtype=float)

    m[0, 3] = x1 / 1000.0
    m[1, 3] = y1 / 1000.0
    m[2, 3] = z1 / 1000.0
    ifcopenshell.api.geometry.edit_object_placement(model, product=element, matrix=m, is_si=True)


def add_pset(model: ifcopenshell.file, element, name: str, props: dict) -> None:
    pset = ifcopenshell.api.pset.add_pset(model, product=element, name=name)
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)


# ---------------------------------------------------------------------------
# Model builder
# ---------------------------------------------------------------------------

def build_model(out_path: str) -> dict:
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    length_unit = ifcopenshell.api.unit.add_si_unit(model, unit_type="LENGTHUNIT", prefix="MILLI")
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit])

    ctx_model = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx_model,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Meridian Campus")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Phase 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    def place(el):
        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[el])
        return el

    # 1. Slabs (structural, access floor, ceiling)
    for name, predef, obj_type, z_bot, thk in [
        ("StructuralSlab", "BASESLAB", "StructuralSlab", Z_STRUCT_SLAB_TOP - 200.0, 200.0),
        ("AccessFloor", "FLOOR", "AccessFloor", Z_ACCESS_FLOOR_TOP - ACCESS_FLOOR_THK, ACCESS_FLOOR_THK),
        ("CeilingSlab", "ROOF", "CeilingSlab", Z_SOFFIT, 200.0),
    ]:
        slab = place(ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcSlab", predefined_type=predef, name=name
        ))
        slab.ObjectType = obj_type
        add_box_representation(model, body_ctx, slab, ROOM_W, ROOM_D, thk, ROOM_W / 2.0, ROOM_D / 2.0, z_bot)

    # 2. Structural columns (600 x 600, Z = 0..3600)
    for ci, cx in enumerate(COL_XS, start=1):
        for ri, cy in enumerate(COL_YS, start=1):
            col = place(ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcColumn", predefined_type="COLUMN", name=f"COL-{chr(64+ci)}{ri}"
            ))
            add_box_representation(model, body_ctx, col, COL_SIZE, COL_SIZE, Z_SOFFIT, cx, cy, 0.0)

    # 3. Server cabinets & in-row CRAHs
    rack_count = 0
    inrow_crah_count = 0
    for spec in ROW_SPECS:
        row_id = spec["row"]
        y_cl = spec["y_cl"]
        facing = spec["facing"]
        rot_z = 0.0 if facing == "NORTH" else math.pi
        x = spec["x_start"]
        r_idx = 0
        cu_idx = 0
        for count, btype in spec["bays"]:
            bw = BAY_WIDTHS[btype]
            for _ in range(count):
                cx = x + bw / 2.0
                if btype in ("C1", "N1"):
                    r_idx += 1
                    rack_count += 1
                    rack = place(ifcopenshell.api.root.create_entity(
                        model, ifc_class="IfcFurniture", predefined_type="USERDEFINED", name=f"RACK-{row_id}{r_idx:02d}"
                    ))
                    rack.ObjectType = "Rack"
                    add_box_representation(model, body_ctx, rack, bw, CABINET_D, CABINET_H, cx, y_cl, 0.0, rot_z)
                    add_pset(model, rack, "Pset_DCM_Rack", {
                        "Row": row_id,
                        "BayType": btype,
                        "Facing": facing,
                        "Width": bw,
                        "Depth": CABINET_D,
                        "Height": CABINET_H,
                    })
                elif btype == "CU":
                    cu_idx += 1
                    inrow_crah_count += 1
                    crah = place(ifcopenshell.api.root.create_entity(
                        model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRHANDLER", name=f"CRAH-{row_id}{cu_idx:02d}"
                    ))
                    crah.ObjectType = "CRAH"
                    add_box_representation(model, body_ctx, crah, bw, CABINET_D, CABINET_H, cx, y_cl, 0.0, rot_z)
                    add_pset(model, crah, "Pset_DCM_Equipment", {
                        "Placement": "InRow",
                        "Row": row_id,
                        "Facing": facing,
                        "Capacity_kW": 50.0,
                    })
                x += bw

    # 4. Perimeter CRAHs
    for tag, x0, y0 in PERIMETER_CRAHS:
        crah = place(ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRHANDLER", name=tag
        ))
        crah.ObjectType = "CRAH"
        add_box_representation(model, body_ctx, crah, 1200.0, 900.0, 2000.0, x0 + 600.0, y0 + 450.0, 0.0, 0.0)
        add_pset(model, crah, "Pset_DCM_Equipment", {
            "Placement": "Perimeter",
            "Facing": "NORTH",
            "Capacity_kW": 100.0,
        })

    # 5. PDUs
    for tag, row_id, x0, y0, facing in PDUS:
        rot_z = 0.0 if facing == "NORTH" else math.pi
        pdu = place(ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcElectricDistributionBoard", predefined_type="DISTRIBUTIONBOARD", name=tag
        ))
        pdu.ObjectType = "PDU"
        add_box_representation(model, body_ctx, pdu, PDU_W, PDU_D, PDU_H, x0 + PDU_W / 2.0, y0 + PDU_D / 2.0, 0.0, rot_z)
        add_pset(model, pdu, "Pset_DCM_Equipment", {
            "ServesRow": row_id,
            "Facing": facing,
            "Rating_kVA": 225.0,
        })

    # 6. Cold-aisle containment roofs & end doors (CAC-BC, CAC-DE)
    containment_sections = [
        ("CAC-BC-W", 1800.0, 9600.0, 7200.0),
        ("CAC-BC-E", 11200.0, 18800.0, 7200.0),
        ("CAC-DE-W", 1800.0, 9800.0, 12600.0),
        ("CAC-DE-E", 11200.0, 18800.0, 12600.0),
    ]
    for name, x1, x2, y_cl in containment_sections:
        roof = place(ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcCovering", predefined_type="CEILING", name=f"{name}-Roof"
        ))
        roof.ObjectType = "ContainmentRoof"
        add_box_representation(model, body_ctx, roof, x2 - x1, CONT_ROOF_W, CONT_ROOF_THK, (x1 + x2) / 2.0, y_cl, CABINET_H)

        for side, dx in [("W", x1 + CONT_DOOR_THK / 2.0), ("E", x2 - CONT_DOOR_THK / 2.0)]:
            door = place(ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcDoor", predefined_type="DOOR", name=f"{name}-Door-{side}"
            ))
            door.ObjectType = "ContainmentDoor"
            add_box_representation(model, body_ctx, door, CONT_DOOR_THK, 1200.0, CONT_DOOR_H, dx, y_cl, 0.0)

    # 7. Sprinklers (63 ceiling heads + 16 in-aisle heads)
    ceiling_xs = [1500.0 + i * 3000.0 for i in range(9)]
    ceiling_ys = [1500.0 + j * 3000.0 for j in range(7)]
    spr_idx = 0
    for sx in ceiling_xs:
        for sy in ceiling_ys:
            # Relocate clear of any structural column
            hx, hy = sx, sy
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(hx - cx) < 600.0 and abs(hy - cy) < 600.0:
                        hx = cx - 750.0
                        hy = cy - 750.0
            spr_idx += 1
            spr = place(ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=f"SPR-C{spr_idx:02d}"
            ))
            spr.ObjectType = "CeilingSprinkler"
            add_box_representation(model, body_ctx, spr, 50.0, 50.0, 25.4, hx, hy, SPRINKLER_DEFLECTOR_Z)
            add_pset(model, spr, "Pset_DCM_Sprinkler", {"DeflectorZ": SPRINKLER_DEFLECTOR_Z, "Standoff": SPRINKLER_STANDOFF})

    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9200.0, 12000.0, 14400.0, 16800.0, 18400.0]
    ia_idx = 0
    for ay in (7200.0, 12600.0):
        for ax in in_aisle_xs:
            ia_idx += 1
            spr = place(ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcFireSuppressionTerminal", predefined_type="SPRINKLER", name=f"SPR-IA{ia_idx:02d}"
            ))
            spr.ObjectType = "InAisleSprinkler"
            add_box_representation(model, body_ctx, spr, 50.0, 50.0, 110.0, ax, ay, IN_AISLE_DEFLECTOR_Z)
            add_pset(model, spr, "Pset_DCM_Sprinkler", {"DeflectorZ": IN_AISLE_DEFLECTOR_Z, "Standoff": SPRINKLER_STANDOFF})

    # -----------------------------------------------------------------------
    # 8. Overhead & Under-floor MEP Routing
    # -----------------------------------------------------------------------

    def add_rect_segment(
        ifc_class: str,
        predef: str,
        obj_type: str,
        name: str,
        service: str,
        tag: str,
        w_mm: float,
        h_mm: float,
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
    ) -> float:
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        seg_len = math.hypot(x2 - x1, y2 - y1)
        if seg_len < 1.0:
            return 0.0
        el = place(ifcopenshell.api.root.create_entity(
            model, ifc_class=ifc_class, predefined_type=predef, name=name
        ))
        el.ObjectType = obj_type
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        z_bot = z1 - h_mm / 2.0
        if abs(x2 - x1) >= abs(y2 - y1):
            add_box_representation(model, body_ctx, el, seg_len, w_mm, h_mm, cx, cy, z_bot)
        else:
            add_box_representation(model, body_ctx, el, w_mm, seg_len, h_mm, cx, cy, z_bot)
        add_pset(model, el, "Pset_DCM_Service", {
            "Service": service,
            "Tag": tag,
            "Elevation_CL": z1,
            "Zone": "Overhead" if z1 >= 0.0 else "UnderFloor",
        })
        return seg_len

    def add_pipe_segment(
        name: str,
        p1: tuple[float, float, float],
        p2: tuple[float, float, float],
    ) -> float:
        x1, y1, z1 = p1
        x2, y2, z2 = p2
        seg_len = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
        if seg_len < 1.0:
            return 0.0
        el = place(ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcPipeSegment", predefined_type="RIGIDSEGMENT", name=name
        ))
        el.ObjectType = "ChilledWaterPipe"
        add_cylinder_representation(model, body_ctx, el, CHW_INSUL_OD / 2.0, seg_len, p1, p2)
        add_pset(model, el, "Pset_DCM_Service", {
            "Service": "ChilledWater",
            "Tag": "CHW-1",
            "OuterDiameter": CHW_INSUL_OD,
            "BareDiameter": CHW_BARE_OD,
            "InsulationThickness": CHW_INSUL_THK,
            "Elevation_CL": z1,
            "Zone": "Overhead" if z1 >= 0.0 else "UnderFloor",
        })
        return seg_len

    def build_tree_segments(z_cl: float, include_perimeter: bool) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
        segs = []
        # Entry feed from west wall (0, 9900) to spine (1200, 9900)
        segs.append(((ENTRY_X, ENTRY_Y, z_cl), (SPINE_X, ENTRY_Y, z_cl)))
        # Spine north & south
        y_min = 1200.0 if include_perimeter else ROW_HEADER_YS[0]
        y_max = ROW_HEADER_YS[-1]
        segs.append(((SPINE_X, ENTRY_Y, z_cl), (SPINE_X, y_min, z_cl)))
        segs.append(((SPINE_X, ENTRY_Y, z_cl), (SPINE_X, y_max, z_cl)))
        # Row headers
        for ry in ROW_HEADER_YS:
            segs.append(((SPINE_X, ry, z_cl), (ROW_HEADER_X_END, ry, z_cl)))
        # Perimeter CRAH header (CHW only)
        if include_perimeter:
            segs.append(((SPINE_X, 1200.0, z_cl), (25800.0, 1200.0, z_cl)))
        return segs

    lengths = {"Busway": 0.0, "CableTray": 0.0, "ChilledWater": 0.0}

    for idx, (p1, p2) in enumerate(build_tree_segments(Z_BW, False), start=1):
        lengths["Busway"] += add_rect_segment(
            "IfcCableCarrierSegment", "CABLETRUNKINGSEGMENT", "Busway",
            f"BW-SEG-{idx:02d}", "Power", "BW-1", BW_W, BW_H, p1, p2
        )

    for idx, (p1, p2) in enumerate(build_tree_segments(Z_CT, False), start=1):
        lengths["CableTray"] += add_rect_segment(
            "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray",
            f"CT-SEG-{idx:02d}", "Telecom", "CT-1", CT_W, CT_H, p1, p2
        )

    for idx, (p1, p2) in enumerate(build_tree_segments(Z_CHW, True), start=1):
        lengths["ChilledWater"] += add_pipe_segment(f"CHW-SEG-{idx:02d}", p1, p2)

    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out_file))

    reconciliation = {
        "hall": "hall_seed000_d000",
        "counts": {
            "cabinets": rack_count,
            "in_row_crahs": inrow_crah_count,
            "perimeter_crahs": len(PERIMETER_CRAHS),
            "pdus": len(PDUS),
            "columns": len(COL_XS) * len(COL_YS),
            "ceiling_sprinklers": spr_idx,
            "in_aisle_sprinklers": ia_idx,
        },
        "vertical_datums_mm": {
            "structural_slab_top": Z_STRUCT_SLAB_TOP,
            "access_floor_top": Z_ACCESS_FLOOR_TOP,
            "access_floor_thickness": ACCESS_FLOOR_THK,
            "min_clear_height": Z_MIN_CLEAR,
            "ceiling_soffit": Z_SOFFIT,
            "sprinkler_deflector": SPRINKLER_DEFLECTOR_Z,
            "sprinkler_standoff": SPRINKLER_STANDOFF,
            "max_overhead_top": SPRINKLER_DEFLECTOR_Z - SPRINKLER_STANDOFF,
        },
        "service_elevations_cl_mm": {
            "busway_BW1": Z_BW,
            "cable_tray_CT1": Z_CT,
            "chilled_water_CHW1": Z_CHW,
        },
        "achieved_clearances_mm": {
            "busway_to_sprinkler_deflector": SPRINKLER_DEFLECTOR_Z - (Z_BW + BW_H / 2.0),
            "busway_bottom_to_clear_height": (Z_BW - BW_H / 2.0) - Z_MIN_CLEAR,
            "tray_to_busway_vertical": (Z_BW - BW_H / 2.0) - (Z_CT + CT_H / 2.0),
            "tray_top_to_access_floor_underside": (-ACCESS_FLOOR_THK) - (Z_CT + CT_H / 2.0),
            "chw_to_tray_vertical": (Z_CT - CT_H / 2.0) - (Z_CHW + CHW_INSUL_OD / 2.0),
            "chw_in_pdu_dedicated_space": "none (routed under-floor, clear of all PDUs)",
        },
        "centreline_lengths_mm": lengths,
    }
    recon_path = out_file.parent / "reconciliation.json"
    recon_path.write_text(json.dumps(reconciliation, indent=2), encoding="utf-8")
    return reconciliation


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("output", "model.ifc")
    build_model(out_path)


if __name__ == "__main__":
    main()
