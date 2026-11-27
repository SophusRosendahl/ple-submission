Delivered the coordinated IFC4 model builder and reconciliation log for Data Hall 1 (`hall_seed000_d000`):

- **`output/solution.py`**: Self-contained Python script (`ifcopenshell==0.8.4` + `numpy`, millimetre project units, metre placement translations, 2D profiles, `Pset_DCM_*` property sets) that builds:
  - **Architectural & equipment background**: 27000 × 21000 mm access floor (`z = -35..0`), 6 structural columns (`400 × 400 × 3600` on grids A–C / 1–2), 128 server cabinets (119 C1 + 9 N1 across rows A–F with exact bay sequences and North/South facings), 4 perimeter + 18 in-row CRAHs, 6 PDUs flush with their served rows, cold-aisle containment (`CAC-BC`, `CAC-DE` roofs and end doors), and 63 ceiling + 16 in-aisle sprinkler heads.
  - **Clash-free, connected MEP routing** (all starting from the west-wall service entry at `x = 0, y = 9900`):
    - **Power Busway (`BW-1`, 128 × 147 mm)**: Overhead at `z = 2693.5` mm (`2620..2767`, ≥ 2600 mm clear height, 807.6 mm below sprinkler deflectors), serving all 6 rows (`124.2 m`).
    - **Telecom Cable Tray (`CT-1`, 683 × 127 mm)**: Under-floor plenum at `z = -300.0` mm (`201.5 mm` below access-floor panel, `2856.5 mm` clear from busway), serving all 6 rows (`125.2 m`).
    - **Chilled-Water Pipe (`CHW-1`, 168.3 mm insulated OD)**: Under-floor plenum at `z = -650.0` mm (zero piping in PDU dedicated electrical space), serving all 6 rows, all 18 in-row CRAHs, and all 4 perimeter CRAHs (`151.8 m`, max 450 mm from any CRAH).
- **`output/reconciliation.json`**: Drawing-note reconciliation log extracted from sheets `A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, and `M-101`.

Geometric verification confirmed **0 clashes** (> 2 mm) across all background and MEP solids, full single-component connectivity for all three services, and 100% row and CRAH coverage.