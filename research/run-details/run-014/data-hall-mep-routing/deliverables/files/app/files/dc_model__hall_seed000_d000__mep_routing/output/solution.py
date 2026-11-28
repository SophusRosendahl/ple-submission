"""IFC4 Data Hall 1 (hall_seed000_d000) coordinated architectural & MEP model.

Rebuilds the data hall from drawing sheets A-101, A-301, A-601, A-602,
E-101, F-101, and M-101, and routes clash-free overhead busway (BW-1),
under-floor telecom cable tray (CT-1), and under-floor chilled-water
piping (CHW-1).

Usage:
    python output/solution.py [output_ifc_path]
"""

import math
import os
import sys
import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.aggregate

OUT_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.ifc")
)

# =============================================================================
# 1. DRAWING DATA (baked literals from sheets A-101..F-101, all in mm)
# =============================================================================

ROOM_W = 27000.0
ROOM_D = 21000.0
TILE_SIZE = 600.0

FF_Z = 0.0
ACCESS_FLOOR_THK = 35.0
SLAB_TOP_Z = -900.0
SOFFIT_Z = 3600.0
MIN_CLEAR_HEIGHT = 2600.0
CEILING_DEFLECTOR_Z = 3574.6  # 25.4 mm below 3600 soffit (A-301)
SPRINKLER_STANDOFF = 460.0
IN_AISLE_DEFLECTOR_Z = 1890.0

# Structural columns: 600 x 600 mm, full clear height 0..3600 (A-101, A-301)
COL_SIZE = 600.0
COLUMNS = [
    ("COL-A1", 8400.0, 8400.0),
    ("COL-B1", 16800.0, 8400.0),
    ("COL-C1", 25200.0, 8400.0),
    ("COL-A2", 8400.0, 16800.0),
    ("COL-B2", 16800.0, 16800.0),
    ("COL-C2", 25200.0, 16800.0),
]

# Cabinet rows (A-101, A-601): (row_id, y_cl, facing, bay_tokens)
# Tokens: ("C1", n), ("N1", n), ("CU", 1), ("CA", 1), ("SP", 1), ("GAP600", n)
ROW_START_X = 1800.0  # Tile D (index 3 * 600)
CAB_DEPTH = 1200.0
CAB_HEIGHT = 2000.0

ROWS = [
    (
        "A",
        3000.0,
        "SOUTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 1), ("C1", 3),
            ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "B",
        6000.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 2), ("CU", 1),
            ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "C",
        8400.0,
        "SOUTH",
        [
            ("C1", 3), ("CU", 1), ("C1", 6), ("GAP600", 2), ("CU", 1),
            ("CA", 1), ("N1", 1), ("C1", 4), ("CU", 1), ("SP", 1),
            ("C1", 1), ("GAP600", 2), ("C1", 3),
        ],
    ),
    (
        "D",
        11400.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 3), ("N1", 2), ("C1", 2),
            ("CU", 1), ("CA", 1), ("C1", 7), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "E",
        13800.0,
        "SOUTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("N1", 1), ("C1", 1),
            ("CU", 1), ("CA", 1), ("C1", 6), ("SP", 1), ("CU", 1), ("C1", 5),
        ],
    ),
    (
        "F",
        16800.0,
        "NORTH",
        [
            ("C1", 4), ("CU", 1), ("C1", 5), ("GAP600", 2), ("CU", 1),
            ("CA", 1), ("N1", 2), ("C1", 5), ("SP", 1), ("GAP600", 1),
            ("CU", 1), ("C1", 4),
        ],
    ),
]

TOKEN_WIDTH = {
    "C1": 600.0,
    "N1": 800.0,
    "CU": 600.0,
    "CA": 1200.0,
    "SP": 600.0,
    "GAP600": 600.0,
}

