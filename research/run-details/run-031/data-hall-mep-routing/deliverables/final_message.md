### Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script that builds the IFC4 model of Data Hall 1 (`hall_seed000_d000`) using `ifcopenshell==0.8.4` and `numpy` only, with all drawing dimensions baked in as literals, writing to `sys.argv[1]` (default `output/model.ifc`).
  - **Coordination background**: 128 server/distributor racks (rows A–F with exact bay sequences and facings), 6 structural columns (600 × 600 mm, FF 0 to +3600 mm), 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs (front flush with served rows), 35 mm access floor, 4 cold-aisle containment roofs + 8 end doors (`CAC-BC`, `CAC-DE`), and 79 sprinkler heads (63 ceiling at +3574.6 mm with column keep-out relocations + 16 in-aisle at +1890 mm).
  - **Coordinated MEP routing** (total centreline length 229.10 m: telecom 67.5 m, busway 67.5 m, CHW 94.1 m): All three services enter at `(0, 9900)` and route via a West service trunk (`x = 900`) and three shared hot-aisle headers (`y = 4500, 9900, 15300`, `x = 900..19500`), plus a CHW perimeter header (`y = 1500`, `x = 900..24500`) serving `CRAH-01..04`.
    - Busway (`BW-1`, 128 × 147 mm): overhead at `z_c = 2950 mm` (`[2876.5, 3023.5]`, 551.1 mm below ceiling deflectors).
    - Telecom cable tray (`CT-1`, 683 × 127 mm): under-floor plenum at `z_c = -200 mm` (`[-263.5, -136.5]`, > 3000 mm vertical separation from busway, 81.5 mm below `-55 mm` plenum limit).
    - Chilled-water pipe (`CHW-1`, extruded at 168.3 mm insulated OD): under-floor plenum at `z_c = -600 mm` (`[-684.15, -515.85]`, clear of all PDUs and columns).
- **`output/reconciliation.json`**: Optional drawing-note reconciliation log summarizing extracted dimensions, clearances, and how each was applied.

### Checks Run (`/tmp/scratch/checks.py`)
All checks passed on `solution.build_scene()` and `output/solution.py`:
- **Element counts**: Verified 128 racks, 6 columns, 22 CRAHs, 6 PDUs, 4 containment roofs, 8 containment doors, and 79 sprinklers.
- **Hard clashes**: Pairwise 3D AABB overlap check (> 2 mm tolerance) across all background solids and route segments — 0 clashes.
- **Connectivity & coverage**: Verified each service forms one connected axis-aligned network reaching `(0, 9900)`, covers ≥ 80% of every rack row within 2500 mm, and CHW is within 2500 mm of all 22 CRAHs.
- **Code compliance**: Verified 2600 mm clear height, 460 mm ceiling sprinkler standoff, 300 mm tray–busway separation, 1800 mm PDU dedicated electrical space, 20 mm under-floor clearance, and 168.3 mm insulated CHW OD.
- **Static contract checks**: Verified valid Python AST, no PNG reading or network calls, and presence of IFC4 classes and `Pset_DCM_*` property sets.

### Assumptions & Unverified Items
- **IFC4 execution / `express_rules=True`**: Because `ifcopenshell` is not importable in this container during the run, `write_ifc()` and `express_rules=True` validation were not executed live; all `ifcopenshell==0.8.4` API calls, 2D profiles, metre-unit placement matrices, and right-handed rotation matrices were verified by inspection.
- **IFC4 classes & `Pset_DCM_*` names**: Standard IFC4 classes (`IfcFurniture`, `IfcColumn`, `IfcUnitaryEquipment`, `IfcElectricDistributionBoard`, `IfcCovering`, `IfcBuildingElementProxy`, `IfcFireSuppressionTerminal`, `IfcCableCarrierSegment`, `IfcCableSegment`, `IfcPipeSegment`) and `Pset_DCM_*` property sets were used consistently as noted in `/tmp/scratch/requirements.md`.