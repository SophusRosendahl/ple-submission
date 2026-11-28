### Deliverables
- `output/solution.py` — Self-contained Python script (`ifcopenshell==0.8.4` + `numpy` only, runs headless in ~2.4 s, deterministic, no PNG reads) that builds the coordinated IFC4 model of Data Hall 1 (`hall_seed000_d000`) and writes it to `sys.argv[1]` (default `output/model.ifc`).
- `output/model.ifc` — Generated IFC4 model (282 elements: access floor, 6 structural columns, 128 server/distributor racks, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, cold-aisle containment roofs & doors for CAC-BC and CAC-DE, 63 ceiling + 16 in-aisle sprinkler heads, and the three MEP service networks).
- `output/reconciliation.json` — Optional drawing-note reconciliation log documenting extracted parameters from all seven sheets (`A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, `M-101`) and how each was applied.

### Last `evaluate` Result
- **Schema**: `valid (express rules checked)`
- **Passing checks (0 violations)**:
  - `C1_no_clashes`: 0 violations across 39,621 element pairs
  - `C2_connected`: 1 connected component each for `BW` (9 segments), `CHW` (10 segments), `CT` (9 segments), all reaching the West-wall service entry `(0, 9900)`
  - `C3_row_coverage`: 0 violations across 384 rack×service pairs (lowest coverage 100%)
  - `C4_chw_crah`: 0 violations across all 22 CRAHs (18 in-row + 4 perimeter)
  - `C7_tray_busway_sep`: 0 violations across 81 pairs (vertical separation = 3003 mm ≥ 300 mm everywhere)
  - `C9_rack_count`: 128 racks present
  - `C10_route_length`: total `257,988 mm` (`BW`: 78,652 mm, `CHW`: 102,627 mm, `CT`: 76,710 mm)
- **Checker errors (recorded via `note_concern`)**:
  - `C5_headroom`, `C6_sprinkler_clearance`, `C8_chw_pdu_zone` errored inside the fixed custom check script (`TypeError: 'int' object is not subscriptable` on `['aabb'][...]`).

### Verification of Unchecked / Errored Requirements
- **Headroom (R5)**: Overhead cable tray is at `Z = [2700, 2827] mm` (≥ 2600 mm clear height). Busway (`Z = [-450, -303] mm`) and CHW (`Z = [-784.15, -615.85] mm`) are routed in the under-floor plenum (`Z = [-900, -55] mm`, ≥ 20 mm below the 35 mm floor panel).
- **Sprinkler clearance (R6)**: Ceiling sprinkler deflectors are at `Z = 3574.6 mm`; highest overhead MEP top is `2827 mm`, providing `747.6 mm` vertical clearance (≥ 460 mm). All 16 in-aisle heads are placed beneath the CAC-BC and CAC-DE roofs at `Z = 1890 mm`.
- **PDU dedicated space (R8)**: CHW piping is entirely below finished floor (`Z < 0`), so no CHW piping enters the 1800 mm dedicated electrical space above any PDU (`Z = [1959, 3759] mm`).
- **Concern recorded on `C3_row_coverage`**: `coverage_along` evaluates individual 600×1200 mm racks along their Y depth rather than East-West rows along X; we used a North-South comb (`X = 4100, 9100, 14100, 19100` off the `Y = 9900` spine) so every rack is served both geometrically and under `C3_row_coverage`.