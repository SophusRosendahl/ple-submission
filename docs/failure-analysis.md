# Why the agents fail: reading, requirements, checks, or adaptation? (Neon, ifcopenshell blocked)

Evidence: 18 runs (rung 1 v4 and rung 2 v2 and v3, six each), their requirement lists, data notes, checks (rung 2 only: logged scratch files), commands and results, delivered scripts, and the grader's reports. What the model "believed" is read from code and notes (hidden thinking is not recorded). Each cell is a small sample; these are patterns, not tests.

## Verdict

| Hypothesis | Verdict | Main evidence |
|---|---|---|
| 1. The agent misreads the drawings | **Not the main cause** | 12 rung 2 data notes share a 70-number consensus (10 of 12 cover at least 89%); connectivity and row-coverage gates passed in every run that reached them; the rules that depend on read values (sprinkler clearance, PDU space, tray-busway separation) mostly pass. No ground truth for the drawings, so consistent misreading cannot be excluded. |
| 2. It misunderstands requirements and turns them into the wrong objectives | **Partly, at one step: choosing what a requirement applies to** | Every requirement of the task text appears in the agents' own lists (all 20 groups in 10 or more of 12 runs). The scope drifts when the list becomes checks: "no overlap anywhere" became route-vs-room and route-vs-other-service; "2600 mm headroom" became "no *route segment* below 2600" (all four checks read loop over route segments, never over the 16 sprinkler heads the grader flagged). |
| 3. The checks are not designed well enough | **Yes, the main cause** | 9 of 12 rung 2 checks passed the first time they ran; they could not fail on the real defect. They exclude the pairs that are wrong, test the plan data and not the built solids, and share the designer's belief. |
| 4. It fails to adapt to feedback | **No, with one caveat** | When a check fails on a real defect the agent fixes the solution: runs 029, 037, 044 (rung 2) and 034, 036, 038 (rung 1) each found and fixed overlaps. The caveat: it stops at the first all-pass, and one run changed the check instead of the design (run-038 edited its own verification script). |

## 1. Reading

- **Consistency across runs:** 12 `data.md` files (rung 2 v2 and v3), 3 to 5 digit numbers. A consensus of 70 numbers appears in at least 7 of 12 runs. Share of that consensus found in each run: 0.89, 0.99, 0.99, 0.97, 0.94, 0.49, 1.00, 0.91, 0.97, 0.70, 0.99, 0.97 (the two low ones are short notes). Numbers unique to one run: 0 to 1 in 8 runs, 4 to 7 in four runs, mostly derived values (the agent working a sum aloud: "wait, let's check") and one PDU position 200 mm off the others (run-040: 11,081 against 10,881).
- **Gates that depend on position:** connectivity and row coverage passed in every run that reached them; every cooling unit reached in all of them.
- **What reading does not explain:** the 16 headroom violations (the heads sit where the drawing puts them, 1,890 mm, and every agent knows it); the same-service overlaps (a modelling choice, not a reading).
- **Limit:** no ground truth for the drawings here, so a consistent misreading is not excluded.

## 2. Requirements

- **Capture is complete.** Keyword check of each `requirements.md` against the 20 requirement groups of the task text: all present in every run, except "efficiency / short routes" in 4 to 5 of 6.
- **The drift happens in scope.** Three cases:
  1. *No overlap anywhere* became checks on the pairs the agent had designed for. Same-service pieces excluded in 12 of 12 rung 2 runs (the reason given is always that they meet at joints); background against background narrowed in v2 (fixed by one sentence in v3: own-room overlaps 4 of 6 to 1 of 6).
  2. *2600 mm headroom* became a test of route segments only (runs 029, 035, 042, 045 read; the others follow the same names). Sixteen in-aisle sprinkler heads at 1,890 mm violate it in every run, and no check looks at them. Whether the rule should apply to heads under containment is not stated in the task and not known to us.
  3. *Heads required beneath containment roofs and wider runs* is listed by all agents and checked by none; the grader finds nothing to check for it in any run.
- **Two rules are not in the task text at all** (stacked-tray headroom 300 mm, tray clear of the tile 20 mm). They cannot be met by reading the task; they only show in the grader's report. They cost compliance (0.92 at best), not the gates.

## 3. Check design

- **They cannot fail on the real defect.** First run of the agent's own checks: 9 of 12 passed at once (031, 033, 035, 039, 040, 041, 042, 043, 045); 3 failed first and were fixed (029, 037, 044), each on a real defect. No agent tried a case that must fail.
- **Correlated errors.** The same belief shapes the design and the check: pieces of a run are drawn centre to centre and overlap at every joint; the check leaves exactly those pairs out. The two never disagree.
- **The plan, not the product.** Every check imports the data builder of the agent's own script; the part that writes the solids is never run (ifcopenshell is blocked). Run-032's stand-in for the library is the only run that tested the built solids, and it passed.
- **Breadth is good, depth is not.** The checks cover counts, clashes, connectivity, row coverage, CRAH proximity, headroom, sprinkler standoff, tray-busway separation and PDU space. Each one is scoped to what the agent was thinking about.
- **The instruction can fix scope, not belief.** Rung 2 v3 (check every pair, say what is left out) completed the background sweeps and left the same-service exclusion untouched in 6 of 6.

## 4. Adaptation

- **Responses to failing checks:** every real failure was followed by a change to the solution and a re-run (runs 029, 037, 044, and 028, 034, 036, 038 in rung 1). One run (029) needed a second attempt at the same failure. One edited the check (038).
- **Where adaptation stops:** the first all-pass ends the work. Rung 2 runs use 8 to 10 calls of the 40 allowed: 7 or 8 to read the sheets, 3 to write notes, 1 to 2 to run the checks, and a few to finish. There is no second look.
- **Not tested here:** feedback from outside the agent's own checks (the grader gives none inside a run).

## What this says about the next change

The failure sits in the loop's weakest link: the check is written by the same mind that holds the belief that causes the defect, tests the plan, and is accepted as soon as it passes. Candidates, each one change, not yet run:

1. **Independent check:** the clash check is written by a second model call that sees only the instruction text (not the design or the first agent's notes) and is applied to the delivered data. Tests the correlated-error reading.
2. **Negative controls:** the agent must show every check can fail: for each kind of item, including pairs of the same kind, add a deliberate violation to a copy of the data and confirm the check reports it. A check that was never seen to fail proves nothing (the note already says so; the agent never did it).
3. **Scope audit:** before running, list every kind of item in the model and, for each requirement, which kinds it applies to; any kind not covered must be named and justified by a quoted sentence. Targets the headroom-and-heads case and the same-service case together.
4. **Print the excluded group's overlaps separately** (what made run-028 pass).
