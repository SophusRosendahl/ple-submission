## Headline

**With ifcopenshell blocked, one Neon run passed every gate and scored 0.921, the first nonzero score on this task. What made the difference is visible in the code: it built joints that butt instead of overlapping.** In the other Neon run (rung 2) the agent wrote its own checks, and its clash check never compared segments of the same service, so the same 20 overlaps got through. Both Flash runs used their whole call budget and delivered nothing. Every cell is one run: this is a lead to repeat, not a result.

## The four runs (task `data-hall-mep-routing`, ifcopenshell not available to the agent)

| | Rung 1 v4, Neon (run-028) | Rung 2 v2, Neon (run-029) | Rung 1 v4, Flash (run-026) | Rung 2 v2, Flash (run-027) |
|---|---|---|---|---|
| model calls (budget) | 9 (20) | 10 (40) | 20 (20, stopped) | 40 (40, stopped) |
| input tokens, cached | 380 k, 319 k | 323 k, 267 k | 344 k, 256 k | 936 k, 761 k |
| tools | bash 4, write 3, edit 1 | read 8, write 5, bash 5, edit 1 | bash 20 | read 32, bash 27, write 2 |
| imports of ifcopenshell the block refused | 0 | 0 | 1 | 2 |
| wrote its own checks | yes (plain Python, `verify.py`) | yes (`checks.py`) | no | requirements only |
| grader | **OK, 0 clashes, all gates passed** | clash gate failed: 20 same-service overlaps | no deliverable | no deliverable |
| score | **0.921** | 0.0 (0.916 if the gate had passed) | 0.0 | 0.0 |

## What the two Neon runs show

1. **The fix is joint construction, and the passing run found it.** Run-028's tray entry ends at the face of the spine (`spine_x - half width`) and each branch starts at the spine's other face (`spine_x + half width`), with the comment "butt-jointed ... 0 mm gap (connected) and 0 mm overlap (clash-free)". Every earlier run drew segments centre to centre and overlapped at each joint (22 to 27 clashes). Its own verification script printed a same-service T-junction check.
2. **The method wrote the right requirement and tested the wrong thing.** Run-029's `requirements.md` quotes the task's clash rule exactly ("one solid overlapping another by > 2 mm anywhere"). Its `checks.py` has a "service vs service" check that loops over pairs of *different* services only; segments of the same service are never compared, so it printed `[OK] Zero service-vs-service clashes`. No comment says it skips them; the narrowing is in the loop structure. Its connectivity check passes because overlapping segments count as connected: connectivity and clash-freedom pull in opposite directions at a joint, and only one was tested.
3. **Blocking ifcopenshell did not cripple the agent.** Neon never tried to import it (0 refusals), wrote the script blind, and both of its scripts produced a valid IFC (0 schema errors), where in rung 0 five of eight scripts did not run or did not validate. It checked its numbers with plain Python instead.
4. **Route length and compliance are now good.** Both runs: route 214 to 215 m against 260.6 m (factor 1.000), compliance 0.92. The remaining rule failures are the constant ones (clear_height 16, two rules that check nothing, tray stack headroom).

## What the two Flash runs show

Flash does not reach the deliverable inside the budget, with or without the method. In rung 1 v4 it ran 20 bash commands and wrote nothing. In rung 2 v2 it made 32 reads (7 of them the drawings, most of the rest crops it cut from them) and 27 bash calls, wrote two files, and never wrote the solution. This is the cross-model finding for now: the same harness suits one model and starves the other. The 20 and 40 call budgets were chosen from Neon's behaviour.

## Batching: the instruction alone did nothing

Rung 2 v2's system note asks the model to batch independent tool calls. In all four runs, and in all earlier ones, **no reply held more than one tool call** (0 of 33, 97, 22 and 28 agent steps). Asking was not enough; if batching matters (it would cut Flash's call count), it needs more than a sentence, for example an example call in the note or a tool that takes several paths at once.

## Next, in order

1. **Repeat before believing it.** Neon rung 1 v4 and rung 2 v2, five runs each (about 1 USD per run), to see how often a run passes.
2. **Flash:** it needs a different lever (a larger budget, a stronger push to write a first version, or fewer crops); decide after seeing the Neon repeats.
3. **Joint construction as a lesson the harness can state in general terms** is a candidate for a later rung, once the repeats show whether it is luck.
