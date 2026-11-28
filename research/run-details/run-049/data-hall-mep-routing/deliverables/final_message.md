### Summary

**Deliverables**
- `output/solution.py`: Self-contained deterministic Python script using `ifcopenshell==0.8.4` and `numpy` only, baking in all coordinates, dimensions, and schedules extracted from the 7 drawing sheets (`A-101`, `A-301`, `A-601`, `A-602`, `M-101`, `E-101`, `F-101`).
- `output/model.ifc`: Generated IFC4 model (270 geometric elements: 128 racks, 6 structural columns, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, 35 mm access floor panel, 2 cold-aisle containment systems with roofs and end doors, 63 ceiling sprinkler heads, 16 in-aisle sprinkler heads, and 16 axis-aligned MEP pathway segments with `Pset_DCM_*` property sets).
- `output/reconciliation.json`: Optional drawing-note reconciliation log documenting extracted datums, clearances, and sizes.

**Routing Strategy**
- **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Routed in the overhead plenum (`Z = 2850..2977 mm`, >= 2600 mm headroom and > 597 mm below ceiling sprinkler deflectors) from entry `(0, 9900)` along 3 hot-aisle headers (`Y = 4500, 9900, 15300`) serving all 6 rows.
- **Power Busway (`BW-1`, 128 × 147 mm)**: Routed in the under-floor plenum (`Z = -600..-453 mm`, within `[-900, -55]`) from `(0, 9900)` along `Y = 4500, 9900, 15300`, achieving > 3300 mm vertical separation from `CT-1` everywhere.
- **Chilled Water (`CHW-1`, insulated OD 168.3 mm)**: Routed in the under-floor plenum (`Z = -350..-181.7 mm`) from `(0, 9900)` along `Y = 2500` (serving all 4 perimeter CRAHs and Row A), `Y = 7200` (Rows B & C), `Y = 12600` (Rows D & E), and `Y = 15300` (Row F), with zero intrusion into the 1800 mm dedicated electrical space above PDUs.

**Final `evaluate` Result**
- `SCHEMA: valid (express rules checked)`
- `EVALUATION: READY (270 items, 18 checks)` — 0 failures, 0 clashes across 36,315 pairs (0 exclusions), 0 missed self-test overlaps.
- **Objective (total route length)**: `204,961 mm` (`CT: 60,042 mm`, `BW: 60,172 mm`, `CHW: 84,748 mm`).

**Checker Revisions**
- Updated `set_checks` once (v1 → v2) to fix a `TypeError` in the `chw_pdu_ded` custom check and to split service-entry reach (`reach_entry`) from the `connected` checks so all 21 synthetic probes passed.

**Assumptions & Unverified Items**
- Structural columns modelled as 600 × 600 mm centered on grid intersections `(A/B/C, 1/2)`.
- Optional supports/hangers and vertical service drops were not modelled.