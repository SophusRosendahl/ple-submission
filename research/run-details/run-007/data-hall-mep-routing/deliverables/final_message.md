]$ and $[16500, 17100]$, $Y \in [16500, 17100]$!
  - Cable Tray: $Y = 16000$ mm.
    Tray bounds: $Y \in [15658.5, 16341.5]$.
    Column begins at $Y = 16500$ mm.
    Clearance to column $= 16500 - 16341.5 = 158.5$ mm! NO CLASH!
    Distance to Row F: $|16000 - 16800| = 800$ mm $\le 2500$ mm!
  - Busway: $Y = 17300$ mm.
    Busway bounds: $Y \in [17236, 17364]$.
    Column ends at $Y = 17100$ mm.
    Clearance to column $= 17236 - 17100 = 136$ mm! NO CLASH!
    Distance to Row F: $|17300 - 16800| = 500$ mm $\le 2500$ mm!
    Separation from Cable Tray: $17300 - 16000 = 1300$ mm $\implies 894.5$ mm clear $\ge 300$ mm!
  - Chilled Water: $Y = 17300$ mm.
    Bounds: $Y \in [17215.85, 17384.15]$.
    Clearance to column $= 115.85$ mm! NO CLASH!
    Distance to Row F: 500 mm $\le 2500$ mm!
    Distance to CRAH-F01, F02, F03: 500 mm $\le 2500$ mm!
    Z disjoint from Busway! NO CLASH!

AND FOR THE PERIMETER CRAHS (CRAH-01, 02, 03, 04):
- Perimeter CRAHs are along the South wall: $Y \in [0, 900]$ mm.
- If Chilled Water runs a branch along $Y = 600$ mm (or $Y = 900$ mm):
  - It runs from $X = X_{\text{trunk\_CHW}}$ to $X = 25800$ mm (past CRAH-04 at 25200-26400).
  - Distance from pipe to CRAH-01 (x=1200, y=450): $< 200$ mm $\le 2500$ mm!
  - Distance to CRAH-02 (x=9600, y=450): $< 200$ mm $\le 2500$ mm!
  - Distance to CRAH-03 (x=17400, y=450): $< 200$ mm $\le 2500$ mm!
  - Distance to CRAH-04 (x=25800, y=450): $< 200$ mm $\le 2500$ mm!
  - ALL 4 perimeter CRAHs are served within 200 mm $\le 2500$ mm!
  - And what about PDU-01? PDU-01 is at $Y \in [2400, 3213]$, $X \in [21000, 21762]$.
    Pipe is at $Y = 600$ mm. Distance in Y $= 2400 - 600 = 1800$ mm!
    NEVER ENTERS PDU-01 DEDICATED SPACE!
  - And what about columns? Columns start at $Y = 8100$ mm.
    Pipe is at $Y = 600$ mm. NO CLASH WITH ANY COLUMN!

Now let's check the TRUNKS in the West Service Strip ($X \in [0, 1800]$ mm):
Let's choose the X coordinates of the three main trunks:
We have $X \in [0, 1800]$ mm.
- Entry point for all three services is at $X = 0, Y = 9900$ mm.
- Let's place the three trunks at:
  - Cable Tray trunk: $X = 500$ mm.
    Width 683 mm $\implies X \in [158.5, 841.5]$ mm.
  - Busway trunk: $X = 1400$ mm.
    Width 128 mm $\implies X \in [1336, 1464]$ mm.
    Separation between Tray and Busway trunks:
    $1336 - 841.5 = 494.5$ mm $\ge 300$ mm! (Complies with 300 mm separation!).
  - Chilled Water trunk: $X = 950$ mm.
    Width 168.3 mm $\implies X \in [865.85, 1034.15]$ mm.
    Separation to Tray trunk: $865.85 - 841.5 = 24.35$ mm.
    Separation to Busway trunk: $1336 - 1034.15 = 301.85$ mm.
    And remember: their Z tiers are disjoint!
- Let's check CRAH-01 in the West Service Strip:
  - CRAH-01 is at the South wall: $X \in [600, 1800]$ mm, $Y \in [0, 900]$ mm, $Z \in [0, 2000]$ mm.
  - Our trunks are at $Z \ge 2600$ mm!
  - $2600 - 2000 = 600$ mm clear above CRAH-01!
  - NO CLASH WITH CRAH-01!
- Let's check the West wall:
  - Trunks are at $X \ge 158.5$ mm > 0 mm.
  - The entry segments connect from $X = 0$ to each trunk at $Y = 9900$ mm.
    - For Cable Tray: straight segment from $(0, 9900, Z_{\text{CT}})$ to $(500, 9900, Z_{\text{CT}})$.
    - For Chilled Water: straight segment from $(0, 9900, Z_{\text{CHW}})$ to $(950, 9900, Z_{\text{CHW}})$.
    - For Busway: straight segment from $(0, 9900, Z_{\text{BW}})$ to $(1400, 9900, Z_{\text{BW}})$.
    - Notice all three entry segments run along $Y = 9900$ mm from $X = 0$ to their respective trunks!
    - And because their Z elevations are $Z_{\text{CT}} = 2670$, $Z_{\text{BW}} = 2830.5$, $Z_{\text{CHW}} = 3013.15$, THEY DO NOT CLASH WITH EACH OTHER AT ALL!

Wait! Let's check the length of each row branch:
- How far along X should each branch run?
  - Row A ends at $X = 19200$ mm.
  - Row B ends at $X = 19800$ mm.
  - Row C ends at $X = 19400$ mm.
  - Row D ends at $X = 19800$ mm.
  - Row E ends at $X = 19200$ mm.
  - Row F ends at $X = 20200$ mm.
  - If each branch runs from its trunk ($X = 500, 950, 1400$) to the end of the row (or $X = 19200$ mm):
    Let's check the 80% coverage rule:
    - Row length:
      Row A: $19200 - 1800 = 17400$ mm. $0.8 \times 17400 = 13920$ mm.
      Row B: $19800 - 1800 = 18000$ mm. $0.8 \times 18000 = 14400$ mm.
      Row C: $19400 - 1800 = 17600$ mm. $0.8 \times 17600 = 14080$ mm.
      Row D: $19800 - 1800 = 18000$ mm. $0.8 \times 18000 = 14400$ mm.
      Row E: $19200 - 1800 = 17400$ mm. $0.8 \times 17400 = 13920$ mm.
      Row F: $20200 - 1800 = 18400$ mm. $0.8 \times 18400 = 14720$ mm.
    - If the branches run to:
      - Row A: $X = 19000$ mm (overlap with row = $19000 - 1800 = 17200$ mm $\implies 98.8\%$).
      - Row B: $X = 19000$ mm (overlap with row = $17200$ mm $\implies 95.5\%$).
      - Row C: $X = 19000$ mm (overlap with row = $17200$ mm $\implies 97.7\%$).
      - Row D: $X = 19000$ mm (overlap with row = $17200$ mm $\implies 95.5\%$).
      - Row E: $X = 19000$ mm (overlap with row = $17200$ mm $\implies 98.8\%$).
      - Row F: $X = 19000$ mm (overlap with row = $17200$ mm $\implies 93.5\%$).
      ALL rows are covered along > 93% of their length (well above >= 80%)!
      AND stopping at $X = 19000$ mm keeps them well clear of the East wall ($X = 27000$) and well clear of the PDUs ($X \ge 21000$)!

Wait! What about