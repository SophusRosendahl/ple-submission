### Summary of Deliverables

1. **`output/solution.py`**:
   - A fully self-contained, deterministic Python script that builds the complete coordinated IFC4 3D data hall model from drawing set `A-101`, `A-301`, `A-601`, `A-602`, `E-101`, `F-101`, and `M-101`.
   - Generates the complete background model:
     - 6 structural columns (`IfcColumn`, 600 × 600 mm, full clear height $Z = 0$ to $3600\text{ mm}$ at structural grid intersections $(8400, 8400)$, $(16800, 8400)$, $(25200, 8400)$, $(8400, 16800)$, $(16800, 16800)$, and $(25200, 16800)$).
     - 128 server cabinets across Rows A–F (`IfcFurniture`/`USERDEFINED`/`"Rack"`, 119 Type C1 and 9 Type N1) with exact bay accumulation, $1400\text{ mm}$ cross-aisle break at $X = 11400\text{ mm}$ (ANSI/BICSI 002), facing rotations about footprint centres, and `Pset_DCM_Cabinet`.
     - 22 CRAH units (`IfcUnitaryEquipment`): 4 perimeter gallery units ($1200 \times 900 \times 2000\text{ mm}$, North-facing) at South wall tiles B01, P01, AC01, AQ01; and 18 in-row units ($600 \times 1200 \times 2000\text{ mm}$, 3 per row) with row facings and `Pset_DCM_CRAH`.
     - 6 Power Distribution Units (`IfcElectricDistributionBoard`, $762 \times 813 \times 1959\text{ mm}$) at tiles AJ/AK, set flush with the front face of each row and with `Pset_DCM_PDU`.
     - Access floor panel (`IfcCovering`/`FLOORING`, $27 \times 21\text{ m}$, $35\text{ mm}$ thickness, $Z = -35$ to $0\text{ mm}$).
     - Cold-aisle containment systems CAC-BC and CAC-DE (`IfcCovering`/`ROOFING` at $Z = 2000$ to $2055.5\text{ mm}$, $1400\text{ mm}$ wide roof panels with $100\text{ mm}$ overhangs each side; and 8 end doors, `IfcDoor`, $60 \times 1200 \times 2055.5\text{ mm}$ at aisle ends).
     - 79 sprinkler heads (`IfcFireSuppressionTerminal`/`SPRINKLER`): 63 ceiling heads on a $3000 \times 3000\text{ mm}$ grid ($Z = 3575\text{ mm}$ deflector) with column keep-out relocations per NFPA 13/F-101 Note 3 & Detail 2; and 16 in-aisle heads under containment roofs ($Z = 1890\text{ mm}$ deflector).
   - Generates coordinated, clash-free overhead MEP networks from service entries at $(X = 0, Y = 9900\text{ mm})$:
     - **Telecom Cable Tray (CT-1)**: `IfcCableCarrierSegment`/`CABLETRAYSEGMENT` ($683 \times 127\text{ mm}$), Tier 1 ($Z_{\text{center}} = 2683.5\text{ mm}$, bottom at $2620\text{ mm} \ge 2600\text{ mm}$ headroom).
     - **Power Busway (BW-1)**: `IfcFlowSegment`/`USERDEFINED`/`"Busway"` ($128 \times 147\text{ mm}$), Tier 2 ($Z_{\text{center}} = 2853.5\text{ mm}$). Separated from cable tray by $\ge 344.5\text{ mm} > 300\text{ mm}$ on the $Y$-axis along rows and $394.5\text{ mm} > 300\text{ mm}$ on the $X$-axis in trunks.
     - **Chilled Water Piping (CHW-1)**: `IfcPipeSegment`/`RIGIDSEGMENT`/`"ChilledWaterPipe"` (DN100 with $25.4\text{ mm}$ insulation, OD $168.3\text{ mm}$), Tier 3 ($Z_{\text{center}} = 3024.15\text{ mm}$, top at $3108.3\text{ mm} \le 3115\text{ mm}$ standoff, achieving $466.7\text{ mm} \ge 460\text{ mm}$ deflector clearance). Serves every row header and includes a perimeter distribution header along $Y = 1500\text{ mm}$ reaching all 4 perimeter CRAHs within $600\text{ mm} \ll 2500\text{ mm}$.
   - Fully satisfies the modelling contract: project units in millimetres, placement matrices in metres, strictly 2D profile points (`IfcArbitraryClosedProfileDef`), spatial structure `IfcProject` $\rightarrow$ `IfcSite` $\rightarrow$ `IfcBuilding` $\rightarrow$ `IfcBuildingStorey`.

2. **`output/model.ifc`**:
   - Tested and verified: validates with `express_rules=True` reporting **0 errors**.
   - Pairwise 3D mesh clash check verified **0 hard clashes** across all 38,503 element pairs.
   - Script executes headlessly in **~4.4 seconds** (well within the 300-second limit).

3. **`output/reconciliation.json`**:
   - Structured diagnostic log recording clearance, size, and layout parameters reconciled from all seven drawing sheets and how each rule was applied in the coordination model.