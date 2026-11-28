### Summary

#### Deliverables
- `output/solution.py`: Self-contained Python script (stdlib + `numpy` + `ifcopenshell==0.8.4`) that rebuilds `hall_seed000_d000` (27,000 × 21,000 mm) from baked-in drawing-set literals and routes telecom cable tray (`CT-1`), power busway (`BW-1`), and insulated chilled-water piping (`CHW-1`) into an IFC4 file written to `sys.argv[1]` (default `output/model.ifc`).
- `output/reconciliation.json`: Optional drawing-note reconciliation log recording extracted datums, section sizes, zones, and applied clearances.

#### Checks Run (`/tmp/scratch/checks.py`)
All checks passed on the 272 generated solids:
- **Entity counts**: 128 racks (Rows A–F), 6 structural columns, 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs, 1 access floor panel, 4 containment roof panels + 8 end doors, 79 sprinklers (63 ceiling + 16 in-aisle).
- **Hard clashes**: Exhaustive pairwise 3D AABB sweep across all 272 solids (excluding 45 same-service junction pairs, explicitly reported) — **0 hard clashes** (> 2 mm overlap). Caught and fixed an initial 100 mm overlap between `COL-02` and `RACK-C15` by setting the common cross-aisle east edge to `x = 11,400 mm` (tile 19/20, matching all six rows' `LAST TILE` in A-601).
- **Connectivity**: Each service (`tray`, `busway`, `chw`) forms 1 connected component reaching its west-wall service entry at `(0, 9900)` (distance 0.0 mm).
- **Coverage**: All 6 rows covered ≥ 80% along their length within 2500 mm by all three services; CHW reaches all 22 CRAHs (max distance 1465.8 mm ≤ 2500 mm).
- **Code compliance**:
  - Overhead `CT-1` at `z = 2850..2977 mm` (≥ 2600 mm headroom; ≥ 460 mm below 3574.6 mm ceiling sprinkler deflector plane).
  - Under-floor `BW-1` at `z = -250..-103 mm` and `CHW-1` (insulated OD 168.3 mm) at `z = -600..-431.7 mm` (both within `[-900, -55] mm`, ≥ 20 mm below the `-35 mm` access-floor panel underside).
  - Tray–busway minimum separation: 2953.0 mm (≥ 300 mm).
  - PDU 1800 mm dedicated electrical space above all 6 PDUs: clear of CHW piping.
- **Total centreline lengths**: tray 84.50 m, busway 84.50 m, CHW 92.70 m.
- **Static checks**: `ast.parse` clean, no PNG/image imports or reads, required IFC4 classes and `Pset_DCM_*` property sets present.

#### Assumptions & Unverified Items
- **Unverified**: Because `ifcopenshell` is unavailable in this container, `build_ifc()` and `express_rules=True` validation could not be executed at runtime; IFC4 entity classes, predefined types (`IfcCableSegment`/`BUSBARSEGMENT`, `IfcCableCarrierSegment`/`CABLETRAYSEGMENT`, `IfcPipeSegment`/`RIGIDSEGMENT`, `IfcFurniture`/`USERDEFINED`/`"Rack"`), 2D profile definitions, and metre-scaled placement matrices were verified by construction and static inspection.
- **Assumptions**: `Pset_DCM_*` property names follow the drawing schedules; shared E-W headers at `y = 7200` (Rows B/C), `y = 12600` (Rows D/E), and `y = 2000` (CHW Row A + perimeter CRAHs) satisfy the 2500 mm lateral service-reach rule while minimizing total run length.