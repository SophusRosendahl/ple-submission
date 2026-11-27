### Summary of Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script (using `ifcopenshell==0.8.4` + `numpy` only, no PNG reads at runtime) that builds the coordinated IFC4 model for Meridian Data Center — Data Hall 1 (`hall_seed000_d000`) and writes it to `sys.argv[1]` (default `output/model.ifc`).
  - **Background model**: 1 access floor panel (`27000 × 21000 × 35` mm at `Z = [-35, 0]`), 6 full-height structural columns (`600 × 600 × 3600` mm on grid A/B/C × 1/2), 128 server cabinets (119 × C1 + 9 × N1 across Rows A–F with exact bay sequences and facings), 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs (`762 × 813 × 1959` mm), 2 cold-aisle containment assemblies (4 roof panels + 8 end doors split at the cross aisle), and 79 sprinkler heads (63 ceiling at `+3574.6` mm + 16 in-aisle at `+1890` mm).
  - **MEP routing** (all axis-aligned straight segments from entry `(0, 9900)`):
    - **BW-1 (Power Busway, `128 × 147` mm)**: Overhead at `Z = [2800, 2947]` mm (spine `X = 1200`, hot-aisle branches at `Y = 4500, 9900, 15300` to `X = 18600`, total `64.2 m`).
    - **CT-1 (Telecom Cable Tray, `683 × 127` mm)**: Under-floor plenum at `Z = [-220, -93]` mm (same spine and branches, total `64.2 m`).
    - **CHW-1 (Chilled-Water Pipe, `168.3` mm insulated OD)**: Under-floor plenum at `Z = [-600.0, -431.7]` mm (spine `X = 1200`, hot-aisle branches at `Y = 4500, 9900, 15300` to `X = 18600`, plus perimeter CRAH branch at `Y = 450` to `X = 25800`, total `92.85 m`).
- **`output/reconciliation.json`**: Optional drawing-note reconciliation log summarizing extracted dimensions, clearances, and how each was applied.

### Checks Run
Ran `/tmp/scratch/checks.py` against `solution.build_model_data()` and `python3 -m py_compile output/solution.py`:
- **Element counts**: Verified 128 racks, 6 columns, 22 CRAHs, 6 PDUs, 1 access floor, 4 containment roofs, 8 containment doors, 79 sprinklers.
- **Zero hard clashes (> 2 mm)**: Swept all background–background, MEP–background, and cross-service MEP–MEP pairs — **0 clashes**.
- **Connectivity**: Verified each service (`CT-1`, `BW-1`, `CHW-1`) forms a single connected network reaching `(0, 9900)`.
- **Coverage**: Verified ≥ 80% row coverage within 2500 mm for all 6 rows across all 3 services, and CHW within 2500 mm of all 22 CRAHs.
- **Code compliance**: Verified overhead headroom (`2800 ≥ 2600` mm), ceiling sprinkler standoff (`627.6 ≥ 460` mm), under-floor panel clearance (`58 ≥ 20` mm), tray–busway separation (`2893 ≥ 300` mm), and zero CHW in any PDU's 1800 mm dedicated space.

### Assumptions & Unverified Items
- **Not verified in this container**: `ifcopenshell` is unavailable in the container environment, so `build_ifc()` and `express_rules=True` validation could not be executed here; `build_ifc()` was authored strictly against `ifcopenshell==0.8.4` IFC4 API conventions (millimetre project units, placement translations in metres, `IfcRectangleProfileDef`/`IfcCircleProfileDef` without 3D profile points, and `Pset_DCM_*` property sets).