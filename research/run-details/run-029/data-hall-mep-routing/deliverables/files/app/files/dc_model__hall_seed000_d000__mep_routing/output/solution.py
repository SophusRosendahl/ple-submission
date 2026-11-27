"""Coordinated 3D IFC4 model builder for Meridian Data Center - Hall 1 (hall_seed000_d000).

Builds the architectural/structural/MEP coordination background from the 7-sheet
drawing set (A-101, A-301, A-601, A-602, M-101, E-101, F-101) and routes the
three services (CT-1 telecom cable tray, BW-1 power busway, CHW-1 chilled water)
clash-free and code-compliant.

Usage:
    python3 output/solution.py [output_path.ifc]
"""
import math
import sys
import numpy as np

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "output/model.ifc"

# ---------------------------------------------------------------------------
# 1. Baked drawing data (all dimensions in millimetres)
# ---------------------------------------------------------------------------
ROOM_W = 27000.0
ROOM_D = 21000.0
SOFFIT_Z = 3600.0
SLAB_Z = -900.0
FLOOR_THK = 35.0
DEFLECTOR_Z = 3574.6
IN_AISLE_DEFLECTOR_Z = 1890.0
MIN_HEADROOM = 2600.0
X_ROW_START = 1800.0
X_CA_EAST = 11400.0

