### Deliverables
- **`output/solution.py`**: Self-contained Python script (`ifcopenshell==0.8.4` + `numpy` only, no PNG reads) that builds the IFC4 coordination model and MEP routing for Data Hall 1 (`hall_seed000_d000`) and writes to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model containing:
  - Spatial hierarchy: `IfcProject` → `IfcSite` → `IfcBuilding` → `IfcBuildingStorey` (`Data Hall 1`), millimetre project units, placement translations in metres, 2D profiles only.
  - Coordination background: 128 racks (`IfcFurniture`/`USERDEFINED`/`"Rack"`), 6 full-height structural columns (`IfcColumn`), 22 CRAHs (4 perimeter + 18 in-row, `IfcUnitaryEquipment`), 6 PDUs (`IfcElectricDistributionBoard`), 35 mm access floor (`IfcSlab`), cold-aisle containment roofs (`IfcCovering`) and end doors (`IfcDoor`), and 79 sprinkler heads (63 ceiling + 16 in-aisle, `IfcFireSuppressionTerminal`).
  - Coordinated MEP routes from the West wall service entry `(0, 9900)` using shared hot-aisle branches (`Y = 4500, 9900, 15300`) and a perimeter CHW branch (`Y = 1500`):
    - Power Busway (`BW-1`, 128 × 147 mm): overhead at `Z = 2610..2757 mm` (6 segments, 66.40 m).
    - Telecom Cable Tray (`CT-1`, 683 × 127 mm): under-floor plenum at `Z = -200..-73 mm` (6 segments, 66.40 m).
    - Chilled Water (`CHW-1`, insulated OD 168.3 mm): under-floor plenum at `Z_center = -500 mm` (`Z = -584.15..-415.85 mm`, 7 segments, 94.20 m).
- **`output/reconciliation.json`**: Diagnostic side file recording extracted drawing datums, clearances, and tier elevations.

### Checks Run (`/tmp/scratch/checks.py`)
1. **IFC4 Schema Validation (`express_rules=True`)**: Passed with 0 errors.
2. **Element Counts**: Verified 128 racks, 6 columns, 22 CRAHs, 6 PDUs, 79 sprinkler heads, 1 access floor slab, and all 3 MEP services.
3. **Hard Clash Check (> 2 mm AABB overlap)**: Passed with 0 clashes between MEP services and background elements or between different MEP services (using 168.3 mm insulated OD for CHW).
4. **Connectivity**: Verified each of the 3 services forms 1 connected network reaching the service entry `(0, 9900)`.
5. **Coverage**: Verified ≥ 80% row length coverage within 2500 mm across all 6 rows for all 3 services, and CHW within 2500 mm of all 22 CRAHs (including all 4 perimeter units).
6. **Code Compliance**: Verified overhead headroom ≥ 2600 mm, under-floor plenum within `[-900, -55]`, ceiling sprinkler standoff ≥ 460 mm (`Z_max <= 3114.6 mm`), tray–busway separation ≥ 300 mm (2683 mm vertically everywhere), and zero CHW piping in the 1800 mm dedicated space above PDUs.

### Assumptions & Unverified Items
- Structural columns are modelled as 600 × 600 mm centered on grid intersections `(A/B/C) × (1/2)`, matching the omitted bay widths (`2–600`) and F-101 Detail 2.
- Optional hangers/supports and service drops/terminations were not modelled.
- Visual inspection of the rendered 3D IFC geometry in an external BIM viewer was not performed; verification relied on `ifcopenshell.geom` world-coordinate AABB checks and `express_rules=True` validation.