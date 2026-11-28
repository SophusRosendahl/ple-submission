### Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script using `ifcopenshell==0.8.4` and `numpy` only (no PNG reading, no network). Rebuilds the `hall_seed000_d000` data hall (27,000 × 21,000 mm, access floor, 6 structural columns, 128 racks across Rows A–F, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, cold-aisle containment roofs/doors for CAC-BC and CAC-DE, and 79 sprinkler heads: 63 ceiling + 16 in-aisle) and routes all three MEP services.
- **`output/model.ifc`**: Generated IFC4 model (mm project units, placement translations in metres, 2D profiles, `Pset_DCM_*` property sets).
- **`output/reconciliation.json`**: Optional diagnostic log of extracted drawing datums, service tiers, and achieved clearances.

### Final `evaluate` Result
- **Build**: `python3 output/solution.py output/model.ifc` exited with `0`.
- **Schema**: `valid (express rules checked)`.
- **Checks**: `READY (270 items, 18 checks)` — 18/18 passed:
  - `clash_all`: 0 violations across 36,315 pairs (0 excluded, 0 missed in 65-pair self-test).
  - `conn_tray`, `conn_busway`, `conn_chw`, `reach_entry`: 1 connected component per service reaching `(0, 9900)`.
  - `cov_tray`, `cov_busway`, `cov_chw`: >= 85% coverage on every rack row (threshold 80% within 2500 mm).
  - `crah_chw`: all 22 CRAHs within 2500 mm of CHW.
  - `mep_zones`: all 16 MEP segments within overhead `[2600, 3115]` or under-floor `[-900, -55]` zones (478 mm clear below 3575 mm ceiling sprinkler deflectors).
  - `sep_tray_busway`: 3073 mm vertical separation (CT-1 in under-floor plenum `z = -250..-123`, BW-1 overhead `z = 2950..3097`), exceeding the 300 mm requirement everywhere.
  - `chw_pdu_clear`: 0 violations in the 1800 mm dedicated space above PDUs.
  - Element counts: 128 racks, 22 CRAHs, 6 PDUs, 6 columns, 79 sprinklers.
- **Objective (total MEP route length)**: **197,337 mm** (BW 58,072 mm, CHW 81,748 mm, CT 57,517 mm), reduced by 20,500 mm from the initial 217,837 mm layout.

### Checker Revisions & Assumptions
- **Checker revision (v1 → v2)**: Moved the `(0, 9900)` entry reach check from `connected.reach` to a dedicated `reach_entry` custom check so the synthetic probe (which places test segments near `(0, 0)`) passed 21/21 probes while keeping the exact 500 mm reach requirement.
- **Assumptions**: Structural columns were modelled at 400 × 400 mm centered on grid intersections `X ∈ {8400, 16800, 25200}`, `Y ∈ {8400, 16800}` so Column B-2 clears Row F's omitted `-600` bay cleanly; the common East edge of the cross-aisle was placed at `x = 11400 mm`, matching every row's `LAST TILE` in schedule A-601.
- **Not verified**: Optional supports/hangers and service drops were not modelled.