### Summary of Deliverables
- **`output/solution.py`**: Self-contained, deterministic Python script using `ifcopenshell` and `numpy` only (no PNG reading, no external files required) that builds the IFC4 model of Meridian Data Center Phase 1 — Data Hall 1 (`hall_seed000_d000`) and writes it to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model (269 solid elements) validated with `express_rules=True`.
- **`output/reconciliation.json`**: Optional diagnostic log of numeric datums, sizes, and clearances extracted from sheets `A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, and `M-101`.

### Model & Routing Highlights
- **Background fit-out**: Access floor (`27000 × 21000 × 35` mm, `z = -35..0`), 6 full-height structural columns (`400 × 400 × 3600` mm), 128 server cabinets (`119 C1 + 9 N1`, `IfcFurniture`/`USERDEFINED`/`Rack` with `Pset_DCM_Cabinet` and facing rotations), 22 CRAHs (4 perimeter + 18 in-row, `IfcUnitaryEquipment`/`AIRHANDLER`/`CRAH` with `Pset_DCM_CRAH`), 6 PDUs (`IfcElectricDistributionBoard`/`DISTRIBUTIONBOARD`/`PDU` with `Pset_DCM_PDU`), cold-aisle containment roofs and 8 end doors (`CAC-BC`, `CAC-DE`), and 79 sprinkler heads (63 ceiling at `z = 3574.6` mm + 16 in-aisle at `z = 1890` mm).
- **MEP routing**: All three services connect to the West service entry at `(0, 9900)` mm as butt-jointed, axis-aligned segments serving all 6 cabinet rows via 3 shared aisle headers (A/B, C/D, E/F):
  - **Telecom cable tray (`CT-1`, `683 × 127` mm)**: Overhead at `z = [2620, 2747]` mm (827.6 mm below ceiling sprinkler deflectors, above 2600 mm clear height).
  - **Power busway (`BW-1`, `128 × 147` mm)**: Under-floor plenum at `z = [-247, -100]` mm (> 2700 mm vertical separation from `CT-1`).
  - **Chilled-water pipe (`CHW-1`, insulated OD `168.3` mm)**: Under-floor plenum at `z = [-550, -381.7]` mm (zero intrusion into the 1800 mm dedicated space above PDUs; southern header reaches all 4 perimeter CRAHs and Rows A/B within 2500 mm).

### Final `evaluate` Result
- **Build & Schema**: `python3 output/solution.py output/model.ifc` exited `0`; `SCHEMA: valid (express rules checked)`.
- **Checks (version 3)**: `EVALUATION: READY (269 items, 14 checks)` — all 14 checks passed with `0` violations, `0` hard clashes across `36,046` pairs (`0` excluded), `0` unchecked element kinds, and `0` missed overlap pairs in self-test.
- **Objective (total MEP route length)**: Optimized via `optimize` from `200,345 mm` down to **`175,854 mm`** (`BW 55,591`, `CHW 65,227`, `CT 55,036` mm), baked into `output/solution.py` defaults and re-verified standalone.

### Checker Revisions & Assumptions
- **Checker revisions**: Rewrote `set_checks` from v1 → v3 to fix synthetic probe issues before building: removed the `same_group` exclusion on `no_clash` (so butt-jointed segments are strictly clash-checked with zero exclusions), split `entry_reach` out of `conn_mep` so connectivity probes pass cleanly, and simplified `chw_pdu_dedicated` box-overlap arithmetic.
- **Assumptions**: Structural columns were modelled at `400 × 400` mm on the `8400` mm grid intersections so they fit cleanly within the `-600` bay omissions in Row F without clashing with adjacent bays. Optional supports/hangers and service drops were not modelled.