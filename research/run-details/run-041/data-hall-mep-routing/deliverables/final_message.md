### Summary

- **Deliverable**: `output/solution.py` — self-contained Python script using `ifcopenshell` + `numpy` that builds the coordinated IFC4 model for `hall_seed000_d000` (millimetre project units, metre placement translations, 2D profile points, `IfcProject` → `IfcSite` → `IfcBuilding` → `IfcBuildingStorey` hierarchy, element classes and `Pset_DCM_*` property sets) and writes to `sys.argv[1]` (default `output/model.ifc`) plus an optional `reconciliation.json` alongside it.
- **Reconciled Hall & Routing Design**:
  - Background: 27,000 × 21,000 mm hall, 128 racks (119 `C1` + 9 `N1`) across Rows A–F with common cross-aisle east edge at `x = 11,200` mm, 6 structural columns (`600 × 600` mm, `z = 0..3600` mm), 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs flush with their served row fronts, 35 mm access floor (`z = -35..0` mm), 2 cold-aisle containments (`CAC-BC`, `CAC-DE`, 4 roof panels + 8 end doors), and 79 sprinkler heads (63 ceiling at `z = 3574.6` mm with column keep-out relocations + 16 in-aisle at `z = 1890` mm).
  - Routes from `(0, 9900)` mm west entry:
    - **CT-1 (Telecom Cable Tray, 683 × 127 mm)**: under-floor plenum at `z = -250` mm (`-313.5..-186.5` mm), 8 segments, 117.60 m total.
    - **BW-1 (Power Busway, 128 × 147 mm)**: overhead lower tier at `z = 2700` mm (`2626.5..2773.5` mm), Rows C & F offset ±800 mm to clear columns, 8 segments, 116.80 m total.
    - **CHW-1 (Chilled Water Pipe, 168.3 mm OD over insulation)**: overhead upper tier at `z = 2950` mm (`2865.85..3034.15` mm), serving all 6 rows plus a south perimeter header at `y = 1200` mm to `x = 25,200` mm for `CRAH-01..04`, 9 segments, 142.60 m total.
- **Checks Run** (`python3 -m py_compile output/solution.py`, `/tmp/scratch/checks.py`, and determinant check on `_pipe_matrix_m`):
  - Element counts: 128 racks, 6 columns, 22 CRAHs, 6 PDUs, 79 sprinklers, 12 containment elements.
  - Hard clashes (> 2 mm): **0** across all 25 route segments vs 254 background solids and all cross-service pairs.
  - Connectivity: **1 connected component** reaching `(0, 9900)` for each of CT, BW, and CHW.
  - Row coverage: **≥ 80%** of every row's length for all three services.
  - CRAH proximity: max distance from CHW across all 22 CRAHs = **960.5 mm** (≤ 2500 mm).
  - Code compliance: overhead headroom ≥ 2600 mm, under-floor clearance ≥ 20 mm below panel underside, min overhead sprinkler standoff **540.4 mm** (≥ 460 mm), min tray–busway separation **2813.0 mm** (≥ 300 mm), **0** CHW intrusions into the 1800 mm PDU dedicated electrical space.
  - Right-handed placement matrices (`det = +1`) verified for all pipe orientations.
- **Assumptions & Unverified Items**:
  - `ifcopenshell` is not installed in this container, so `build_ifc()` and `ifcopenshell.validate.validate(..., express_rules=True)` were not executed here; IFC4 entity types, `PredefinedType`/`ObjectType` pairs, and API calls were authored to conform to `ifcopenshell==0.8.4` and IFC4 schema rules.