### Summary

**Deliverables**
- `output/solution.py`: Self-contained Python script (`ifcopenshell` + `numpy` + stdlib only, no runtime PNG reads) that constructs the coordinated IFC4 model of Data Hall 1 (`hall_seed000_d000`) in millimetres (with placement-matrix translations in metres) and writes it to `sys.argv[1]` (default `output/model.ifc`).
  - **Background**: 128 racks (`119 × C1`, `9 × N1`) across Rows A–F with cross-aisle east edge at `X = 11400 mm` and correct north/south facings, 6 full-height structural columns (`600 × 600 × 3600 mm`), 22 CRAHs (4 perimeter + 18 in-row), 6 PDUs flush with served row fronts, 35 mm access floor slab (`-35..0 mm`), cold-aisle containment (`CAC-BC`, `CAC-DE`: 4 roof panels + 8 end doors), and 79 sprinkler heads (63 ceiling at `+3574.6 mm`, 16 in-aisle at `+1890 mm`).
  - **MEP Routing** (all connected to the west-wall service entry at `X = 0, Y = 9900 mm`):
    - **Telecom Cable Tray (`CT-1`, `683 × 127 mm`)**: Overhead at `Z = 2713.5 mm` (`[2650, 2777] mm`), 8 segments, 116.10 m total.
    - **Power Busway (`BW-1`, `128 × 147 mm`)**: Under-floor plenum at `Z = -300.0 mm` (`[-373.5, -226.5] mm`), 8 segments, 117.60 m total.
    - **Chilled Water (`CHW-1`, insulated OD `168.3 mm`)**: Overhead at `Z = 2950.0 mm` (`[2865.85, 3034.15] mm`), 9 segments, 140.85 m total (serving all 6 rows, all 18 in-row CRAHs, and all 4 perimeter CRAHs via `Y = 1200 mm`).
- `output/reconciliation.json`: Optional diagnostic log of vertical datums, pathway sections, and clearances extracted from the 7 drawing sheets.

**Checks Run (`/tmp/scratch/checks.py` — all passed)**
1. **Static / contract check**: Verified valid Python syntax, allowed imports only, no PNG references, and `sys.argv[1]` handling.
2. **Element counts**: Verified 128 racks (119 C1, 9 N1), 6 columns, 22 CRAHs (4 perimeter, 18 in-row), 6 PDUs, and 79 sprinklers (63 ceiling, 16 in-aisle).
3. **Hard clash sweep**: Exhaustive pairwise AABB overlap check across all 200 solids (19,900 pairs; same-service joints excluded) — **0 clashes > 2.0 mm**.
4. **Connectivity**: Verified each of the 3 services forms 1 connected component reaching `(0, 9900)`.
5. **Coverage**: Verified all 6 rows are served along ≥ 80% of their length within 2500 mm by all 3 services, and CHW is within 2500 mm of all 22 CRAHs.
6. **Code compliance**: Verified overhead headroom ≥ 2600 mm, ceiling sprinkler standoff ≤ 3114.6 mm, under-floor zone in `[-900, -55] mm`, tray–busway separation ≥ 300 mm (achieved 2876.5 mm vertical), and 0 CHW intrusions into the 1800 mm dedicated space above all 6 PDUs.

**Assumptions & Unverified Items**
- `ifcopenshell` is not importable in this container, so `write_ifc()` and `express_rules=True` validation could not be executed live here; IFC4 schema compliance (2D profile points, `PredefinedType`/`ObjectType` rules, metric placement translations, and spatial hierarchy) was verified by static inspection.