"""IFC4 Data Hall Background & Overhead MEP Routing Generator.

IMPORTANT TRANSPARENCY NOTICE
=============================
This script was authored in a text-only environment where the seven input PNG
drawing sheets (input/A-101.png, A-301.png, A-601.png, A-602.png, E-101.png,
F-101.png, M-101.png) were omitted from the context ("image: not included as
text") and could not be inspected.

Accordingly:
- All hall dimensions, structural grid coordinates, cabinet/CRAH/PDU positions
  and facings, ceiling/plenum elevations, containment geometry, sprinkler
  locations, pathway dimensions, and service entry points in ``DRAWING_DATA``
  below are PROVISIONAL placeholders for a ~27 x 21 m, 128-cabinet data hall.
- They are isolated in a single top-level ``DRAWING_DATA`` dictionary so that
  once the seven drawing sheets are visually read, every literal can be
  transcribed 1:1 without changing the IFC4 modelling or verification logic.
- All code constraints stated in the task text (IFC4 schema via
  ifcopenshell==0.8.4 + numpy, mm project units with metre placement
  translations, 2D profile points, 0 hard clashes > 2 mm, full network
  connectivity, >=80% row coverage within 2500 mm, CHW within 2500 mm of every
  CRAH, >=2600 mm headroom, >=460 mm clear below sprinkler deflectors, >=300 mm
  tray-busway separation, 1800 mm dedicated zone above PDUs, 25.4 mm CHW pipe
  insulation) are strictly enforced and verified on the generated geometry.

Usage:
    python output/solution.py [output/model.ifc]
"""

from __future__ import annotations

import math
import os
import sys
import uuid
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.guid


# ---------------------------------------------------------------------------
# Deterministic GUID helper
# ---------------------------------------------------------------------------
_GUID_NS = uuid.UUID("7f3c9d1a-4b2e-4f10-9a8c-000000000000")


def det_guid(key: str) -> str:
    """Return a deterministic 22-char IFC4 GlobalId for a given logical key."""
    return ifcopenshell.guid.compress(uuid.uuid5(_GUID_NS, key).hex)


# ---------------------------------------------------------------------------
# PROVISIONAL DRAWING DATA (replace literals after reading A-101..F-101 PNGs)
# All linear dimensions are in millimetres (mm); FFL = 0.0 mm.
# ---------------------------------------------------------------------------
DRAWING_DATA = {
    "status": "PROVISIONAL_UNVERIFIED_PNGS_UNAVAILABLE",
    "hall": {
        "length_x": 27000.0,
        "width_y": 21000.0,
        "tile_pitch": 600.0,
        "wall_thickness": 200.0,
        "subfloor_top_z": -600.0,
        "subfloor_thickness": 250.0,
        "access_floor_thickness": 40.0,  # z in [-40, 0]
        "clear_height_z": 4500.0,        # underside of roof slab
        "roof_slab_thickness": 250.0,    # z in [4500, 4750]
    },
    # Structural columns: full height from subfloor_top_z to clear_height_z
    "columns": {
        "size_x": 500.0,
        "size_y": 500.0,
        "x_coords": [2100.0, 13500.0, 24900.0],
        "y_coords": [3600.0, 10500.0, 17400.0],
    },
    # 128 cabinets = 8 rows x 16 cabinets/row (2 pods x 4 row bands)
    # Local cabinet convention: width along local X (600), depth along local Y (1200),
    # intake/front face = local +Y. yaw_deg=0 -> faces +Y; yaw_deg=180 -> faces -Y.
    "cabinets": {
        "width_x": 600.0,
        "depth_y": 1200.0,
        "height_z": 2200.0,
        "racks_per_row": 16,
        "pods": [
            {"id": "W", "x_start": 3000.0},
            {"id": "E", "x_start": 14400.0},
        ],
        "row_bands": [
            {"id": "A", "y_center": 4800.0, "yaw_deg": 0.0, "aisle": "CA1"},
            {"id": "B", "y_center": 8400.0, "yaw_deg": 180.0, "aisle": "CA1"},
            {"id": "C", "y_center": 12600.0, "yaw_deg": 0.0, "aisle": "CA2"},
            {"id": "D", "y_center": 16200.0, "yaw_deg": 180.0, "aisle": "CA2"},
        ],
    },
    # Cold Aisle Containment (4 enclosed cold aisles)
    "containment": {
        "roof_z_bottom": 2200.0,
        "roof_thickness": 50.0,
        "door_thickness": 40.0,
        "aisles": [
            {"id": "CA1-W", "x1": 3000.0, "x2": 12600.0, "y1": 5400.0, "y2": 7800.0},
            {"id": "CA1-E", "x1": 14400.0, "x2": 24000.0, "y1": 5400.0, "y2": 7800.0},
            {"id": "CA2-W", "x1": 3000.0, "x2": 12600.0, "y1": 13200.0, "y2": 15600.0},
            {"id": "CA2-E", "x1": 14400.0, "x2": 24000.0, "y1": 13200.0, "y2": 15600.0},
        ],
    },
    # CRAH units (including East & West perimeter units not on a row header)
    # Local front = +Y; yaw=0 faces +Y, 180 faces -Y, -90 faces +X, +90 faces -X.
    "crahs": {
        "width_x": 2400.0,
        "depth_y": 1000.0,
        "height_z": 2200.0,
        "units": [
            {"id": "CRAH-S1", "cx": 5400.0,  "cy": 800.0,   "yaw_deg": 0.0},
            {"id": "CRAH-S2", "cx": 10200.0, "cy": 800.0,   "yaw_deg": 0.0},
            {"id": "CRAH-S3", "cx": 16800.0, "cy": 800.0,   "yaw_deg": 0.0},
            {"id": "CRAH-N1", "cx": 5400.0,  "cy": 20200.0, "yaw_deg": 180.0},
            {"id": "CRAH-N2", "cx": 10200.0, "cy": 20200.0, "yaw_deg": 180.0},
            {"id": "CRAH-N3", "cx": 16800.0, "cy": 20200.0, "yaw_deg": 180.0},
            {"id": "CRAH-W1", "cx": 800.0,   "cy": 10500.0, "yaw_deg": -90.0},
            {"id": "CRAH-E1", "cx": 26200.0, "cy": 10500.0, "yaw_deg": 90.0},
        ],
    },
    # PDUs (1800 mm dedicated electrical space above top -> z in [2100, 3900])
    "pdus": {
        "width_x": 1200.0,
        "depth_y": 1000.0,
        "height_z": 2100.0,
        "dedicated_space_above": 1800.0,
        "units": [
            {"id": "PDU-SW", "cx": 1200.0,  "cy": 800.0,   "yaw_deg": 0.0},
            {"id": "PDU-SE", "cx": 21600.0, "cy": 800.0,   "yaw_deg": 0.0},
            {"id": "PDU-NW", "cx": 1200.0,  "cy": 20200.0, "yaw_deg": 180.0},
            {"id": "PDU-NE", "cx": 21600.0, "cy": 20200.0, "yaw_deg": 180.0},
        ],
    },
    # Sprinkler heads (ceiling grid + required sub-containment-roof heads)
    "sprinklers": {
        "head_diameter": 80.0,
        "ceiling_deflector_z": 4350.0,
        "ceiling_top_z": 4500.0,
        "ceiling_x": [1800.0, 5400.0, 9000.0, 12600.0, 16200.0, 19800.0, 23400.0, 26100.0],
        "ceiling_y": [2100.0, 5700.0, 9300.0, 12900.0, 16500.0, 19800.0],
        "sub_containment_deflector_z": 2120.0,
        "sub_containment_top_z": 2200.0,
        "sub_containment_x_west": [4600.0, 7800.0, 11000.0],
        "sub_containment_x_east": [16000.0, 19200.0, 22400.0],
        "sub_containment_y": [6600.0, 14400.0],
    },
    # Overhead MEP service parameters & tiers (all above 2600 mm headroom,
    # all below 4350 - 460 = 3890 mm ceiling sprinkler clear zone)
    "mep": {
        "busway": {
            "width": 150.0,
            "height": 120.0,
            "z_center": 2860.0,  # z in [2800, 2920]
            "entry": (21600.0, 0.0, 2860.0),
        },
        "cable_tray": {
            "width": 450.0,      # <= 1200 mm -> no sub-tray sprinklers required
            "height": 100.0,
            "z_center": 3370.0,  # z in [3320, 3420]; 400 mm clear above busway
            "entry": (12900.0, 21000.0, 3370.0),
        },
        "chilled_water": {
            "bare_od": 168.3,            # DN150 nominal OD
            "insulation_thickness": 25.4,
            "insulated_od": 219.1,       # 168.3 + 2 * 25.4
            "z_center": 3700.0,          # z in [3590.45, 3809.55]; 540.45 mm clear below sprinklers
            "entry": (14100.0, 0.0, 3700.0),
        },
    },
    # Code compliance thresholds
    "code": {
        "clash_tol_mm": 2.0,
        "min_headroom_mm": 2600.0,
        "sprinkler_clear_below_mm": 460.0,
        "tray_busway_sep_mm": 300.0,
        "row_service_dist_mm": 2500.0,
        "row_coverage_min": 0.80,
        "crah_service_dist_mm": 2500.0,
    },
}


