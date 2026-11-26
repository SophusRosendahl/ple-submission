thought
Let's check:
Each row (A, B, C, D, E, F) has:
Row A: Y = 3000 (centreline)
Row B: Y = 6000
Row C: Y = 8400
Row D: Y = 11400
Row E: Y = 13800
Row F: Y = 16800

For Busway to serve every row:
A branch of Busway must run along each row (East-West) within 2500 mm of the row centreline, covering >= 80% of the row length.
Where should the Busway branch be located relative to the row?
Let's see:
Can the Busway branch run directly above the row, e.g. at the row centreline?
Let's check:
Above the row:
Row cabinets are 2000 mm high (Z in [0, 2000]).
Containment roof (on rows B/C and D/E):
Containment roof is over the COLD aisle (between B and C, and between D and E).
The containment roof sits at Z in [2000, 2055.5], with 100 mm overhang onto the cabinets.
Above Z = 2055.5 mm up to Z = 2600 mm is clear headroom.
Above Z = 2600 mm is the overhead pathway zone!
So directly above the row centreline at Z in [2600, 3114.6], IT IS COMPLETELY OPEN!
There are NO racks at Z >= 2600 mm!
There is NO containment roof at Z >= 2600 mm!
The only things in the overhead space (Z >= 2600 mm) are:
1. Structural columns (which run full height from 0 to 3600 mm)!
2. Sprinkler heads (deflectors at 3574.6 mm, keep-out 460 mm down to 3114.6 mm).
3. The other MEP services!

Let's check the columns in the overhead space:
Columns are at:
(8400, 8400)
(16800, 8400)
(25200, 8400)
(8400, 16800)
(16800, 16800)
(25200, 16800)
Notice:
All 6 columns are on:
Grid 1 (Y = 8400, Row C centreline)
Grid 2 (Y = 16800, Row F centreline)!
THERE ARE NO COLUMNS ON ROW A, ROW B, ROW D, OR ROW E!
Columns are ONLY on Row C (Y = 8400) and Row F (Y = 16800)!
So if a service runs along Row C centreline (Y = 8400), it would hit the columns at X = 8400 and X = 16800!
UNLESS it is offset slightly in Y from the centreline!
How far does it need to be offset in Y to miss the columns?
Columns are 600 mm wide, so Y is [8100, 8700]!
If a service runs at Y = 8400 + 400 = 8800 mm:
Y = 8800 mm is outside [8100, 8700]!
Distance to column is 8800 - 8700 = 100 mm!
And distance to row centreline (8400) is only 400 mm << 2500 mm!
It serves the row perfectly and misses all columns completely!
And on Row F (Y = 16800):
If it runs at Y = 16800 - 400 = 16400 mm:
Distance to column ([16500, 17100]) is 16500 - 16400 = 100 mm!
Misses the columns completely!

Wait, what if we offset the service by, say, 500 mm or 600 mm from the row centreline for all rows?
Let's check:
If a service runs at an offset of, say, +400 mm from the row centreline:
For Row A (3000): Y = 3400.
For Row B (6000): Y = 5600 (or 6400).
For Row C (8400): Y = 8900.
For Row D (11400): Y = 11000 (or 11800).
For Row E (13800): Y = 14200.
For Row F (16800): Y = 16300.
Let's check where the hot aisles and cold aisles are:
Between Row A and Row B: HOT AISLE (Y in [3600, 5400]).
Between Row B and Row C: COLD AISLE (Y in [6600, 7800]).
Between Row C and Row D: HOT AISLE (Y in [9000, 10800]).
Between Row D and Row E: COLD AISLE (Y in [12000, 13200]).
Between Row E and Row F: HOT AISLE (Y in [14400, 16200]).

Notice:
In the HOT AISLES (between A and B, between C and D, between E and F):
There is NO containment roof!
There are NO in-aisle sprinkler heads!
The hot aisles are 1800 mm wide, completely open from 2600 mm up to 3114.6 mm!
And the distance from the hot aisle centre to either adjacent row is only 900 mm!
900 mm << 2500 mm!
Wait! Can a service run in the hot aisle?
Yes! Within 2500 mm of the row centreline, 900 mm is well within 2500 mm!
OR a service can run directly over the row of cabinets!
Above the cabinet row:
Cabinets are 1200 mm deep.
Row centreline is Y_row.
Cabinet footprint is [Y_row - 600, Y_row + 600].
If a service runs at Y = Y_row - 200 or Y_row + 200:
It is directly above the cabinet tops!
And above 2600 mm, there are NO cabinets, so it is completely open!

Now let's check SPRINKLER HEADS:
Where are the sprinkler heads?
Let's check:
Ceiling sprinkler heads are on a 3000 mm grid:
X = 1500, 4500, 7500, 10500, 13500, 16500, 19500, 22500, 25500.
Y = 1500, 4500, 7500, 10500, 13500, 16500, 19500.
Look at the Y coordinates of the ceiling sprinkler heads:
Y = 1500 (south of Row A)
Y = 4500 (in the HOT aisle between Row A and Row B: 4500 is exactly halfway between 3600 and 5400!)
Y = 7500 (in the COLD aisle between Row B and Row C: halfway between 6600 and 7800!)
Y = 10500 (in the HOT aisle between Row C and Row D: halfway between 9000 and 10800!)
Y = 13500 (in the COLD aisle between Row D and Row E: halfway between 12000 and 13200!)
Y = 16500 (near Row F)
Y = 19500 (north of Row F).

LOOK AT THAT!
The ceiling sprinkler heads are at Y = 1500, 4500, 7500, 10500, 13500, 16500, 19500!
Now, what are the row centrelines?
Row A: Y = 3000! Distance to nearest sprinkler head line (1500 and 4500) = 1500 mm!
Row B: Y = 6000! Distance to nearest sprinkler head line (4500 and 7500) = 1500 mm!
Row C: Y = 8400! Distance to nearest sprinkler head line (7500) = 900 mm!
Row D: Y = 11400! Distance to nearest sprinkler head line (10500) = 900 mm!
Row E: Y = 13800! Distance to nearest sprinkler head line (13500) = 300 mm!
Row F: Y = 16800! Distance to nearest sprinkler head line (16500) = 300 mm!

Wait! What is the rule about sprinkler heads?
Let's read the rule very carefully:
"460 mm kept clear below every sprinkler deflector (plus the NFPA 13 obstruction rule within 450 mm below a deflector); heads required beneath runs wider than 1200 mm and beneath containment roofs"
AND:
"Deflector elevation: 3574.6 mm. 460 mm kept clear below every sprinkler deflector."
3574.6 - 460 = 3114.6 mm!
IF YOUR SERVICES STAY AT OR BELOW Z = 3100 mm (below 3114.6 mm):
THEY ARE ALREADY OUTSIDE THE 460 mm KEEP-CLEAR ZONE BELOW THE SPRINKLER DEFLECTORS!
Because 3100 < 3114.6 mm!
Any service whose top is <= 3114.6 mm is MORE THAN 460 mm below the ceiling sprinkler deflectors!
So it NEVER enters the 460 mm standoff zone under ANY ceiling sprinkler head!
LOOK AT THAT!
Let's verify:
Ceiling soffit = 3600 mm.
Deflector plane = 3574.6 mm.
3574.6 - 460 = 3114.6 mm.
If the top of the highest service is at Z = 3090 mm: