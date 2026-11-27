### Summary of Deliverables
- **`output/solution.py`**: Self-contained Python script (using `ifcopenshell==0.8.4` and `numpy` only, with all drawing dimensions baked in as literals) that builds the coordinated IFC4 model for `dc_model__hall_seed000_d000` and writes it to `sys.argv[1]` (default `output/model.ifc`).
  - **Background fit-out**: 128 server/distributor racks (`IfcFurniture`/`USERDEFINED`/`"Rack"` with `Pset_DCM_Rack`), 6 full-height structural columns (`400 × 400 × 3600 mm`), 4 perimeter CRAHs + 18 in-row CRAHs (`IfcUnitaryEquipment` with `Pset_DCM_CRAH`), 6 PDUs (`IfcElectricDistributionBoard` with `Pset_DCM_PDU`), 35 mm access floor (`27000 × 21000 mm`), 2 cold-aisle containment systems (`CAC-BC`, `CAC-DE`: 4 roof panels + 8 end doors), and 79 sprinkler heads (63 ceiling + 16 in-aisle).
  - **MEP routing**:
    - Telecom cable tray (`CT-1`, `683 × 127 mm`, 8 segments, `127.05 m`): overhead at `z = 2970..3097 mm` (clear of 2600 mm headroom, 477.6 mm below ceiling sprinkler deflectors, offset clear of columns in Rows C and F).
    - Power busway (`BW-1`, `128 × 147 mm`, 8 segments, `124.30 m`): under-floor plenum at `z = -250..-103 mm` (providing >3000 mm vertical separation from cable tray and 68 mm clearance below the 35 mm access floor panel).
    - Chilled-water pipe (`CHW-1`, DN100, insulated OD `168.3 mm`, 9 segments, `151.75 m`): under-floor plenum at `z_centre = -515.85 mm`, serving all 6 cabinet rows and all 4 perimeter CRAHs while remaining completely outside the 1800 mm dedicated space above every PDU.
- **`output/reconciliation.json`**: Optional diagnostic log of numeric clearances, sizes, and spacings reconciled across all seven sheets (`A-101`, `A-301`, `A-601`, `A-602`, `M-101`, `E-101`, `F-101`).

### Checks Run
- **`python3 /tmp/scratch/checks.py`** (all passed):
  - Verified exact element counts (128 racks, 6 columns, 4 perimeter CRAHs, 18 in-row CRAHs, 6 PDUs, 63 ceiling + 16 in-aisle sprinklers).
  - Verified zero hard clashes (> 2 mm AABB overlap) across all background solids and all three MEP services (including 168.3 mm insulated pipe OD). Caught and resolved an initial column-width clash (`CRAH-F03` vs `COL-B2`) by setting structural columns to `400 × 400 mm`.
  - Verified single connected component per service reaching entry `(0, 9900)`, ≥ 80% row coverage within 2500 mm across every row, and CHW within 2500 mm of all 22 CRAHs.
  - Verified headroom (≥ 2600 mm), under-floor plenum bounds (`-900` to `-55 mm`), 460 mm ceiling sprinkler standoff, ≥ 300 mm tray–busway separation, and zero CHW in the 1800 mm dedicated space above PDUs.
- **`python3 -m py_compile output/solution.py`**: Passed with no syntax errors.

### Assumptions & Unverified Items
- Because `ifcopenshell` cannot be imported in this container during the run, `write_ifc()` and `express_rules=True` validation were not executed against a live `ifcopenshell==0.8.4` runtime; IFC4 entity types, millimetre units, metre placement matrices, 2D profile definitions, and property sets were authored directly to the `ifcopenshell==0.8.4` API contract.