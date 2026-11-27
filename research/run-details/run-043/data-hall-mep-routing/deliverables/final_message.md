### Deliverables
- `output/solution.py`: Self-contained IFC4 model builder (`ifcopenshell==0.8.4` + `numpy` only) that reconstructs Data Hall 1 (`27000 × 21000 mm`) and routes all three MEP services (power busway, telecom cable tray, chilled-water pipe) with all dimensions, schedules, and elevations baked in as literals. Writes to `sys.argv[1]` (default `output/model.ifc`).
- `output/reconciliation.json`: Optional drawing-note reconciliation log mapping numeric clearances, sizes, and spacings from sheets `A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, and `M-101` to their implementation.

### Routing & Tier Summary
- **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead at `Z = [2800, 2947] mm` (`>= 2600 mm` headroom, `628 mm` clear below `+3575 mm` ceiling sprinkler deflectors), west trunk at `X = 600 mm` from entry `(0, 9900)` with 6 row branches offset clear of columns on Grid 1 (`Y = 8400`) and Grid 2 (`Y = 16800`).
- **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum at `Z = [-250, -123] mm` (`88 mm` clear below `-35 mm` access-floor panel underside, `2923 mm` vertical separation from busway), west trunk at `X = 600 mm` from entry `(0, 9900)` with 6 row branches.
- **Chilled-Water Pipe (`CHW-1`, OD 168.3 mm incl. 25.4 mm insulation)**: Under-floor plenum at `Zc = -565.85 mm` (`Z = [-650, -481.7] mm`, clear of slab, tray, and all PDU dedicated electrical spaces), west trunk at `X = 600 mm` from entry `(0, 9900)`, 6 row branches (covering all 18 in-row CRAHs), and a south perimeter header at `Y = 450 mm` to `X = 25800 mm` (reaching all 4 perimeter CRAHs).

### Verification (`/tmp/scratch/checks.py`)
- **Syntax**: `py_compile` passed on `output/solution.py`.
- **Element counts**: 128 racks (119 C1 + 9 N1), 6 structural columns, 22 CRAHs (18 in-row + 4 perimeter), 6 PDUs, 1 access floor, 4 containment roof panels + 8 end doors, 79 sprinkler heads (63 ceiling + 16 in-aisle).
- **Hard clashes**: All-pairs AABB sweep across all 279 solids (38,781 pairs; same-service junctions excluded) — **0 clashes > 2 mm**.
- **Connectivity & coverage**: All 3 services form 1 connected network reaching `(0, 9900)`, cover `>= 80%` of every row within `2500 mm`, and CHW reaches all 22 CRAHs within `2500 mm`.
- **Code compliance**: Overhead headroom `>= 2600 mm`, sprinkler standoff `<= 3115 mm`, under-floor within `[-900, -55] mm`, minimum tray–busway separation `2923.0 mm >= 300 mm`, and zero CHW intrusion into the `1800 mm` dedicated space above any PDU.

### Assumptions & Unverified Items
- `ifcopenshell` is not importable in this container, so runtime IFC generation and `ifcopenshell.validate(..., express_rules=True)` were not executed here; IFC4 schema calls, millimetre project units, metre placement translations, 2D profiles, and `Pset_DCM_*` property sets were authored and checked statically.
- Structural columns are modelled at `400 × 400 mm` centred on Grid `(A,B,C) × (1,2)` so Row F's single `-600` structural gap clears Column B2 without clashing `CRAH-F03`.