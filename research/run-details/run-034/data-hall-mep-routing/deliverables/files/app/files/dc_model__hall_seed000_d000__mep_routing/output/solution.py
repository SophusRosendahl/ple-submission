"""Coordinated 3D IFC4 model and clash-free MEP routing for Data Hall 1 (hall_seed000_d000).

Builds the full data hall background (access floor, structural columns, 128 server
cabinets across rows A-F, 4 perimeter + 18 in-row CRAHs, 6 PDUs, cold-aisle
containment CAC-BC and CAC-DE, 63 ceiling + 16 in-aisle sprinkler heads) and routes
three overhead/under-floor MEP services (CT-1 telecom cable tray, BW-1 power busway,
CHW-1 insulated chilled-water pipe) clash-free and code-compliant.

Writes one IFC4 file to sys.argv[1] (default: output/model.ifc) and a drawing-note
reconciliation log to output/reconciliation.json.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Baked-in hall geometry & drawing data (all linear dimensions in millimetres)
# ---------------------------------------------------------------------------

HALL_X = 27000.0
HALL_Y = 21000.0
SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0
FLOOR_BOT_Z = -35.0
FLOOR_TOP_Z = 0.0
SOFFIT_Z = 3600.0
MIN_CLEAR_Z = 2600.0
SPRINKLER_DEFLECTOR_Z = 3574.6   # 25.4 mm below 3600 soffit
SPRINKLER_STANDOFF = 460.0       # clear below deflector -> 3114.6 mm max
IN_AISLE_DEFLECTOR_Z = 1890.0    # 110 mm below 2000 mm containment roof

# Structural grid (centrelines) and column size
COL_XS = [8400.0, 16800.0, 25200.0]
COL_YS = [8400.0, 16800.0]
COL_SIZE = 400.0  # 400 x 400 mm, fits cleanly in Row F 600 mm structural gap

# Row definitions (A-101 & A-601)
# West half starts at x = 1800 (tile D); east half starts at x = 11400 (common east edge of cross aisle).
ROW_WEST_X = 1800.0
ROW_EAST_X = 11400.0
CABINET_DEPTH = 1200.0
CABINET_HEIGHT = 2000.0
BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "GAP": 600.0}

ROW_SPECS: list[dict[str, Any]] = [
    {
        "row": "A",
        "y_center": 3000.0,
        "facing": "SOUTH",
        "seq": [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
                ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    },
    {
        "row": "B",
        "y_center": 6000.0,
        "facing": "NORTH",
        "seq": [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
                ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    },
    {
        "row": "C",
        "y_center": 8400.0,
        "facing": "SOUTH",
        "seq": [("C1", 3), ("CU", 1), ("C1", 6), ("GAP", 2), ("CU", 1),
                ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("GAP", 2), ("C1", 3)],
    },
    {
        "row": "D",
        "y_center": 11400.0,
        "facing": "NORTH",
        "seq": [("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
                ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5)],
    },
    {
        "row": "E",
        "y_center": 13800.0,
        "facing": "SOUTH",
        "seq": [("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
                ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5)],
    },
    {
        "row": "F",
        "y_center": 16800.0,
        "facing": "NORTH",
        "seq": [("C1", 4), ("CU", 1), ("C1", 5), ("GAP", 2), ("CU", 1),
                ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("GAP", 1), ("CU", 1), ("C1", 4)],
    },
]

# Perimeter CRAHs (A-601 & M-101): 1200 W x 900 D x 2000 H, facing NORTH
PERIM_CRAHS: list[dict[str, Any]] = [
    {"tag": "CRAH-01", "x0": 600.0, "y0": 0.0, "w": 1200.0, "d": 900.0, "h": 2000.0, "facing": "NORTH"},
    {"tag": "CRAH-02", "x0": 9000.0, "y0": 0.0, "w": 1200.0, "d": 900.0, "h": 2000.0, "facing": "NORTH"},
    {"tag": "CRAH-03", "x0": 16800.0, "y0": 0.0, "w": 1200.0, "d": 900.0, "h": 2000.0, "facing": "NORTH"},
    {"tag": "CRAH-04", "x0": 25200.0, "y0": 0.0, "w": 1200.0, "d": 900.0, "h": 2000.0, "facing": "NORTH"},
]

# PDUs (A-601 & E-101): 762 W x 813 D x 1959 H, front flush with served row front face
PDU_SPECS: list[dict[str, Any]] = [
    {"tag": "PDU-01", "row": "A", "x0": 21000.0, "y0": 2400.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "SOUTH"},
    {"tag": "PDU-02", "row": "B", "x0": 21600.0, "y0": 5787.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "NORTH"},
    {"tag": "PDU-03", "row": "C", "x0": 21000.0, "y0": 7800.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "SOUTH"},
    {"tag": "PDU-04", "row": "D", "x0": 21600.0, "y0": 11187.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "NORTH"},
    {"tag": "PDU-05", "row": "E", "x0": 21000.0, "y0": 13200.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "SOUTH"},
    {"tag": "PDU-06", "row": "F", "x0": 21600.0, "y0": 16587.0, "w": 762.0, "d": 813.0, "h": 1959.0, "facing": "NORTH"},
]

# Service entry point on West wall (E-101 & M-101)
ENTRY_X = 0.0
ENTRY_Y = 9900.0

# Pathway section dimensions (A-602, E-101, M-101)
CT_W = 683.0
CT_H = 127.0
BW_W = 128.0
BW_H = 147.0
CHW_OD = 168.3  # DN100 (114.3 mm bare OD) + 25.4 mm insulation -> 168.3 mm jacketed OD

# Routing elevations (centreline Z in mm)
CT_Z = -200.0     # Under-floor plenum: z = -263.5..-136.5 (101.5 mm below floor panel underside -35)
BW_Z = 2683.5     # Overhead Tier 1: z = 2610.0..2757.0 (>= 2600 min clear height)
CHW_Z = 2934.15   # Overhead Tier 2: z = 2850.0..3018.3 (93 mm above BW-1, 96.3 mm below 3114.6 standoff)


def build_layout_data() -> dict[str, Any]:
    """Compute exact 3D bounding boxes and metadata for all architectural and MEP elements."""
    racks: list[dict[str, Any]] = []
    inrow_crahs: list[dict[str, Any]] = []
    row_extents: dict[str, dict[str, float]] = {}

    for spec in ROW_SPECS:
        row = spec["row"]
        yc = spec["y_center"]
        y0 = yc - CABINET_DEPTH / 2.0
        facing = spec["facing"]
        x = ROW_WEST_X
        rack_idx = 0
        crah_idx = 0
        west_end = ROW_WEST_X
        for bay_type, count in spec["seq"]:
            if bay_type == "CA":
                west_end = x
                x = ROW_EAST_X
                continue
            w = BAY_WIDTHS[bay_type]
            for _ in range(count):
                if bay_type in ("C1", "N1"):
                    rack_idx += 1
                    racks.append({
                        "tag": f"RACK-{row}{rack_idx:02d}",
                        "row": row,
                        "type": bay_type,
                        "x0": x,
                        "y0": y0,
                        "w": w,
                        "d": CABINET_DEPTH,
                        "h": CABINET_HEIGHT,
                        "facing": facing,
                    })
                elif bay_type == "CU":
                    crah_idx += 1
                    inrow_crahs.append({
                        "tag": f"CRAH-{row}{crah_idx:02d}",
                        "row": row,
                        "x0": x,
                        "y0": y0,
                        "w": w,
                        "d": CABINET_DEPTH,
                        "h": CABINET_HEIGHT,
                        "facing": facing,
                    })
                x += w
        row_extents[row] = {
            "x_start": ROW_WEST_X,
            "west_end": west_end,
            "east_start": ROW_EAST_X,
            "x_end": x,
            "y_center": yc,
        }

    # Structural columns (0 to 3600 mm)
    columns: list[dict[str, Any]] = []
    col_labels_x = ["A", "B", "C"]
    col_labels_y = ["1", "2"]
    for ix, cx in enumerate(COL_XS):
        for iy, cy in enumerate(COL_YS):
            columns.append({
                "tag": f"COL-{col_labels_x[ix]}{col_labels_y[iy]}",
                "cx": cx,
                "cy": cy,
                "w": COL_SIZE,
                "d": COL_SIZE,
                "h": SOFFIT_Z,
            })

    # Cold-aisle containment (CAC-BC and CAC-DE)
    containment: list[dict[str, Any]] = []
    cac_defs = [
        ("CAC-BC", 7200.0, min(row_extents["B"]["west_end"], row_extents["C"]["west_end"]),
         min(row_extents["B"]["x_end"], row_extents["C"]["x_end"])),
        ("CAC-DE", 12600.0, min(row_extents["D"]["west_end"], row_extents["E"]["west_end"]),
         min(row_extents["D"]["x_end"], row_extents["E"]["x_end"])),
    ]
    for tag, yc, w_end, e_end in cac_defs:
        # West & East roof panels (1400 mm wide, 55.5 mm thick, z = 2000..2055.5)
        for side, x0, x1 in [("W", ROW_WEST_X, w_end), ("E", ROW_EAST_X, e_end)]:
            containment.append({
                "tag": f"{tag}-ROOF-{side}",
                "cac": tag,
                "kind": "ROOF",
                "x0": x0,
                "y0": yc - 700.0,
                "z0": 2000.0,
                "w": x1 - x0,
                "d": 1400.0,
                "h": 55.5,
            })
            # End doors (60 mm thick x 1200 mm wide x 2055.5 mm high), flush outside roof ends
            for end_name, dx in [("W", x0 - 60.0), ("E", x1)]:
                containment.append({
                    "tag": f"{tag}-DOOR-{side}{end_name}",
                    "cac": tag,
                    "kind": "DOOR",
                    "x0": dx,
                    "y0": yc - 600.0,
                    "z0": 0.0,
                    "w": 60.0,
                    "d": 1200.0,
                    "h": 2055.5,
                })

    # Sprinkler heads: 63 ceiling + 16 in-aisle (F-101)
    sprinklers: list[dict[str, Any]] = []
    s_idx = 0
    for iy in range(7):
        sy = 1500.0 + iy * 3000.0
        for ix in range(9):
            sx = 1500.0 + ix * 3000.0
            # Relocate clear of 1500 mm column keep-out if needed
            for cx in COL_XS:
                for cy in COL_YS:
                    if abs(sx - cx) < 750.0 and abs(sy - cy) < 750.0:
                        sx = cx - 900.0 if sx <= cx else cx + 900.0
            s_idx += 1
            sprinklers.append({
                "tag": f"SPR-C{s_idx:02d}",
                "kind": "CEILING",
                "x": sx,
                "y": sy,
                "z": SPRINKLER_DEFLECTOR_Z,
            })
    ia_idx = 0
    for yc in (7200.0, 12600.0):
        for sx in (2400.0, 4800.0, 7200.0, 9000.0, 12000.0, 14400.0, 16800.0, 18600.0):
            ia_idx += 1
            sprinklers.append({
                "tag": f"SPR-IA{ia_idx:02d}",
                "kind": "IN-AISLE",
                "x": sx,
                "y": yc,
                "z": IN_AISLE_DEFLECTOR_Z,
            })

    # -----------------------------------------------------------------------
    # MEP Routing — straight axis-aligned segments (x0, y0, z0) -> (x1, y1, z1)
    # -----------------------------------------------------------------------
    # All three services enter at (0, 9900) and form single connected networks.
    # Row header Y offset: y_row - 450 mm clears all 400x400 columns at y_row!
    row_y_mep = {spec["row"]: spec["y_center"] - 450.0 for spec in ROW_SPECS}
    row_x_end = {r: row_extents[r]["x_end"] - 300.0 for r in row_extents}

    mep_segments: list[dict[str, Any]] = []

    def add_seg(service: str, tag: str, p0: tuple[float, float, float], p1: tuple[float, float, float]) -> None:
        mep_segments.append({
            "service": service,
            "tag": tag,
            "p0": p0,
            "p1": p1,
        })

    # 1. Telecom Cable Tray (CT-1) — Under-floor plenum (z = -200.0 mm)
    # Spine at x = 900 mm from y = 2550 (Row A) to y = 16350 (Row F), connected to entry (0, 9900).
    ct_spine_x = 900.0
    add_seg("TELECOM", "CT-ENTRY", (ENTRY_X, ENTRY_Y, CT_Z), (ct_spine_x, ENTRY_Y, CT_Z))
    add_seg("TELECOM", "CT-SPINE-S", (ct_spine_x, ENTRY_Y, CT_Z), (ct_spine_x, row_y_mep["A"], CT_Z))
    add_seg("TELECOM", "CT-SPINE-N", (ct_spine_x, ENTRY_Y, CT_Z), (ct_spine_x, row_y_mep["F"], CT_Z))
    for r in ("A", "B", "C", "D", "E", "F"):
        ry = row_y_mep[r]
        add_seg("TELECOM", f"CT-ROW-{r}", (ct_spine_x, ry, CT_Z), (row_x_end[r], ry, CT_Z))

    # 2. Power Busway (BW-1) — Overhead Tier 1 (z = 2683.5 mm)
    # Spine at x = 600 mm from y = 2550 (Row A) to y = 16350 (Row F), connected to entry (0, 9900).
    bw_spine_x = 600.0
    add_seg("POWER", "BW-ENTRY", (ENTRY_X, ENTRY_Y, BW_Z), (bw_spine_x, ENTRY_Y, BW_Z))
    add_seg("POWER", "BW-SPINE-S", (bw_spine_x, ENTRY_Y, BW_Z), (bw_spine_x, row_y_mep["A"], BW_Z))
    add_seg("POWER", "BW-SPINE-N", (bw_spine_x, ENTRY_Y, BW_Z), (bw_spine_x, row_y_mep["F"], BW_Z))
    for r in ("A", "B", "C", "D", "E", "F"):
        ry = row_y_mep[r]
        add_seg("POWER", f"BW-ROW-{r}", (bw_spine_x, ry, BW_Z), (row_x_end[r], ry, BW_Z))

    # 3. Chilled Water Pipe (CHW-1) — Overhead Tier 2 (z = 2934.15 mm)
    # Spine at x = 600 mm from y = 1200 (Perimeter CRAH header) to y = 16350 (Row F).
    chw_spine_x = 600.0
    perim_y = 1200.0  # 750 mm from CRAH-01..04 centres (y=450), clear of all columns and PDUs
    add_seg("CHW", "CHW-ENTRY", (ENTRY_X, ENTRY_Y, CHW_Z), (chw_spine_x, ENTRY_Y, CHW_Z))
    add_seg("CHW", "CHW-SPINE-S", (chw_spine_x, ENTRY_Y, CHW_Z), (chw_spine_x, perim_y, CHW_Z))
    add_seg("CHW", "CHW-SPINE-N", (chw_spine_x, ENTRY_Y, CHW_Z), (chw_spine_x, row_y_mep["F"], CHW_Z))
    for r in ("A", "B", "C", "D", "E", "F"):
        ry = row_y_mep[r]
        add_seg("CHW", f"CHW-ROW-{r}", (chw_spine_x, ry, CHW_Z), (row_x_end[r], ry, CHW_Z))
    # Perimeter CRAH header reaching CRAH-01 (x=1200) through CRAH-04 (x=25800)
    add_seg("CHW", "CHW-PERIM", (chw_spine_x, perim_y, CHW_Z), (25200.0, perim_y, CHW_Z))

    return {
        "racks": racks,
        "inrow_crahs": inrow_crahs,
        "perim_crahs": PERIM_CRAHS,
        "pdus": PDU_SPECS,
        "columns": columns,
        "containment": containment,
        "sprinklers": sprinklers,
        "mep_segments": mep_segments,
        "row_extents": row_extents,
    }


def _placement_matrix(cx_mm: float, cy_mm: float, z0_mm: float, yaw_rad: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in SI metres (required by ifcopenshell 0.8.4)."""
    c = math.cos(yaw_rad)
    s = math.sin(yaw_rad)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z0_mm / 1000.0
    return m