# ---------------------------------------------------------------------------
# Geometry & IFC4 creation helpers
# ---------------------------------------------------------------------------
def _make_2d_origin(model: ifcopenshell.file):
    pt = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0))
    ref = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0))
    return model.create_entity("IfcAxis2Placement2D", Location=pt, RefDirection=ref)


def _make_3d_pos(model: ifcopenshell.file, ox: float = 0.0, oy: float = 0.0, oz: float = 0.0):
    pt = model.create_entity("IfcCartesianPoint", Coordinates=(float(ox), float(oy), float(oz)))
    dz = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    dx = model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    return model.create_entity("IfcAxis2Placement3D", Location=pt, Axis=dz, RefDirection=dx)


def make_rect_solid(
    model: ifcopenshell.file,
    x_dim: float,
    y_dim: float,
    depth: float,
    ox: float = 0.0,
    oy: float = 0.0,
    oz: float = 0.0,
):
    """Create a centered rectangular IfcExtrudedAreaSolid using 2D profile points."""
    profile = model.create_entity(
        "IfcRectangleProfileDef",
        ProfileType="AREA",
        Position=_make_2d_origin(model),
        XDim=float(x_dim),
        YDim=float(y_dim),
    )
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    return model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=_make_3d_pos(model, ox, oy, oz),
        ExtrudedDirection=extrude_dir,
        Depth=float(depth),
    )


def make_circle_solid(
    model: ifcopenshell.file,
    radius: float,
    depth: float,
    ox: float = 0.0,
    oy: float = 0.0,
    oz: float = 0.0,
):
    """Create a circular IfcExtrudedAreaSolid using 2D profile points."""
    profile = model.create_entity(
        "IfcCircleProfileDef",
        ProfileType="AREA",
        Position=_make_2d_origin(model),
        Radius=float(radius),
    )
    extrude_dir = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    return model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=_make_3d_pos(model, ox, oy, oz),
        ExtrudedDirection=extrude_dir,
        Depth=float(depth),
    )


def assign_swept_rep(model: ifcopenshell.file, ctx_body, product, solids: Sequence):
    rep = model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=ctx_body,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=list(solids),
    )
    ifcopenshell.api.run("geometry.assign_representation", model, product=product, representation=rep)


def placement_matrix_yaw(cx_mm: float, cy_mm: float, z0_mm: float, yaw_deg: float = 0.0) -> np.ndarray:
    """4x4 placement matrix rotating about footprint centre; translations in METRES."""
    t = math.radians(yaw_deg)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4, dtype=float)
    m[0, 0], m[0, 1] = c, -s
    m[1, 0], m[1, 1] = s, c
    m[0, 3] = float(cx_mm) / 1000.0
    m[1, 3] = float(cy_mm) / 1000.0
    m[2, 3] = float(z0_mm) / 1000.0
    return m


