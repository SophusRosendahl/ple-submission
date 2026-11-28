### Summary

**Deliverables**
- `output/solution.py` — self-contained deterministic Python script (`ifcopenshell==0.8.4` + `numpy`) that builds the IFC4 data hall model in millimetres and writes to `sys.argv[1]` (default `output/model.ifc`).
- `output/model.ifc` — generated IFC4 model (271 elements: 128 server/distributor cabinets, 18 in-row CRAHs, 4 perimeter CRAHs, 6 PDUs, 6 structural columns, access floor & structural slab, 2 cold-aisle containment systems with 4 roof panels and 8 end doors, 79 sprinkler heads [63 ceiling + 16 in-aisle], and 16 MEP route segments).
- `output/reconciliation.json` — optional diagnostic drawing-note reconciliation log.

**Design & Routing**
- **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: routed in the under-floor plenum at `Z = [-200, -73]` mm (≥ 20 mm below the `-35` mm access-floor underside), with a west spine at `X = 1800` mm and three hot-aisle headers (`Y = 4500, 9900, 15300` mm) to `X = 17200` mm.
- **Power Busway (`BW-1`, 128 × 147 mm)**: routed in the lower overhead tier at `Z = [2610, 2757]` mm (≥ 2600 mm headroom, 2683 mm vertical separation from cable tray), following the same three hot-aisle headers.
- **Chilled-Water Pipe (`CHW-1`, insulated OD 168.3 mm)**: routed in the upper overhead tier at `Z = [2940, 3108.3]` mm (466.3 mm below ceiling sprinkler deflectors at `Z = 3574.6` mm, clear of all PDU 1800 mm dedicated spaces), with three hot-aisle headers to `X = 17200` mm plus a south perimeter header at `Y = 2100` mm to `X = 23200` mm serving all four perimeter CRAHs.

**Final `evaluate` Result**
- `SCHEMA: valid (express rules checked)`
- `EVALUATION: READY (271 items, 15 checks)` — all 15 checks pass:
  - `C1_clash`: 0 violations across 36,585 pairs (0 excluded); self-test missed 0 of 76 injected overlaps.
  - `C2_conn_tray`, `C2_conn_busway`, `C2_conn_pipe`, `C2_entry`: each service forms 1 connected component reaching `(0, 9900)`.
  - `C3_row_cov`: every row served by all three services within 2500 mm (lowest coverage 85%, ≥ 80% required).
  - `C4_crah_chw`: all 22 CRAHs within 2500 mm of CHW piping.
  - `C5_headroom_and_sprinkler`, `C7_tray_busway_sep`, `C8_pdu_dedicated`, `C9_count_*`: 0 violations.
- **Objective (total route length)**: `199,137 mm` (`BW 58,672`, `CHW 82,348`, `CT 58,117`).

**Checker Revisions**
- Updated `C1_clash` from `exclude: [{"same_group": true}]` to no exclusions (segments abut cleanly without overlap), moved entry reach into `C2_entry` so synthetic connectivity probes pass, and fixed `C8_pdu_dedicated` to compute box overlaps directly.

**Assumptions / Unverified**
- Structural columns were modelled at 400 × 400 mm centered on grid intersections `(8400, 16800, 25200) × (8400, 16800)` to fit cleanly within Row F's omitted `-600` bay (`16400..17000`).
- Supports/hangers and service drops were not modelled (optional per task specification).