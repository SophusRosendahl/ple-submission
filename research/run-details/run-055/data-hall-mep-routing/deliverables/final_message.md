### Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script (`ifcopenshell` + `numpy` only, no runtime PNG reads) that builds the coordinated IFC4 model of Data Hall 1 (`hall_seed000_d000`) and writes it to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model (269 elements: 128 racks across Rows A–F, 6 structural columns, 22 CRAHs [4 perimeter + 18 in-row], 6 PDUs, access floor, 2 cold-aisle containment systems with roofs & end doors, 79 sprinkler heads [63 ceiling + 16 in-aisle], and 15 MEP route segments across BW-1, CT-1, and CHW-1).
- **`output/reconciliation.json`**: Optional diagnostic reconciliation log of drawing dimensions, clearances, and how each was applied.

### Final Evaluation Result
- **Build**: `python3 output/solution.py output/model.ifc` exited with `0`.
- **Schema**: `valid (express rules checked)`.
- **Status**: `READY` — all 18 checks passed with 0 violations (`C1_no_clash`: 0 overlaps > 2 mm across 36,046 pairs, 0 excluded; `C2a–d`: all 3 services form 1 connected network reaching `(0, 9900)`; `C3a–c`: ≥ 80% row coverage within 2500 mm; `C4`: CHW within 2500 mm of all 22 CRAHs; `C5`: all segments in overhead `[2600, 3114.6]` or under-floor `[-900, -55]`; `C6`: ≥ 300 mm tray–busway separation; `C7`: no CHW in 1800 mm PDU dedicated space; `C8a–e`: exact equipment counts).
- **Scope & Self-Test**: `kinds that no geometric check selects: none`; `missed by a check: 0` across 65 kind pairs.
- **Objective (Total MEP Route Length)**: `176,302 mm` (BW `56,312 mm`, CHW `63,304 mm`, CT `56,686 mm`), optimized via `optimize` from the initial `215,861 mm`.

### Checker Changes & Assumptions
- **Checker revision (v1 → v2)**: Split `reach` out of the `connected` checks into a dedicated `C2d_reach_entry` custom check so the synthetic probe (which places test segments near `(0, 0)`) passed all 21/21 probes cleanly without weakening the `(0, 9900)` entry requirement.
- **Routing strategy**: Power busway (`BW-1`) is routed overhead at `Z = [2620, 2767]` mm (807.6 mm below ceiling sprinkler deflectors); telecom cable tray (`CT-1`) and insulated chilled-water pipe (`CHW-1`, OD `168.3 mm`) are routed in the under-floor plenum at `Z = [-200, -73]` mm and `Z_center = -450` mm respectively (per A-602 `OVERHEAD OR PLENUM` permission), guaranteeing 2693 mm tray–busway separation and zero CHW piping above PDUs.
- **Unverified / optional items**: Optional supports/hangers and service drops were not modelled; `Pset_DCM_*` property set contents were authored directly per the contract and validated against IFC4 express rules.