### Deliverables
- `output/solution.py`: Self-contained IFC4 model builder (`ifcopenshell==0.8.4` + `numpy` only) writing to `sys.argv[1]` (default `output/model.ifc`), with all drawing dimensions baked as literals.
  - **Coordination background**: 128 server/distributor racks (`IfcFurniture`/`USERDEFINED`/`"Rack"`), 4 perimeter + 18 in-row CRAHs (`IfcUnitaryEquipment`/`AIRHANDLER`), 6 PDUs (`IfcElectricDistributionBoard`/`DISTRIBUTIONBOARD`), 6 full-height structural columns (`IfcColumn`), 27000 × 21000 × 35 mm access floor (`IfcSlab`/`FLOOR`), cold-aisle containment roofs and end doors for `CAC-BC` and `CAC-DE` (`IfcBuildingElementProxy`), and 63 ceiling + 16 in-aisle sprinkler heads (`IfcFireSuppressionTerminal`/`SPRINKLER`), all with `Pset_DCM_*` property sets.
  - **Coordinated MEP routes** (all straight axis-aligned segments from the West wall service entry at `X=0, Y=9900`):
    - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Overhead at `Z = [2800.0, 2927.0]` mm (`63.00 m`, 5 segments) along hot-aisle centrelines (`Y = 4500, 9900, 15300`).
    - **Power Busway (`BW-1`, 128 × 147 mm)**: Under-floor plenum at `Z = [-273.5, -126.5]` mm (`63.00 m`, 5 segments).
    - **Chilled Water (`CHW-1`, 168.3 mm insulated OD)**: Under-floor plenum at `Z = [-684.15, -515.85]` mm (`91.20 m`, 6 segments), serving all 6 rows and extending along `Y = 1200` to reach all 4 perimeter CRAHs (`CRAH-01`..`CRAH-04`).
    - **Total MEP length**: `217.20 m`.
- `output/reconciliation.json`: Optional diagnostic log of numeric clearances, sizes, and spacings reconciled across the seven sheets.

### Checks Run (`/tmp/scratch/checks.py` & `py_compile`)
- **Element counts**: Verified 128 racks, 22 CRAHs, 6 PDUs, 6 columns, 79 sprinklers.
- **Hard clashes (> 2 mm)**: Verified zero clashes across background-vs-background, MEP-vs-background, and MEP-vs-MEP (including 168.3 mm insulated CHW OD).
- **Connectivity & coverage**: Verified each service forms one connected network reaching `(0, 9900)`, >= 80% coverage along every rack row (within 2500 mm across the row), and CHW within 2500 mm of all 22 CRAHs.
- **Code compliance**: Verified overhead headroom (>= 2600 mm), ceiling sprinkler standoff (top <= 3114.6 mm, 647.6 mm below deflectors), under-floor zone (`[-900, -55]` mm, >= 20 mm below floor panel), tray–busway separation (`2926.5 mm >= 300 mm`), and zero CHW inside the 1800 mm dedicated electrical space above PDUs.
- **Syntax**: `python3 -m py_compile output/solution.py` passed.

### Assumptions & Unverified Items
- Structural column cross-section is modelled as `400 × 400 mm` centered on grid intersections `(8400/16800/25200, 8400/16800)` so it clears `CRAH-F03` at `X = 17000`; all MEP routes stay >= 1500 mm from column centrelines.
- `ifcopenshell` is not installed in this container, so live IFC4 export and `express_rules=True` validation could not be executed here and will run in the grading environment.