def _segment_matrix(p0: tuple[float, float, float], p1: tuple[float, float, float]) -> tuple[np.ndarray, float]:
    """Build 4x4 placement matrix (translations in metres) aligning local +Z along p0->p1."""
    v = np.array(p1, dtype=float) - np.array(p0, dtype=float)
    length = float(np.linalg.norm(v))
    if length < 1e-6:
        raise ValueError(f"Zero-length segment: {p0} -> {p1}")
    z_axis = v / length
    # Choose local Y as world +Z when segment is horizontal, else world +Y
    if abs(z_axis[2]) < 0.9:
        y_axis = np.array([0.0, 0.0, 1.0])
    else:
        y_axis = np.array([0.0, 1.0, 0.0])
    x_axis = np.cross(y_axis, z_axis)
    x_axis /= np.linalg.norm(x_axis)
    y_axis = np.cross(z_axis, x_axis)

    m = np.eye(4, dtype=float)
    m[:3, 0] = x_axis
    m[:3, 1] = y_axis
    m[:3, 2] = z_axis
    m[0, 3] = p0[0] / 1000.0
    m[1, 3] = p0[1] / 1000.0
    m[2, 3] = p0[2] / 1000.0
    return m, length


def _add_rect_solid(model: Any, body_ctx: Any, xdim: float, ydim: float, depth: float) -> Any:
    """Create an IFC4 IfcShapeRepresentation with a centered 2D rectangle extruded along +Z."""
    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=float(xdim), YDim=float(ydim))
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, ExtrudedDirection=direction, Depth=float(depth))
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _add_circle_solid(model: Any, body_ctx: Any, radius: float, depth: float) -> Any:
    """Create an IFC4 IfcShapeRepresentation with a 2D circle extruded along +Z."""
    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
    direction = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, ExtrudedDirection=direction, Depth=float(depth))
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def write_reconciliation_log(out_ifc_path: str) -> None:
    """Write optional drawing-note reconciliation log next to the IFC."""
    rec_path = Path(out_ifc_path).parent / "reconciliation.json"
    notes = {
        "hall_dimensions_mm": {"x": HALL_X, "y": HALL_Y, "soffit_z": SOFFIT_Z, "slab_top_z": SLAB_TOP_Z},
        "access_floor_mm": {"thickness": FLOOR_THK, "top_z": FLOOR_TOP_Z, "under_panel_clear": 20.0},
        "clear_height_mm": MIN_CLEAR_Z,
        "sprinkler_mm": {
            "ceiling_deflector_z": SPRINKLER_DEFLECTOR_Z,
            "standoff_clear": SPRINKLER_STANDOFF,
            "max_overhead_top_z": SPRINKLER_DEFLECTOR_Z - SPRINKLER_STANDOFF,
            "in_aisle_deflector_z": IN_AISLE_DEFLECTOR_Z,
        },
        "pathways_mm": {
            "CT-1": {"width": CT_W, "height": CT_H, "zone": "UNDERFLOOR", "center_z": CT_Z},
            "BW-1": {"width": BW_W, "height": BW_H, "zone": "OVERHEAD", "center_z": BW_Z, "max_support_spacing": 1500.0},
            "CHW-1": {"bare_od": 114.3, "insulated_od": CHW_OD, "zone": "OVERHEAD", "center_z": CHW_Z},
        },
        "separations_mm": {
            "tray_to_busway_min": 300.0,
            "tray_to_busway_achieved": round((BW_Z - BW_H / 2.0) - (CT_Z + CT_H / 2.0), 1),
            "pdu_dedicated_space_height": 1800.0,
            "chw_over_pdu": False,
        },
    }
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    rec_path.write_text(json.dumps(notes, indent=2) + "\n", encoding="utf-8")