# Perimeter CRAHs (A-601, M-101): 1200 x 900 x 2000, facing NORTH
# Tiles B01, P01, AC01, AQ01 -> X = 600, 9000, 16800, 25200; Y = 0
PERIMETER_CRAHS = [
    ("CRAH-01", 600.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-02", 9000.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-03", 16800.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
    ("CRAH-04", 25200.0, 0.0, 1200.0, 900.0, 2000.0, "NORTH"),
]

# PDUs (A-101 Note 8, A-601, E-101): 762 x 813 x 1959
# Front flush with served row front face
PDUS = [
    ("PDU-01", "A", 21000.0, 2400.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-02", "B", 21600.0, 6600.0 - 813.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-03", "C", 21000.0, 7800.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-04", "D", 21600.0, 12000.0 - 813.0, 762.0, 813.0, 1959.0, "NORTH"),
    ("PDU-05", "E", 21000.0, 13200.0, 762.0, 813.0, 1959.0, "SOUTH"),
    ("PDU-06", "F", 21600.0, 17400.0 - 813.0, 762.0, 813.0, 1959.0, "NORTH"),
]

# Containment roofs (A-602): CAC-BC (Y_cl=7200), CAC-DE (Y_cl=12600)
# Roof width 1400, thickness 55.5, underside 2000, split at cross aisle
CONTAINMENT_ROOF_W = 1400.0
CONTAINMENT_ROOF_THK = 55.5
CONTAINMENT_ROOF_Z = 2000.0

# Pathway section dimensions (A-602, E-101, M-101)
CT_W, CT_H = 683.0, 127.0       # Telecom cable tray (CT-1)
BW_W, BW_H = 128.0, 147.0       # Power busway (BW-1)
CHW_OD = 168.3                  # Insulated DN100 CHW pipe (CHW-1)
CHW_R = CHW_OD / 2.0


# =============================================================================
# 2. GEOMETRY & IFC HELPERS
# =============================================================================

def facing_angle_rad(facing: str) -> float:
    """Rotation about Z so local -Y (or +Y) aligns with facing direction.
    Convention: 0 = NORTH (+Y), pi = SOUTH (-Y), -pi/2 = EAST (+X), pi/2 = WEST (-X).
    """
    return {
        "NORTH": 0.0,
        "SOUTH": math.pi,
        "EAST": -math.pi / 2.0,
        "WEST": math.pi / 2.0,
    }[facing]


def placement_matrix(cx_mm: float, cy_mm: float, z_mm: float, rot_z: float = 0.0) -> np.ndarray:
    """4x4 placement matrix with translations in METRES (for ifcopenshell.api)."""
    c = math.cos(rot_z)
    s = math.sin(rot_z)
    m = np.eye(4, dtype=float)
    m[0, 0] = c
    m[0, 1] = -s
    m[1, 0] = s
    m[1, 1] = c
    m[0, 3] = cx_mm / 1000.0
    m[1, 3] = cy_mm / 1000.0
    m[2, 3] = z_mm / 1000.0
    return m


def make_box_rep(model, body_ctx, w_mm: float, d_mm: float, h_mm: float):
    """Create a centered rectangular extrusion of size (w_mm, d_mm, h_mm) along +Z."""
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
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def make_cyl_rep(model, body_ctx, radius_mm: float, length_mm: float):
    """Create a circular extrusion of given radius and length along +Z."""
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
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def axis_segment_matrix(p0, p1) -> tuple:
    """Return (4x4 placement matrix in metres, length_mm) for an axis-aligned segment p0->p1
    whose local +Z axis points from p0 to p1, and local +Y is vertical (+Z world) for
    horizontal segments (or +Y world for vertical segments).
    """
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dz = p1[2] - p0[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        raise ValueError(f"Zero-length segment: {p0} -> {p1}")

    z_axis = np.array([dx / length, dy / length, dz / length], dtype=float)
    if abs(z_axis[2]) < 0.99:
        # Horizontal segment: local Y = world +Z (height), local X = Y x Z (width)
        y_axis = np.array([0.0, 0.0, 1.0], dtype=float)
        x_axis = np.cross(y_axis, z_axis)
        x_axis /= np.linalg.norm(x_axis)
    else:
        # Vertical segment
        x_axis = np.array([1.0, 0.0, 0.0], dtype=float)
        y_axis = np.cross(z_axis, x_axis)
        y_axis /= np.linalg.norm(y_axis)

    m = np.eye(4, dtype=float)
    m[0:3, 0] = x_axis
    m[0:3, 1] = y_axis
    m[0:3, 2] = z_axis
    m[0, 3] = p0[0] / 1000.0
    m[1, 3] = p0[1] / 1000.0
    m[2, 3] = p0[2] / 1000.0
    return m, length


def add_pset(model, elem, name: str, props: dict):
    pset = ifcopenshell.api.pset.add_pset(model, product=elem, name=name)
    ifcopenshell.api.pset.edit_pset(model, pset=pset, properties=props)


# =============================================================================
# 3. MODEL BUILDER
# =============================================================================

def build_model() -> ifcopenshell.file:
    model = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1"
    )
    ifcopenshell.api.unit.assign_unit(
        model, length={"is_metric": True, "raw": "MILLIMETRE"}
    )

    model_ctx = ifcopenshell.api.context.add_context(model, context_type="Model")
    body_ctx = ifcopenshell.api.context.add_context(
        model,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_ctx,
    )

    site = ifcopenshell.api.root.create_entity(model, ifc_class="IfcSite", name="Site")
    building = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuilding", name="Phase 1"
    )
    storey = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcBuildingStorey", name="Data Hall 1"
    )
    ifcopenshell.api.aggregate.assign_object(model, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=site, products=[building])
    ifcopenshell.api.aggregate.assign_object(model, relating_object=building, products=[storey])

    def place_element(elem, rep, mat):
        ifcopenshell.api.spatial.assign_container(
            model, relating_structure=storey, products=[elem]
        )
        ifcopenshell.api.geometry.assign_representation(
            model, product=elem, representation=rep
        )
        ifcopenshell.api.geometry.edit_object_placement(
            model, product=elem, matrix=mat
        )

    # -------------------------------------------------------------------------
    # A. Access Floor (35 mm panel, top at FF = 0 -> z = -35..0)
    # -------------------------------------------------------------------------
    floor_elem = ifcopenshell.api.root.create_entity(
        model, ifc_class="IfcSlab", predefined_type="FLOOR", name="Access Floor"
    )
    floor_elem.ObjectType = "AccessFloor"
    floor_rep = make_box_rep(model, body_ctx, ROOM_W, ROOM_D, ACCESS_FLOOR_THK)
    place_element(
        floor_elem,
        floor_rep,
        placement_matrix(ROOM_W / 2.0, ROOM_D / 2.0, -ACCESS_FLOOR_THK),
    )

    # -------------------------------------------------------------------------
    # B. Structural Columns (600 x 600, z = 0..3600)
    # -------------------------------------------------------------------------
    col_rep = make_box_rep(model, body_ctx, COL_SIZE, COL_SIZE, SOFFIT_Z)
    for col_name, cx, cy in COLUMNS:
        col = ifcopenshell.api.root.create_entity(
            model, ifc_class="IfcColumn", predefined_type="COLUMN", name=col_name
        )
        place_element(col, col_rep, placement_matrix(cx, cy, 0.0))

    # -------------------------------------------------------------------------
    # C. Server Cabinets & In-Row CRAHs
    # -------------------------------------------------------------------------
    rep_c1 = make_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT)
    rep_n1 = make_box_rep(model, body_ctx, 800.0, CAB_DEPTH, CAB_HEIGHT)
    rep_cu = make_box_rep(model, body_ctx, 600.0, CAB_DEPTH, CAB_HEIGHT)

    row_spans = {}  # row_id -> (west_end_x, ca_start_x, ca_end_x, east_end_x)

    for row_id, y_cl, facing, tokens in ROWS:
        x = ROW_START_X
        cab_idx = 0
        cu_idx = 0
        ca_start = None
        ca_end = None
        rot = facing_angle_rad(facing)

        for tok, count in tokens:
            w = TOKEN_WIDTH[tok]
            for _ in range(count):
                cx = x + w / 2.0
                if tok in ("C1", "N1"):
                    cab_idx += 1
                    tag = f"RACK-{row_id}{cab_idx:02d}"
                    rack = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcFurniture",
                        predefined_type="USERDEFINED",
                        name=tag,
                    )
                    rack.ObjectType = "Rack"
                    place_element(
                        rack,
                        rep_c1 if tok == "C1" else rep_n1,
                        placement_matrix(cx, y_cl, 0.0, rot),
                    )
                    add_pset(
                        model,
                        rack,
                        "Pset_DCM_Rack",
                        {
                            "Row": row_id,
                            "Tag": tag,
                            "CabinetType": tok,
                            "Facing": facing,
                            "Width_mm": float(w),
                            "Depth_mm": float(CAB_DEPTH),
                            "Height_mm": float(CAB_HEIGHT),
                            "RU": 42,
                        },
                    )
                elif tok == "CU":
                    cu_idx += 1
                    tag = f"CRAH-{row_id}{cu_idx:02d}"
                    crah = ifcopenshell.api.root.create_entity(
                        model,
                        ifc_class="IfcUnitaryEquipment",
                        predefined_type="AIRHANDLER",
                        name=tag,
                    )
                    crah.ObjectType = "CRAH"
                    place_element(crah, rep_cu, placement_matrix(cx, y_cl, 0.0, rot))
                    add_pset(
                        model,
                        crah,
                        "Pset_DCM_Equipment",
                        {
                            "Tag": tag,
                            "EquipmentType": "InRowCRAH",
                            "Row": row_id,
                            "Facing": facing,
                            "Capacity_kW": 50.0,
                        },
                    )
                elif tok == "CA":
                    ca_start = x
                    ca_end = x + w
                x += w
        row_spans[row_id] = (ROW_START_X, ca_start, ca_end, x)

    # -------------------------------------------------------------------------
    # D. Perimeter CRAHs (CRAH-01..04)
    # -------------------------------------------------------------------------
    rep_perim_crah = make_box_rep(model, body_ctx, 1200.0, 900.0, 2000.0)
    for tag, x0, y0, w, d, h, facing in PERIMETER_CRAHS:
        crah = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcUnitaryEquipment",
            predefined_type="AIRHANDLER",
            name=tag,
        )
        crah.ObjectType = "CRAH"
        place_element(
            crah,
            rep_perim_crah,
            placement_matrix(x0 + w / 2.0, y0 + d / 2.0, 0.0, facing_angle_rad(facing)),
        )
        add_pset(
            model,
            crah,
            "Pset_DCM_Equipment",
            {
                "Tag": tag,
                "EquipmentType": "PerimeterCRAH",
                "Facing": facing,
                "Capacity_kW": 100.0,
            },
        )

    # -------------------------------------------------------------------------
    # E. PDUs (PDU-01..06)
    # -------------------------------------------------------------------------
    rep_pdu = make_box_rep(model, body_ctx, 762.0, 813.0, 1959.0)
    for tag, row_id, x0, y0, w, d, h, facing in PDUS:
        pdu = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcElectricDistributionBoard",
            predefined_type="DISTRIBUTIONBOARD",
            name=tag,
        )
        pdu.ObjectType = "PDU"
        place_element(
            pdu,
            rep_pdu,
            placement_matrix(x0 + w / 2.0, y0 + d / 2.0, 0.0, facing_angle_rad(facing)),
        )
        add_pset(
            model,
            pdu,
            "Pset_DCM_Equipment",
            {
                "Tag": tag,
                "EquipmentType": "PDU",
                "ServesRow": row_id,
                "Facing": facing,
                "Rating_kVA": 225.0,
            },
        )

    # -------------------------------------------------------------------------
    # F. Cold-Aisle Containment Roofs (CAC-BC at Y=7200, CAC-DE at Y=12600)
    # -------------------------------------------------------------------------
    for cac_tag, y_cl, row_south, row_north in [
        ("CAC-BC", 7200.0, "B", "C"),
        ("CAC-DE", 12600.0, "D", "E"),
    ]:
        s_w, s_ca0, s_ca1, s_e = row_spans[row_south]
        n_w, n_ca0, n_ca1, n_e = row_spans[row_north]
        # West half and East half of containment roof (split at cross aisle)
        west_x0 = min(s_w, n_w)
        west_x1 = min(s_ca0, n_ca0)
        east_x0 = max(s_ca1, n_ca1)
        east_x1 = max(s_e, n_e)

        for part_idx, (x0, x1) in enumerate([(west_x0, west_x1), (east_x0, east_x1)], 1):
            length = x1 - x0
            roof = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcCovering",
                predefined_type="CEILING",
                name=f"{cac_tag}-ROOF-{part_idx}",
            )
            roof.ObjectType = "ContainmentRoof"
            roof_rep = make_box_rep(
                model, body_ctx, length, CONTAINMENT_ROOF_W, CONTAINMENT_ROOF_THK
            )
            place_element(
                roof,
                roof_rep,
                placement_matrix((x0 + x1) / 2.0, y_cl, CONTAINMENT_ROOF_Z),
            )

    # -------------------------------------------------------------------------
    # G. Sprinkler Heads (63 ceiling + 16 in-aisle, F-101)
    # -------------------------------------------------------------------------
    rep_sprinkler = make_cyl_rep(model, body_ctx, 25.0, 25.4)
    ceiling_xs = [1500.0 + 3000.0 * i for i in range(9)]
    ceiling_ys = [1500.0 + 3000.0 * j for j in range(7)]

    head_idx = 0
    for gy in ceiling_ys:
        for gx in ceiling_xs:
            head_idx += 1
            hx, hy = gx, gy
            # Relocate heads interrupted by column 1500x1500 keep-out (F-101 Detail 2)
            for _, cx, cy in COLUMNS:
                if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                    hx = cx - 900.0
                    hy = cy - 900.0
            sp = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SPR-CLG-{head_idx:02d}",
            )
            place_element(
                sp,
                rep_sprinkler,
                placement_matrix(hx, hy, CEILING_DEFLECTOR_Z),
            )
            add_pset(
                model,
                sp,
                "Pset_DCM_Sprinkler",
                {
                    "SprinklerType": "Ceiling",
                    "DeflectorElevation_mm": CEILING_DEFLECTOR_Z,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    # 16 In-aisle heads (8 in CAC-BC at Y=7200, 8 in CAC-DE at Y=12600)
    in_aisle_xs = [2400.0, 4800.0, 7200.0, 9600.0, 12000.0, 14400.0, 16800.0, 18600.0]
    ia_idx = 0
    for y_cl in (7200.0, 12600.0):
        for hx in in_aisle_xs:
            ia_idx += 1
            sp = ifcopenshell.api.root.create_entity(
                model,
                ifc_class="IfcFireSuppressionTerminal",
                predefined_type="SPRINKLER",
                name=f"SPR-AISLE-{ia_idx:02d}",
            )
            place_element(
                sp,
                rep_sprinkler,
                placement_matrix(hx, y_cl, IN_AISLE_DEFLECTOR_Z),
            )
            add_pset(
                model,
                sp,
                "Pset_DCM_Sprinkler",
                {
                    "SprinklerType": "InAisle",
                    "DeflectorElevation_mm": IN_AISLE_DEFLECTOR_Z,
                    "Standoff_mm": SPRINKLER_STANDOFF,
                },
            )

    # -------------------------------------------------------------------------
    # H. MEP Routing — 3 Services, Clash-Free, End-to-End Connected
    # -------------------------------------------------------------------------
    # Service 1: Power Busway (BW-1) — Overhead at z = 2900 mm center
    #   z = 2826.5..2973.5 (226.5 mm above 2600 clear, 601.1 mm below deflector)
    bw_z = 2900.0
    bw_half = BW_W / 2.0
    bw_segments = [
        ("BW-ENTRY", (0.0, 9900.0, bw_z), (1000.0 - bw_half, 9900.0, bw_z)),
        ("BW-TRUNK", (1000.0, 4500.0 - bw_half, bw_z), (1000.0, 15300.0 + bw_half, bw_z)),
        ("BW-BR-AB", (1000.0 + bw_half, 4500.0, bw_z), (19000.0, 4500.0, bw_z)),
        ("BW-BR-CD", (1000.0 + bw_half, 9900.0, bw_z), (19000.0, 9900.0, bw_z)),
        ("BW-BR-EF", (1000.0 + bw_half, 15300.0, bw_z), (19000.0, 15300.0, bw_z)),
    ]
    for name, p0, p1 in bw_segments:
        mat, length = axis_segment_matrix(p0, p1)
        seg = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcCableSegment",
            predefined_type="BUSBARSEGMENT",
            name=name,
        )
        seg.ObjectType = "BW-1"
        rep = make_box_rep(model, body_ctx, BW_W, BW_H, length)
        place_element(seg, rep, mat)
        add_pset(
            model,
            seg,
            "Pset_DCM_Service",
            {
                "Service": "PowerBusway",
                "PathwayTag": "BW-1",
                "Elevation_mm": bw_z,
                "Zone": "Overhead",
                "Width_mm": BW_W,
                "Height_mm": BW_H,
            },
        )

    # Service 2: Telecom Cable Tray (CT-1) — Under-floor plenum at z = -250 mm center
    #   z = -313.5..-186.5 (131.5 mm clear below -55 limit; >3000 mm from Busway)
    ct_z = -250.0
    ct_half = CT_W / 2.0
    ct_segments = [
        ("CT-ENTRY", (0.0, 9900.0, ct_z), (1000.0 - ct_half, 9900.0, ct_z)),
        ("CT-TRUNK", (1000.0, 4500.0 - ct_half, ct_z), (1000.0, 15300.0 + ct_half, ct_z)),
        ("CT-BR-AB", (1000.0 + ct_half, 4500.0, ct_z), (19000.0, 4500.0, ct_z)),
        ("CT-BR-CD", (1000.0 + ct_half, 9900.0, ct_z), (19000.0, 9900.0, ct_z)),
        ("CT-BR-EF", (1000.0 + ct_half, 15300.0, ct_z), (19000.0, 15300.0, ct_z)),
    ]
    for name, p0, p1 in ct_segments:
        mat, length = axis_segment_matrix(p0, p1)
        seg = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcCableCarrierSegment",
            predefined_type="CABLETRAYSEGMENT",
            name=name,
        )
        seg.ObjectType = "CT-1"
        rep = make_box_rep(model, body_ctx, CT_W, CT_H, length)
        place_element(seg, rep, mat)
        add_pset(
            model,
            seg,
            "Pset_DCM_Service",
            {
                "Service": "TelecomTray",
                "PathwayTag": "CT-1",
                "Elevation_mm": ct_z,
                "Zone": "UnderFloor",
                "Width_mm": CT_W,
                "Height_mm": CT_H,
            },
        )

    # Service 3: Chilled-Water Pipe (CHW-1) — Under-floor plenum at z = -600 mm center
    #   z = -684.15..-515.85 (202.35 mm clear below Tray, 215.85 mm above slab)
    #   Never enters 1800 mm dedicated space above PDUs; serves all rows + perimeter CRAHs
    chw_z = -600.0
    chw_segments = [
        ("CHW-ENTRY", (0.0, 9900.0, chw_z), (1000.0 - CHW_R, 9900.0, chw_z)),
        ("CHW-TRUNK", (1000.0, 1500.0 - CHW_R, chw_z), (1000.0, 15300.0 + CHW_R, chw_z)),
        ("CHW-BR-PERIM", (1000.0 + CHW_R, 1500.0, chw_z), (25800.0, 1500.0, chw_z)),
        ("CHW-BR-AB", (1000.0 + CHW_R, 4500.0, chw_z), (19000.0, 4500.0, chw_z)),
        ("CHW-BR-CD", (1000.0 + CHW_R, 9900.0, chw_z), (19000.0, 9900.0, chw_z)),
        ("CHW-BR-EF", (1000.0 + CHW_R, 15300.0, chw_z), (19000.0, 15300.0, chw_z)),
    ]
    for name, p0, p1 in chw_segments:
        mat, length = axis_segment_matrix(p0, p1)
        seg = ifcopenshell.api.root.create_entity(
            model,
            ifc_class="IfcPipeSegment",
            predefined_type="RIGIDSEGMENT",
            name=name,
        )
        seg.ObjectType = "CHW-1"
        rep = make_cyl_rep(model, body_ctx, CHW_R, length)
        place_element(seg, rep, mat)
        add_pset(
            model,
            seg,
            "Pset_DCM_Service",
            {
                "Service": "ChilledWater",
                "PathwayTag": "CHW-1",
                "Elevation_mm": chw_z,
                "Zone": "UnderFloor",
                "OD_mm": CHW_OD,
            },
        )

    return model


if __name__ == "__main__":
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    ifc_model = build_model()
    ifc_model.write(OUT_PATH)
    print(f"Wrote IFC4 model to {OUT_PATH}")