def segment_matrix_length_aabb(
    p1: Tuple[float, float, float],
    p2: Tuple[float, float, float],
    width: float,
    height: float,
) -> Tuple[np.ndarray, float, Tuple[float, float, float, float, float, float]]:
    """Return (4x4 placement matrix [m], length [mm], world AABB [mm]) for an axis-aligned segment."""
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    dx, dy, dz = x2 - x1, y2 - y1, z2 - z1
    nz = sum(abs(d) > 1e-6 for d in (dx, dy, dz))
    if nz != 1:
        raise ValueError(f"Segment must be strictly axis-aligned with positive length: {p1} -> {p2}")

    # Normalize direction to positive axis
    if dx < 0 or dy < 0 or dz < 0:
        x1, y1, z1, x2, y2, z2 = x2, y2, z2, x1, y1, z1
        dx, dy, dz = -dx, -dy, -dz

    m = np.eye(4, dtype=float)
    if dx > 0:
        length = dx
        # local +X -> +Y (width), local +Y -> +Z (height), local +Z -> +X (length)
        m[:3, :3] = np.array([
            [0.0, 0.0, 1.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ])
        aabb = (x1, y1 - width / 2.0, z1 - height / 2.0, x2, y1 + width / 2.0, z1 + height / 2.0)
    elif dy > 0:
        length = dy
        # local +X -> -X (width), local +Y -> +Z (height), local +Z -> +Y (length)
        m[:3, :3] = np.array([
            [-1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 1.0, 0.0],
        ])
        aabb = (x1 - width / 2.0, y1, z1 - height / 2.0, x1 + width / 2.0, y2, z1 + height / 2.0)
    else:
        length = dz
        m[:3, :3] = np.eye(3)
        aabb = (x1 - width / 2.0, y1 - height / 2.0, z1, x1 + width / 2.0, y1 + height / 2.0, z2)

    m[0, 3] = float(x1) / 1000.0
    m[1, 3] = float(y1) / 1000.0
    m[2, 3] = float(z1) / 1000.0
    return m, float(length), aabb


def box_aabb(cx: float, cy: float, z0: float, wx: float, dy: float, hz: float, yaw_deg: float = 0.0):
    """Exact world AABB for a box rotated by an integer multiple of 90 deg about footprint centre."""
    a = abs(yaw_deg) % 180.0
    if abs(a - 90.0) < 1e-6:
        sx, sy = dy, wx
    else:
        sx, sy = wx, dy
    return (cx - sx / 2.0, cy - sy / 2.0, z0, cx + sx / 2.0, cy + sy / 2.0, z0 + hz)


def add_pset(model: ifcopenshell.file, product, name: str, props: Dict[str, object]):
    pset = ifcopenshell.api.run("pset.add_pset", model, product=product, name=name)
    pset.GlobalId = det_guid(f"pset:{product.GlobalId}:{name}")
    clean = {}
    for k, v in props.items():
        if isinstance(v, (bool, np.bool_)):
            clean[k] = bool(v)
        elif isinstance(v, (int, np.integer)):
            clean[k] = int(v)
        elif isinstance(v, (float, np.floating)):
            clean[k] = float(v)
        else:
            clean[k] = str(v)
    ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties=clean)


def create_element(
    model: ifcopenshell.file,
    ifc_class: str,
    name: str,
    guid_key: str,
    predefined_type: Optional[str] = None,
    object_type: Optional[str] = None,
):
    kwargs = {"ifc_class": ifc_class, "name": name}
    if predefined_type is not None:
        kwargs["predefined_type"] = predefined_type
    elem = ifcopenshell.api.run("root.create_entity", model, **kwargs)
    elem.GlobalId = det_guid(guid_key)
    if object_type is not None:
        elem.ObjectType = object_type
    return elem


# ---------------------------------------------------------------------------
# Overhead MEP route definitions (axis-aligned, 0-overlap at tees & elbows)
# ---------------------------------------------------------------------------
def build_mep_routes(cfg: dict) -> Dict[str, List[dict]]:
    """Construct axis-aligned, clash-free, single-connected-network segment lists."""
    routes: Dict[str, List[dict]] = {"chilled_water": [], "cable_tray": [], "busway": []}

    # 1. Chilled Water (Tier 3: z = 3700 mm, insulated OD = 219.1 mm, R = 109.55 mm)
    chw = cfg["mep"]["chilled_water"]
    z_chw = chw["z_center"]
    r_chw = chw["insulated_od"] / 2.0
    x_chw = 14100.0  # East side of center aisle (240 mm clear of center columns)

    chw_segs = [
        ("CHW-MAIN-NS",      (x_chw, 0.0, z_chw),                (x_chw, 18900.0 + r_chw, z_chw)),
        ("CHW-SCRAH-W",      (5400.0, 2100.0, z_chw),            (x_chw - r_chw, 2100.0, z_chw)),
        ("CHW-SCRAH-E",      (x_chw + r_chw, 2100.0, z_chw),     (16800.0, 2100.0, z_chw)),
        ("CHW-CA1-W",        (3300.0, 6600.0, z_chw),            (x_chw - r_chw, 6600.0, z_chw)),
        ("CHW-CA1-E",        (x_chw + r_chw, 6600.0, z_chw),     (23700.0, 6600.0, z_chw)),
        ("CHW-PERIM-CRAH-W", (1200.0, 11300.0, z_chw),           (x_chw - r_chw, 11300.0, z_chw)),
        ("CHW-PERIM-CRAH-E", (x_chw + r_chw, 11300.0, z_chw),    (25800.0, 11300.0, z_chw)),
        ("CHW-CA2-W",        (3300.0, 14400.0, z_chw),           (x_chw - r_chw, 14400.0, z_chw)),
        ("CHW-CA2-E",        (x_chw + r_chw, 14400.0, z_chw),    (23700.0, 14400.0, z_chw)),
        ("CHW-NCRAH-W",      (5400.0, 18900.0, z_chw),           (x_chw - r_chw, 18900.0, z_chw)),
        ("CHW-NCRAH-E",      (x_chw + r_chw, 18900.0, z_chw),    (16800.0, 18900.0, z_chw)),
    ]
    for seg_id, p1, p2 in chw_segs:
        routes["chilled_water"].append({"id": seg_id, "p1": p1, "p2": p2})

    # 2. Telecom Cable Tray (Tier 2: z = 3370 mm, 450 x 100 mm, half-W = 225 mm)
    tray = cfg["mep"]["cable_tray"]
    z_tr = tray["z_center"]
    hw_tr = tray["width"] / 2.0
    x_tr = 12900.0  # West side of center aisle (125 mm clear of center columns)

    tray_segs = [
        ("TRAY-MAIN-NS", (x_tr, 6600.0 - hw_tr, z_tr),   (x_tr, 21000.0, z_tr)),
        ("TRAY-CA1-W",   (3300.0, 6600.0, z_tr),         (x_tr - hw_tr, 6600.0, z_tr)),
        ("TRAY-CA1-E",   (x_tr + hw_tr, 6600.0, z_tr),   (23700.0, 6600.0, z_tr)),
        ("TRAY-CA2-W",   (3300.0, 14400.0, z_tr),        (x_tr - hw_tr, 14400.0, z_tr)),
        ("TRAY-CA2-E",   (x_tr + hw_tr, 14400.0, z_tr),  (23700.0, 14400.0, z_tr)),
    ]
    for seg_id, p1, p2 in tray_segs:
        routes["cable_tray"].append({"id": seg_id, "p1": p1, "p2": p2})

    # 3. Power Busway (Tier 1: z = 2860 mm, 150 x 120 mm, half-W = 75 mm)
    bus = cfg["mep"]["busway"]
    z_bu = bus["z_center"]
    hw_bu = bus["width"] / 2.0
    x_bu = 14100.0  # East side of center aisle (275 mm clear of center columns)

    bus_segs = [
        ("BUS-ENTRY-NS", (21600.0, 0.0, z_bu),             (21600.0, 2400.0 + hw_bu, z_bu)),
        ("BUS-ENTRY-EW", (x_bu + hw_bu, 2400.0, z_bu),     (21600.0 - hw_bu, 2400.0, z_bu)),
        ("BUS-MAIN-NS",  (x_bu, 2400.0 - hw_bu, z_bu),     (x_bu, 16200.0 + hw_bu, z_bu)),
        ("BUS-ROWA-W",   (3300.0, 4800.0, z_bu),           (x_bu - hw_bu, 4800.0, z_bu)),
        ("BUS-ROWA-E",   (x_bu + hw_bu, 4800.0, z_bu),     (23700.0, 4800.0, z_bu)),
        ("BUS-ROWB-W",   (3300.0, 8400.0, z_bu),           (x_bu - hw_bu, 8400.0, z_bu)),
        ("BUS-ROWB-E",   (x_bu + hw_bu, 8400.0, z_bu),     (23700.0, 8400.0, z_bu)),
        ("BUS-ROWC-W",   (3300.0, 12600.0, z_bu),          (x_bu - hw_bu, 12600.0, z_bu)),
        ("BUS-ROWC-E",   (x_bu + hw_bu, 12600.0, z_bu),    (23700.0, 12600.0, z_bu)),
        ("BUS-ROWD-W",   (3300.0, 16200.0, z_bu),          (x_bu - hw_bu, 16200.0, z_bu)),
        ("BUS-ROWD-E",   (x_bu + hw_bu, 16200.0, z_bu),    (23700.0, 16200.0, z_bu)),
    ]
    for seg_id, p1, p2 in bus_segs:
        routes["busway"].append({"id": seg_id, "p1": p1, "p2": p2})

    return routes


