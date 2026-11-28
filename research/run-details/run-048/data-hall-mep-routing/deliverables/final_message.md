### Deliverables
- `output/solution.py` — Self-contained IFC4 generator (`ifcopenshell==0.8.4` + `numpy`, headless, deterministic, no image reads) writing to `sys.argv[1]` (default `output/model.ifc`).
- `output/model.ifc` — Generated IFC4 model (270 geometric items: 128 racks, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, 6 structural columns, access floor slab, 2 cold-aisle containment systems with 4 roof panels and 8 end doors, 63 ceiling + 16 in-aisle sprinkler heads, and 16 butt-jointed MEP segments).
- `output/reconciliation.json` — Optional drawing-note reconciliation log summarizing extracted dimensions, datums, and clearances from all 7 sheets.

### Routing & Coordination Summary
- **Shared 3-header topology**: Three East–West headers at `Y = 4500` (Rows A & B, to `X = 18600`), `Y = 9900` (Rows C & D, to `X = 18600`), and `Y = 15300` (Rows E & F, to `X = 19800`), fed from a North–South trunk at `X = 900` connected to the West service entry `(0, 9900)`.
- **Tiering**:
  - `BW-1` (Power Busway, `128 × 147 mm`): Overhead at `z = 2700 mm` (`2626.5..2773.5 mm`, clear of `2600 mm` headroom and `3114.6 mm` sprinkler standoff).
  - `CT-1` (Telecom Cable Tray, `683 × 127 mm`): Under-floor plenum at `z = -250 mm` (`-313.5..-186.5 mm`, >2800 mm vertical separation from `BW-1`).
  - `CHW-1` (Chilled Water Pipe, insulated OD `168.3 mm`): Under-floor plenum at `z = -700 mm` (`-784.15..-615.85 mm`), plus a perimeter CRAH header at `Y = 2000 mm` (`X = 984.15..25200 mm`), completely clear of the 1800 mm dedicated electrical space above all PDUs.

### Last `evaluate` Result
- **Build**: `python3 output/solution.py output/model.ifc` exited with `0`.
- **Schema**: `valid (express rules checked)`.
- **Status**: `READY (270 items, 15 checks)` — 0 violations across all checks:
  - `C1_no_clash`: 0 clashes across 36,315 pairs (0 excluded).
  - `C2_conn_ct`, `C2_conn_bw`, `C2_conn_chw`: 1 connected component each, reaching `(0, 9900)`.
  - `C3_cov_rows`: all rows served ≥ 80% by all three services (lowest coverage 84%).
  - `C4_cov_crah`: all 22 CRAHs within 2500 mm of `CHW`.
  - `C5_vert_zones`, `C6_ct_bw_sep`, `C7_chw_pdu`, `C8_cnt_*`: all pass.
- **Objective (total route length)**: `223,861 mm` (`BW`: 65,872 mm, `CHW`: 92,548 mm, `CT`: 65,442 mm).

### Checker Revisions & Assumptions
- Rewrote `C7_chw_pdu` (v1 → v3) only to fix a Python array-indexing error in the custom check code; no requirement thresholds were loosened.
- Structural columns are modelled as `600 × 600 mm` centred on grid intersections (`X = 8400, 16800, 25200`, `Y = 8400, 16800`), and ceiling sprinkler heads within the 1500 mm column keep-out are relocated clear of columns per F-101 Note 3.
- Optional supports/hangers and service drops were not modelled.