# Harness design decisions

Running log of decisions for our PLE competition entry. Newest at the bottom of each section.

## Competition context

- Runs on Kaggle, November 9, 2026 – January 5, 2027. Prizes 250K / 100K / 50K USD.
- Models in the official evaluation are supplied (and paid for) by the evaluator. Development
  runs, including the dev-set run whose artifacts we submit, are billed to our own Google Cloud
  project: no sponsored credits. Keep iteration cheap: build and test without model calls
  where possible, run on a few tasks, use a cheaper model for plumbing tests.
- Leaderboard on the 56 hidden tasks (stock vendor harnesses): Gemini 4 Neon 0.507, Claude
  Opus 5.5 0.483, Gemini 4 Carbon 0.468, Gemini 3.8 Flash 0.275. Lead candidate models: Neon
  and Opus 5.5.
- Official starter repo: `physical-engineerings-last-exam/submission-template`.

## Decided

1. **Deliverables are frozen designs, not programs.** The delivered file (e.g. `solution.py`)
   takes no inputs and recomputes nothing from data at run time. It is emitted by the harness
   from a design state, with every value written as a literal. A small fixed helper runtime
   (e.g. `place_box(...)`) is allowed; loops over data are not.
2. **The harness is data-driven internally:** facts → design → emitter → deliverable.
   - *Facts*: structured data read from the inputs, each item tagged with its source (sheet/note).
   - *Design*: the decisions, as structured state.
   - *Emitter*: renders the design into the deliverable deterministically (stable order and rounding).
3. **Evaluator first.** Before designing, the agent writes its own evaluator for the task:
   objective + constraints as code, computed deterministically. It then designs, emits, and
   evaluates the emitted deliverable in a loop.
4. **Requirement coverage.** The agent first extracts the task's requirements; every
   requirement maps to a check and every check traces back to a requirement.
5. **Evaluators are tested before they are trusted.** Each check must fail on a design broken
   specifically to trip it, and the evaluator must pass a trivially compliant design.
6. **Shared check library.** Generic checks (deliverable exists at the exact path, runs headless
   within the time limit, gives the same output twice, IFC4 + `express_rules` validation, unit
   sanity, clashes, connectivity, keep-out volumes) are tested library code. The agent writes only
   the task-specific parts. The library is uploaded into the task container (pure Python + numpy).
7. **Evaluators report a breakdown, not one number:** gates, per-rule violations with element
   IDs, and the objective with its inputs.
8. **Checks run on the emitted deliverable against the full set of facts**, not just the
   elements the agent chose to model.

9. **Pipeline per task:**
   1. *Ingest* all files: an inventory of inputs (images, rendered PDFs, MCP tool lists,
      the stub and its expected output path).
   2. *Deliverables, requirements and evaluator*: first the deliverables manifest (decision 17)
      with a placeholder written for each deliverable; then the requirement list and
      `evaluate(facts, design)`, written against the shape of the facts.
   3. *Model of reality*: facts reconstructed from the drawings, each tied to its source,
      checked for consistency.
   4. *Test the evaluator* on the model of reality: deliberately broken designs fail, a
      compliant baseline passes.
   5. *Design loop*: design → emit → evaluate → fix, iterated until good. Stop at the first of:
      all gates pass with zero violations and the objective is close to a lower bound the agent
      computes itself; no improvement for N iterations; or the time reserved for freezing is
      reached. Always keep the best valid design so far (freeze that, not the latest attempt),
      and never trade a passing gate for a better objective.
   6. *Freeze*: emit the final deliverable and run the generic checks on exactly the file
      that gets graded.

10. **Requirements are captured in a YAML register, not SysML.** One entry per requirement: id,
    text, source, kind (deliverable | information | geometric | topological),
    severity (gate | score | advisory), scope as ifcopenshell selectors, threshold, and `verify`
    (the check that proves it). The traceability ideas come from SysML (derive / satisfy / verify);
    the notation does not. Information requirements follow buildingSMART IDS concepts; geometric
    and topological ones are Python checks from the library.
    *Open:* vendor `ifctester` (not in the task container), or keep information checks in the
    register.
11. **Requirements and objectives are kept separate.** Requirements decide feasibility (pass/fail,
    or a compliance rate); objectives rank feasible designs. An objective records its formula, its
    direction (minimise / maximise) and its priority relative to feasibility, because tasks combine
    them differently: task 1 multiplies compliance by the objective; the site-model task puts
    feasibility first and, in blind scoring, does not count the objective at all.
    - A requirement has a threshold and is met or not; meeting it "better" earns nothing. An
      objective keeps rewarding improvement.
    - Severity says how the grader punishes a miss: *gate* (task scores 0), *scored* (partial
      credit lost: a compliance rate, a fraction of requirements met, or a rubric criterion),
      *advisory* (reported only). Scored requirements are still requirements, not objectives.
    - Out-of-scope items are **negative requirements** ("must not cite X as a blocker"), not a
      separate category.
