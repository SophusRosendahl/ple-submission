### Summary

**Deliverables**
- `output/solution.py`: Self-contained deterministic Python script (`ifcopenshell==0.8.4` + `numpy`) that builds the full Data Hall 1 (`hall_seed000_d000`) fit-out and coordinated MEP routing directly from literals extracted from all 7 drawing sheets, writing an IFC4 model in millimetre project units to `sys.argv[1]` (default `output/model.ifc`).
- `output/model.ifc`: Generated IFC4 model (269 elements: 128 racks, 22 CRAHs [4 perimeter + 18 in-row], 6 PDUs, 6 structural columns, access floor slab, cold-aisle containment roofs & doors, 79 sprinkler heads [63 ceiling + 16 in-aisle], and 15 cleanly butted MEP route segments).
- `output/reconciliation.json`: Optional drawing-note reconciliation log summarizing extracted dimensions, clearances, and how each was applied.

**Last `evaluate` Result**
- **Build**: `python3 output/solution.py output/model.ifc` exited with `0`.
- **Schema**: `valid (express rules checked)`.
- **Checks**: `READY (269 items, 18 checks)` — 0 violations across all 18 checks:
  - Zero hard clashes (> 2 mm) across all 36,046 element pairs (`excluded: 0`, self-test missed `0` of 65 kind pairs).
  - All 3 services (`BW`, `CT`, `CHW`) form 1 connected component each and reach the west service entry `(0, 9900)`.
  - Row coverage: ≥ 83% for `BW` and `CT`, 100% for `CHW` (requirement ≥ 80% within 2500 mm).
  - All 22 CRAHs within 2500 mm of `CHW`.
  - Vertical zones: `BW` in overhead `[2800, 2947]` mm (within `[2600, 3114.6]` mm); `CT` in under-floor plenum `[-300, -173]` mm and `CHW` in `[-700, -531.7]` mm (within `[-900, -55]` mm).
  - Tray–busway separation > 2970 mm (requirement ≥ 300 mm on at least one axis).
  - Zero `CHW` in the 1800 mm dedicated electrical space above any PDU.
- **Objective (total route length)**: **180,521 mm** (`BW` 57,272 mm, `CHW` 66,532 mm, `CT` 56,717 mm), reduced by 34,740 mm from the initial 215,261 mm layout.

**Checker Revisions**
- Rewrote checks once (v1 → v2) before building to fix synthetic probe failures: removed `same_group` exclusion from `C1_no_clash` (enforcing zero overlaps even within the same service by clean face-to-face butting), split entry-reach verification into custom check `C2d_entries`, and replaced `helpers['overlap_depths']` in `C7_pdu_dedicated` with direct AABB overlap calculation.

**Assumptions & Unverified Items**
- Optional supports/hangers and service drops/terminations were not modelled.
- All 63 ceiling sprinklers are placed on the 3000 mm grid relocated clear of columns; exact per-tile relocation offsets on F-101 do not affect overhead clearances since all overhead routes stay below `Z = 2947 mm` (≥ 627 mm below ceiling deflectors).