# Row definitions from A-101 & A-601
ROW_SPECS = [
    ("A", 5, "SOUTH", ["4C1", "CU", "3C1", "N1", "3C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("B", 10, "NORTH", ["4C1", "CU", "5C1", "2N1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("C", 14, "SOUTH", ["3C1", "CU", "6C1", "2-600", "CU", "CA", "N1", "4C1", "CU", "SP", "C1", "2-600", "3C1"]),
    ("D", 19, "NORTH", ["4C1", "CU", "3C1", "2N1", "2C1", "CU", "CA", "7C1", "SP", "CU", "5C1"]),
    ("E", 23, "SOUTH", ["4C1", "CU", "5C1", "N1", "C1", "CU", "CA", "6C1", "SP", "CU", "5C1"]),
    ("F", 28, "NORTH", ["4C1", "CU", "5C1", "2-600", "CU", "CA", "2N1", "5C1", "SP", "-600", "CU", "4C1"]),
]

# Perimeter CRAHs from A-601 (1200 W x 900 D x 2000 H, faces NORTH)
PERIM_CRAHS = [
    ("CRAH-01", 1 * 600.0, 0.0),   # B01
    ("CRAH-02", 15 * 600.0, 0.0),  # P01
    ("CRAH-03", 28 * 600.0, 0.0),  # AC01
    ("CRAH-04", 42 * 600.0, 0.0),  # AQ01
]

# PDUs from A-101, A-601, E-101 (762 W x 813 D x 1959 H, front flush with row front)
PDU_SPECS = [
    ("PDU-01", "A", 35 * 600.0, 2400.0, "SOUTH"),        # AJ05
    ("PDU-02", "B", 36 * 600.0, 6600.0 - 813.0, "NORTH"),  # AK10
    ("PDU-03", "C", 35 * 600.0, 7800.0, "SOUTH"),        # AJ14
    ("PDU-04", "D", 36 * 600.0, 12000.0 - 813.0, "NORTH"),  # AK19
    ("PDU-05", "E", 35 * 600.0, 13200.0, "SOUTH"),       # AJ23
    ("PDU-06", "F", 36 * 600.0, 17400.0 - 813.0, "NORTH"),  # AK28
]

# Structural columns (600 x 600 x 3600) at grid intersections A/B/C x 1/2
COL_GRID_X = [("A", 8400.0), ("B", 16800.0), ("C", 25200.0)]
COL_GRID_Y = [("1", 8400.0), ("2", 16800.0)]
COL_SIZE = 600.0


def parse_bay_token(tok):
    """Return (count, kind) for a bay sequence token."""
    if tok == "CA":
        return (1, "CA")
    if tok == "SP":
        return (1, "SP")
    if tok == "CU":
        return (1, "CU")
    if tok == "-600":
        return (1, "OMIT600")
    if tok == "2-600":
        return (2, "OMIT600")
    if tok.endswith("C1"):
        n = int(tok[:-2]) if len(tok) > 2 else 1
        return (n, "C1")
    if tok.endswith("N1"):
        n = int(tok[:-2]) if len(tok) > 2 else 1
        return (n, "N1")
    raise ValueError(f"Unknown bay token: {tok}")


def build_model_data():
    """Construct pure-Python geometry & routing data for verification and IFC export."""
    racks = []
    crahs = []
    rows = {}

    for row_name, tile_row, facing, tokens in ROW_SPECS:
        y0 = (tile_row - 1) * 600.0
        y1 = y0 + 1200.0
        x = X_ROW_START
        rack_idx = 0
        crah_idx = 0
        x_west_end = x

        for tok in tokens:
            cnt, kind = parse_bay_token(tok)
            if kind == "CA":
                x_west_end = x
                x = X_CA_EAST
                continue
            for _ in range(cnt):
                if kind == "C1":
                    rack_idx += 1
                    w = 600.0
                    racks.append({
                        "tag": f"RACK-{row_name}{rack_idx:02d}",
                        "row": row_name,
                        "type": "C1",
                        "facing": facing,
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind == "N1":
                    rack_idx += 1
                    w = 800.0
                    racks.append({
                        "tag": f"RACK-{row_name}{rack_idx:02d}",
                        "row": row_name,
                        "type": "N1",
                        "facing": facing,
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind == "CU":
                    crah_idx += 1
                    w = 600.0
                    crahs.append({
                        "tag": f"CRAH-{row_name}{crah_idx:02d}",
                        "placement": "IN-ROW",
                        "row": row_name,
                        "facing": facing,
                        "capacity_kw": 50.0,
                        "aabb": (x, y0, 0.0, x + w, y1, 2000.0),
                    })
                    x += w
                elif kind in ("SP", "OMIT600"):
                    x += 600.0

        rows[row_name] = {
            "x_min": X_ROW_START,
            "x_west_end": x_west_end,
            "x_east_start": X_CA_EAST,
            "x_max": x,
            "y0": y0,
            "y1": y1,
            "y_c": (y0 + y1) / 2.0,
            "facing": facing,
        }

    # Perimeter CRAHs
    for tag, x0, y0 in PERIM_CRAHS:
        crahs.append({
            "tag": tag,
            "placement": "PERIMETER",
            "row": "PERIMETER",
            "facing": "NORTH",
            "capacity_kw": 100.0,
            "aabb": (x0, y0, 0.0, x0 + 1200.0, y0 + 900.0, 2000.0),
        })

    # PDUs
    pdus = []
    for tag, row_name, x0, y0, facing in PDU_SPECS:
        pdus.append({
            "tag": tag,
            "row": row_name,
            "facing": facing,
            "rating_kva": 225.0,
            "aabb": (x0, y0, 0.0, x0 + 762.0, y0 + 813.0, 1959.0),
        })

    # Structural columns
    columns = []
    for gx, cx in COL_GRID_X:
        for gy, cy in COL_GRID_Y:
            h = COL_SIZE / 2.0
            columns.append({
                "tag": f"COL-{gx}{gy}",
                "aabb": (cx - h, cy - h, 0.0, cx + h, cy + h, SOFFIT_Z),
            })

    # Cold-aisle containment (CAC-BC and CAC-DE)
    containment = []
    for cac_name, r_south, r_north in [("CAC-BC", "B", "C"), ("CAC-DE", "D", "E")]:
        y_aisle_0 = rows[r_south]["y1"]
        y_aisle_1 = rows[r_north]["y0"]
        x_w_end = min(rows[r_south]["x_west_end"], rows[r_north]["x_west_end"])
        x_e_end = min(rows[r_south]["x_max"], rows[r_north]["x_max"])
        for sec, (xs, xe) in [("W", (X_ROW_START, x_w_end)), ("E", (X_CA_EAST, x_e_end))]:
            # Roof panel (1400 wide = 100 overhang onto each row, 55.5 thick, underside at 2000)
            containment.append({
                "tag": f"{cac_name}-ROOF-{sec}",
                "kind": "ROOF",
                "aabb": (xs, y_aisle_0 - 100.0, 2000.0, xe, y_aisle_1 + 100.0, 2055.5),
            })
            # 2 end doors per section (60 thick x 1200 wide x 2055.5 high), flush outside roof ends
            containment.append({
                "tag": f"{cac_name}-DOOR-{sec}1",
                "kind": "DOOR",
                "aabb": (xs - 60.0, y_aisle_0, 0.0, xs, y_aisle_1, 2055.5),
            })
            containment.append({
                "tag": f"{cac_name}-DOOR-{sec}2",
                "kind": "DOOR",
                "aabb": (xe, y_aisle_0, 0.0, xe + 60.0, y_aisle_1, 2055.5),
            })

    # Sprinklers: 63 ceiling (9 x 7) + 16 in-aisle (8 in CAC-BC, 8 in CAC-DE)
    sprinklers = []
    idx = 0
    for iy in range(7):
        ny = 1500.0 + iy * 3000.0
        for ix in range(9):
            nx = 1500.0 + ix * 3000.0
            # Relocate heads within 750 mm of a column centre (1500 keep-out box)
            hx, hy = nx, ny
            for col in columns:
                cx = (col["aabb"][0] + col["aabb"][3]) / 2.0
                cy = (col["aabb"][1] + col["aabb"][4]) / 2.0
                if abs(hx - cx) < 750.0 and abs(hy - cy) < 750.0:
                    hy = cy - 900.0
            idx += 1
            sprinklers.append({
                "tag": f"SPR-C{idx:02d}",
                "kind": "CEILING",
                "x": hx,
                "y": hy,
                "z": DEFLECTOR_Z,
            })

    aisle_xs = [2700.0, 4800.0, 6900.0, 9000.0, 12300.0, 14400.0, 16500.0, 18600.0]
    a_idx = 0
    for ay in (7200.0, 12600.0):
        for ax in aisle_xs:
            a_idx += 1
            sprinklers.append({
                "tag": f"SPR-A{a_idx:02d}",
                "kind": "IN-AISLE",
                "x": ax,
                "y": ay,
                "z": IN_AISLE_DEFLECTOR_Z,
            })

    # -----------------------------------------------------------------------
    # 2. Clash-free, minimal-length MEP routes (axis-aligned segments)
    #    - BW-1 (Power Busway, 128 W x 147 H): Overhead at Z = 2700 mm
    #      (bottom 2626.5 > 2600 headroom; top 2773.5 < 3114.6 sprinkler standoff)
    #    - CT-1 (Telecom Cable Tray, 683 W x 127 H): Under-floor at Z = -150 mm
    #      (top -86.5 <= -55; bottom -213.5 >= -900; 2713 mm vertical sep from BW-1)
    #    - CHW-1 (Chilled Water DN100, 168.3 OD insulated): Under-floor at Z = -450 mm
    #      (top -365.85 < -213.5 CT-1 bottom; bottom -534.15 >= -900; zero PDU conflict)
    # -----------------------------------------------------------------------
    def hot_aisle_tree(z_elev, x_spine=900.0, x_end=18000.0, include_perimeter=False):
        segs = [
            # Entry from (0, 9900) to spine
            ((0.0, 9900.0, z_elev), (x_spine, 9900.0, z_elev)),
            # Spine N-S
            ((x_spine, 9900.0, z_elev), (x_spine, 15300.0, z_elev)),
            ((x_spine, 9900.0, z_elev), (x_spine, 4500.0, z_elev)),
            # 3 hot-aisle headers serving Rows A+B, C+D, E+F
            ((x_spine, 4500.0, z_elev), (x_end, 4500.0, z_elev)),
            ((x_spine, 9900.0, z_elev), (x_end, 9900.0, z_elev)),
            ((x_spine, 15300.0, z_elev), (x_end, 15300.0, z_elev)),
        ]
        if include_perimeter:
            segs.append(((x_spine, 4500.0, z_elev), (x_spine, 1500.0, z_elev)))
            segs.append(((x_spine, 1500.0, z_elev), (24000.0, 1500.0, z_elev)))
        return segs

    routes = {
        "BW-1": hot_aisle_tree(2700.0, x_spine=900.0, x_end=18000.0, include_perimeter=False),
        "CT-1": hot_aisle_tree(-150.0, x_spine=900.0, x_end=18000.0, include_perimeter=False),
        "CHW-1": hot_aisle_tree(-450.0, x_spine=900.0, x_end=18000.0, include_perimeter=True),
    }

    return {
        "racks": racks,
        "crahs": crahs,
        "pdus": pdus,
        "columns": columns,
        "containment": containment,
        "sprinklers": sprinklers,
        "rows": rows,
        "routes": routes,
    }


# ---------------------------------------------------------------------------
# 3. IFC4 Model Builder
# ---------------------------------------------------------------------------
def _make_matrix(tx_mm, ty_mm, tz_mm, rot_z_rad=0.0):
    """4x4 placement matrix with translations in METRES (required by ifcopenshell)."""
    c = math.cos(rot_z_rad)
    s = math.sin(rot_z_rad)
    return np.array([
        [c, -s, 0.0, tx_mm / 1000.0],
        [s,  c, 0.0, ty_mm / 1000.0],
        [0.0, 0.0, 1.0, tz_mm / 1000.0],
        [0.0, 0.0, 0.0, 1.0],
    ], dtype=float)


def _add_box_rep(model, body_ctx, dx, dy, dz):
    """Centered-in-XY, bottom-at-Z=0 box using 2D IfcRectangleProfileDef."""
    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=float(dx), YDim=float(dy))
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, ExtrudedDirection=dir_z, Depth=float(dz))
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _add_cyl_rep(model, body_ctx, radius, length, axis="Z"):
    """Cylinder using 2D IfcCircleProfileDef extruded along local +Z, rotated if needed."""
    profile = model.create_entity("IfcCircleProfileDef", ProfileType="AREA", Radius=float(radius))
    dir_z = model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0))
    if axis == "Z":
        pos = None
    elif axis == "X":
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, -1.0)),
        )
    else:  # Y
        pos = model.create_entity(
            "IfcAxis2Placement3D",
            Location=model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=model.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)),
            RefDirection=model.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
        )
    solid = model.create_entity(
        "IfcExtrudedAreaSolid",
        SweptArea=profile,
        Position=pos,
        ExtrudedDirection=dir_z,
        Depth=float(length),
    )
    return model.create_entity(
        "IfcShapeRepresentation",
        ContextOfItems=body_ctx,
        RepresentationIdentifier="Body",
        RepresentationType="SweptSolid",
        Items=[solid],
    )


