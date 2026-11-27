### Summary of Deliverables
- **`output/solution.py`**: Self-contained IFC4 model builder (`ifcopenshell==0.8.4` + `numpy` only, no PNG reads or network access) writing to `sys.argv[1]` (default `output/model.ifc`).
  - Rebuilds the full coordination background from the 7-sheet drawing set: access floor (`27000 × 21000 × 35 mm`), 6 full-height structural columns (`600 × 600 × 3600 mm` at Grids A/B/C × 1/2), 128 server/distributor cabinets (`IfcFurniture`/`USERDEFINED`/`"Rack"` with facing rotations about footprint centres), 22 CRAHs (18 in-row + 4 perimeter), 6 PDUs, cold-aisle containment (`CAC-BC` and `CAC-DE`, 4 roof panels + 8 end doors), and 79 sprinkler heads (63 ceiling at `+3574.6 mm`, 16 in-aisle at `+1890 mm`).
  - Routes all three MEP services as single connected axis-aligned networks from the West wall entry `(0, 9900)` along the three column-free hot aisles (`Y = 4500, 9900, 15300`), plus a South perimeter CRAH header (`Y = 1500`) for CHW:
    - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum (`Z = -300.0..-173.0 mm`, 64.80 m total, 5 segments).
    - **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead Tier 1 (`Z = 2620.0..2767.0 mm`, 65.80 m total, 5 segments).
    - **Chilled Water (`CHW-1`, 168.3 mm insulated OD)**: Overhead Tier 2 (`Z = 2850.0..3018.3 mm`, 93.00 m total, 6 segments).
  - Includes `Pset_DCM_*` property sets, millimetre project units with metre placement translations (`is_si=True`), 2D profile extrusions only, and `ifcopenshell.validate.validate(..., express_rules=True)`.
- **`output/reconciliation.json`**: Optional side file logging 8 key numeric notes extracted from the seven sheets and how each was applied.

### Checks Run (`/tmp/scratch/checks.py`)
1. **Element counts**: Verified 128 racks, 6 columns, 22 CRAHs, 6 PDUs, 4 containment roofs, 8 end doors, 79 sprinklers, and 1 access floor.
2. **Hard clashes**: Verified zero > 2 mm AABB overlaps across all services and background elements.
3. **Connectivity**: Verified each of `CT`, `BW`, and `CHW` forms a single connected network reaching `(0, 9900)`.
4. **Row & CRAH coverage**: Verified >= 80% length coverage within 2500 mm for all 6 rows by all 3 services, and CHW within 2500 mm of all 22 CRAHs.
5. **Code compliance**: Verified >= 2600 mm overhead headroom, >= 460 mm sprinkler standoff below `+3574.6 mm` deflectors, >= 20 mm under-floor clearance below `-35 mm` floor panel, >= 300 mm tray–busway separation (2793 mm vertical), zero CHW in the 1800 mm dedicated space above PDUs, and 168.3 mm insulated CHW OD.
6. **Static checks**: Verified Python AST syntax, no PNG reading, IFC4/Pset conventions, and valid JSON in `output/reconciliation.json`.

### Assumptions & Unverified Items
- **Unverified**: Because `ifcopenshell` cannot be imported in this container during the run, `build_ifc()` and `ifcopenshell.validate.validate(..., express_rules=True)` were not executed here; all geometry, clash, connectivity, and compliance checks were verified against `build_geometry_data()`.
- **Assumptions**: Structural columns were modeled conservatively at `600 × 600 mm` centered on grid intersections; standard IFC4 classes (`IfcColumn`, `IfcSlab`, `IfcUnitaryEquipment`, `IfcElectricDistributionBoard`, `IfcFireSuppressionTerminal`, `IfcCableCarrierSegment`, `IfcCableSegment`, `IfcPipeSegment`) and `Pset_DCM_*` property sets were used.