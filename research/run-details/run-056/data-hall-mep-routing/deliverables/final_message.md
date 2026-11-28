Delivered the coordinated IFC4 model generator and outputs for Data Hall 1 (`hall_seed000_d000`):

### Deliverables
- `output/solution.py` — self-contained deterministic Python script (`ifcopenshell==0.8.4` + `numpy`) that builds the complete hall fit-out (128 racks, 22 CRAHs, 6 PDUs, 6 full-height structural columns, 35 mm access floor, 2 cold-aisle containment systems with roofs and end doors, 63 ceiling + 16 in-aisle sprinkler heads) and clash-free MEP routes (telecom cable tray `CT-1`, power busway `BW-1`, insulated chilled-water pipe `CHW-1`) with `Pset_DCM_*` property sets, writing IFC4 to `sys.argv[1]` (default `output/model.ifc`).
- `output/model.ifc` — generated IFC4 model (270 elements).
- `output/reconciliation.json` — drawing-note reconciliation log summarizing extracted dimensions, clearances, and how each was applied.

### Final `evaluate` Result
- **Build & Schema**: `python3 output/solution.py output/model.ifc` exited 0; `SCHEMA: valid (express rules checked)`.
- **Checks**: `READY (270 items, 15 checks)` — **0 violations** across all checks:
  - `C1_no_clash`: 0 overlaps > 2 mm across all 36,315 element pairs (0 excluded, 0 missed in 65-pair self-test).
  - `C2_conn_*`: `CT`, `BW`, and `CHW` each form 1 connected component reaching the West-wall entry at `(0, 9900)`.
  - `C3_row_cov`: all 6 rack rows served along ≥ 80% of length by all three services within 2500 mm (lowest 81%).
  - `C4_crah_cov`: all 22 CRAHs (4 perimeter + 18 in-row) within 2500 mm of `CHW`.
  - `C5_C6_z_bands`: all overhead routes in `[2600, 3114.6]` mm (`CT` at `[2610, 2737]`, `CHW` at `[2920, 3088.3]`); under-floor `BW` in `[-900, -55]` mm (`[-250, -103]`).
  - `C7_tray_busway_sep`: ≥ 300 mm separation between `CT` and `BW` (2713 mm vertical separation).
  - `C8_pdu_dedicated`: 0 `CHW` segments in the 1800 mm dedicated space above any PDU.
  - `C9_*_count`: 128 racks, 22 CRAHs, 6 PDUs, 6 columns, 79 sprinklers.
- **Objective**: optimized via `optimize` from 214,937 mm down to **172,331 mm** (`BW` 50,601 mm, `CHW` 71,657 mm, `CT` 50,073 mm), with the best parameters baked into `output/solution.py` defaults.

### Check Rewrites & Assumptions
- Rewrote `set_checks` once (v1 → v2) to remove the `same_group` exclusion from `C1_no_clash` (so segment-to-segment overlaps are also checked) and fix a list-indexing bug in `C8_pdu_dedicated`.
- Assumed 600 × 600 mm structural column footprints centered on grid intersections `(A/B/C, 1/2)` and routed `BW-1` in the permitted under-floor plenum (`A-602`, `A-301` Note 3) to guarantee ≥ 300 mm tray–busway separation everywhere.