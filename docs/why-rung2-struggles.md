# Why rung 2 fails where rung 1 sometimes succeeds (Neon, ifcopenshell blocked, six runs each)

Evidence read from the logs: the agents' commands and outputs, their scratch files (rung 2 only: `checks.py`, `requirements.md`), their delivered scripts, and the grader's clash lists. Hidden thinking is not recorded, so mechanisms are read from code. Six runs each: these are patterns that fit all the runs, not statistics.

## The pattern in one table

| | Rung 1 v4 | Rung 2 v2 |
|---|---|---|
| passed all gates | 2 of 6 | 0 of 6 |
| what the agent's own clash check said at the end | 0 clashes in all 6 runs that wrote one; in the 4 where the grader could judge clashes (the other 2 had invalid IFC), 2 were right | "ALL CHECKS PASSED / zero hard clashes" in 6 of 6; none was right |
| same-service pieces compared with each other | in the 2 passing runs, yes; run-036 no (code seen); run-034 almost certainly no (its check printed 0 against the grader's 25; its code is cut off in the log) | no, in 6 of 6 (code or comments seen) |
| roof against door compared | yes: found and fixed in 3 of 3 runs that had the overlap | no, in 3 of the runs that had it (033, 037, 039) |
| invalid IFC | 2 of 6 | 0 of 6 |

## Finding 1: rung 2 wrote its clash check as a list of the categories it had designed for; rung 1 wrote one sweep over everything

- **Rung 2 (6 of 6):** the instruction to define a check for each requirement, from the requirement's text, produced checks built around the agent's own model: *route against background*, *route against route of a different service*, *equipment against columns*. The quoted requirement says "one solid overlapping another by > 2 mm anywhere", and every `requirements.md` quotes it correctly; the check does not implement it.
  - Route against route: only different services are compared in all six (run-029 and run-035 loop over pairs of services; run-033 and run-037 test `s1 != s2`; run-031 writes "Same-service route segments are allowed to meet at joints"; run-039 "excluding connected segments of the same service"). That is the overlap the grader found in every run (8 to 22 pairs).
  - Background against background: only equipment against columns in run-037 and run-039; not at all in run-033. The grader found door-against-roof overlaps in exactly these three (8, 8 and 13 own-room pairs). Run-029 and run-035 compared all background pairs and had none.
- **Rung 1 (the runs that wrote a clash check, 028, 032, 034, 036, 038):** a generic sweep over all solids ("Total solids: 279, Clashes: n"). It found the 8 door-against-roof overlaps in 034, 036 and 038 and the agents fixed them; the grader found none of those in any rung 1 run. The same sweep is also where same-service pairs can be left out by one condition (run-036 `if mep[i][0] != mep[j][0]`).
- **Reading:** asking for one check per requirement turns a universal requirement ("anywhere") into several specific ones, scoped to what the agent was thinking about. Asking for nothing produced a single sweep, which is coarser and more complete.

## Finding 2: the two runs that passed are the two that looked at same-service pieces at all

- **Run-028 (0.921):** its first verification printed `Same-service T-junction overlaps (>2mm): 20`, kept as a separate category. It rewrote the script so each branch starts at the face of its trunk instead of the centre line; the second verification printed 0. The check failed first, and the failure was the signal.
- **Run-032 (0.612):** its first attempt to run the real script through its own checks failed; it then built a stand-in for ifcopenshell that records every element the real builder creates, and swept all 279 recorded solids (including same-service pairs): 0 clashes, which the grader agreed with. It is the only run, in either rung, that checked the solids the script actually builds.
- **Every run that failed the clash gate had a check that did not compare same-service pairs:** rung 2, all six (code or comments seen); rung 1, run-036 (code seen) and run-034 (inferred: its check printed 0 clashes while the grader found 25 same-service overlaps; the part of its script that holds the loop is truncated in the log).

## Finding 3: the checks test the plan, not the product (both rungs)

With ifcopenshell blocked, every agent split its script into a data builder (centre lines, assumed widths) and a writer that makes the IFC solids, and its checks import the data builder. The writer is never run. Any difference between the data and the solids (a door extruded differently, a segment drawn centre to centre) is invisible to the check. Run-032's stand-in is the one exception. This is a cost of the ifcopenshell block, not of either rung's method, and it affects both.

## Finding 4: why rung 2 does better on validity (a hypothesis)

- Both invalid rung 1 scripts (030, 038) create one shape representation per kind of object (`c1_rep`, `pdu_rep`, `door_rep`) and assign it to many products, which violates an IFC rule (one representation, one product; the grader prints it as WR11 with "6 = sizeof(...)"). The same error appeared in rung 0 and in rung 2 v1's first run. The passing scripts make a fresh representation inside the loop for each element.
- No rung 2 script made that mistake (0 of 6). Their requirements already carry the sentence "Validate with express_rules=True" and several add "ifcopenshell cannot be imported in this run, so we must be careful": the requirement list may have put the schema rule in front of the agent when it wrote the code. This is a hypothesis; the effect is 0 of 6 against 2 of 6.

## What this means

- The method did what it is built to do in one respect (it keeps the requirement in view, and the schema errors went away) and failed in another (the check it asked for was written from the design, not from the requirement). The failure is a property of how the instruction is followed: **it asks the agent to turn a requirement into checks, and a universal requirement is turned into a list of specific checks.**
- "A check that cannot fail proves nothing" (in the note) did not help: the checks could fail, on the cases the agent had in mind.

## Experiments that would test these readings (not run)

1. **Finding 1:** rung 2 with one changed sentence: write the clash check as one sweep over every pair of solids, nothing excluded; list anything you leave out and why. If rung 2 then compares same-service pairs, the instruction wording was the cause; if the exclusion survives, it is the model's prior about joints.
2. **Finding 3:** a version where the check is run against the built solids (the later rung with ifcopenshell, or the stand-in of run-032 offered as a tool).
3. **Finding 4:** a rung 1 variant with the schema sentence from the task text repeated in the note, to see whether the invalid-IFC rate follows it.
4. **More runs:** six each cannot separate a 33% from a 0% pass rate with confidence (Fisher exact about 0.45); repeats on the same task, then other tasks.

## Test of the wording: rung 2 v3 (one sentence added; six Neon runs; 2026-11-27)

The added sentence: where a requirement is about every item or every pair, write that check as one sweep over every item or pair, with nothing excluded, and say in the check's output what is left out and why.

| | rung 2 v2 | rung 2 v3 |
|---|---|---|
| passed the gates | 0 of 6 | 0 of 6 |
| clash gate failed on same-service overlaps | 6 of 6 (8 to 22 pairs) | 6 of 6 (13 to 22 pairs) |
| overlaps inside the model's own room rebuild | 4 of 6 | **1 of 6** |
| clash check compares same-service pieces | 0 of 6 | **0 of 6** (all six leave them out) |
| final message says what the check excluded | no | **yes in 6 of 6** (4 say "same-service junctions excluded", 2 say "cross-service pairs") |

- **The sentence fixed one thing and left the other.** The room-against-room sweeps are now complete (own-room overlaps 4 of 6 down to 1 of 6): the narrow *scope* came from the wording. The same-service exclusion did not move: in all six runs the agent writes the sweep, leaves out same-service pairs, and does what the sentence asks for the exclusion: it says so, with the reason the agent already believed ("they meet at elbows/tees", "same-service junctions"; run-044 even counts the 45 pairs it skipped and prints them). An exclusion with a stated reason satisfied the instruction; the reason itself was never questioned.
- **So there are two causes.** (1) Scope narrowed by category: caused by the wording, fixed by the sentence. (2) A belief that overlaps at joints between pieces of one service are acceptable: held by the model in 12 of 12 rung 2 runs (v2 and v3) and in the rung 1 runs that failed the gate, not changed by wording; the two runs that passed are the two whose checks reported those pairs (run-028) or tested the built solids (run-032).
- **A gain in transparency:** the final messages now say what the check left out, where v2's said "zero clashes" without the qualification. It does not raise the score, but it stops a reader (or a judge) from taking an unqualified "zero" at face value.
- **What would address the belief:** the checks must put the evidence in front of the agent. Run-028 passed because its check printed `Same-service T-junction overlaps (>2mm): 20` as a separate category; the agent saw a number it could not call zero. Candidate next change, one sentence: when a check leaves a group of pairs out because the agent believes they are exempt, it must still compute and print the overlaps for that group separately, and the agent may only call the requirement met if that count is zero or a quoted sentence of the instruction grants the exemption.
