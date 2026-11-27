I have built and verified the coordinated IFC4 model generator for Data Hall 1 (`hall_seed000_d000`).

### Deliverables
- **`output/solution.py`**: Self-contained Python script (`ifcopenshell==0.8.4` + `numpy` only, no external/PNG reads) that builds the IFC4 model in millimetre project units and writes it to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model (282 geometric products).
- **`output/reconciliation.json`**: Drawing-note reconciliation log summarizing extracted datums, clearances, service tiers, and equipment counts.

### Model & Routing Summary
- **Coordination background**: 27,000 × 21,000 mm access floor (35 mm panel, top at ±0), 6 structural columns (600 × 600 mm, Z = 0..3600 mm on grids A/B/C × 1/2), 128 server/distributor cabinets (`IfcFurniture`/`USERDEFINED`/`Rack`) across Rows A–F with exact bay sequences and facings, 18 in-row CRAHs + 4 perimeter CRAHs (`CRAH-01`..`04`), 6 PDUs (`PDU-01`..`06`), cold-aisle containment (`CAC-BC`, `CAC-DE` roofs and end doors), and 79 sprinkler heads (63 ceiling at +3574.6 mm + 16 in-aisle at +1890 mm).
- **MEP routing** (all three services connected to the West service entry at `X = 0, Y = 9900` mm, serving 100% of every rack row):
  - **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead tier at centreline `Z = +3013.5` mm (bottom `+2940` mm ≥ 2600 mm headroom; top `+3087` mm ≥ 487.6 mm clear below ceiling sprinkler deflectors); Rows C and F offset −450 mm in Y to clear the structural columns.
  - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum at centreline `Z = -186.5` mm (top `-123` mm, 88 mm clear below the −35 mm floor panel underside; > 3000 mm vertical separation from `BW-1`).
  - **Chilled Water (`CHW-1`, DN100 insulated OD 168.3 mm)**: Under-floor plenum at centreline `Z = -515.85` mm (clear of `CT-1`, structural slab, and PDU dedicated electrical space), serving all 6 rows (18 in-row CRAHs) plus a perimeter header along `Y = 450` mm directly beneath `CRAH-01`..`04`.

### Verification
- `ifcopenshell.validate.validate(..., express_rules=True)`: **0 issues**.
- 3D bounding-box clash check (> 2 mm overlap across all 282 solids): **0 hard clashes**.
- Connectivity & coverage: `BW-1` (9 segments), `CT-1` (9 segments), and `CHW-1` (10 segments) are each a single connected network; max 2D distance from all 22 CRAHs to `CHW-1` is **0.0 mm**.