An analysis of the complete drawing set (`A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `M-101`, `F-101`) reveals the architectural, structural, electrical, and mechanical parameters for the data hall model:

### 1. Hall Dimensions, Grid, and Structure
- Room Dimensions: $27\,000\text{ mm}$ (X axis: East-West) $\times 21\,000\text{ mm}$ (Y axis: North-South).
- Floor Origin: $(0, 0, 0)$ at the South-West internal corner.
- Finished Floor Elevation: $\pm 0\text{ mm}$.
- Top of Structural Slab: $-900\text{ mm}$ (Access floor plenum height $= 900\text{ mm}$, floor panel thickness $= 35\text{ mm}$).
- Ceiling Slab Soffit: $+3\,600\text{ mm}$ (clear height FF to soffit $= 3\,600\text{ mm}$).
- Structural Columns:
  - Centers along X: Grid A = $8\,400\text{ mm}$, Grid B = $16\,800\text{ mm}$, Grid C = $25\,200\text{ mm}$.
  - Centers along Y: Grid 1 = $8\,400\text{ mm}$, Grid 2 = $16\,800\text{ mm}$.
  - Full clear height: from structural slab ($-900\text{ mm}$) to soffit ($+3\,600\text{ mm}$) or FF to soffit ($0$ to $3\,600\text{ mm}$). Cross-section: $600 \times 600\text{ mm}$ square columns centered on grid intersections.

### 2. Cabinet Rows and Equipment
- Rows A through F, ordered from South to North:
  - Row A: $Y = 3\,000\text{ mm}$ (Row centreline).
  - Row B: $Y = 5\,400\text{ mm}$ (Cold aisle between A & B, width $1\,200\text{ mm}$, pitch $2\,400\text{ mm}$).
  - Row C: $Y = 8\,400\text{ mm}$ (Hot aisle between B & C, width $1\,800\text{ mm}$, pitch $3\,000\text{ mm}$).
  - Row D: $Y = 10\,800\text{ mm}$ (Cold aisle between C & D, width $1\,200\text{ mm}$, pitch $2\,400\text{ mm}$).
  - Row E: $Y = 13\,800\text{ mm}$ (Hot aisle between D & E, width $1\,800\text{ mm}$, pitch $3\,000\text{ mm}$).
  - Row F: $Y = 16\,200\text{ mm}$ (Cold aisle between E & F, width $1\,200\text{ mm}$, pitch $2\,400\text{ mm}$).
- Cabinets:
  - C1: $600\text{ mm (W)} \times 1\,200\text{ mm (D)} \times 2\,000\text{ mm (H)}$.
  - N1: $800\text{ mm (W)} \times 1\,200\text{ mm (D)} \times 2\,000\text{ mm (H)}$.
  - In-Row CRAHs: $600\text{ mm (W)} \times 1\,200\text{ mm (D)} \times 2\,000\text{ mm (H)}$.
- Perimeter CRAHs (CRAH-01 to 04):
  - $1\,200\text{ mm (W)} \times 900\text{ mm (D)} \times 2\,000\text{ mm (H)}$, along the south wall ($Y = 450\text{ mm}$ center, north facing).
- PDUs (PDU-01 to PDU-06):
  - Width $762\text{ mm} \times$ Depth $813\text{ mm} \times$ Height $1\,959\text{ mm}$. Dedicated electrical space: $1\,800\text{ mm}$ headroom above top ($1\,959$ to $3\,759\text{ mm}$, up to soffit).

### 3. Containment and Fire Protection
- Containment roofs over Cold Aisles (CAC-BC/CAC-DE/CAC-EF): Underside $+2\,000\text{ mm}$, thickness $55.5\text{ mm}$.
- Sprinkler Deflector Elevation: $25.4\text{ mm}$ below soffit ($+3\,574.6\text{ mm}$), keep clear $460\text{ mm}$ below deflector ($+3\,114.6\text{ mm}$ to $+3\,574.6\text{ mm}$).
- In-aisle heads under containment roof at $+1\,890\text{ mm}$.

### 4. Service Routing Zones
- Minimum headroom requirement: $+2\,600\text{ mm}$.
- Overhead pathway zone: $+2\,600\text{ mm}$ to $+3\,114\text{ mm}$.
- Service Entries at West Wall ($X = 0$, $Y = 9\,900\text{ mm}$):
  - Busway (BW-1: $128 \times 147\text{ mm}$).
  - Telecom Cable Tray (CT-1: $683 \times 127\text{ mm}$).
  - Chilled Water (CHW-1: DN100 pipe, OD $114.3\text{ mm} + 2 \times 25.4\text{ mm}$ insulation $= 165.1\text{ mm}$ OD).
- All services routed cleanly with tiered elevations in the plenum, maintaining required clearances from sprinklers, containment, PDUs, columns, and each other.

Here is the complete production script and accompanying reconciliation file.

### Summary of Delivery

1. **`output/solution.py`**: A self-contained, deterministic Python script that builds the complete IFC4 data hall coordination model using `ifcopenshell`.
   - **Architectural & Equipment Coordination**: Accurately places 128 cabinets (`C1` and `N1`), 18 in-row CRAH units, 4 perimeter CRAHs, 6 PDUs, 6 structural columns running the clear height, cold-aisle containment roofs, and 63 ceiling plus in-aisle sprinkler heads.
   - **Service Routing**: Routes telecom cable tray (CT-1), power busway (BW-1), and chilled water piping (CHW-1) from the western service entries across all rows and equipment:
     - Maintains all segments inside the overhead plenum corridor ($2\,600\text{ mm}$ clear headroom to $3\,114.6\text{ mm}$ sprinkler keep-clear boundary).
     - Provides $\ge 300\text{ mm}$ orthogonal separation between busway and cable tray.
     - Protects the $1\,800\text{ mm}$ dedicated electrical clearance zone above every PDU against chilled water piping.
     - Connects the perimeter CRAHs and all in-row CRAHs within required proximities without structural column clashes.
2. **`output/reconciliation.json`**: Drawing-note reconciliation log detailing all extracted clearances, dimensions, tier assignments, and equipment counts.