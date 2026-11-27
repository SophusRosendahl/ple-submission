"""Data Hall MEP Coordination Model (hall_seed000_d000).

Self-contained IFC4 builder using ifcopenshell==0.8.4 and numpy only.
All dimensions baked as literals from drawing sheets A-101, A-301, A-601,
A-602, M-101, E-101, and F-101.

Usage:
    python3 output/solution.py [output/model.ifc]
"""
import math
import os
import sys
import numpy as np

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# ---------------------------------------------------------------------------
# Baked architectural, structural, equipment & MEP data (all in mm)
# ---------------------------------------------------------------------------
HALL_W = 27000.0
HALL_D = 21000.0
SOFFIT_Z = 3600.0
SLAB_TOP_Z = -900.0
FLOOR_THK = 35.0
CAB_H = 2000.0
CAB_D = 1200.0
CA_EAST_X = 11200.0  # Common east edge of cross-aisle (A-101 Note 5)

ROW_SPECS = [
    # (row_id, y_centre, facing, bay_sequence)
    (
        "A",
        3000.0,
        "SOUTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3), ("CU", 1),
            ("CA", 1),
            ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "B",
        6000.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
            ("CA", 1),
            ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "C",
        8400.0,
        "SOUTH",
        [
            ("C1", 3), ("CU", 1), ("C1", 6), ("-600", 2), ("CU", 1),
            ("CA", 1),
            ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1), ("C1", 1), ("-600", 2), ("C1", 3),
        ],
    ),
    (
        "D",
        11400.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2), ("CU", 1),
            ("CA", 1),
            ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "E",
        13800.0,
        "SOUTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1), ("CU", 1),
            ("CA", 1),
            ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "F",
        16800.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("-600", 2), ("CU", 1),
            ("CA", 1),
            ("N1", 2), ("C1", 5), ("SP", 1), ("-600", 1), ("CU", 1), ("C1", 4),
        ],
    ),
]

BAY_WIDTHS = {"C1": 600.0, "N1": 800.0, "CU": 600.0, "SP": 600.0, "-600": 600.0}

# Structural columns: 400 x 400 mm centered on grid intersections (Z = 0..3600)
COL_SIZE = 400.0
COL_GRID_X = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
COL_GRID_Y = [("1", 8400.0), ("2", 16800.0)]

# Perimeter CRAHs (A-601): B01, P01, AC01, AQ01; 1200 W x 900 D x 2000 H, face NORTH
PERIM_CRAHS = [
    ("CRAH-01", 600.0, 0.0),
    ("CRAH-02", 9000.0, 0.0),
    ("CRAH-03", 16800.0, 0.0),
    ("CRAH-04", 25200.0, 0.0),
]

# PDUs (A-601, A-101 Note 8): 762 W x 813 D x 1959 H, front flush with row front
PDU_SPECS = [
    # (tag, serves_row, x0, row_front_y, facing)
    ("PDU-01", "A", 21000.0, 2400.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0, "NORTH"),
]


