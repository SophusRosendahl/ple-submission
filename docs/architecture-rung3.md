# Rung 3: a robust engine, a check-builder that never sees the design, and a designer who reviews (revised 2026-11-27)

Status: **design, for agreement. Nothing is built.** Figures: `docs/figures/fig4-structured-workflow.png` (workflow) and `fig5-structured-architecture.png` (parts).

**Revision note.** The first draft validated requirements by checking that the agent's quotes appear in the task and made exemptions depend on a quoted source. Rejected (user): a quote is text, and text can be written to satisfy a rule. Nothing in this design depends on the agent being truthful about itself. The mechanisms are (1) an engine whose defaults are strict and whose reports are facts it computed, (2) a check-builder that is not the designer and never sees the design, and (3) a review by the designer of facts, not claims.

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

**2. The check-builder (a sub-agent on a different model).** Before the design exists, the harness calls the model once, with fresh context: the task text, the library's catalogue and the configuration schema, and nothing else. It returns a configuration: for each requirement it finds, which library check, over which roles ("any solid", "route segments", "sprinkler heads"), with which numbers. It never sees the design, the drawings' content or the designer's notes. The hypothesis it tests: the exclusion of same-service pieces came from the designer's context (it knows its segments overlap at joints), not from the model's reading of the rule, so a check-builder without that context will not write it. If the check-builder writes it anyway, the belief is the model's own and the engine's strict default and fault self-test are what remain.

**3. The designer (the main agent).** It reads the drawings, builds the solution, exposes its items, **binds** the check-builder's roles to its item kinds, evaluates, and then **reviews**: it reads the check-builder's configuration and the report, and may amend (add, tighten, or narrow a check). Every amendment, and above all every narrowing, is recorded by the engine and printed in the report and in the final evidence. The designer is not stopped from narrowing a check; it cannot do so unseen.

## The workflow (fig 4)

Specify (checker) then Design then Bind then Evaluate then Review then Fix and Evaluate again, until nothing is violated, every item kind is covered, and every check caught its injected fault; then Finish. The final message is the agent's summary followed by an evidence block the harness appends from the engine: the checks run, pairs examined, exclusions and amendments, objective values. The agent cannot edit the evidence block; it cannot be made to say more than the engine measured.

## The model contract (until the ifcopenshell rung)

`solution.py` exposes `model_items()`: a list of `{id, kind, group, aabb: [x0, y0, z0, x1, y1, z1], attrs}` in millimetres (the boxes it would extrude into IFC solids). The engine tests the plan, not the built solids (finding 3 of the failure analysis); when the agent may run ifcopenshell, the engine reads the produced IFC and the contract disappears. Roles the check-builder names are bound to kinds by the designer; the engine lists any role with no kind and any kind in no role.

## General and specific

- **General:** the engine's strictness rules, scope facts, self-test, objective tracker, evidence block, the check-builder/designer split.
- **Geometry pack:** the library's check types (this task needs them first; other tasks need other packs: numeric formulas, documents).
- **Nothing of this task is built in:** no thresholds, kinds, names or dimensions. The numbers reach the engine through the check-builder's configuration, read from the task text.

## What it will not do

Know the real score, find a rule the task does not state (two grader rules are not in the task text), make the agent read a drawing correctly, test built solids, or stop a check-builder from sharing the designer's model-level prior. It narrows the ways a wrong check can survive; it does not close them.

## The experiment

Rung 3 v1 (checker + engine + review) against rung 2 v3 (same task, Neon, ifcopenshell blocked, six runs each). Read: pass rate; whether the check-builder's configuration compares same-service pieces (the central test); whether the engine's final report agrees with the grader; amendments the designer made and whether any narrowed a check; calls, tokens, minutes. Then one ablation at a time: the engine with strict defaults but **no checker** (the designer configures its own checks), to separate the two effects; and without the self-test.

## Risks

1. **The engine disagrees with the grader** (boxes against exact solids; tolerance). Report the margin and the count, compare per run.
2. **The check-builder repeats the designer's prior.** Then the strict default and the self-test carry the result; the experiment shows it.
3. **The check-builder's roles do not fit the designer's kinds.** The binding step shows the gaps; budget a round to resolve them.
4. **More tools, more calls.** Budget 60; short tool descriptions; report ordered by what to fix first.
5. **Over-fitting to this task.** Core and packs stay task-free; a second spatial task of the development set is the test.

