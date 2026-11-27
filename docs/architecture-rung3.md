# Rung 3: a robust engine, a checker that never sees the design, and a designer who reviews (revised 2026-11-27)

Status: **design, for agreement. Nothing is built.** Figures: `docs/figures/fig4-structured-workflow.png` (workflow) and `fig5-structured-architecture.png` (parts).

**Revision note.** The first draft validated requirements by checking that the agent's quotes appear in the task and made exemptions depend on a quoted source. Rejected (user): a quote is text, and text can be written to satisfy a rule. Nothing in this design depends on the agent being truthful about itself. The mechanisms are (1) an engine whose defaults are strict and whose reports are facts it computed, (2) a checker that is not the designer and never sees the design, and (3) a review by the designer of facts, not claims.

## What the analysis asks of the tooling

The agent reads well, lists the requirements, and fixes what its checks report (`docs/failure-analysis.md`). What fails is the checks: written by the designer, scoped by the designer's beliefs (pieces of a run "meet at joints", headroom is for routes), tested on the plan, and accepted at the first all-pass. The tooling has to remove the designer's hand from the checks, make the checks strict by default, and show whether they can fail.

## The three parts (fig 5)

**1. The engine (ours, deterministic, tested).** A check library plus an evaluator, in the serve container, outside the task container and outside the agent's code.
- **Library (prepopulated):** all-pairs overlap with a tolerance; overlap between two roles; minimum clearance (any axis, or per axis, "at least one axis"); z-range of a role (headroom, vertical zones); distance from each item of one role to the nearest of another; connectivity of a group (touching within a tolerance) and whether it reaches a point; coverage of a line by a group within a distance; counts; sums of length. A **custom check** can be programmed against a small API (items, boxes, pair iterators, graph helpers) when the library does not fit; it runs in the same report.
- **Strict by default:** `no_overlap` examines all pairs of all items. Anything narrower must be declared in the configuration as an explicit scope or exclusion, and the engine **prints it** in the report ("pairs examined: 38,781 of 38,781; excluded: none", or the exact excluded group and its count). No claim is needed from anyone: the numbers are the engine's.
- **Excluded groups still measured:** for any declared exclusion the engine reports the overlaps inside the excluded group separately, so a "joint" that overlaps by 170 mm is visible as a number whether or not anyone excluded it.
- **Scope facts:** a matrix of every item kind in the model against every check; kinds no check touches are listed.
- **Self-test:** the engine copies the model, injects a violation for each kind of pair (including two items of one kind) and reports which declared checks reported it. A check that missed an injected fault is reported as insensitive.
- **Objective tracker:** route length by group and total, and the change against the previous and the best evaluation.
- **Robustness is a requirement of its own:** unit tests for touching against overlapping (the 2 mm tolerance edge), identical boxes, empty groups, thousands of items; fast pair search; explicit units; no hidden state between evaluations.

**2. The checker (a separate model call).** Before the design exists, the harness calls the model once, with fresh context: the task text, the library's catalogue and the configuration schema, and nothing else. It returns a configuration: for each requirement it finds, which library check, over which roles ("any solid", "route segments", "sprinkler heads"), with which numbers. It never sees the design, the drawings' content or the designer's notes. The hypothesis it tests: the exclusion of same-service pieces came from the designer's context (it knows its segments overlap at joints), not from the model's reading of the rule, so a checker without that context will not write it. If the checker writes it anyway, the belief is the model's own and the engine's strict default and fault self-test are what remain.

**3. The designer (the main agent).** It reads the drawings, builds the solution, exposes its items, **binds** the checker's roles to its item kinds, evaluates, and then **reviews**: it reads the checker's configuration and the report, and may amend (add, tighten, or narrow a check). Every amendment, and above all every narrowing, is recorded by the engine and printed in the report and in the final evidence. The designer is not stopped from narrowing a check; it cannot do so unseen.

## The workflow (fig 4)

Specify (checker) then Design then Bind then Evaluate then Review then Fix and Evaluate again, until nothing is violated, every item kind is covered, and every check caught its injected fault; then Finish. The final message is the agent's summary followed by an evidence block the harness appends from the engine: the checks run, pairs examined, exclusions and amendments, objective values. The agent cannot edit the evidence block; it cannot be made to say more than the engine measured.

## The model contract (until the ifcopenshell rung)

`solution.py` exposes `model_items()`: a list of `{id, kind, group, aabb: [x0, y0, z0, x1, y1, z1], attrs}` in millimetres (the boxes it would extrude into IFC solids). The engine tests the plan, not the built solids (finding 3 of the failure analysis); when the agent may run ifcopenshell, the engine reads the produced IFC and the contract disappears. Roles the checker names are bound to kinds by the designer; the engine lists any role with no kind and any kind in no role.

## General and specific

- **General:** the engine's strictness rules, scope facts, self-test, objective tracker, evidence block, the checker/designer split.
- **Geometry pack:** the library's check types (this task needs them first; other tasks need other packs: numeric formulas, documents).
- **Nothing of this task is built in:** no thresholds, kinds, names or dimensions. The numbers reach the engine through the checker's configuration, read from the task text.

## What it will not do

Know the real score, find a rule the task does not state (two grader rules are not in the task text), make the agent read a drawing correctly, test built solids, or stop a checker from sharing the designer's model-level prior. It narrows the ways a wrong check can survive; it does not close them.

## The experiment

Rung 3 v1 (checker + engine + review) against rung 2 v3 (same task, Neon, ifcopenshell blocked, six runs each). Read: pass rate; whether the checker's configuration compares same-service pieces (the central test); whether the engine's final report agrees with the grader; amendments the designer made and whether any narrowed a check; calls, tokens, minutes. Then one ablation at a time: the engine with strict defaults but **no checker** (the designer configures its own checks), to separate the two effects; and without the self-test.

## Risks

1. **The engine disagrees with the grader** (boxes against exact solids; tolerance). Report the margin and the count, compare per run.
2. **The checker repeats the designer's prior.** Then the strict default and the self-test carry the result; the experiment shows it.
3. **The checker's roles do not fit the designer's kinds.** The binding step shows the gaps; budget a round to resolve them.
4. **More tools, more calls.** Budget 60; short tool descriptions; report ordered by what to fix first.
5. **Over-fitting to this task.** Core and packs stay task-free; a second spatial task of the development set is the test.

## Decisions needed before building

1. The checker runs once, before the design, from the task text only (recommended), or again after the design with the item list?
2. The designer may amend checks, with every amendment and narrowing logged and shown (recommended), or is the checker's configuration fixed?
3. Library plus a custom-check escape hatch (recommended), or library only?
4. Call budget 60?
