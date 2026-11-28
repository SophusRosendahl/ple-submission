I have authored the coordinated IFC4 data-hall BIM model and MEP routing script for `hall_seed000_d000`.

### Deliverables
- **`output/solution.py`** — Self-contained Python script (`ifcopenshell==0.8.4` + `numpy`, deterministic, no external image reads) that builds the IFC4 model in millimetre project units and writes it to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`** — Generated and validated IFC4 model (`279` geometric elements).
- **`output/reconciliation.json`** — Drawing-note reconciliation log summarizing extracted hall dimensions, clearance datums, and pathway tier assignments.

### Summary of Modeled Hall & MEP Coordination
- **Coordination Background**:
  - 27,000 × 21,000 mm hall, 35 mm access floor (`Z = -35..0`), soffit at `+3600` mm, structural slab at `-900` mm.
  - 6 structural columns (`600 × 600 × 3600` mm) at grids `A/B/C × 1/2`.
  - 128 server/distributor cabinets (`IfcFurniture` / `USERDEFINED` / `"Rack"`) across Rows A–F with exact bay sequences, cross-aisle east alignment at `X = 11400` mm, and North/South facing rotations.
  - 22 CRAHs (`4` perimeter + `18` in-row), 6 PDUs (`762 × 813 × 1959` mm, fronts flush with served rows), cold-aisle containment (`CAC-BC`, `CAC-DE` roofs and end doors), and 79 sprinkler heads (`63` ceiling at `+3574.6` mm with column keep-out relocations + `16` in-aisle at `+1890` mm).
- **MEP Routing (from West wall entry at `X = 0, Y = 9900` mm)**:
  - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Routed in the under-floor plenum at `Z = -200` mm (`-263.5..-136.5` mm), serving all 6 rows and maintaining >2,800 mm separation from overhead power busway.
  - **Power Busway (`BW-1`, 128 × 147 mm)**: Routed overhead at `Z = 2700` mm (`2626.5..2773.5` mm), spine at `X = 600` mm, row branches at `Y = row_CL + 450` mm (clearing all columns and maintaining >2,600 mm headroom and >340 mm below the sprinkler standoff plane).
  - **Chilled Water (`CHW-1`, insulated OD 168.3 mm)**: Routed overhead at `Z = 2950` mm (`2865.85..3034.15` mm), spine at `X = 1200` mm, row headers at `Y = row_CL - 450` mm, and perimeter CRAH header at `Y = 900` mm to `X = 25800` mm — serving all 6 rows and all 22 CRAHs while staying clear of all PDU dedicated electrical spaces.

### Verification
- `ifcopenshell.validate.validate(..., express_rules=True)`: **0 errors**.
- 3D world-coordinate bounding-box clash check across all 279 elements: **0 hard clashes (> 2 mm)**.