# ---------------------------------------------------------------------------
# Mechanical self-check (clashes, connectivity, coverage, code clearances)
# ---------------------------------------------------------------------------
def _aabb_overlap(a, b) -> Tuple[float, float, float]:
    ox = min(a[3], b[3]) - max(a[0], b[0])
    oy = min(a[4], b[4]) - max(a[1], b[1])
    oz = min(a[5], b[5]) - max(a[2], b[2])
    return ox, oy, oz


def _aabb_min_dist(a, b) -> float:
    dx = max(0.0, max(a[0] - b[3], b[0] - a[3]))
    dy = max(0.0, max(a[1] - b[4], b[1] - a[4]))
    dz = max(0.0, max(a[2] - b[5], b[2] - a[5]))
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def verify_model(
    cfg: dict,
    solids_registry: List[Tuple[str, str, Tuple[float, float, float, float, float, float]]],
    mep_aabbs: Dict[str, List[Tuple[str, Tuple[float, float, float, float, float, float], dict]]],
    row_extents: List[dict],
) -> dict:
    tol = cfg["code"]["clash_tol_mm"]

    # 1. Hard clash check across ALL placed solid pairs
    clashes = []
    n = len(solids_registry)
    for i in range(n):
        n1, c1, a = solids_registry[i]
        for j in range(i + 1, n):
            n2, c2, b = solids_registry[j]
            ox, oy, oz = _aabb_overlap(a, b)
            if ox > tol and oy > tol and oz > tol:
                clashes.append((n1, n2, round(ox, 2), round(oy, 2), round(oz, 2)))

    # 2. Service connectivity (BFS on touching AABBs, gap <= 1.0 mm) + entry reach
    connectivity = {}
    for svc, items in mep_aabbs.items():
        adj = {k: set() for k in range(len(items))}
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if _aabb_min_dist(items[i][1], items[j][1]) <= 1.0:
                    adj[i].add(j)
                    adj[j].add(i)
        visited = set()
        stack = [0] if items else []
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            stack.extend(adj[cur] - visited)
        entry = cfg["mep"][svc]["entry"]
        entry_box = (entry[0], entry[1], entry[2], entry[0], entry[1], entry[2])
        entry_dist = min(_aabb_min_dist(it[1], entry_box) for it in items)
        connectivity[svc] = {
            "connected_count": len(visited),
            "total_segments": len(items),
            "is_single_network": len(visited) == len(items),
            "entry_distance_mm": round(entry_dist, 2),
        }

    # 3. Code clearances
    min_headroom = min(
        a[2] for items in mep_aabbs.values() for _, a, _ in items
    )
    ceiling_deflector_z = cfg["sprinklers"]["ceiling_deflector_z"]
    min_sprinkler_clr = min(
        ceiling_deflector_z - a[5]
        for items in mep_aabbs.values()
        for _, a, _ in items
    )

    # Tray-busway separation (minimum over all pairs of max-axis clear gap)
    min_tray_bus_sep = float("inf")
    for _, ta, _ in mep_aabbs["cable_tray"]:
        for _, ba, _ in mep_aabbs["busway"]:
            gx = max(0.0, max(ta[0] - ba[3], ba[0] - ta[3]))
            gy = max(0.0, max(ta[1] - ba[4], ba[1] - ta[4]))
            gz = max(0.0, max(ta[2] - ba[5], ba[2] - ta[5]))
            min_tray_bus_sep = min(min_tray_bus_sep, max(gx, gy, gz))

    # CHW vs PDU dedicated space (1800 mm above PDU top)
    pdu_cfg = cfg["pdus"]
    pdu_chw_violations = 0
    for u in pdu_cfg["units"]:
        p_zone = box_aabb(
            u["cx"],
            u["cy"],
            pdu_cfg["height_z"],
            pdu_cfg["width_x"],
            pdu_cfg["depth_y"],
            pdu_cfg["dedicated_space_above"],
            u["yaw_deg"],
        )
        for _, ca, _ in mep_aabbs["chilled_water"]:
            ox, oy, oz = _aabb_overlap(p_zone, ca)
            if ox > 0.0 and oy > 0.0 and oz > 0.0:
                pdu_chw_violations += 1

    # Row coverage (>= 80% within 2500 mm across the row)
    min_row_cov = 1.0
    for row in row_extents:
        rx1, rx2, ry = row["x1"], row["x2"], row["y_center"]
        for svc, items in mep_aabbs.items():
            intervals = []
            for _, _, seg in items:
                (x1, y1, _), (x2, y2, _) = seg["p1"], seg["p2"]
                if abs(y1 - y2) < 1e-6 and abs(y1 - ry) <= cfg["code"]["row_service_dist_mm"]:
                    lo, hi = max(rx1, min(x1, x2)), min(rx2, max(x1, x2))
                    if hi > lo:
                        intervals.append((lo, hi))
            intervals.sort()
            covered = 0.0
            cur_lo, cur_hi = None, None
            for lo, hi in intervals:
                if cur_lo is None:
                    cur_lo, cur_hi = lo, hi
                elif lo <= cur_hi + 250.0:
                    cur_hi = max(cur_hi, hi)
                else:
                    covered += cur_hi - cur_lo
                    cur_lo, cur_hi = lo, hi
            if cur_lo is not None:
                covered += cur_hi - cur_lo
            min_row_cov = min(min_row_cov, covered / (rx2 - rx1))

    # CRAH reachability (CHW within 2500 mm of every CRAH)
    max_crah_dist = 0.0
    for u in cfg["crahs"]["units"]:
        cx, cy = u["cx"], u["cy"]
        best = float("inf")
        for _, _, seg in mep_aabbs["chilled_water"]:
            (x1, y1, _), (x2, y2, _) = seg["p1"], seg["p2"]
            # 2D point-to-segment distance
            vx, vy = x2 - x1, y2 - y1
            l2 = vx * vx + vy * vy
            t = max(0.0, min(1.0, ((cx - x1) * vx + (cy - y1) * vy) / l2))
            px, py = x1 + t * vx, y1 + t * vy
            best = min(best, math.hypot(cx - px, cy - py))
        max_crah_dist = max(max_crah_dist, best)

    summary = {
        "hard_clashes": len(clashes),
        "connectivity": connectivity,
        "min_headroom_mm": round(min_headroom, 2),
        "min_sprinkler_clearance_mm": round(min_sprinkler_clr, 2),
        "min_tray_busway_sep_mm": round(min_tray_bus_sep, 2),
        "pdu_chw_violations": pdu_chw_violations,
        "min_row_coverage_fraction": round(min_row_cov, 4),
        "max_crah_chw_distance_mm": round(max_crah_dist, 2),
    }

    if clashes:
        raise RuntimeError(f"Hard clashes detected: {clashes[:5]}")
    if not all(v["is_single_network"] and v["entry_distance_mm"] <= 1.0 for v in connectivity.values()):
        raise RuntimeError(f"Connectivity check failed: {connectivity}")
    if min_headroom < cfg["code"]["min_headroom_mm"]:
        raise RuntimeError(f"Headroom violation: {min_headroom} mm")
    if min_sprinkler_clr < cfg["code"]["sprinkler_clear_below_mm"]:
        raise RuntimeError(f"Sprinkler clearance violation: {min_sprinkler_clr} mm")
    if min_tray_bus_sep < cfg["code"]["tray_busway_sep_mm"]:
        raise RuntimeError(f"Tray-busway separation violation: {min_tray_bus_sep} mm")
    if pdu_chw_violations > 0:
        raise RuntimeError(f"CHW intrudes into PDU dedicated zone ({pdu_chw_violations} violations)")
    if min_row_cov < cfg["code"]["row_coverage_min"]:
        raise RuntimeError(f"Row coverage below 80%: {min_row_cov}")
    if max_crah_dist > cfg["code"]["crah_service_dist_mm"]:
        raise RuntimeError(f"CRAH CHW distance exceeds 2500 mm: {max_crah_dist}")

    return summary


