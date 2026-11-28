### Summary of Deliverables
- **`output/solution.py`**: Self-contained Python script (`ifcopenshell==0.8.4` + `numpy` only, no PNG reading, deterministic, ~1.6 s runtime) that builds the complete IFC4 coordination model for `hall_seed000_d000` and writes it to `sys.argv[1]` (default `output/model.ifc`).
- **`output/model.ifc`**: Generated IFC4 model (millimetre project units, placement translations in metres, 2D profile points, `Pset_DCM_*` property sets).
- **`output/reconciliation.json`**: Optional drawing-note reconciliation log summarizing extracted dimensions, clearances, and equipment counts.

### Model & Routing Overview
- **Hall fit-out rebuilt from sheets A-101, A-301, A-601, A-602, M-101, E-101, F-101**:
  - 27,000 × 21,000 mm hall, 35 mm access floor panel (`z = -35..0`), 6 structural columns (`600 × 600 mm`, full height `0..3600`).
  - 128 server/distributor cabinets (`IfcFurniture`/`USERDEFINED`/`"Rack"`) across Rows A–F with exact bay sequences, cross-aisle step, and North/South facings.
  - 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs (front flush with served row), 2 cold-aisle containment assemblies (`CAC-BC`, `CAC-DE`, roofs + end doors), and 79 sprinkler heads (63 ceiling at `z = 3574.6` + 16 in-aisle at `z = 1890`).
- **MEP Routing** (all entering at `x = 0, y = 9900`, straight axis-aligned segments with flush 0 mm-overlap junctions):
  - **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead at `z_center = 2875 mm` (`z = 2801.5..2948.5`), serving Rows A/B (`y = 4500`), C/D (`y = 9900`), and E/F (`y = 15300`).
  - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum at `z_center = -250 mm` (`z = -313.5..-186.5`), serving Rows A/B, C/D, and E/F.
  - **Chilled Water (`CHW-1`, insulated OD 168.3 mm)**: Under-floor plenum at `z_center = -600 mm` (`z = -684.15..-515.85`), serving Row A + all 4 perimeter CRAHs (`y = 1800`), Rows B/C (`y = 7200`), Rows D/E (`y = 12600`), and Row F (`y = 16800`).

### Verification & Concerns
- **`evaluate` tool**: Failed with an internal environment error (`ModuleNotFoundError: No module named '_pytest'`) after `output/solution.py` exited with 0. Recorded via `note_concern`.
- **Independent verification** (`ifcopenshell.validate` with `express_rules=True` and geometric AABB checks via `ifcopenshell.geom` in world coordinates):
  - `express_rules=True`: **0 validation issues**.
  - `C1` Hard clashes (> 2 mm): **0**.
  - `C2` Connectivity: CableTray **5/5**, Busway **5/5**, CHW **6/6** connected.
  - `C3` Row coverage (≥ 80% within 2500 mm): Tray **97.0%**, Busway **96.0%**, CHW **97.0%**.
  - `C4` CHW max distance to any CRAH: **1451.1 mm** (≤ 2500 mm).
  - `C5` Min overhead headroom: **2801.5 mm** (≥ 2600 mm).
  - `C6` Min ceiling sprinkler vertical clearance: **626.1 mm** (≥ 460 mm).
  - `C8` Min tray–busway separation: **2988.0 mm** (≥ 300 mm).
  - `C9` CHW in PDU dedicated space: **0 violations**.
  - `C10` Rack count: **128**.
  - `OBJ_length` Total route length: **210.86 m** (Tray 60.94 m, Busway 61.37 m, CHW 88.55 m).