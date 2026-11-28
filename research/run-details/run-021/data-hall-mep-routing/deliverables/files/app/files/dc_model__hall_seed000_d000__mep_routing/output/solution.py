"""Coordinated IFC4 model generator for Data Hall 1 (hall_seed000_d000).

Builds the full coordination background (access floor, structural columns,
128 server/distributor cabinets, 4 perimeter + 18 in-row CRAHs, 6 PDUs,
cold-aisle containment, 63 ceiling + 16 in-aisle sprinkler heads) and routes
the three MEP services (Telecom Cable Tray CT-1, Power Busway BW-1, Chilled
Water CHW-1) clash-free and code-compliant.

Usage:
    python3 output/solution.py [OUT_PATH]
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.api
import numpy as np

DEFAULT_OUT = "/app/files/dc_model__hall_seed000_d000__mep_routing/output/model.ifc"
OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT

# ---------------------------------------------------------------------------
# Architectural & Schedule Data (baked from A-101, A-301, A-601, A-602,
# E-101, F-101, M-101)
# ---------------------------------------------------------------------------

ROOM_W = 27000.0
ROOM_D = 21000.0
CEILING_Z = 3600.0
SLAB_Z = -900.0
ACCESS_FLOOR_THK = 35.0
MIN_CLEAR_Z = 2600.0
SPRINKLER_DEFLECTOR_Z = 3574.6  # 25.4 mm below 3600 soffit
SPRINKLER_STANDOFF = 460.0
IN_AISLE_DEFLECTOR_Z = 1890.0

COL_GRID_X = [8400.0, 16800.0, 25200.0]
COL_GRID_Y = [8400.0, 16800.0]
COL_SIZE = 600.0

ROW_SPECS = [
    ("A", 3000.0, "SOUTH", "4C1 · CU · 3C1 · N1 · 3C1 · CU", "6C1 · SP · CU · 5C1"),
    ("B", 6000.0, "NORTH", "4C1 · CU · 5C1 · 2N1 · CU", "7C1 · SP · CU · 5C1"),
    ("C", 8400.0, "SOUTH", "3C1 · CU · 6C1 · 2-600 · CU", "N1 · 4C1 · CU · SP · C1 · 2-600 · 3C1"),
    ("D", 11400.0, "NORTH", "4C1 · CU · 3C1 · 2N1 · 2C1 · CU", "7C1 · SP · CU · 5C1"),
    ("E", 13800.0, "SOUTH", "4C1 · CU · 5C1 · N1 · C1 · CU", "6C1 · SP · CU · 5C1"),
    ("F", 16800.0, "NORTH", "4C1 · CU · 5C1 · 2-600 · CU", "2N1 · 5C1 · SP · -600 · CU · 4C1"),
]

ROW_START_X = 1800.0       # Column D (tile index 3 * 600)
CROSS_AISLE_EAST_X = 11400.0  # Common East edge of cross aisle (tile 19 * 600)
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0
BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0}

# Perimeter CRAHs (A-601: B01, P01, AC01, AQ01 -> X = 600, 9000, 16800, 25200; Y = 0)
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs (A-601 & A-101 Note 8: front flush with row front face)
# Plan 762 x 813, Height 1959
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

# Cold-Aisle Containment (A-602)
CAC_ROOF_W = 1400.0
CAC_ROOF_THK = 55.5
CAC_ROOF_Z = 2000.0
CAC_DOOR_THK = 60.0
CAC_DOOR_H = 2055.5
CAC_AISLE_W = 1200.0
CAC_DEFS = [
    ("CAC-BC", 7200.0, (1800.0, 9600.0), (11400.0, 19400.0)),
    ("CAC-DE", 12600.0, (1800.0, 9800.0), (11400.0, 19200.0)),
]

# Service Entry (E-101, M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Pathway section sizes (A-602, M-101)
CT_W, CT_H = 683.0, 127.0
BW_W, BW_H = 128.0, 147.0
CHW_OD = 168.3  # DN100 (114.3 bare) + 25.4 insulation jacket per ASTM C585

# Coordinated Service Elevations (centrelines, mm relative to Finished Floor ±0)
# - BW-1: Overhead tier, bottom 2940, top 3087 (>2600 headroom, >460 below 3574.6 deflector)
# - CT-1: Under-floor plenum tier 1, bottom -250, top -123 (>20 below -35 floor panel)
# - CHW-1: Under-floor plenum tier 2, bottom -600, top -431.7 (>180 below CT-1, >300 above -900 slab)
BW_Z = 3013.5
CT_Z = -186.5
CHW_Z = -515.85


# ---------------------------------------------------------------------------
# IFC4 Helper Functions
# ---------------------------------------------------------------------------

def make_matrix(tx_mm: float, ty_mm: float, tz_mm: float, yaw_deg: float = 0.0) -> np.ndarray:
    """Return a 4x4 placement matrix with translations in METRES (for ifcopenshell is_si=True)."""
    rad = math.radians(yaw_deg)
    c, s = math.cos(rad), math.sin(rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = tx_mm / 1000.0
    m[1, 3] = ty_mm / 1000.0
    m[2, 3] = tz_mm / 1000.0
    return m


def facing_to_yaw(facing: str) -> float:
    """Local +Y is NORTH (0 deg); SOUTH is 180 deg; EAST is -90; WEST is +90."""
    return {"NORTH": 0.0, "SOUTH": 180.0, "EAST": -90.0, "WEST": 90.0}[facing]


def create_box_rep(model: ifcopenshell.file, ctx: Any, dx: float, dy: float, dz: float) -> Any:
    """Create a centered-in-XY, Z-extruded [0, dz] IfcExtrudedAreaSolid in mm."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        XDim=float(dx),
        YDim=float(dy),
    )
    axis = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axis,
        ExtrudedDirection=direction,
        Depth=float(dz),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def create_cyl_rep(model: ifcopenshell.file, ctx: Any, radius: float, length: float) -> Any:
    """Create a Z-extruded cylinder [0, length] of given radius in mm."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Radius=float(radius),
    )
    axis = model.create_entity(
        "IfcAxis2Placement3D",
        Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
    )
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=axis,
        ExtrudedDirection=direction,
        Depth=float(length),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def assign_product(
    model: ifcopenshell.file,
    storey: Any,
    ctx: Any,
    ifc_class: str,
    name: str,
    rep: Any,
    matrix: np.ndarray,
    predefined_type: str | None = None,
    object_type: str | None = None,
    pset_name: str | None = None,
    pset_props: dict[str, Any] | None = None,
    system: Any | None = None,
) -> Any:
    kwargs: dict[str, Any] = {"ifc_class": ifc_class, "name": name}
    if predefined_type is not None:
        kwargs["predefined_type"] = predefined_type
    elem = ifcopenshell.api.run("root.create_entity", model, **kwargs)
    if object_type is not None:
        elem.ObjectType = object_type
    ifcopenshell.api.run("spatial.assign_container", model, products=[elem], relating_structure=storey)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=matrix, is_si=True)
    ifcopenshell.api.run("geometry.assign_representation", model, product=elem, representation=rep)
    if pset_name and pset_props:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=elem, name=pset_name)
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=pset_props)
    if system is not None:
        ifcopenshell.api.run("system.assign_system", model, products=[elem], system=system)
    return elem


def add_rect_segment(
    model: ifcopenshell.file,
    storey: Any,
    ctx: Any,
    ifc_class: str,
    predefined_type: str,
    object_type: str,
    name: str,
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    width: float,
    height: float,
    system: Any,
    service_name: str,
    zone_name: str,
) -> Any:
    """Create an axis-aligned rectangular MEP segment from p0 to p1 (centrelines in mm)."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    assert length > 1e-3, f"Zero-length segment {name}"
    cx, cy, cz = (x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0

    if abs(dx) > 1e-3 and abs(dy) < 1e-3 and abs(dz) < 1e-3:
        # Runs along X: box is (length, width, height)
        rep = create_box_rep(model, ctx, length, width, height)
        mat = make_matrix(cx, cy, cz - height / 2.0, 0.0)
    elif abs(dy) > 1e-3 and abs(dx) < 1e-3 and abs(dz) < 1e-3:
        # Runs along Y: box is (width, length, height)
        rep = create_box_rep(model, ctx, width, length, height)
        mat = make_matrix(cx, cy, cz - height / 2.0, 0.0)
    elif abs(dz) > 1e-3 and abs(dx) < 1e-3 and abs(dy) < 1e-3:
        # Runs along Z: box is (width, width, length)
        rep = create_box_rep(model, ctx, width, width, length)
        mat = make_matrix(cx, cy, min(z0, z1), 0.0)
    else:
        raise ValueError(f"Non-axis-aligned segment {name}: {p0} -> {p1}")

    return assign_product(
        model,
        storey,
        ctx,
        ifc_class=ifc_class,
        name=name,
        rep=rep,
        matrix=mat,
        predefined_type=predefined_type,
        object_type=object_type,
        pset_name="Pset_DCM_Service",
        pset_props={
            "Service": service_name,
            "Tag": object_type,
            "Elevation_mm": float(cz),
            "Zone": zone_name,
            "Length_mm": float(length),
        },
        system=system,
    )


def add_pipe_segment(
    model: ifcopenshell.file,
    storey: Any,
    ctx: Any,
    name: str,
    p0: tuple[float, float, float],
    p1: tuple[float, float, float],
    od: float,
    system: Any,
    zone_name: str,
) -> Any:
    """Create an axis-aligned cylindrical pipe segment from p0 to p1 (centrelines in mm)."""
    x0, y0, z0 = p0
    x1, y1, z1 = p1
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    assert length > 1e-3, f"Zero-length pipe {name}"
    r = od / 2.0
    rep = create_cyl_rep(model, ctx, r, length)

    # Local cylinder extrudes along +Z from 0 to length.
    m = np.eye(4, dtype=float)
    if abs(dx) > 1e-3 and abs(dy) < 1e-3 and abs(dz) < 1e-3:
        # +Z -> +X (or -X)
        sx = 1.0 if dx > 0 else -1.0
        m[:3, 0] = [0.0, 0.0, -sx]
        m[:3, 1] = [0.0, 1.0, 0.0]
        m[:3, 2] = [sx, 0.0, 0.0]
    elif abs(dy) > 1e-3 and abs(dx) < 1e-3 and abs(dz) < 1e-3:
        # +Z -> +Y (or -Y)
        sy = 1.0 if dy > 0 else -1.0
        m[:3, 0] = [1.0, 0.0, 0.0]
        m[:3, 1] = [0.0, 0.0, -sy]
        m[:3, 2] = [0.0, sy, 0.0]
    elif abs(dz) > 1e-3 and abs(dx) < 1e-3 and abs(dy) < 1e-3:
        # +Z -> +Z (or -Z)
        sz = 1.0 if dz > 0 else -1.0
        if sz < 0:
            m[:3, 0] = [1.0, 0.0, 0.0]
            m[:3, 1] = [0.0, -1.0, 0.0]
            m[:3, 2] = [0.0, 0.0, -1.0]
    else:
        raise ValueError(f"Non-axis-aligned pipe {name}: {p0} -> {p1}")

    m[0, 3] = x0 / 1000.0
    m[1, 3] = y0 / 1000.0
    m[2, 3] = z0 / 1000.0

    return assign_product(
        model,
        storey,
        ctx,
        ifc_class="IfcPipeSegment",
        name=name,
        rep=rep,
        matrix=m,
        predefined_type="RIGIDSEGMENT",
        object_type="CHW-1",
        pset_name="Pset_DCM_Service",
        pset_props={
            "Service": "ChilledWater",
            "Tag": "CHW-1",
            "NominalDiameter_mm": 100.0,
            "InsulatedOD_mm": float(od),
            "Elevation_mm": float((z0 + z1) / 2.0),
            "Zone": zone_name,
            "Length_mm": float(length),
        },
        system=system,
    )


# ---------------------------------------------------------------------------
# Bay Sequence Parser
# ---------------------------------------------------------------------------

def parse_bay_sequence(seq_str: str) -> list[tuple[str, float]]:
    """Return list of (token_type, width_mm) from a schedule bay sequence."""
    out: list[tuple[str, float]] = []
    for tok in [t.strip() for t in seq_str.split("·")]:
        if tok.startswith("-"):
            out.append(("OMIT", float(int(tok[1:]))))
        elif "-" in tok:
            m = re.match(r"^(\d+)-(\d+)$", tok)
            assert m, f"Bad token: {tok}"
            for _ in range(int(m.group(1))):
                out.append(("OMIT", float(int(m.group(2)))))
        else:
            m = re.match(r"^(\d*)([A-Z0-9]+)$", tok)
            assert m, f"Bad token: {tok}"
            cnt = int(m.group(1)) if m.group(1) else 1
            typ = m.group(2)
            for _ in range(cnt):
                out.append((typ, BAY_WIDTHS[typ]))
    return out


# ---------------------------------------------------------------------------
# Main Builder
# ---------------------------------------------------------------------------

def build_model(out_path: str) -> None:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1")

    # Millimetre project units
    length_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI")
    area_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="AREAUNIT")
    vol_unit = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="VOLUMEUNIT")
    ifcopenshell.api.run("unit.assign_unit", model, units=[length_unit, area_unit, vol_unit])

    # Geometric representation context
    ctx_3d = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    body_ctx = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx_3d,
    )

    # Spatial hierarchy
    site = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcSite", name="Meridian Campus")
    building = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuilding", name="Phase 1 Building")
    storey = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)

    # MEP Systems
    sys_ct = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_ct.Name = "Telecom Cable Tray"
    sys_bw = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_bw.Name = "Power Busway"
    sys_chw = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
    sys_chw.Name = "Chilled Water"

    # 1. Access Floor (35 mm panel, top at ±0, bottom at -35)
    floor_rep = create_box_rep(model, body_ctx, ROOM_W, ROOM_D, ACCESS_FLOOR_THK)
    assign_product(
        model,
        storey,
        body_ctx,
        ifc_class="IfcSlab",
        name="Access Floor",
        rep=floor_rep,
        matrix=make_matrix(ROOM_W / 2.0, ROOM_D / 2.0, -ACCESS_FLOOR_THK),
        predefined_type="FLOOR",
        object_type="AccessFloor",
    )

    # 2. Structural Columns (6 columns, 600x600, Z = 0..3600)
    for ix, gx in enumerate(COL_GRID_X):
        col_letter = chr(ord("A") + ix)
        for iy, gy in enumerate(COL_GRID_Y):
            assign_product(
                model,
                storey,
                body_ctx,
                ifc_class="IfcColumn",
                name=f"COL-{col_letter}{iy + 1}",
                rep=create_box_rep(model, body_ctx, COL_SIZE, COL_SIZE, CEILING_Z),
                matrix=make_matrix(gx, gy, 0.0),
                predefined_type="COLUMN",
            )

    # 3. Server Cabinets (128) & In-Row CRAHs (18)
    row_x_extents: dict[str, tuple[float, float]] = {}
    for row_id, row_y, facing, west_seq, east_seq in ROW_SPECS:
        yaw = facing_to_yaw(facing)
        rack_idx = 0
        crah_idx = 0
        x_min = ROW_START_X
        x_max = ROW_START_X

        for start_x, seq_str in [(ROW_START_X, west_seq), (CROSS_AISLE_EAST_X, east_seq)]:
            x = start_x
            for typ, w in parse_bay_sequence(seq_str):
                cx = x + w / 2.0
                if typ in ("C1", "N1"):
                    rack_idx += 1
                    assign_product(
                        model,
                        storey,
                        body_ctx,
                        ifc_class="IfcFurniture",
                        name=f"RACK-{row_id}{rack_idx:02d}",
                        rep=create_box_rep(model, body_ctx, w, CAB_DEPTH, CAB_HEIGHT),
                        matrix=make_matrix(cx, row_y, 0.0, yaw),
                        predefined_type="USERDEFINED",
                        object_type="Rack",
                        pset_name="Pset_DCM_Rack",
                        pset_props={
                            "Row": row_id,
                            "Facing": facing,
                            "CabinetType": typ,
                            "Width_mm": float(w),
                            "Depth_mm": CAB_DEPTH,
                            "Height_mm": CAB_HEIGHT,
                            "RU": 42,
                            "Power_kW": 8.0,
                            "Load_kg": 1363.0,
                        },
                    )
                    x_max = max(x_max, x + w)
                elif typ == "CU":
                    crah_idx += 1
                    assign_product(
                        model,
                        storey,
                        body_ctx,
                        ifc_class="IfcUnitaryEquipment",
                        name=f"CRAH-{row_id}{crah_idx:02d}",
                        rep=create_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT),
                        matrix=make_matrix(cx, row_y, 0.0, yaw),
                        predefined_type="AIRCONDITIONINGUNIT",
                        object_type="CRAH",
                        pset_name="Pset_DCM_CRAH",
                        pset_props={
                            "Placement": f"IN ROW {row_id}",
                            "Facing": facing,
                            "Capacity_kW": 50.0,
                            "Airflow_m3h": 9000.0,
                        },
                    )
                    x_max = max(x_max, x + w)
                x += w
        row_x_extents[row_id] = (x_min, x_max)

    # 4. Perimeter CRAHs (4)
    for tag, x0, y0, w, d, h, facing in PERIMETER_CRAHS:
        assign_product(
            model,
            storey,
            body_ctx,
            ifc_class="IfcUnitaryEquipment",
            name=tag,
            rep=create_box_rep(model, body_ctx, w, d, h),
            matrix=make_matrix(x0 + w / 2.0, y0 + d / 2.0, 0.0, facing_to_yaw(facing)),
            predefined_type="AIRCONDITIONINGUNIT",
            object_type="CRAH",
            pset_name="Pset_DCM_CRAH",
            pset_props={
                "Placement": "PERIMETER",
                "Facing": facing,
                "Capacity_kW": 100.0,
                "Airflow_m3h": 20000.0,
            },
        )

    # 5. PDUs (6)
    for tag, serves_row, x0, y0, facing in PDUS:
        assign_product(
            model,
            storey,
            body_ctx,
            ifc_class="IfcElectricDistributionBoard",
            name=tag,
            rep=create_box_rep(model, body_ctx, PDU_W, PDU_D, PDU_H),
            matrix=make_matrix(x0 + PDU_W / 2.0, y0 + PDU_D / 2.0, 0.0, facing_to_yaw(facing)),
            predefined_type="DISTRIBUTIONBOARD",
            object_type="PDU",
            pset_name="Pset_DCM_PDU",
            pset_props={
                "ServesRow": serves_row,
                "Facing": facing,
                "Rating_kVA": 225.0,
                "WorkingSpace_mm": 900.0,
            },
        )

    # 6. Cold-Aisle Containment (2 aisles x (2 roof panels + 4 end doors))
    for tag, cy, (wx0, wx1), (ex0, ex1) in CAC_DEFS:
        for side, (sx0, sx1) in [("W", (wx0, wx1)), ("E", (ex0, ex1))]:
            roof_rep = create_box_rep(model, body_ctx, sx1 - sx0, CAC_ROOF_W, CAC_ROOF_THK)
            assign_product(
                model,
                storey,
                body_ctx,
                ifc_class="IfcBuildingElementProxy",
                name=f"{tag}-ROOF-{side}",
                rep=roof_rep,
                matrix=make_matrix((sx0 + sx1) / 2.0, cy, CAC_ROOF_Z),
                predefined_type="USERDEFINED",
                object_type="ContainmentRoof",
            )
            for end_lbl, dx_pos in [("W", sx0 - CAC_DOOR_THK / 2.0), ("E", sx1 + CAC_DOOR_THK / 2.0)]:
                assign_product(
                    model,
                    storey,
                    body_ctx,
                    ifc_class="IfcBuildingElementProxy",
                    name=f"{tag}-DOOR-{side}{end_lbl}",
                    rep=create_box_rep(model, body_ctx, CAC_DOOR_THK, CAC_AISLE_W, CAC_DOOR_H),
                    matrix=make_matrix(dx_pos, cy, 0.0),
                    predefined_type="USERDEFINED",
                    object_type="ContainmentDoor",
                )

    # 7. Sprinkler Heads (63 ceiling + 16 in-aisle)
    spk_idx = 0
    for gx in [1500.0 + 3000.0 * i for i in range(9)]:
        for gy in [1500.0 + 3000.0 * j for j in range(7)]:
            hx, hy = gx, gy
            # Relocate heads falling inside 750 mm column keep-out (per F-101 Detail 2)
            for cx in COL_GRID_X:
                for cy in COL_GRID_Y:
                    if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                        hy = cy - 900.0
            spk_idx += 1
            assign_product(
                model,
                storey,
                body_ctx,
                ifc_class="IfcFireSuppressionTerminal",
                name=f"SPK-C-{spk_idx:02d}",
                rep=create_cyl_rep(model, body_ctx, 25.0, 25.4),
                matrix=make_matrix(hx, hy, SPRINKLER_DEFLECTOR_Z),
                predefined_type="SPRINKLER",
                object_type="CeilingSprinkler",
                pset_name="Pset_DCM_Sprinkler",
                pset_props={
                    "Type": "Ceiling",
                    "DeflectorElevation_mm": SPRINKLER_DEFLECTOR_Z,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    in_aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12300.0, 14700.0, 17100.0, 18900.0]
    ia_idx = 0
    for tag, cy, _, _ in CAC_DEFS:
        for hx in in_aisle_xs:
            ia_idx += 1
            assign_product(
                model,
                storey,
                body_ctx,
                ifc_class="IfcFireSuppressionTerminal",
                name=f"SPK-A-{ia_idx:02d}",
                rep=create_cyl_rep(model, body_ctx, 25.0, 25.4),
                matrix=make_matrix(hx, cy, IN_AISLE_DEFLECTOR_Z),
                predefined_type="SPRINKLER",
                object_type="InAisleSprinkler",
                pset_name="Pset_DCM_Sprinkler",
                pset_props={
                    "Type": "InAisle",
                    "Containment": tag,
                    "DeflectorElevation_mm": IN_AISLE_DEFLECTOR_Z,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    # -----------------------------------------------------------------------
    # 8. MEP Routing — Three Connected, Clash-Free, Code-Compliant Networks
    # -----------------------------------------------------------------------
    spine_x = 1000.0

    # --- 8A. Power Busway (BW-1) — Overhead tier Z = 3013.5 mm ---
    # Offset Rows C & F by -450 mm in Y to clear the 600x600 columns at Y=8400, 16800
    bw_row_ys = {
        "A": 3000.0,
        "B": 6000.0,
        "C": 7950.0,
        "D": 11400.0,
        "E": 13800.0,
        "F": 16350.0,
    }
    bw_seg = 0
    # Entry feeder
    bw_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
        f"BW-SEG-{bw_seg:02d}", (ENTRY_X, ENTRY_Y, BW_Z), (spine_x, ENTRY_Y, BW_Z),
        BW_W, BW_H, sys_bw, "Power", "Overhead",
    )
    # West spine (South from 9900 to Row A, North from 9900 to Row F)
    bw_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
        f"BW-SEG-{bw_seg:02d}", (spine_x, ENTRY_Y, BW_Z), (spine_x, bw_row_ys["A"], BW_Z),
        BW_W, BW_H, sys_bw, "Power", "Overhead",
    )
    bw_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
        f"BW-SEG-{bw_seg:02d}", (spine_x, ENTRY_Y, BW_Z), (spine_x, bw_row_ys["F"], BW_Z),
        BW_W, BW_H, sys_bw, "Power", "Overhead",
    )
    # Row branches
    for row_id, _, _, _, _ in ROW_SPECS:
        bw_seg += 1
        ry = bw_row_ys[row_id]
        _, rx_max = row_x_extents[row_id]
        add_rect_segment(
            model, storey, body_ctx, "IfcCableSegment", "BUSBARSEGMENT", "BW-1",
            f"BW-SEG-{bw_seg:02d}", (spine_x, ry, BW_Z), (rx_max, ry, BW_Z),
            BW_W, BW_H, sys_bw, "Power", "Overhead",
        )

    # --- 8B. Telecom Cable Tray (CT-1) — Under-floor plenum Z = -186.5 mm ---
    ct_seg = 0
    ct_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
        f"CT-SEG-{ct_seg:02d}", (ENTRY_X, ENTRY_Y, CT_Z), (spine_x, ENTRY_Y, CT_Z),
        CT_W, CT_H, sys_ct, "Telecom", "UnderFloorPlenum",
    )
    ct_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
        f"CT-SEG-{ct_seg:02d}", (spine_x, ENTRY_Y, CT_Z), (spine_x, 3000.0, CT_Z),
        CT_W, CT_H, sys_ct, "Telecom", "UnderFloorPlenum",
    )
    ct_seg += 1
    add_rect_segment(
        model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
        f"CT-SEG-{ct_seg:02d}", (spine_x, ENTRY_Y, CT_Z), (spine_x, 16800.0, CT_Z),
        CT_W, CT_H, sys_ct, "Telecom", "UnderFloorPlenum",
    )
    for row_id, ry, _, _, _ in ROW_SPECS:
        ct_seg += 1
        _, rx_max = row_x_extents[row_id]
        add_rect_segment(
            model, storey, body_ctx, "IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CT-1",
            f"CT-SEG-{ct_seg:02d}", (spine_x, ry, CT_Z), (rx_max, ry, CT_Z),
            CT_W, CT_H, sys_ct, "Telecom", "UnderFloorPlenum",
        )

    # --- 8C. Chilled Water Pipe (CHW-1) — Under-floor plenum Z = -515.85 mm ---
    chw_seg = 0
    chw_seg += 1
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (ENTRY_X, ENTRY_Y, CHW_Z), (spine_x, ENTRY_Y, CHW_Z),
        CHW_OD, sys_chw, "UnderFloorPlenum",
    )
    # Spine South to perimeter CRAH gallery (Y = 450) and North to Row F (Y = 16800)
    chw_seg += 1
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (spine_x, ENTRY_Y, CHW_Z), (spine_x, 450.0, CHW_Z),
        CHW_OD, sys_chw, "UnderFloorPlenum",
    )
    chw_seg += 1
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (spine_x, ENTRY_Y, CHW_Z), (spine_x, 16800.0, CHW_Z),
        CHW_OD, sys_chw, "UnderFloorPlenum",
    )
    # Row branches (serving every row & all 18 in-row CRAHs)
    for row_id, ry, _, _, _ in ROW_SPECS:
        chw_seg += 1
        _, rx_max = row_x_extents[row_id]
        add_pipe_segment(
            model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
            (spine_x, ry, CHW_Z), (rx_max, ry, CHW_Z),
            CHW_OD, sys_chw, "UnderFloorPlenum",
        )
    # Perimeter CRAH gallery header (reaches CRAH-01..04 at X=1200, 9600, 17400, 25800)
    chw_seg += 1
    add_pipe_segment(
        model, storey, body_ctx, f"CHW-SEG-{chw_seg:02d}",
        (spine_x, 450.0, CHW_Z), (25800.0, 450.0, CHW_Z),
        CHW_OD, sys_chw, "UnderFloorPlenum",
    )

    # Write IFC4 file
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(out_file))

    # Optional drawing-note reconciliation log
    recon = {
        "room_mm": {"width": ROOM_W, "depth": ROOM_D, "soffit_z": CEILING_Z, "slab_z": SLAB_Z},
        "clearances_mm": {
            "min_clear_height": MIN_CLEAR_Z,
            "sprinkler_deflector_z": SPRINKLER_DEFLECTOR_Z,
            "sprinkler_standoff": SPRINKLER_STANDOFF,
            "tray_busway_separation_required": 300.0,
            "tray_busway_separation_achieved_z": round(BW_Z - BW_H / 2.0 - (CT_Z + CT_H / 2.0), 1),
            "underfloor_panel_clearance_required": 20.0,
            "underfloor_panel_clearance_achieved": round(-ACCESS_FLOOR_THK - (CT_Z + CT_H / 2.0), 1),
            "pdu_dedicated_space_above": 1800.0,
            "chw_in_pdu_dedicated_space": False,
        },
        "service_tiers_mm": {
            "BW-1": {"zone": "Overhead", "centreline_z": BW_Z, "bottom_z": BW_Z - BW_H / 2.0, "top_z": BW_Z + BW_H / 2.0},
            "CT-1": {"zone": "UnderFloorPlenum", "centreline_z": CT_Z, "bottom_z": CT_Z - CT_H / 2.0, "top_z": CT_Z + CT_H / 2.0},
            "CHW-1": {"zone": "UnderFloorPlenum", "centreline_z": CHW_Z, "bottom_z": CHW_Z - CHW_OD / 2.0, "top_z": CHW_Z + CHW_OD / 2.0},
        },
        "counts": {
            "racks": 128,
            "in_row_crahs": 18,
            "perimeter_crahs": 4,
            "pdus": 6,
            "columns": 6,
            "ceiling_sprinklers": 63,
            "in_aisle_sprinklers": 16,
        },
    }
    recon_path = out_file.parent / "reconciliation.json"
    recon_path.write_text(json.dumps(recon, indent=2))


if __name__ == "__main__":
    build_model(OUT_PATH)