# ---------------------------------------------------------------------------
# Main IFC4 model builder
# ---------------------------------------------------------------------------
def build_ifc(out_path: str, cfg: dict = DRAWING_DATA) -> dict:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    # Deterministic file header metadata
    model.header.file_name.name = os.path.basename(out_path)
    model.header.file_name.time_stamp = "2025-01-01T00:00:00"
    model.header.file_name.author = ("MEP Coordinator",)
    model.header.file_name.organization = ("DataCenter Coordination",)

    project = create_element(model, "IfcProject", "DataHall_hall_seed000_d000", "project:main")

    # Millimetre project units (length = MILLI METRE -> unit_scale = 0.001)
    u_len = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI")
    u_area = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="AREAUNIT")
    u_vol = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="VOLUMEUNIT")
    u_ang = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="PLANEANGLEUNIT")
    ifcopenshell.api.run("unit.assign_unit", model, units=[u_len, u_area, u_vol, u_ang])

    # Geometric representation contexts
    ctx_model = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    ctx_body = ifcopenshell.api.run(
        "context.add_context",
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=ctx_model,
    )

    # Prescribed spatial structure: Project -> Site -> Building -> BuildingStorey
    site = create_element(model, "IfcSite", "Site_DataCenter", "spatial:site")
    building = create_element(model, "IfcBuilding", "Building_DataHall", "spatial:building")
    storey = create_element(model, "IfcBuildingStorey", "Level_01_FFL", "spatial:storey")
    storey.Elevation = 0.0

    ifcopenshell.api.run("aggregate.assign_object", model, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", model, products=[storey], relating_object=building)
    for sp in (site, building, storey):
        ifcopenshell.api.run("geometry.edit_object_placement", model, product=sp, matrix=np.eye(4))

    add_pset(model, storey, "Pset_DCM_Hall", {
        "DataStatus": cfg["status"],
        "HallLength_mm": cfg["hall"]["length_x"],
        "HallWidth_mm": cfg["hall"]["width_y"],
        "ClearHeight_mm": cfg["hall"]["clear_height_z"],
        "UnderfloorPlenumDepth_mm": abs(cfg["hall"]["subfloor_top_z"]) - cfg["hall"]["access_floor_thickness"],
        "FloorTilePitch_mm": cfg["hall"]["tile_pitch"],
    })

    contained_products: List = []
    solids_registry: List[Tuple[str, str, Tuple[float, float, float, float, float, float]]] = []

    hall = cfg["hall"]
    Lx, Ly, wt = hall["length_x"], hall["width_y"], hall["wall_thickness"]
    z_sub_top = hall["subfloor_top_z"]
    t_sub = hall["subfloor_thickness"]
    t_af = hall["access_floor_thickness"]
    z_clr = hall["clear_height_z"]
    t_roof = hall["roof_slab_thickness"]

    # ------------------------------------------------------------------
    # 1. Building shell: subfloor slab, roof slab, 4 perimeter walls
    # ------------------------------------------------------------------
    sub_slab = create_element(model, "IfcSlab", "Subfloor_Slab", "shell:subfloor", "BASESLAB")
    assign_swept_rep(model, ctx_body, sub_slab, [make_rect_solid(model, Lx + 2 * wt, Ly + 2 * wt, t_sub)])
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=sub_slab,
        matrix=placement_matrix_yaw(Lx / 2.0, Ly / 2.0, z_sub_top - t_sub),
    )
    contained_products.append(sub_slab)
    solids_registry.append(("Subfloor_Slab", "shell", (-wt, -wt, z_sub_top - t_sub, Lx + wt, Ly + wt, z_sub_top)))

    roof_slab = create_element(model, "IfcSlab", "Roof_Slab", "shell:roof", "ROOF")
    assign_swept_rep(model, ctx_body, roof_slab, [make_rect_solid(model, Lx + 2 * wt, Ly + 2 * wt, t_roof)])
    ifcopenshell.api.run(
        "geometry.edit_object_placement",
        model,
        product=roof_slab,
        matrix=placement_matrix_yaw(Lx / 2.0, Ly / 2.0, z_clr),
    )
    contained_products.append(roof_slab)
    solids_registry.append(("Roof_Slab", "shell", (-wt, -wt, z_clr, Lx + wt, Ly + wt, z_clr + t_roof)))

    wall_h = z_clr - z_sub_top
    walls_spec = [
        ("Wall_South", Lx / 2.0, -wt / 2.0, Lx + 2 * wt, wt),
        ("Wall_North", Lx / 2.0, Ly + wt / 2.0, Lx + 2 * wt, wt),
        ("Wall_West",  -wt / 2.0, Ly / 2.0, wt, Ly),
        ("Wall_East",  Lx + wt / 2.0, Ly / 2.0, wt, Ly),
    ]
    for wname, cx, cy, wx, wy in walls_spec:
        wall = create_element(model, "IfcWall", wname, f"shell:{wname}", "STANDARD")
        assign_swept_rep(model, ctx_body, wall, [make_rect_solid(model, wx, wy, wall_h)])
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=wall,
            matrix=placement_matrix_yaw(cx, cy, z_sub_top),
        )
        contained_products.append(wall)
        solids_registry.append((wname, "shell", box_aabb(cx, cy, z_sub_top, wx, wy, wall_h)))

    # ------------------------------------------------------------------
    # 2. Structural columns (full height: subfloor_top_z -> clear_height_z)
    # ------------------------------------------------------------------
    col_cfg = cfg["columns"]
    cw, cd = col_cfg["size_x"], col_cfg["size_y"]
    col_h = z_clr - z_sub_top
    for ix, cx in enumerate(col_cfg["x_coords"], start=1):
        for iy, cy in enumerate(col_cfg["y_coords"], start=1):
            cname = f"Column_C{ix}{iy}"
            col = create_element(model, "IfcColumn", cname, f"col:{cname}", "COLUMN")
            assign_swept_rep(model, ctx_body, col, [make_rect_solid(model, cw, cd, col_h)])
            ifcopenshell.api.run(
                "geometry.edit_object_placement",
                model,
                product=col,
                matrix=placement_matrix_yaw(cx, cy, z_sub_top),
            )
            add_pset(model, col, "Pset_DCM_Column", {
                "Width_mm": cw,
                "Depth_mm": cd,
                "BottomZ_mm": z_sub_top,
                "TopZ_mm": z_clr,
            })
            contained_products.append(col)
            solids_registry.append((cname, "column", box_aabb(cx, cy, z_sub_top, cw, cd, col_h)))

    # ------------------------------------------------------------------
    # 3. Raised access floor (tiled cleanly around the 9 full-height columns)
    # ------------------------------------------------------------------
    x_bands = []
    prev = 0.0
    for cx in col_cfg["x_coords"]:
        x_bands.append((prev, cx - cw / 2.0, False))
        x_bands.append((cx - cw / 2.0, cx + cw / 2.0, True))
        prev = cx + cw / 2.0
    x_bands.append((prev, Lx, False))

    y_bands = []
    prev = 0.0
    for cy in col_cfg["y_coords"]:
        y_bands.append((prev, cy - cd / 2.0, False))
        y_bands.append((cy - cd / 2.0, cy + cd / 2.0, True))
        prev = cy + cd / 2.0
    y_bands.append((prev, Ly, False))

    af_solids = []
    af_idx = 0
    for y1, y2, y_is_col in y_bands:
        if not y_is_col:
            # Full hall width band
            af_idx += 1
            cx, cy = Lx / 2.0, (y1 + y2) / 2.0
            af_solids.append(make_rect_solid(model, Lx, y2 - y1, t_af, ox=cx, oy=cy, oz=-t_af))
            solids_registry.append((f"AccessFloor_Band_{af_idx}", "access_floor", (0.0, y1, -t_af, Lx, y2, 0.0)))
        else:
            for x1, x2, x_is_col in x_bands:
                if x_is_col:
                    continue  # Column cutout -> zero clash with column
                af_idx += 1
                cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                af_solids.append(make_rect_solid(model, x2 - x1, y2 - y1, t_af, ox=cx, oy=cy, oz=-t_af))
                solids_registry.append((f"AccessFloor_Strip_{af_idx}", "access_floor", (x1, y1, -t_af, x2, y2, 0.0)))

    access_floor = create_element(model, "IfcCovering", "Raised_Access_Floor", "shell:access_floor", "FLOORING", "AccessFloor")
    assign_swept_rep(model, ctx_body, access_floor, af_solids)
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=access_floor, matrix=np.eye(4))
    add_pset(model, access_floor, "Pset_DCM_AccessFloor", {
        "FinishedFloorElevation_mm": 0.0,
        "DeckThickness_mm": t_af,
        "PlenumClearDepth_mm": abs(z_sub_top) - t_af,
        "TilePitch_mm": hall["tile_pitch"],
    })
    contained_products.append(access_floor)

    # ------------------------------------------------------------------
    # 4. 128 Cabinets (IfcFurniture / USERDEFINED / "Rack")
    # ------------------------------------------------------------------
    cab = cfg["cabinets"]
    rw, rd, rh = cab["width_x"], cab["depth_y"], cab["height_z"]
    n_racks = cab["racks_per_row"]
    row_extents = []

    for pod in cab["pods"]:
        for rb in cab["row_bands"]:
            row_id = f"Row_{rb['id']}_{pod['id']}"
            x_start = pod["x_start"]
            row_extents.append({
                "id": row_id,
                "x1": x_start,
                "x2": x_start + n_racks * rw,
                "y_center": rb["y_center"],
            })
            for k in range(n_racks):
                cx = x_start + (k + 0.5) * rw
                cy = rb["y_center"]
                rname = f"Rack_{rb['id']}{pod['id']}_{k + 1:02d}"
                rack = create_element(model, "IfcFurniture", rname, f"rack:{rname}", "USERDEFINED", "Rack")
                assign_swept_rep(model, ctx_body, rack, [make_rect_solid(model, rw, rd, rh)])
                ifcopenshell.api.run(
                    "geometry.edit_object_placement",
                    model,
                    product=rack,
                    matrix=placement_matrix_yaw(cx, cy, 0.0, rb["yaw_deg"]),
                )
                add_pset(model, rack, "Pset_DCM_Rack", {
                    "RowId": row_id,
                    "PodId": pod["id"],
                    "ColdAisleId": rb["aisle"],
                    "FacingDeg": rb["yaw_deg"],
                    "Width_mm": rw,
                    "Depth_mm": rd,
                    "Height_mm": rh,
                })
                contained_products.append(rack)
                solids_registry.append((rname, "rack", box_aabb(cx, cy, 0.0, rw, rd, rh, rb["yaw_deg"])))

    # ------------------------------------------------------------------
    # 5. Cold Aisle Containment (roofs + end-of-aisle doors)
    # ------------------------------------------------------------------
    cont = cfg["containment"]
    rz0, rzt, dt = cont["roof_z_bottom"], cont["roof_thickness"], cont["door_thickness"]
    for a in cont["aisles"]:
        aw, ad = a["x2"] - a["x1"], a["y2"] - a["y1"]
        acx, acy = (a["x1"] + a["x2"]) / 2.0, (a["y1"] + a["y2"]) / 2.0
        roof_name = f"ContainmentRoof_{a['id']}"
        roof = create_element(model, "IfcPlate", roof_name, f"cont:{roof_name}", "USERDEFINED", "ContainmentRoof")
        assign_swept_rep(model, ctx_body, roof, [make_rect_solid(model, aw, ad, rzt)])
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=roof,
            matrix=placement_matrix_yaw(acx, acy, rz0),
        )
        add_pset(model, roof, "Pset_DCM_Containment", {
            "AisleId": a["id"],
            "ContainmentType": "ColdAisle",
            "RoofElevation_mm": rz0,
            "SubRoofSprinklersProvided": True,
        })
        contained_products.append(roof)
        solids_registry.append((roof_name, "containment", box_aabb(acx, acy, rz0, aw, ad, rzt)))

        for end_tag, dcx in (("W", a["x1"] + dt / 2.0), ("E", a["x2"] - dt / 2.0)):
            dname = f"ContainmentDoor_{a['id']}_{end_tag}"
            door = create_element(model, "IfcPlate", dname, f"cont:{dname}", "USERDEFINED", "ContainmentDoor")
            assign_swept_rep(model, ctx_body, door, [make_rect_solid(model, dt, ad, rz0)])
            ifcopenshell.api.run(
                "geometry.edit_object_placement",
                model,
                product=door,
                matrix=placement_matrix_yaw(dcx, acy, 0.0),
            )
            contained_products.append(door)
            solids_registry.append((dname, "containment", box_aabb(dcx, acy, 0.0, dt, ad, rz0)))

    # ------------------------------------------------------------------
    # 6. CRAH units (IfcUnitaryEquipment / AIRCONDITIONINGUNIT)
    # ------------------------------------------------------------------
    ccfg = cfg["crahs"]
    for u in ccfg["units"]:
        crah = create_element(
            model, "IfcUnitaryEquipment", u["id"], f"crah:{u['id']}", "AIRCONDITIONINGUNIT", "CRAH"
        )
        assign_swept_rep(
            model, ctx_body, crah, [make_rect_solid(model, ccfg["width_x"], ccfg["depth_y"], ccfg["height_z"])]
        )
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=crah,
            matrix=placement_matrix_yaw(u["cx"], u["cy"], 0.0, u["yaw_deg"]),
        )
        add_pset(model, crah, "Pset_DCM_CRAH", {
            "UnitId": u["id"],
            "FacingDeg": u["yaw_deg"],
            "Width_mm": ccfg["width_x"],
            "Depth_mm": ccfg["depth_y"],
            "Height_mm": ccfg["height_z"],
        })
        contained_products.append(crah)
        solids_registry.append((
            u["id"],
            "crah",
            box_aabb(u["cx"], u["cy"], 0.0, ccfg["width_x"], ccfg["depth_y"], ccfg["height_z"], u["yaw_deg"]),
        ))

    # ------------------------------------------------------------------
    # 7. PDUs (IfcElectricDistributionBoard / DISTRIBUTIONBOARD)
    # ------------------------------------------------------------------
    pcfg = cfg["pdus"]
    for u in pcfg["units"]:
        pdu = create_element(
            model, "IfcElectricDistributionBoard", u["id"], f"pdu:{u['id']}", "DISTRIBUTIONBOARD", "PDU"
        )
        assign_swept_rep(
            model, ctx_body, pdu, [make_rect_solid(model, pcfg["width_x"], pcfg["depth_y"], pcfg["height_z"])]
        )
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=pdu,
            matrix=placement_matrix_yaw(u["cx"], u["cy"], 0.0, u["yaw_deg"]),
        )
        add_pset(model, pdu, "Pset_DCM_PDU", {
            "UnitId": u["id"],
            "FacingDeg": u["yaw_deg"],
            "Height_mm": pcfg["height_z"],
            "DedicatedSpaceAbove_mm": pcfg["dedicated_space_above"],
        })
        contained_products.append(pdu)
        solids_registry.append((
            u["id"],
            "pdu",
            box_aabb(u["cx"], u["cy"], 0.0, pcfg["width_x"], pcfg["depth_y"], pcfg["height_z"], u["yaw_deg"]),
        ))

    # ------------------------------------------------------------------
    # 8. Sprinkler Heads (ceiling grid + sub-containment-roof heads)
    # ------------------------------------------------------------------
    scfg = cfg["sprinklers"]
    sr = scfg["head_diameter"] / 2.0
    ch = scfg["ceiling_top_z"] - scfg["ceiling_deflector_z"]
    for ix, sx in enumerate(scfg["ceiling_x"], start=1):
        for iy, sy in enumerate(scfg["ceiling_y"], start=1):
            sname = f"Sprinkler_Ceil_{ix:02d}_{iy:02d}"
            spr = create_element(model, "IfcFireSuppressionTerminal", sname, f"spr:{sname}", "SPRINKLER", "CeilingSprinkler")
            assign_swept_rep(model, ctx_body, spr, [make_circle_solid(model, sr, ch)])
            ifcopenshell.api.run(
                "geometry.edit_object_placement",
                model,
                product=spr,
                matrix=placement_matrix_yaw(sx, sy, scfg["ceiling_deflector_z"]),
            )
            add_pset(model, spr, "Pset_DCM_Sprinkler", {
                "Zone": "Ceiling",
                "DeflectorElevation_mm": scfg["ceiling_deflector_z"],
                "MinClearBelow_mm": cfg["code"]["sprinkler_clear_below_mm"],
            })
            contained_products.append(spr)
            solids_registry.append((
                sname,
                "sprinkler",
                (sx - sr, sy - sr, scfg["ceiling_deflector_z"], sx + sr, sy + sr, scfg["ceiling_top_z"]),
            ))

    sh = scfg["sub_containment_top_z"] - scfg["sub_containment_deflector_z"]
    sub_xs = scfg["sub_containment_x_west"] + scfg["sub_containment_x_east"]
    for ix, sx in enumerate(sub_xs, start=1):
        for iy, sy in enumerate(scfg["sub_containment_y"], start=1):
            sname = f"Sprinkler_SubCont_{ix:02d}_{iy:02d}"
            spr = create_element(
                model, "IfcFireSuppressionTerminal", sname, f"spr:{sname}", "SPRINKLER", "SubContainmentSprinkler"
            )
            assign_swept_rep(model, ctx_body, spr, [make_circle_solid(model, sr, sh)])
            ifcopenshell.api.run(
                "geometry.edit_object_placement",
                model,
                product=spr,
                matrix=placement_matrix_yaw(sx, sy, scfg["sub_containment_deflector_z"]),
            )
            add_pset(model, spr, "Pset_DCM_Sprinkler", {
                "Zone": "SubContainment",
                "DeflectorElevation_mm": scfg["sub_containment_deflector_z"],
                "MinClearBelow_mm": cfg["code"]["sprinkler_clear_below_mm"],
            })
            contained_products.append(spr)
            solids_registry.append((
                sname,
                "sprinkler",
                (sx - sr, sy - sr, scfg["sub_containment_deflector_z"], sx + sr, sy + sr, scfg["sub_containment_top_z"]),
            ))

    # ------------------------------------------------------------------
    # 9. Overhead MEP Services (Chilled Water, Cable Tray, Power Busway)
    # ------------------------------------------------------------------
    routes = build_mep_routes(cfg)
    mep_aabbs: Dict[str, List[Tuple[str, Tuple[float, float, float, float, float, float], dict]]] = {
        "chilled_water": [],
        "cable_tray": [],
        "busway": [],
    }
    service_lengths: Dict[str, float] = {"chilled_water": 0.0, "cable_tray": 0.0, "busway": 0.0}

    sys_specs = [
        (
            "chilled_water",
            "System_Chilled_Water",
            "IfcPipeSegment",
            "RIGIDSEGMENT",
            "ChilledWaterPipe",
            "circle",
            cfg["mep"]["chilled_water"]["insulated_od"],
            cfg["mep"]["chilled_water"]["insulated_od"],
            "Tier3_Overhead_3700mm",
        ),
        (
            "cable_tray",
            "System_Telecom_Cable_Tray",
            "IfcCableCarrierSegment",
            "CABLETRAYSEGMENT",
            "TelecomCableTray",
            "rect",
            cfg["mep"]["cable_tray"]["width"],
            cfg["mep"]["cable_tray"]["height"],
            "Tier2_Overhead_3370mm",
        ),
        (
            "busway",
            "System_Power_Busway",
            "IfcCableSegment",
            "BUSBARSEGMENT",
            "PowerBusway",
            "rect",
            cfg["mep"]["busway"]["width"],
            cfg["mep"]["busway"]["height"],
            "Tier1_Overhead_2860mm",
        ),
    ]

    for svc_key, sys_name, ifc_cls, pred_type, obj_type, shape, w_dim, h_dim, tier_label in sys_specs:
        ifc_sys = ifcopenshell.api.run("system.add_system", model, ifc_class="IfcSystem")
        ifc_sys.GlobalId = det_guid(f"sys:{svc_key}")
        ifc_sys.Name = sys_name
        sys_members = []

        for seg in routes[svc_key]:
            mat, seg_len, aabb = segment_matrix_length_aabb(seg["p1"], seg["p2"], w_dim, h_dim)
            elem = create_element(model, ifc_cls, seg["id"], f"mep:{seg['id']}", pred_type, obj_type)
            if shape == "circle":
                solid = make_circle_solid(model, w_dim / 2.0, seg_len)
            else:
                solid = make_rect_solid(model, w_dim, h_dim, seg_len)
            assign_swept_rep(model, ctx_body, elem, [solid])
            ifcopenshell.api.run("geometry.edit_object_placement", model, product=elem, matrix=mat)

            props = {
                "Service": svc_key,
                "Tier": tier_label,
                "ElevationFFL_mm": seg["p1"][2],
                "Length_mm": seg_len,
                "WidthOrOD_mm": w_dim,
                "HeightOrOD_mm": h_dim,
                "PlenumZone": "Overhead" if seg["p1"][2] >= 0.0 else "Underfloor",
            }
            if svc_key == "chilled_water":
                props["BarePipeOD_mm"] = cfg["mep"]["chilled_water"]["bare_od"]
                props["InsulationThickness_mm"] = cfg["mep"]["chilled_water"]["insulation_thickness"]
            add_pset(model, elem, "Pset_DCM_MEPSegment", props)

            contained_products.append(elem)
            sys_members.append(elem)
            solids_registry.append((seg["id"], svc_key, aabb))
            mep_aabbs[svc_key].append((seg["id"], aabb, seg))
            service_lengths[svc_key] += seg_len

        ifcopenshell.api.run("system.assign_system", model, products=sys_members, system=ifc_sys)

    # Assign all physical elements to the storey
    ifcopenshell.api.run("spatial.assign_container", model, products=contained_products, relating_structure=storey)

    # Verify geometry, clashes, connectivity, and code rules before writing
    summary = verify_model(cfg, solids_registry, mep_aabbs, row_extents)
    summary["service_lengths_m"] = {k: round(v / 1000.0, 3) for k, v in service_lengths.items()}
    summary["element_count"] = len(contained_products)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    model.write(out_path)
    return summary


def main() -> None:
    default_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
    out_path = sys.argv[1] if len(sys.argv) > 1 else default_out
    summary = build_ifc(out_path)
    print(f"Wrote IFC4 model to {out_path}")
    print(f"Verification summary: {summary}")


if __name__ == "__main__":
    main()