## Decisions taken (user, 2026-11-27)

1. **Name:** it is a sub-agent that **programs the checks**: the check-builder, not "the checker".
2. **Runs once, before the design, from the task text and the library only.** Simple first; something richer later (for example a second pass once the design exists).
3. **The checks are fixed after the check-builder sets them up.** The designer reviews the checks and the report and may record a concern; the concern is shown in the evidence block; it does not change the checks. (This replaces the amend-and-log idea: simpler; the cost is that a wrong check cannot be repaired inside a run, which we will see in the reports.)
4. **Library plus custom checks:** a library-only design is too restrictive.
5. **Budget: 40 calls for the designer** (as in rung 2) rather than 60; the check-builder's calls are counted and reported separately (expected 1 to 3).
6. **Sub-agents always run on a different model from the designer.** Open point below.

## Settled: a second model, and the competition's rules (organizers' `docs/rules.md` and `docs/models.md`, read 2026-11-27)

- `rules.md`: "The `model_api` in `submission.yaml` must match the model your harness actually calls."
- `models.md`: "Call only the model you declared. In evaluation, the key works for that model..." and `kit/README.md`: in evaluation a `google-cloud` entry's key "works only for its declared model", while the local proxy serves all eleven.
- **So a sub-agent on a different model cannot be part of a submitted entry** (the call would be refused and the entry would break the rule). It can be used in **local research runs**, where our proxy serves every model.
- **Consequence for the design:** the check-builder takes its model as a setting. The submittable harness uses the declared model with a **fresh context** (the independence comes from the context, not the model). A different model is a research ablation: it tells us whether independence of model adds anything beyond independence of context. The user's principle, sub-agents on a different model, is kept for those research runs.

## Engine validated against the grader (2026-11-27)

The engine's strict all-pairs `no_overlap` (2 mm tolerance, boxes) was run on the solids of 12 delivered models (built locally, each element's bounding box) and compared with the clash list in the grader's own report for that run, by element name:

| runs | grader clashes | engine clashes | same pairs |
|---|---|---|---|
| 029, 031, 033, 034, 035, 036, 037, 039, 041, 043 | 20, 21, 21, 25, 13, 38, 30, 23, 23, 22 | the same numbers | all of them, no pair on one side only |
| 028, 032 (the two that passed) | 0, 0 | 0, 0 | n/a |

Pair for pair, in 12 of 12. On built solids the engine is a faithful clash oracle for this task. **This holds for the solids, not for a plan:** the numbers come from the IFC the script writes. That is the case for the next decision below. (Tool: `research/engine_vs_grader.py`. A first version of the extraction read vertex data from an object that had already been freed and produced garbage; the earlier cross-run geometry comparison suffered from the same bug and was never used for a conclusion. Fixed; `cross_run_geometry.py` carries the same fix.)

## Decision to take: where the items come from

- **Mode A, the plan (as designed above):** the agent's `solution.py` exposes `model_items()`; ifcopenshell stays blocked for the agent. Risk: the plan can differ from the solids the writer makes (the doors and joints that the data checks missed).
- **Mode B, the product:** the harness itself runs the agent's `solution.py` in the task container **with the real library** (the harness's runner is not under the agent's block), reads the IFC, and builds the items in the serve container. The agent never runs ifcopenshell and sees only the engine's report: clashes, schema errors, scope facts. Fidelity is that of the table above, and the invalid-IFC failures (2 of 6 in rung 1) become visible. It does give the agent run-and-validate feedback, which the "later rung" was meant to introduce, so it relaxes the earlier rule in one controlled way.
- Recommendation: B, with A kept as a fallback when the script cannot run. The evidence favours it; the choice is the user's.

## What gets built first

1. The engine and its unit tests (library, evaluator, strictness, scope facts, self-test, objective tracker); 2. the check-builder call (prompt, schema validation, retry on a rejected configuration); 3. the Pi tools for the designer (`bind_roles`, `evaluate`, `note_concern`) and the contract `model_items()`; 4. the system note; 5. a first run of six Neon runs against rung 2 v3.