def build_scene():
    """Build deterministic geometric representation of the entire hall and MEP."""
    racks = []
    crahs = []
    pdus = []
    columns = []
    floor = []
    containment = []
    sprinklers = []

    # 1. Access floor panel (Z = -35..0)
    floor.append({
        "name": "AccessFloor",
        "aabb": (0.0, HALL_W, 0.0, HALL_D, -FLOOR_THK, 0.0),
        "facing": "NORTH",
    })

    # 2. Structural columns (Z = 0..3600)
    for gx_lbl, gx in COL_GRID_X:
        for gy_lbl, gy in COL_GRID_Y:
            h = COL_SIZE / 2.0
            columns.append({
                "name": f"COL-{gx_lbl}{gy_lbl}",
                "aabb": (gx - h, gx + h, gy - h, gy + h, 0.0, SOFFIT_Z),
                "facing": "NORTH",
            })

    # 3. Cabinet rows & in-row CRAHs
    row_extents = {}
    for row_id, yc, facing, seq in ROW_SPECS:
        x = 1800.0  # Tile D
        y0 = yc - CAB_D / 2.0
        y1 = yc + CAB_D / 2.0
        cab_idx = 0
        cu_idx = 0
        west_end_x = None
        east_end_x = None
        for typ, cnt in seq:
            if typ == "CA":
                west_end_x = x
                x = CA_EAST_X
                continue
            w = BAY_WIDTHS[typ]
            for _ in range(cnt):
                if typ in ("C1", "N1"):
                    cab_idx += 1
                    racks.append({
                        "name": f"RACK-{row_id}{cab_idx:02d}",
                        "row": row_id,
                        "type": typ,
                        "aabb": (x, x + w, y0, y1, 0.0, CAB_H),
                        "facing": facing,
                        "w": w,
                        "d": CAB_D,
                        "h": CAB_H,
                    })
                elif typ == "CU":
                    cu_idx += 1
                    crahs.append({
                        "name": f"CRAH-{row_id}{cu_idx:02d}",
                        "placement": "IN-ROW",
                        "row": row_id,
                        "aabb": (x, x + w, y0, y1, 0.0, CAB_H),
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "airflow_m3h": 9000.0,
                    })
                x += w
        east_end_x = x
        row_extents[row_id] = (1800.0, west_end_x, CA_EAST_X, east_end_x)

    # 4. Perimeter CRAHs
    for name, x0, y0 in PERIM_CRAHS:
        crahs.append({
            "name": name,
            "placement": "PERIMETER",
            "row": "PERIMETER",
            "aabb": (x0, x0 + 1200.0, y0, y0 + 900.0, 0.0, 2000.0),
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "airflow_m3h": 20000.0,
        })

    # 5. PDUs
    for tag, srow, x0, front_y, facing in PDU_SPECS:
        if facing == "SOUTH":
            y0, y1 = front_y, front_y + 813.0
        else:
            y0, y1 = front_y - 813.0, front_y
        pdus.append({
            "name": tag,
            "serves_row": srow,
            "aabb": (x0, x0 + 762.0, y0, y1, 0.0, 1959.0),
            "facing": facing,
        })

    # 6. Cold-Aisle Containment (CAC-BC at Y=6600..7800, CAC-DE at Y=12000..13200)
    # Roofs: width 1400 mm (100 mm overhang onto cabinet tops each side), Z = 2000..2055.5
    # End doors: 60 mm thick x 1200 mm wide x 2055.5 mm high (just outside aisle ends)
    for cac_name, y_s, y_n, r_s, r_n in [
        ("CAC-BC", 6600.0, 7800.0, "B", "C"),
        ("CAC-DE", 12000.0, 13200.0, "D", "E"),
    ]:
        # West half & East half split at cross-aisle
        w_x0 = 1800.0
        w_x1 = min(row_extents[r_s][1], row_extents[r_n][1])
        e_x0 = CA_EAST_X
        e_x1 = min(row_extents[r_s][3], row_extents[r_n][3])
        for half, hx0, hx1 in [("W", w_x0, w_x1), ("E", e_x0, e_x1)]:
            containment.append({
                "name": f"{cac_name}-Roof-{half}",
                "aisle": cac_name,
                "component": "Roof",
                "aabb": (hx0, hx1, y_s - 100.0, y_n + 100.0, 2000.0, 2055.5),
                "facing": "NORTH",
            })
            # West & East end doors (placed flush outside roof ends so zero overlap with roof)
            containment.append({
                "name": f"{cac_name}-Door-{half}1",
                "aisle": cac_name,
                "component": "EndDoor",
                "aabb": (hx0 - 60.0, hx0, y_s, y_n, 0.0, 2055.5),
                "facing": "NORTH",
            })
            containment.append({
                "name": f"{cac_name}-Door-{half}2",
                "aisle": cac_name,
                "component": "EndDoor",
                "aabb": (hx1, hx1 + 60.0, y_s, y_n, 0.0, 2055.5),
                "facing": "NORTH",
            })

    # 7. Sprinkler Heads: 63 ceiling heads (Z_deflector = 3574.6) + 16 in-aisle (Z = 1890.0)
    # Modelled as 50x50x25 mm pendent head body ending at deflector elevation
    spr_idx = 0
    for j in range(7):
        sy_base = 1500.0 + 3000.0 * j
        for i in range(9):
            sx_base = 1500.0 + 3000.0 * i
            sx, sy = sx_base, sy_base
            # Relocate heads within 1500 mm column keep-out (F-101 Detail 2)
            if abs(sx - 16800.0) < 750.0 and abs(sy - 16800.0) < 750.0:
                sx, sy = 16050.0, 16050.0
            elif abs(sx - 25200.0) < 750.0 and abs(sy - 16800.0) < 750.0:
                sx, sy = 25950.0, 16050.0
            spr_idx += 1
            sprinklers.append({
                "name": f"SPR-C{spr_idx:02d}",
                "location": "Ceiling",
                "deflector_z": 3574.6,
                "aabb": (sx - 25.0, sx + 25.0, sy - 25.0, sy + 25.0, 3574.6, 3600.0),
                "facing": "NORTH",
            })

    # 16 in-aisle heads (8 in CAC-BC at Y=7200, 8 in CAC-DE at Y=12600)
    aisle_xs = [2700.0, 5100.0, 7500.0, 9300.0, 12100.0, 14300.0, 16500.0, 18500.0]
    in_idx = 0
    for ay in (7200.0, 12600.0):
        for ax in aisle_xs:
            in_idx += 1
            sprinklers.append({
                "name": f"SPR-A{in_idx:02d}",
                "location": "InAisle",
                "deflector_z": 1890.0,
                "aabb": (ax - 25.0, ax + 25.0, ay - 25.0, ay + 25.0, 1890.0, 2000.0),
                "facing": "NORTH",
            })

    # 8. Coordinated MEP Routes (all straight axis-aligned segments)
    # Service entry for all three services: West wall X = 0, Y = 9900
    # - Cable Tray (CT-1): 683 W x 127 H, OVERHEAD at Z_centre = 2863.5 (Z = [2800.0, 2927.0])
    # - Busway (BW-1): 128 W x 147 H, UNDER-FLOOR at Z_centre = -200.0 (Z = [-273.5, -126.5])
    # - CHW Pipe (CHW-1): 168.3 OD (insulated), UNDER-FLOOR at Z_centre = -600.0 (Z = [-684.15, -515.85])
    def make_tree(prefix, zc, w, h, zone, include_perim=False):
        segs = []
        idx = 0

        def add(p0, p1):
            nonlocal idx
            idx += 1
            segs.append({
                "name": f"{prefix}-{idx:03d}",
                "p0": p0,
                "p1": p1,
                "w": w,
                "h": h,
                "z": zc,
                "zone": zone,
            })

        # Entry stub from X=0 to trunk X=900 at Y=9900
        add((0.0, 9900.0, zc), (900.0, 9900.0, zc))
        # North-South trunk along X=900
        if include_perim:
            add((900.0, 1200.0, zc), (900.0, 15300.0, zc))
        else:
            add((900.0, 4500.0, zc), (900.0, 15300.0, zc))
        # Three East-West branches along hot-aisle centrelines (serve all 6 rows within 1500 mm)
        for by in (4500.0, 9900.0, 15300.0):
            add((900.0, by, zc), (18000.0, by, zc))
        # Perimeter CRAH branch for CHW (serves CRAH-01..04 within 750 mm)
        if include_perim:
            add((900.0, 1200.0, zc), (25800.0, 1200.0, zc))
        return segs

    mep = {
        "tray": make_tree("CT", 2863.5, 683.0, 127.0, "Overhead", include_perim=False),
        "busway": make_tree("BW", -200.0, 128.0, 147.0, "UnderFloor", include_perim=False),
        "chw": make_tree("CHW", -600.0, 168.3, 168.3, "UnderFloor", include_perim=True),
    }

    return {
        "racks": racks,
        "crahs": crahs,
        "pdus": pdus,
        "columns": columns,
        "floor": floor,
        "containment": containment,
        "sprinklers": sprinklers,
        "mep": mep,
    }


