# Rung 3: the structured workflow (the initial idea, introduced now)

Status: **design, for agreement. Nothing is built.** Figures: `docs/figures/fig4-structured-workflow.png` (the workflow) and `fig5-structured-architecture.png` (the parts).

## Why now: what the failure analysis asks of a tool

The runs so far (`docs/failure-analysis.md`) say the agent reads the drawings well, lists every requirement, and fixes what its checks report. What fails is the loop around the checks: they are written by the same mind that holds the belief that causes the defect, they are scoped to what the agent was thinking about, nothing shows they can fail, and the work ends at the first all-pass. Each failure maps to one feature:

| What went wrong (evidence) | What the tool does about it |
|---|---|
| The check leaves out exactly the pairs that are wrong: same-service pieces, in 12 of 12 rung 2 runs | A clash check is declared as data and defaults to **all pairs**. Leaving a group out is an *exemption* that must carry a sentence **quoted word for word from the task**; no quote, no exemption. The engine also reports the overlaps of any exempted group separately, so the number is always visible. |
| The headroom check loops over routes only; 16 heads are never looked at | The engine builds a **coverage matrix**: every kind of item in the model against every check. A kind no check touches is listed in the report ("sprinkler heads: covered by no headroom check"). |
| 9 of 12 checks passed the first time; none was ever seen to fail | A **self-test**: the engine copies the model, injects a violation for each kind of pair (including two items of the same kind) and reports which declared checks caught it. A check that cannot fail is flagged as insensitive. |
| The agent stops at its own first all-pass | The workflow offers **Finish** only when every requirement has a check, every check passed the self-test, and nothing is violated. Until then the report says what is missing. |
| Final messages claim "zero clashes" for a check that skipped the failing pairs | **Finalize** writes the final message from the ledger and the last evaluation: each requirement, its status, the evidence, the exemptions and assumptions. The agent can add a note; it cannot delete a line. |
| Connectivity wanted pieces to touch; the clash rule wanted them not to overlap; only one was tested | Both live in the same engine and the same report: pieces that overlap at a joint show up as clashes, pieces that do not touch show up as a break. The trade-off is visible instead of resolved silently. |
| No numerical feedback on the objective (route length) | An **objective tracker** reports route length by service, the total, and the change against the previous and the best evaluation. |

## The workflow (fig 4)

Requirements (a ledger the harness validates) then Design (the agent writes its solution) then Declare (checks as data) then Evaluate (the engine reports) then Fix and Evaluate again, until the report says READY, then Finish. The only free-form part is Design; everything else has a structure the agent fills in and the harness validates.

## The parts (fig 5)

All tools run in the serve container, in Python (with numpy), outside the task container and outside the agent's own code. The engine is ours: it cannot be told to skip a pair, and the agent's belief about joints cannot enter it.

1. **Requirements ledger** `requirements_submit`. Each entry: `id`, `quote` (a sentence or phrase from the task), `kind` (constraint, objective, deliverable), `applies_to` (kinds of item, or all), `metric`, `threshold`, `assumption` (true if the agent is adding something the task does not say).
   - Rejected if the quote is not a word-for-word substring of the task (whitespace aside).
   - Reports every **number with a unit** and every sentence with *zero, every, all, no, must, at least, at most* in the task that no quote covers, so a dropped requirement is visible.
2. **Check declaration** `checks_declare`, geometry pack first. Checks are JSON bound to a requirement id: `no_overlap` (kinds A against kinds B, tolerance, exemptions with quotes), `min_clearance`, `z_range` (items of a kind must lie in a range), `connected` (items of a group form one network and reach a point), `coverage_along` (a group serves a line over a fraction of its length within a distance), `length` (sum over a group). Unknown kinds or an exemption without a verbatim quote are rejected with the reason.
3. **Evaluate** `evaluate`. The harness runs the agent's `solution.py` in the task container through a fixed runner, reads the items, runs the engine, and returns one report:
   - per requirement: pass or fail, count, **worst offenders with identifiers and margins in the task's units**;
   - exempted groups: their overlaps, counted separately;
   - the coverage matrix and the list of uncovered kinds;
   - the self-test: which checks caught which injected violation;
   - the objective: values, change, best so far;
   - a READY flag with the reasons it is not set.
4. **Finalize** `finalize`. Builds the final message from the ledger and the last evaluation.

**The model contract (until the later rung with ifcopenshell).** The agent's `solution.py` exposes `model_items()`: a list of `{id, kind, group, aabb: [x0, y0, z0, x1, y1, z1], attrs}` in millimetres, the same boxes it would extrude into IFC solids. This tests the *plan* (see finding 3 of the failure analysis); the writer is not exercised. When the agent may run ifcopenshell, the engine reads the produced IFC instead and the contract goes away.

## What is general and what is not

- **General, any task:** the requirements ledger (quote validation, number coverage), the exemption rule, the final message from the ledger, the workflow gating.
- **Geometry pack, tasks with a spatial model:** the check types and the engine. Other packs (numeric calculations, documents) are separate and later; this one is built first because the evidence is here.
- **Nothing task-specific is built in:** no thresholds, kinds, names or dimensions of this task; the numbers come from the agent's requirements and quotes. The primitives are textbook geometry. No grader knowledge is used.

## What it will not do

It does not read the grader, does not know the real score, and cannot find a requirement the task does not state (two of the grader's rules are not in the task text). It cannot make the agent read a drawing correctly. It tests the plan, not the built solids. An agent that declares a weak check is caught only where the coverage matrix, the quote rule and the self-test reach.

## The experiment

Rung 3 v1 against rung 2 v3 (same task, Neon, ifcopenshell blocked, six runs each). Read: pass rate; for each run, the report's account of why it stopped; whether the engine's last evaluation matched the grader (agreement is the test of the engine); calls, tokens and minutes (tools add calls: budget 60). After that, ablations one at a time: without the self-test, without the exemption rule.

## Risks

1. **The engine disagrees with the grader** (different tolerance, exact geometry against boxes). Mitigation: report both the margin and the count; compare to the grader per run.
2. **More tools, more calls, a distracted agent.** Mitigation: tool descriptions short, the report ordered by what to fix first.
3. **Over-fitting to this task.** Mitigation: the core stays task-free, and a second spatial task of the development set is the test.
4. **The contract (`model_items`) drifts from the solids** until the IFC is read directly.

## Decisions needed before building

1. Geometry pack first, with the general core (ledger, exemptions, finalize), then generalise: yes or no?
2. The `model_items()` contract until the ifcopenshell rung: yes or no?
3. Call budget 60 for this rung: yes or no?
4. The final message written by the harness from the ledger, the agent adding a note only: yes or no?
