## Headline

**Rung 1 fixed what rung 0 got wrong mechanically, and exposed a different failure: both models checked their own work against a wrong definition of a clash.** In rung 1 every script runs and writes a valid model (rung 0: 5 of 8 did not), and the room the model rebuilds no longer overlaps itself. What still fails is the same 22 overlaps between segments of one service, in every run. Both agents wrote their own clash check, and both **skipped same-service pairs** ("they meet at tees/elbows"), although the task defines a hard clash as "one solid overlapping another by > 2 mm anywhere". The check agreed with the model's belief, not with the task.

## Rung 0 and rung 1 side by side (task `data-hall-mep-routing`, the five runs that reached the rules)

| | run-010 | run-011 | run-016 | run-017 | run-019 |
|---|---|---|---|---|---|
| rung, model | 0, Neon | 0, Flash | 0, Neon | **1**, Flash | **1**, Neon |
| model calls | 1 | 1 | 1 | 287 | 10 |
| same-service overlaps (chilled water / busway / tray) | 8 / 7 / 7 | 9 / 7 / 7 | 9 / 8 / 8 | 8 / 7 / 7 | 8 / 7 / 7 |
| overlaps in its own room rebuild | 8 | 2 (+8 with the route) | 10 | **0** | **0** |
| clear_height violations | 16 of 85 | 16 of 101 | 16 of 86 | 16 of 102 | 16 of 94 |
| tray_stack_headroom violations | 8 of 25 | 8 of 32 | 9 of 28 | 15 of 25 | 7 of 25 |
| rules that checked nothing | 2 | 2 | 2 | 2 | 2 |
| route length against the reference | 0.648 | 0.613 | 0.670 | 0.689 | 0.652 |
| score if the clash gate had passed | 0.593 | 0.538 | 0.612 | 0.569 | 0.600 |
| actual score | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |

## What the five runs show

1. **Rung 1 removed the mechanical failures.** The scripts run, and the overlaps inside the model's own rebuild of the room (8, 2, 10 in rung 0) are gone in both rung 1 runs. Neon's own check found 8 roof-and-door overlaps in its first build, and its final model has none.
2. **The 22 same-service overlaps never move.** 22 to 25 in every run, in both models, with and without the loop. Both agents' own clash check excluded exactly this category, by assumption. The loop gave them a way to check, but not a reason to doubt the definition.
3. **Three things are constant across all five runs:** the 16 `clear_height` violations (all 16 are sprinkler heads, at 1,890 mm, or 1,870 mm in run-017; the models' own notes name them as the 16 in-aisle heads hung under the containment roofs, matching the drawings), the two rules that checked nothing, and a route length of 0.61 to 0.69 of the reference. They do not depend on model or rung, which fits the hidden naming-contract hypothesis for the first two (unproven).
4. **More calls did not mean a better result here.** Flash needed 287 calls and 42.6 M prompt tokens, Neon 10 calls and 0.3 M, for the same outcome.

## The models wrote their own checks, unprompted, and one was wrong

We gave rung 1 tools and a note asking it to review its work. We did not ask for checks, and the harness has none. Both models wrote them anyway:

| | Flash (run-017) | Neon (run-019) |
|---|---|---|
| commands run | 295 | 21 |
| schema validation of its own model | 6 | 3 |
| pairwise geometry clash checks | 10 | 2 |
| of those, skipping same-service pairs | 4 | 2 |

The validation was right (the grader's schema gate passed). The clash checks were wrong in scope: both skipped pairs from the same service, which is exactly where the grader found its 22 overlaps. Counts are keyword matches over the agents' commands; one run per model.

## How to improve from rung 1, ranked by what the evidence supports

Each is one change for one rung, so its effect can be measured. Score gains are what the grader formula allows, not predictions.

1. **Check against the task's own words, not the model's reading of them (structured self-check, rung 2).** Before building, the harness has the model list each requirement exactly as written; after building, each is tested literally and the result logged. For clashes that means "any overlap above 2 mm, same service included". This is general (any task with stated acceptance criteria) and targets the one failure that zeroes every run. If it clears the clash gate, the score moves from 0 to about 0.55 to 0.6.
2. **Joint construction.** Once same-service overlaps are visible, the model must make adjoining segments butt at joints. This is domain skill the check will force; nothing extra to build.
3. **Route length.** 0.61 to 0.69 of the reference caps the score at about 0.65 even with every gate and rule passing. Second in value after the clash gate, and it is a different kind of change (planning, not checking).
4. **The hidden naming contract.** Would lift the compliance factor and the two unchecked rules. Look only in public competition documents; no probing of the grader.
5. **Run-and-validate and the call budget.** Both agents already ran and validated their script unprompted, so a harness step for that would add little now. The 20-call budget (v3, running) shows what the loop does inside a fixed budget.

## What is not yet known

These are single runs per model: the same-service pattern holds in all five, but repeats would show whether the other numbers (tray_stack_headroom, route length) move. The input-token figures are Pi's own and are not yet compared with the proxy's request log.