# ---------------------------------------------------------------------------
# IFC4 Model Builder (ifcopenshell==0.8.4)
# ---------------------------------------------------------------------------
def _placement_matrix(cx_mm, cy_mm, z0_mm, yaw_rad=0.0):
    """4x4 placement matrix with translation in METRES (per ifcopenshell API)."""
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


def _facing_yaw(facing):
    """Rotation about Z so local +Y (front) points in the facing direction."""
    if facing == "SOUTH":
        return math.pi
    if facing == "EAST":
        return -math.pi / 2.0
    if facing == "WEST":
        return math.pi / 2.0
    return 0.0  # NORTH


def _add_box_rep(model, body_ctx, product, x_dim, y_dim, z_dim):
    """Create 2D-profile IfcExtrudedAreaSolid box centered in XY, Z in [0, z_dim]."""
    pos2d = model.createIfcAxis2Placement2D(
        model.createIfcCartesianPoint((0.0, 0.0))
    )
    prof = model.createIfcRectangleProfileDef("AREA", None, pos2d, float(x_dim), float(y_dim))
    pos3d = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        model.createIfcDirection((1.0, 0.0, 0.0)),
    )
    solid = model.createIfcExtrudedAreaSolid(
        prof, pos3d, model.createIfcDirection((0.0, 0.0, 1.0)), float(z_dim)
    )
    rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
    product.Representation = model.createIfcProductDefinitionShape(None, None, [rep])


