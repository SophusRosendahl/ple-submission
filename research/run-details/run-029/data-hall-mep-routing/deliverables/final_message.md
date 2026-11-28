### Deliverables
- **`output/solution.py`**: Self-contained IFC4 model builder using `ifcopenshell` + `numpy` only, with all dimensions, bay sequences, equipment schedules, sprinkler positions, and MEP routes baked in as literals. Writes to `sys.argv[1]` (default `output/model.ifc`) in millimetre project units with metre placement-matrix translations, 2D profile definitions, and `Pset_DCM_*` property sets.
- **`output/reconciliation.json`**: Optional diagnostic log of numeric clearances, sizes, and datums reconciled across `A-101`, `A-301`, `A-601`, `A-602`, `M-101`, `E-101`, and `F-101`.

### Routing Summary
- **`BW-1` (Power Busway, 128 × 147 mm)**: Overhead at `Z = 2700 mm` (`2626.5..2773.5 mm`), 3 hot-aisle headers (`y = 4500, 9900, 15300`) from a West service-strip spine (`x = 900`) connected to `(0, 9900)`. Total length: **63.00 m**.
- **`CT-1` (Telecom Cable Tray, 683 × 127 mm)**: Under-floor plenum at `Z = -150 mm` (`-213.5..-86.5 mm`), same 3-header topology. Total length: **63.00 m**. Vertical separation from `BW-1`: **2713 mm** (≥ 300 mm everywhere).
- **`CHW-1` (Chilled Water DN100, 168.3 mm OD insulated)**: Under-floor plenum at `Z = -450 mm` (`-534.15..-365.85 mm`), same 3-header topology plus a south perimeter header at `y = 1500` (`x = 900..24000`) serving `CRAH-01..04`. Total length: **89.10 m**.

### Checks Run (`/tmp/scratch/checks.py`)
All checks passed:
- **Element counts**: 128 racks, 22 CRAHs (18 in-row + 4 perimeter), 6 PDUs, 6 structural columns, 79 sprinklers (63 ceiling + 16 in-aisle), access floor, and containment roofs/doors.
- **Zero hard clashes (> 2 mm)**: Verified across all background-vs-background, service-vs-background, and service-vs-service solid AABBs (including 168.3 mm insulated CHW OD).
- **Connectivity & coverage**: Each service forms 1 connected component reaching `(0, 9900)`; all 6 rows covered ≥ 80% within 2500 mm by all 3 services; `CHW-1` within 2500 mm of all 22 CRAHs.
- **Code compliance**: Overhead headroom ≥ 2600 mm; ceiling sprinkler standoff ≥ 460 mm below `3574.6 mm`; under-floor clearance ≥ 20 mm below panel (`-35 mm`) and above slab (`-900 mm`); tray–busway separation ≥ 300 mm; no `CHW-1` in the 1800 mm dedicated space above any PDU.
- **Static check**: Verified no `.png` references in `output/solution.py`.

### Assumptions & Unverified Items
- **Assumptions**: Structural columns modelled as `600 × 600 mm` centered on gridlines `A/B/C × 1/2`; containment end doors placed flush outside the roof panel ends (`[xs-60, xs]` and `[xe, xe+60]`) to avoid roof-door overlap.
- **Not verified in container**: Because `ifcopenshell` cannot be imported in this environment, runtime IFC generation and `ifcopenshell.validate(..., express_rules=True)` were not executed here.