12. **Document deliverables go through the same design loop.** For a memo or letter the design
    is the analysis: determinations, adopted values, calculations, findings and gaps, each with
    its source. It is evaluated and improved first; writing the Word document is the emitter
    step. The freeze step then checks that the document reflects the analysis (every finding
    present, numbers match, format rules met).
13. **The model of reality records more than values.** Each fact carries its source, and the
    model also records: which source governs when two disagree (e.g. the certified test report
    over a client's revised figure); an as-of date, with later documents filtered out; and an
    explicit list of what is missing or contradictory (e.g. "no run identifier exists"). In three
    of the four tasks reviewed, that list is where many of the points are.
14. **Deliverables are not only files.** Besides generated files, a deliverable can be an action
    in a task app (e.g. opening a work package in OpenProject over MCP) or a provided template to
    fill while keeping its format. Each has its own emitter, and the freeze step verifies each
    one: query the app's state; check the template's structure was kept.
15. **The ingest step inventories the tools in the task container.** Containers differ: the
    rubric tasks have python-docx, openpyxl, PyMuPDF and LibreOffice; the site-model task has bare
    Python with no ifcopenshell. Library checks use what is present, or bring a pure-Python
    fallback (e.g. our own minimal STEP reader/writer for IFC).
16. **Evaluator types vary by task.** Geometry tasks get fully deterministic evaluators. Document
    tasks combine deterministic checks (every ask answered, numbers recomputed from facts, format
    rules, negative requirements) with an LLM-judge role for the reasoning. Both are tested the
    same way: a deliberately broken input (an answer removed, the wrong source's value adopted)
    must trip the check aimed at it.
17. **Deliverables are defined first, in a manifest.** A task is defined by three things:
    deliverables, requirements and objectives. Each deliverable records what it is (a file, an
    app action, or the closing `done` message, which the rubric judge also reads), its exact path
    or app target, its format (e.g. IFC4 via a script, raw STEP, `.docx` from a given template),
    a content map (which requirements and asks it must carry), and its emitter and
    verification.
    - Before any design work, the manifest is checked against the prompt: every named
      deliverable is present and every path matches exactly.
    - A minimal valid placeholder is written for each deliverable as soon as the manifest
      exists, then replaced as the design improves, so a crash or timeout still leaves
      something gradable.
18. **The harness is a staged workflow that gives the agent feedback.** The model does the work
    inside each stage; the workflow defines when a stage is done and says what is wrong when it
    is not.
    - Each stage (ingest, deliverables, requirements, reality model, evaluator test, design loop,
      freeze) produces an artifact with a contract, and a checker returns structured feedback:
      specific items ("ask #4 maps to no requirement", "broken design 'pipe over PDU' passed"),
      not just pass/fail.
    - The agent cannot leave a stage while its contract fails. Going back to an earlier stage is
      allowed and logged with a reason (e.g. a design failure traced to a wrong fact reopens the
      reality model, then the evaluator is re-tested).
    - Time is budgeted per stage; the freeze stage always keeps its reserve.
    - The model always sees a compact status: current stage, open feedback items, time left,
      best result so far.
    - Every run leaves a trace (stages, feedback items, backward steps, time per stage), so we
      can improve the workflow itself across dev tasks, not just the prompts.

## Proposed (to confirm)

- **The workflow engine is code, not a prompt.** Stage contracts, checkers, transitions and
  budgets are enforced in code; the model works inside the stages. The alternative (a long
  prompt describing the workflow) is roughly what the stock vendor harnesses do.

- **Every requirement is must-meet.** The harness optimises objectives only among fully
  compliant designs, even where a grader's formula would reward trading a scored violation
  for a better objective.

## To test

- **Separate evaluator-author role** (evaluator written by a different role from the designer,
  frozen before design, revisions logged with a reason). Run with and without; keep it only
  if it measurably matters.

## Leaning towards (not yet decided)

- Hybrid design: a deterministic solver written by the agent for optimisation-shaped problems
  (routing, sizing, cost); LLM judgement for interpretive work (reading drawings, applying code
  clauses, memo arguments).
- Facts kept as a JSON file in the task container, with predefined consistency checks
  (counts match schedules, row ends land on their stated tiles, sheets agree on dimensions).
- Image input for the model (`read_file` or a `view_image` tool). None of the samples support it.
- Use the dev set to score the evaluator separately from the design: compare the agent's
  evaluator with the real grader on the same designs.

## Findings behind these decisions (task 1: `data-hall-mep-routing`)

- Score = (1 − violation_rate) × min(1, L_opt / L), behind three pass/fail gates: IFC4 schema,
  zero clashes over 2 mm, connectivity. This variant does not grade how accurately the room was
  rebuilt.
- The grader checks clashes and compliance only against the agent's own model, so leaving
  elements out hides violations. That is why our checks must use the full set of facts (decision 8).
- Reading facts accurately looks like the main source of lost points; the routing itself is
  fairly forgiving.

## Rung 0 validity (2026-11-26)

- **Rung 0 is invalid so far.** The harness showed images by name only. On image-based tasks the
  model works from the task text alone (confirmed on `data-hall-mep-routing`: its only inputs are
  seven PNG drawing sheets, and the model said it could not see them). Runs run-001 to run-004 are
  flagged invalid in `research/runs.jsonl` and kept as a record.
- **Rung 0 v3 = rung 0 plus the images attached to the single request.** One change only. The switch
  `NAIVE_IMAGES=0` restores the old behaviour for ablations.
- Reasoning effort and the 64,000-token output cap are unchanged; Gemini spends much of its output on
  thinking, which is a separate question to study later (an ablation on effort).

## Output budget (2026-11-26)

- **Rung 0 v3 is invalid too:** with the images attached, both models spent the whole output budget
  thinking and wrote no file.
- **The output-token ceiling was measured**, not assumed: Gemini 3.8 Flash accepts at most 65,536
  (HTTP 400 above), Gemini 4 Neon accepted up to 1,000,000. The harness uses a per-model budget:
  Flash 65,536, Neon 200,000, Gemini 4 Argon 65,536 (as the competition notes say).
- **Open:** if a model still spends its whole budget thinking, the next lever is the reasoning level
  (low / medium / high), measured as an ablation. A 400 error on the evaluation server counts
  against the entry, so a budget is only used if the endpoint accepted it in a probe.

## Output budget: the ceiling is 65,536 (2026-11-26, correcting the entry above)

- Neon accepted `max_completion_tokens` up to 1,000,000 in a probe, but a real request for 200,000 stopped
  at exactly 65,536 output tokens, all of them thinking. **Accepted by the API is not the same as honoured
  by the model.** Treat 65,536 as the ceiling for both Gemini models and never set a budget from a probe
  with a trivial prompt alone.
- Consequence: at the highest reasoning level a single call on `data-hall-mep-routing` spends the whole
  ceiling thinking. The harness's per-model cap table stays (it is harmless) but cannot help; the lever is
  the reasoning level, to be set and measured explicitly.

## Restart on interruption: SCRAPPED (2026-11-26, user decision)

**Scrapped the same day it was built.** Reason: the model's hidden thinking cannot be fed back, so for Neon
(all 65,536 tokens hidden thinking, no visible output) a restart is only "retry with less effort", and the
real answer to a limited output budget is an agent loop, which keeps state in files and gives every step its
own budget. The design below is kept as a record of the idea; the code was removed from `harnesses/naive`.
Rung 0 instead tries a **low reasoning effort** (v5).

(Original entry:)

- **Not two separate calls.** When the output budget can't be raised, a reply that is cut off is restarted by
  calling again with the original input **and the model's output so far**, asking it to continue where it
  stopped. The pieces are joined into one answer and the files are written from that.
- **Cut-off detection** is `finish_reason == length` **or** the output used at least 97 % of the budget,
  because the proxy reports `stop` for some calls that used the whole budget (Neon, run-008).
- **If the output so far is empty** (Neon: all 65,536 tokens were hidden thinking, so there is nothing to feed
  back), the restart says so and tells the model to write the files now, without long thinking.
- **Added by us, switchable:** each restart steps the reasoning level down one notch (max/high, medium, low;
  `NAIVE_RESTART_EFFORT_STEP=0` turns it off). Without it, restarting an all-thinking call would think for
  65,536 tokens again. Up to 5 restarts (`NAIVE_MAX_RESTARTS`), and none when under 15 minutes remain.
- **Known limits:** the model's hidden thinking is never returned by the API, so it cannot be fed back; a
  restart re-thinks from the visible text only. Every restart re-sends the inputs and images (prompt caching
  should make that cheap, which `research/kvcache.py` will show).
- Tests: `research/test_restart.py`.


- **Source of the 65,536 limit (checked 2026-11-26).** Google's Vertex AI API itself, for Gemini 3.8 Flash:
  "maxOutputTokens value of 100000 but the supported range is from 1 (inclusive) to 65537 (exclusive)". It is a
  documented model maximum, not something we or the competition set. For Gemini 4 Neon the API accepts larger
  values but real runs stop at exactly 65,536; a test asking it for a 150,000-word answer was inconclusive (it
  declined and wrote 341 tokens), so that the same limit applies there is likely, not proven.