def _add_cyl_rep(model, body_ctx, product, radius, length):
    """Create 2D-profile IfcExtrudedAreaSolid cylinder along local +Z."""
    pos2d = model.createIfcAxis2Placement2D(
        model.createIfcCartesianPoint((0.0, 0.0))
    )
    prof = model.createIfcCircleProfileDef("AREA", None, pos2d, float(radius))
    pos3d = model.createIfcAxis2Placement3D(
        model.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        model.createIfcDirection((0.0, 0.0, 1.0)),
        model.createIfcDirection((1.0, 0.0, 0.0)),
    )
    solid = model.createIfcExtrudedAreaSolid(
        prof, pos3d, model.createIfcDirection((0.0, 0.0, 1.0)), float(length)
    )
    rep = model.createIfcShapeRepresentation(body_ctx, "Body", "SweptSolid", [solid])
    product.Representation = model.createIfcProductDefinitionShape(None, None, [rep])


def _set_pset(model, product, pset_name, props):
    import ifcopenshell.api.pset as pset_api

    pset = pset_api.add_pset(model, product=product, name=pset_name)
    pset_api.edit_pset(model, pset=pset, properties=props)


def build_ifc(scene, out_path):
    import ifcopenshell
    import ifcopenshell.api.root as root_api
    import ifcopenshell.api.unit as unit_api
    import ifcopenshell.api.context as ctx_api
    import ifcopenshell.api.aggregate as agg_api
    import ifcopenshell.api.spatial as spatial_api
    import ifcopenshell.api.geometry as geom_api

    model = ifcopenshell.file(schema="IFC4")
    project = root_api.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center")
    unit_api.assign_unit(model, length={"is_metric": True, "raw": "MILLIMETRE"})

    model_ctx = ctx_api.add_context(model, context_type="Model")
    body_ctx = ctx_api.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = root_api.create_entity(model, ifc_class="IfcSite", name="Site")
    building = root_api.create_entity(model, ifc_class="IfcBuilding", name="Data Hall 1")
    storey = root_api.create_entity(model, ifc_class="IfcBuildingStorey", name="Level 0")
    storey.Elevation = 0.0

    agg_api.assign_object(model, products=[site], relating_object=project)
    agg_api.assign_object(model, products=[building], relating_object=site)
    agg_api.assign_object(model, products=[storey], relating_object=building)

    all_products = []

    def place_aabb(el, aabb, facing="NORTH"):
        x0, x1, y0, y1, z0, z1 = aabb
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        yaw = _facing_yaw(facing)
        geom_api.edit_object_placement(model, product=el, matrix=_placement_matrix(cx, cy, z0, yaw))
        # Box dimensions in local frame (for 0 or pi rotation, X=x1-x0, Y=y1-y0)
        _add_box_rep(model, body_ctx, el, x1 - x0, y1 - y0, z1 - z0)
        all_products.append(el)

    # 1. Access Floor
    for fl in scene["floor"]:
        el = root_api.create_entity(
            model, ifc_class="IfcSlab", predefined_type="FLOOR", name=fl["name"]
        )
        el.ObjectType = "AccessFloor"
        place_aabb(el, fl["aabb"])

    # 2. Structural Columns
    for col in scene["columns"]:
        el = root_api.create_entity(
            model, ifc_class="IfcColumn", predefined_type="COLUMN", name=col["name"]
        )
        place_aabb(el, col["aabb"])

    # 3. Racks
    for r in scene["racks"]:
        el = root_api.create_entity(
            model, ifc_class="IfcFurniture", predefined_type="USERDEFINED", name=r["name"]
        )
        el.ObjectType = "Rack"
        place_aabb(el, r["aabb"], r["facing"])
        _set_pset(model, el, "Pset_DCM_Rack", {
            "Row": r["row"],
            "CabinetType": r["type"],
            "Width_mm": float(r["w"]),
            "Depth_mm": float(r["d"]),
            "Height_mm": float(r["h"]),
            "RU": 42,
            "Power_kW": 8.0,
            "Weight_kg": 1363.0,
            "Facing": r["facing"],
        })

    # 4. CRAHs
    for c in scene["crahs"]:
        el = root_api.create_entity(
            model, ifc_class="IfcUnitaryEquipment", predefined_type="AIRHANDLER", name=c["name"]
        )
        el.ObjectType = "CRAH"
        place_aabb(el, c["aabb"], c["facing"])
        _set_pset(model, el, "Pset_DCM_CRAH", {
            "Placement": c["placement"],
            "Row": c["row"],
            "Capacity_kW": float(c["capacity_kw"]),
            "Airflow_m3h": float(c["airflow_m3h"]),
            "Facing": c["facing"],
        })

    # 5. PDUs
    for p in scene["pdus"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcElectricDistributionBoard",
            predefined_type="DISTRIBUTIONBOARD",
            name=p["name"],
        )
        el.ObjectType = "PDU"
        place_aabb(el, p["aabb"], p["facing"])
        _set_pset(model, el, "Pset_DCM_PDU", {
            "ServesRow": p["serves_row"],
            "Rating_kVA": 225.0,
            "Facing": p["facing"],
            "DedicatedSpace_mm": 1800.0,
        })

    # 6. Containment
    for ct in scene["containment"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcBuildingElementProxy",
            predefined_type="USERDEFINED",
            name=ct["name"],
        )
        el.ObjectType = "Containment"
        place_aabb(el, ct["aabb"])
        _set_pset(model, el, "Pset_DCM_Containment", {
            "Aisle": ct["aisle"],
            "Component": ct["component"],
        })

    # 7. Sprinklers
    for sp in scene["sprinklers"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcFireSuppressionTerminal",
            predefined_type="SPRINKLER",
            name=sp["name"],
        )
        el.ObjectType = "SprinklerHead"
        place_aabb(el, sp["aabb"])
        _set_pset(model, el, "Pset_DCM_Sprinkler", {
            "Location": sp["location"],
            "DeflectorElevation_mm": float(sp["deflector_z"]),
            "Standoff_mm": 460.0,
        })

    # 8. MEP Segments
    def place_mep_seg(el, seg, is_pipe=False):
        p0, p1 = seg["p0"], seg["p1"]
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        dz = p1[2] - p0[2]
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        cx = (p0[0] + p1[0]) / 2.0
        cy = (p0[1] + p1[1]) / 2.0
        cz = (p0[2] + p1[2]) / 2.0

        if is_pipe:
            # Extrude cylinder along local +Z from p0 to p1
            m = np.eye(4, dtype=float)
            if abs(dx) > 1e-6:
                sx = 1.0 if dx > 0 else -1.0
                # Local +Z -> (+sx, 0, 0)
                m[:3, 0] = [0.0, 1.0, 0.0]
                m[:3, 1] = [0.0, 0.0, sx]
                m[:3, 2] = [sx, 0.0, 0.0]
            elif abs(dy) > 1e-6:
                sy = 1.0 if dy > 0 else -1.0
                # Local +Z -> (0, +sy, 0)
                m[:3, 0] = [1.0, 0.0, 0.0]
                m[:3, 1] = [0.0, 0.0, -sy]
                m[:3, 2] = [0.0, sy, 0.0]
            m[0, 3] = p0[0] / 1000.0
            m[1, 3] = p0[1] / 1000.0
            m[2, 3] = p0[2] / 1000.0
            geom_api.edit_object_placement(model, product=el, matrix=m)
            _add_cyl_rep(model, body_ctx, el, seg["w"] / 2.0, length)
        else:
            # Rectangular tray/busway: box centered in XY, Z in [cz - h/2, cz + h/2]
            if abs(dx) > 1e-6:
                bx, by = length, seg["w"]
            else:
                bx, by = seg["w"], length
            geom_api.edit_object_placement(
                model, product=el, matrix=_placement_matrix(cx, cy, cz - seg["h"] / 2.0, 0.0)
            )
            _add_box_rep(model, body_ctx, el, bx, by, seg["h"])
        all_products.append(el)

    for s in scene["mep"]["tray"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcCableCarrierSegment",
            predefined_type="CABLETRAYSEGMENT",
            name=s["name"],
        )
        el.ObjectType = "CableTray"
        place_mep_seg(el, s, is_pipe=False)
        _set_pset(model, el, "Pset_DCM_MEP", {
            "Service": "Telecom",
            "Tag": "CT-1",
            "Zone": s["zone"],
            "Elevation_mm": float(s["z"]),
            "Width_mm": float(s["w"]),
            "Height_mm": float(s["h"]),
        })

    for s in scene["mep"]["busway"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcCableSegment",
            predefined_type="BUSBARSEGMENT",
            name=s["name"],
        )
        el.ObjectType = "Busway"
        place_mep_seg(el, s, is_pipe=False)
        _set_pset(model, el, "Pset_DCM_MEP", {
            "Service": "Power",
            "Tag": "BW-1",
            "Zone": s["zone"],
            "Elevation_mm": float(s["z"]),
            "Width_mm": float(s["w"]),
            "Height_mm": float(s["h"]),
        })

    for s in scene["mep"]["chw"]:
        el = root_api.create_entity(
            model,
            ifc_class="IfcPipeSegment",
            predefined_type="RIGIDSEGMENT",
            name=s["name"],
        )
        el.ObjectType = "CHWPipe"
        place_mep_seg(el, s, is_pipe=True)
        _set_pset(model, el, "Pset_DCM_MEP", {
            "Service": "ChilledWater",
            "Tag": "CHW-1",
            "Zone": s["zone"],
            "Elevation_mm": float(s["z"]),
            "BareOD_mm": 114.3,
            "InsulatedOD_mm": 168.3,
            "Insulation_mm": 25.4,
        })

    spatial_api.assign_container(model, products=all_products, relating_structure=storey)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    model.write(out_path)


if __name__ == "__main__":
    scene = build_scene()
    build_ifc(scene, OUT_PATH)