def _assign_pset(model, elem, name, props):
    import ifcopenshell.api.pset as pset_api
    ps = pset_api.add_pset(model, product=elem, name=name)
    pset_api.edit_pset(model, pset=ps, properties=props)


def build_ifc(out_path):
    import ifcopenshell
    import ifcopenshell.api.root as root_api
    import ifcopenshell.api.unit as unit_api
    import ifcopenshell.api.context as ctx_api
    import ifcopenshell.api.aggregate as agg_api
    import ifcopenshell.api.spatial as spatial_api
    import ifcopenshell.api.geometry as geom_api

    data = build_model_data()
    model = ifcopenshell.file(schema="IFC4")

    project = root_api.create_entity(model, ifc_class="IfcProject", name="Meridian Data Center - Hall 1")
    unit_api.assign_unit(model, length={"is_metric": True, "raw": "MILLIMETRE"})

    context = ctx_api.add_context(model, context_type="Model")
    body = ctx_api.add_context(
        model, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context
    )

    site = root_api.create_entity(model, ifc_class="IfcSite", name="Meridian Site")
    building = root_api.create_entity(model, ifc_class="IfcBuilding", name="Data Hall 1 Building")
    storey = root_api.create_entity(model, ifc_class="IfcBuildingStorey", name="Data Hall 1")
    storey.Elevation = 0.0

    agg_api.assign_object(model, relating_object=project, products=[site])
    agg_api.assign_object(model, relating_object=site, products=[building])
    agg_api.assign_object(model, relating_object=building, products=[storey])

    def place_box(ifc_class, name, predef, obj_type, aabb, facing=None):
        elem = root_api.create_entity(model, ifc_class=ifc_class, name=name)
        if predef is not None and hasattr(elem, "PredefinedType"):
            elem.PredefinedType = predef
        if obj_type is not None:
            elem.ObjectType = obj_type
        x0, y0, z0, x1, y1, z1 = aabb
        dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rot = math.pi if facing == "SOUTH" else 0.0
        rep = _add_box_rep(model, body, dx, dy, dz)
        geom_api.assign_representation(model, product=elem, representation=rep)
        geom_api.edit_object_placement(model, product=elem, matrix=_make_matrix(cx, cy, z0, rot))
        spatial_api.assign_container(model, relating_structure=storey, products=[elem])
        return elem

    # Access floor
    place_box("IfcSlab", "ACCESS-FLOOR", "FLOOR", "AccessFloor", (0.0, 0.0, -FLOOR_THK, ROOM_W, ROOM_D, 0.0))

    # Structural columns
    for col in data["columns"]:
        place_box("IfcColumn", col["tag"], "COLUMN", "StructuralColumn", col["aabb"])

    # Racks
    for r in data["racks"]:
        e = place_box("IfcFurniture", r["tag"], "USERDEFINED", "Rack", r["aabb"], facing=r["facing"])
        _assign_pset(model, e, "Pset_DCM_Cabinet", {
            "Row": r["row"],
            "CabinetType": r["type"],
            "RU": 42,
            "PowerKW": 8.0,
            "LoadKg": 1363.0,
            "Facing": r["facing"],
        })

    # CRAHs
    for c in data["crahs"]:
        e = place_box("IfcUnitaryEquipment", c["tag"], "AIRHANDLER", "CRAH", c["aabb"], facing=c["facing"])
        _assign_pset(model, e, "Pset_DCM_Equipment", {
            "EquipmentType": "CRAH",
            "Placement": c["placement"],
            "ServesRow": c["row"],
            "CapacityKW": c["capacity_kw"],
            "Facing": c["facing"],
        })

    # PDUs
    for p in data["pdus"]:
        e = place_box("IfcElectricDistributionBoard", p["tag"], "DISTRIBUTIONBOARD", "PDU", p["aabb"], facing=p["facing"])
        _assign_pset(model, e, "Pset_DCM_Equipment", {
            "EquipmentType": "PDU",
            "ServesRow": p["row"],
            "RatingKVA": p["rating_kva"],
            "Facing": p["facing"],
            "DedicatedSpaceAboveMM": 1800.0,
        })

    # Containment
    for cont in data["containment"]:
        if cont["kind"] == "ROOF":
            place_box("IfcCovering", cont["tag"], "CEILING", "ContainmentRoof", cont["aabb"])
        else:
            place_box("IfcDoor", cont["tag"], "DOOR", "ContainmentDoor", cont["aabb"])

    # Sprinklers (small 50 mm diameter x 50 mm cylinder at deflector)
    for sp in data["sprinklers"]:
        elem = root_api.create_entity(model, ifc_class="IfcFireSuppressionTerminal", name=sp["tag"])
        elem.PredefinedType = "SPRINKLER"
        elem.ObjectType = "SprinklerHead"
        rep = _add_cyl_rep(model, body, 25.0, 50.0, axis="Z")
        geom_api.assign_representation(model, product=elem, representation=rep)
        geom_api.edit_object_placement(model, product=elem, matrix=_make_matrix(sp["x"], sp["y"], sp["z"], 0.0))
        spatial_api.assign_container(model, relating_structure=storey, products=[elem])
        _assign_pset(model, elem, "Pset_DCM_Sprinkler", {
            "SprinklerType": sp["kind"],
            "DeflectorElevationMM": sp["z"],
            "StandoffMM": 460.0,
        })

    # MEP Route Segments
    svc_meta = {
        "CT-1": ("IfcCableCarrierSegment", "CABLETRAYSEGMENT", "CableTray", 683.0, 127.0, 0.0),
        "BW-1": ("IfcCableCarrierSegment", "USERDEFINED", "Busway", 128.0, 147.0, 0.0),
        "CHW-1": ("IfcPipeSegment", "RIGIDSEGMENT", "ChilledWaterPipe", 168.3, 168.3, 25.4),
    }

    for svc, segs in data["routes"].items():
        ifc_cls, predef, obj_type, w, h, insul = svc_meta[svc]
        for idx, (p0, p1) in enumerate(segs, start=1):
            x0, y0, z0 = p0
            x1, y1, z1 = p1
            dx, dy, dz = abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)
            length = math.dist(p0, p1)
            zone = "UNDERFLOOR" if z0 < 0 else "OVERHEAD"
            name = f"{svc}-{idx:03d}"

            if svc == "CHW-1":
                elem = root_api.create_entity(model, ifc_class=ifc_cls, name=name)
                elem.PredefinedType = predef
                elem.ObjectType = obj_type
                axis = "X" if dx >= dy else "Y"
                sx, sy = (min(x0, x1), y0) if axis == "X" else (x0, min(y0, y1))
                rep = _add_cyl_rep(model, body, w / 2.0, length, axis=axis)
                geom_api.assign_representation(model, product=elem, representation=rep)
                geom_api.edit_object_placement(model, product=elem, matrix=_make_matrix(sx, sy, z0, 0.0))
                spatial_api.assign_container(model, relating_structure=storey, products=[elem])
            else:
                if dx >= dy:
                    aabb = (min(x0, x1), y0 - w / 2.0, z0 - h / 2.0, max(x0, x1), y0 + w / 2.0, z0 + h / 2.0)
                else:
                    aabb = (x0 - w / 2.0, min(y0, y1), z0 - h / 2.0, x0 + w / 2.0, max(y0, y1), z0 + h / 2.0)
                elem = place_box(ifc_cls, name, predef, obj_type, aabb)

            _assign_pset(model, elem, "Pset_DCM_Pathway", {
                "ServiceTag": svc,
                "ServiceType": obj_type,
                "ElevationMM": z0,
                "Zone": zone,
                "WidthMM": w,
                "HeightMM": h,
                "InsulationMM": insul,
                "LengthMM": length,
            })

    model.write(out_path)


if __name__ == "__main__":
    build_ifc(OUT_PATH)
