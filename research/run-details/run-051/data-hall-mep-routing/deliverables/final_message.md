### Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script (`ifcopenshell==0.8.4` + `numpy`) that builds the full IFC4 data hall coordination model in millimetres (placement translations in metres, 2D profile points only) with `Pset_DCM_*` property sets and writes to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model (270 elements: 1 access floor slab, 6 structural columns, 128 racks across Rows A–F, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, 4 containment roof panels, 8 containment end doors, 63 ceiling + 16 in-aisle sprinkler heads, and 16 coordinated MEP segments).
- **`output/reconciliation.json`**: Drawing-note reconciliation log summarizing extracted datums, pathway sections, tiers, and applied clearances.

### Routing & Coordination Summary
- **Shared comb topology** from the west-wall service entry `(0, 9900)`:
  - Middle header at `Y = 9900` (serving Rows C & D), spine at `X = 2400` branching to `Y = 4500` (serving Rows A & B) and `Y = 15300` (serving Rows E & F).
  - CHW spine extends south to `Y = 1500` and east to `X = 23500` to serve all 4 perimeter CRAHs (`CRAH-01`–`CRAH-04`).
- **Vertical tiers**:
  - **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead at `Z = [2650, 2797]` mm (above 2600 mm min headroom and 777.6 mm below the 3574.6 mm ceiling sprinkler deflector plane).
  - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum at `Z = [-220, -93]` mm (≥ 20 mm below the -35 mm access floor panel underside; > 2700 mm vertical separation from busway).
  - **Chilled Water (`CHW-1`, 168.3 mm insulated OD)**: Under-floor plenum at `Z = [-600, -431.7]` mm (211 mm clear below cable tray; zero intrusion into the 1800 mm dedicated electrical space above PDUs).

### Last `evaluate` Result
- **Schema**: `valid (express rules checked)`
- **Status**: `READY (270 items, 18 checks)` — 0 failures across all checks:
  - `C1_clashes`: 0 violations (36,315 pairs examined, 0 excluded; self-test 65/65 kind pairs covered).
  - `C2a–C2d`: All 3 services form 1 connected component each and reach `(0, 9900)`.
  - `C3a–C3c`: All rack rows ≥ 85% covered within 2500 mm (≥ 80% required).
  - `C4_crah_chw`: All 22 CRAHs within 2500 mm of CHW.
  - `C5–C7`: All vertical zones, 300 mm tray–busway separation, and PDU dedicated spaces pass.
  - `C8a–C8e`: Exact counts verified (128 racks, 22 CRAHs, 6 PDUs, 6 columns, 79 sprinklers).
- **Objective (total route length)**: `194,037 mm` (`BW 56,872 mm`, `CT 56,317 mm`, `CHW 80,848 mm`).

### Checker Revisions & Assumptions
- Rewrote `set_checks` once (v1 → v2) before building: replaced `reach` inside `connected` (whose synthetic probe placed segments at `(0,0)`) with a dedicated `C2d_reach_entry` custom check, and fixed a numpy-vs-list indexing bug in `C7_pdu_dedicated`.
- Assumed 600 × 600 mm structural column cross-sections centered on gridlines A/B/C × 1/2, and cross-aisle east edge at `X = 11400` mm (verified against every row's `LAST TILE` in schedule `A-601`). Optional supports/hangers and service drops were not modeled.