An end-to-end Python script has been developed at `output/solution.py` to coordinate and build the complete IFC4 building information model for Data Hall 1 (`hall_seed000_d000`).

### Architecture and Reconciliation Summary
1. **Grid & Geometry**:
   - Room bounding dimensions: $27\,000 \times 21\,000\text{ mm}$.
   - Grid tile origin $(0, 0)$ at the internal south-west corner with $600\text{ mm}$ floor grid spacing ($45 \times 35$ grid lines: AA–BT horizontally, 1–36 vertically).
   - Columns: 6 structural columns ($600 \times 600\text{ mm}$) at grid intersections ①, ② along lines A, B, C extending full height from $Z = 0$ to $3\,600\text{ mm}$.
   - Access floor: $35\text{ mm}$ thick panel at finished floor $Z = 0$, top of slab at $Z = -900\text{ mm}$.
2. **Equipment**:
   - 128 server cabinets across rows A through F based on sequence schedules with proper orientations (South/North facing alternating cold/hot aisles).
   - 18 In-row CRAH units ($600 \times 1\,200 \times 2\,000\text{ mm}$) integrated into rows A–F.
   - 4 Perimeter CRAH units ($1\,200 \times 900 \times 2\,000\text{ mm}$) located along the south perimeter at tiles B01, P01, AC01, AQ01.
   - 6 Power Distribution Units (PDUs, $762 \times 813 \times 1\,959\text{ mm}$) with dedicated electrical clearance space up to $+3\,759\text{ mm}$ ($1\,800\text{ mm}$ above PDU tops).
   - Cold aisle containment roofs and end doors on Rows B/C and D/E at $Z = 2\,000\text{ to }2\,055.5\text{ mm}$.
   - 63 ceiling sprinkler heads at $Z = 3\,575\text{ mm}$ and 16 in-aisle heads under containment roofs at $Z = 1\,890\text{ mm}$.
3. **MEP Routing**:
   - **Service Entry**: Busway and Telecom tray enter at $(X = 0, Y = 9\,900\text{ mm})$. Chilled water enters at $(X = 0, Y = 9\,900\text{ mm})$.
   - **Vertical Tiers**:
     - Chilled water main supply/return: Under-floor plenum distribution along the western service strip at $Z = -450\text{ mm}$, branching to every cabinet row header and directly serving all perimeter and in-row CRAHs with 0 clash risk against overhead sprinkler clearance and PDU dedicated space.
     - Busway (`BW-1`, $128 \times 147\text{ mm}$): Main trunk routed overhead at $Z = 2\,750\text{ mm}$ along the western corridor ($X = 1\,500\text{ mm}$), extending branches across every row A through F at $Z = 2\,750\text{ mm}$.
     - Telecom Tray (`CT-1`, $683 \times 127\text{ mm}$): Overhead at $Z = 3\,000\text{ mm}$, maintaining $> 300\text{ mm}$ separation from power busways, running below the $460\text{ mm}$ sprinkler standoff zone ($Z \le 3\,115\text{ mm}$) and above the $2\,600\text{ mm}$ headroom clearance.
4. **Compliance & Properties**:
   - Built strictly using `ifcopenshell==0.8.4` with valid IFC4 entities, placement matrices, extrusions, and exact `Pset_DCM_*` property sets.