def build_ifc(out_path: str) -> None:
    import ifcopenshell
    import ifcopenshell.api.aggregate
    import ifcopenshell.api.context
    import ifcopenshell.api.geometry
    import ifcopenshell.api.project
    import ifcopenshell.api.pset
    import ifcopenshell.api.root
    import ifcopenshell.api.spatial
    import ifcopenshell.api.unit

    data = build_layout_data()

    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Data Hall 1")
    ifcopenshell.api.unit.assign_unit(model, length={"is_metric": True, "raw": "MILLIMETRE"})

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = ifcopenshell.api.root.create_entity(model, ifc_class="IfcBuildingStorey", name="Level 00")
    storey.Elevation = 0.0

    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    def add_pset(elem: Any, pset_name: str, props: dict[str, Any]) -> None:
        pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=pset_name)
        ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)

    def place_box(
        ifc_class: str,
        name: str,
        predefined_type: str | None,
        object_type: str | None,
        cx: float,
        cy: float,
        z0: float,
        w: float,
        d: float,
        h: float,
        yaw_rad: float = 0.0,
    ) -> Any:
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class=ifc_class,
            name=name,
            predefined_type=predefined_type,
        )
        if object_type is not None:
            elem.ObjectType = object_type
        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[elem])
        rep = _add_rect_solid(model, body_ctx, w, d, h)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=elem, matrix=_placement_matrix(cx, cy, z0, yaw_rad)
        )
        return elem

    # 1. Access floor panel (z = -35..0)
    place_box(
        "IfcSlab", "AccessFloor", "FLOOR", "AccessFloor",
        HALL_X / 2.0, HALL_Y / 2.0, FLOOR_BOT_Z, HALL_X, HALL_Y, FLOOR_THK,
    )

    # 2. Structural columns (z = 0..3600)
    for col in data["columns"]:
        place_box(
            "IfcColumn", col["tag"], "COLUMN", "StructuralColumn",
            col["cx"], col["cy"], 0.0, col["w"], col["d"], col["h"],
        )

    # 3. Server cabinets (128 racks)
    for r in data["racks"]:
        yaw = 0.0 if r["facing"] == "NORTH" else math.pi
        elem = place_box(
            "IfcFurniture", r["tag"], "USERDEFINED", "Rack",
            r["x0"] + r["w"] / 2.0, r["y0"] + r["d"] / 2.0, 0.0,
            r["w"], r["d"], r["h"], yaw,
        )
        add_pset(elem, "Pset_DCM_Rack", {
            "Tag": r["tag"],
            "Row": r["row"],
            "CabinetType": r["type"],
            "RU": 42,
            "Width_mm": r["w"],
            "Depth_mm": r["d"],
            "Height_mm": r["h"],
            "Facing": r["facing"],
            "Power_kW": 8.0,
            "Load_kg": 1363.0,
        })

    # 4. Perimeter & in-row CRAH units
    for c in data["perim_crahs"]:
        yaw = 0.0 if c["facing"] == "NORTH" else math.pi
        elem = place_box(
            "IfcUnitaryEquipment", c["tag"], "AIRCONDITIONINGUNIT", "CRAH",
            c["x0"] + c["w"] / 2.0, c["y0"] + c["d"] / 2.0, 0.0,
            c["w"], c["d"], c["h"], yaw,
        )
        add_pset(elem, "Pset_DCM_CRAH", {
            "Tag": c["tag"],
            "Placement": "PERIMETER",
            "Capacity_kW": 100.0,
            "Airflow_m3h": 20000.0,
            "Facing": c["facing"],
            "Service": "CHILLED WATER, DN100",
        })
    for c in data["inrow_crahs"]:
        yaw = 0.0 if c["facing"] == "NORTH" else math.pi
        elem = place_box(
            "IfcUnitaryEquipment", c["tag"], "AIRCONDITIONINGUNIT", "CRAH",
            c["x0"] + c["w"] / 2.0, c["y0"] + c["d"] / 2.0, 0.0,
            c["w"], c["d"], c["h"], yaw,
        )
        add_pset(elem, "Pset_DCM_CRAH", {
            "Tag": c["tag"],
            "Placement": "IN-ROW",
            "Row": c["row"],
            "Capacity_kW": 50.0,
            "Airflow_m3h": 9000.0,
            "Facing": c["facing"],
            "Service": "CHILLED WATER, DN50",
        })

    # 5. PDUs
    for p in data["pdus"]:
        yaw = 0.0 if p["facing"] == "NORTH" else math.pi
        elem = place_box(
            "IfcElectricDistributionBoard", p["tag"], "DISTRIBUTIONBOARD", "PDU",
            p["x0"] + p["w"] / 2.0, p["y0"] + p["d"] / 2.0, 0.0,
            p["w"], p["d"], p["h"], yaw,
        )
        add_pset(elem, "Pset_DCM_PDU", {
            "Tag": p["tag"],
            "ServesRow": p["row"],
            "Rating_kVA": 225.0,
            "Facing": p["facing"],
            "WorkingSpace_mm": 900.0,
        })

    # 6. Cold-aisle containment
    for cac in data["containment"]:
        obj_type = "ContainmentRoof" if cac["kind"] == "ROOF" else "ContainmentDoor"
        elem = place_box(
            "IfcBuildingElementProxy", cac["tag"], "USERDEFINED", obj_type,
            cac["x0"] + cac["w"] / 2.0, cac["y0"] + cac["d"] / 2.0, cac["z0"],
            cac["w"], cac["d"], cac["h"],
        )
        add_pset(elem, "Pset_DCM_Containment", {
            "Tag": cac["cac"],
            "Component": cac["kind"],
        })

    # 7. Sprinkler heads (63 ceiling + 16 in-aisle)
    for sp in data["sprinklers"]:
        elem = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcFireSuppressionTerminal",
            name=sp["tag"],
            predefined_type="SPRINKLER",
        )
        elem.ObjectType = "SprinklerHead"
        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[elem])
        rep = _add_circle_solid(model, body_ctx, 25.0, 25.4)
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=elem, matrix=_placement_matrix(sp["x"], sp["y"], sp["z"], 0.0)
        )
        add_pset(elem, "Pset_DCM_Sprinkler", {
            "Tag": sp["tag"],
            "LocationType": sp["kind"],
            "DeflectorElevation_mm": sp["z"],
            "Standoff_mm": SPRINKLER_STANDOFF,
        })

    # 8. MEP routed segments
    for seg in data["mep_segments"]:
        svc = seg["service"]
        m, length = _segment_matrix(seg["p0"], seg["p1"])
        z_mid = 0.5 * (seg["p0"][2] + seg["p1"][2])
        if svc == "TELECOM":
            elem = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcCableCarrierSegment", name=seg["tag"], predefined_type="CABLETRAYSEGMENT"
            )
            elem.ObjectType = "CableTray"
            rep = _add_rect_solid(model, body_ctx, CT_W, CT_H, length)
            props = {"Service": "TELECOM", "Tag": "CT-1", "Zone": "UNDERFLOOR", "Elevation_mm": z_mid, "Width_mm": CT_W, "Height_mm": CT_H}
        elif svc == "POWER":
            elem = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcCableSegment", name=seg["tag"], predefined_type="BUSBARSEGMENT"
            )
            elem.ObjectType = "Busway"
            rep = _add_rect_solid(model, body_ctx, BW_W, BW_H, length)
            props = {"Service": "POWER", "Tag": "BW-1", "Zone": "OVERHEAD", "Elevation_mm": z_mid, "Width_mm": BW_W, "Height_mm": BW_H}
        else:
            elem = ifcopenshell.api.root.create_entity(
                model, ifc_class="IfcPipeSegment", name=seg["tag"], predefined_type="RIGIDSEGMENT"
            )
            elem.ObjectType = "CHWPipe"
            rep = _add_circle_solid(model, body_ctx, CHW_OD / 2.0, length)
            props = {"Service": "CHW", "Tag": "CHW-1", "Zone": "OVERHEAD", "Elevation_mm": z_mid, "OD_mm": CHW_OD}

        ifcopenshell.api.spatial.assign_container(model, relating_structure=storey, products=[elem])
        ifcopenshell.api.geometry.assign_representation(model, product=elem, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(model, product=elem, matrix=m)
        add_pset(elem, "Pset_DCM_MEP", props)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    model.write(out_path)
    write_reconciliation_log(out_path)


if __name__ == "__main__":
    out_ifc = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "model.ifc")
    build_ifc(out_ifc)
