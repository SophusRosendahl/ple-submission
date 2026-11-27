### Deliverables
- **`output/solution.py`** — Self-contained IFC4 model builder (`ifcopenshell==0.8.4` + `numpy`) that reconstructs Data Hall 1 (`27000 × 21000 mm`) from the seven drawing sheets (128 racks: 119 C1 + 9 N1; 6 structural columns; 4 perimeter + 18 in-row CRAHs; 6 PDUs; access floor; 2 cold-aisle containments with 4 roof panels and 8 end doors; 63 ceiling + 16 in-aisle sprinklers) and routes all three services from the west-wall service entry `(0, 9900)` as axis-aligned straight segments:
  - **Power Busway (`BW-1`, 128 × 147 mm)**: overhead at `Z = +2850 mm` (`+2776.5..+2923.5 mm`), 66.00 m total.
  - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: under-floor plenum at `Z = -150 mm` (`-213.5..-86.5 mm`), 66.00 m total.
  - **Chilled-Water Pipe (`CHW-1`, DN100, 168.3 mm insulated OD)**: under-floor plenum at `Z = -500 mm` (`-584.15..-415.85 mm`), 94.20 m total (including the south perimeter header serving `CRAH-01`–`CRAH-04`).
  - Writes the validated (`express_rules=True`) IFC4 model to `sys.argv[1]` (default `output/model.ifc`).
- **`output/reconciliation.json`** — Drawing-note reconciliation log summarizing the extracted clearances, datums, and section sizes and how each was applied.

### Checks Run (`python3 -B /tmp/scratch/checks.py`)
All checks passed (`ALL CHECKS PASSED!`):
1. **Inventory**: Verified 128 racks (119 C1, 9 N1), 6 columns, 4 perimeter + 18 in-row CRAHs, 6 PDUs, 63 ceiling + 16 in-aisle sprinklers.
2. **Zero hard clashes (> 2 mm)**: Checked all route segments (including 168.3 mm insulated CHW OD) against all background solids (including full-height columns `-900..+3600 mm`) and against each other.
3. **Connectivity**: Verified each service forms 1 connected network reaching `(0, 9900)`.
4. **Row coverage & CRAH reach**: Verified every row A–F is covered ≥ 80% of its length within 2500 mm by all three services, and CHW is within 2500 mm of all 22 CRAHs.
5. **Code compliance**: Verified overhead headroom ≥ 2600 mm, ceiling sprinkler standoff ≥ 460 mm below `+3574.6 mm`, under-floor clearance ≥ 20 mm below panel underside (`-35 mm`) and above slab (`-900 mm`), tray–busway separation ≥ 300 mm (`2863 mm` vertical), and zero CHW piping in the 1800 mm dedicated space above any PDU.
6. **Static IFC4 contract check**: Parsed `output/solution.py` AST and verified `IFC4`, `MILLIMETRES` units, metre placement translations, 2D profile points, `IfcFurniture`/`Rack`, `Pset_DCM_*`, and `express_rules=True`.

### Assumptions & Unverified Items
- Because `ifcopenshell` cannot be imported in this container during the run, `build_ifc()` and `ifcopenshell.validate.validate(..., express_rules=True)` were verified statically rather than executed end-to-end against `ifcopenshell==0.8.4`.
- All vertical datums and equipment coordinates were taken directly from the seven drawing sheets (`A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, `M-101`) with `Z = 0` at Finished Floor.