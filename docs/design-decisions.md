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

## Rung 0 first valid result (2026-11-26)

- **Rung 0 v5 = one call, images attached once, reasoning effort low.** It is the first rung-0 configuration that
  produces output on `data-hall-mep-routing`. Flash: the delivered script failed when the grader ran it (wrong ifcopenshell argument). Neon: valid
  model, connectivity gate passed, 30 clashes. Both 0.0 (run-009, run-010).
- **The failures are of the kind a run-and-check loop finds**, which is the case for rung 1 (the agent loop).
- **Reasoning effort is now a recorded, switchable setting** (`run_dev.py --effort`), so it can be varied as an
  ablation (low / medium / high) rather than left at the proxy's default.

## A check that tested nothing is not a pass (2026-11-26, user decision)

- The grader reports some compliance rules with "0 items checked" (the submitted model had nothing the rule
  applies to) and lets them through. **We count those as NOT PASSED**: no evidence of compliance. Tables and
  tallies (`research/check_table.py`) show `NOT PASSED`, and the tally reads "N of M passed, F failed, U not
  passed". Run-010: 6 of 11 passed, 3 failed, 2 not passed.
- **The same rule applies to our own harness's self-checks** (rung 1 on): a self-check that found nothing to
  check, skipped, or errored is logged as `passed: null` and is treated as not passed, never as a pass. A
  check must prove it looked at something.
- Why it matters: the grader only checks what is in the submitted model, so leaving elements out (or modelling
  them in a form the grader does not recognise) hides violations. An empty check is a warning sign, not good news.

## A hidden naming contract (2026-11-27, from the task's own drawings)

- Two compliance rules (`tray_below_tile`, `wide_obstruction_needs_sprinkler`) checked nothing on run-010 even
  though the model built what the drawings define: one 35 mm floor panel following the room outline, a tray
  top 88 mm below its underside, and four 1,400 mm containment roofs with in-aisle heads beneath them.
- The task text refers to "exact element classes" and "required Pset_DCM_* property sets" but gives only one
  example (racks), and **none of the seven sheets states any IFC class, type or property name**. The grader
  appears to identify the floor panel and the containment roof by names the task never gives.
- **Consequence for the harness:** a model cannot see this failure from the inside, and the grader reports
  nothing about it except a rule that checked nothing (which we count as not passed). Using a convention found
  by probing the dev grader would be task-specific tuning, which the fair-play rules forbid; a general lesson
  is allowed (name real-world elements with the standard IFC class that fits them, and say which names were
  assumed in the final message).
- **Open:** whether the public competition docs or the dataset card state the convention. Look there only.


## Run the deliverable (2026-11-27, user decision)

- **What happened:** in 8 rung-0 v5 observations (run-009 to run-016) three deliveries (all Flash) were scripts that failed when
  the grader ran them (wrong ifcopenshell arguments, a non-existent attribute), each within 1 second; two
  wrote invalid IFC (both Neon) and three had clashes. **The agent did not crash.** It finished, sent `done`, and delivered a
  file that does not work. The process that failed was the grader running `output/solution.py`.
- **Requirement:** trying to run the delivered file is the first thing an agent must do, and **the harness must do
  it too**: execute the deliverable in the task container and see whether it runs and writes the model, before
  `done`. Where the task's deliverable is code, this is the cheapest check there is.
- **Placement in the ladder:** rung 1 stays unstructured (the agent may run the file with `bash` if it chooses); we
  log whether it did. The harness-driven step is the first structured self-check of the next rung, and is
  general (any code deliverable), not specific to this task.
- **To verify:** that the task container has the libraries the grader uses (ifcopenshell), so a run there is
  representative of the grader's run.

### Candidate: validate the produced model with ifcopenshell (2026-11-27, user idea)

- After the harness runs `solution.py`, it opens the model the script wrote with ifcopenshell and validates it
  against the IFC schema. This is the public library's own check, not the grader's code, so it is allowed.
- **What it would have caught:** the 2 `ERR_VALIDATE` observations (invalid IFC) and the 3 `ERR_EXEC` ones (the
  script fails at the run step). **What it cannot catch:** clashes, rule violations, efficiency, and the hidden
  naming contract; those need other checks.
- **Where it runs:** in the task container if ifcopenshell is there (to verify), else in the serve container with
  ifcopenshell installed in the `install` step and the model fetched with `read_file`.
- Same placement as "Run the deliverable": the first structured self-check of the next rung, with the check
  results logged (`CHECK` lines) so the write-up can show what each check caught.

### Where ifcopenshell can run in the competition (2026-11-27, answer to a user question)

- **Serve container (our harness): yes.** `install` runs at build time as root with internet, so ifcopenshell can be
  installed into `/opt/harness` (pinned version) and ships in the bundle (limit 2 GiB compressed). No download is
  needed at run time. The harness can fetch the produced model with `read_file` and validate it there.
- **Task container: probably, not verified.** No network, so nothing can be installed there. The grader's traceback
  shows ifcopenshell in the task image's `python3.11/site-packages`, so the task image likely has it. If so, `exec`
  can run `solution.py` where the inputs are, with the grader's library version.
- **Fair play:** public library, no grader files read: allowed.
- **Open check (not run):** `python -c "import ifcopenshell"` and its version in the task image, one read-only VM job.

## Rung 1 definition (2026-11-27, user decision)

- **Pi agent loop. The input files are fed as context** (option A: pre-attached text and drawing images, as in
  rung 0); the agent does not read inputs with a tool. It can write and read its own work (scratch and
  deliverables), edit, and use `bash`; it is asked to review and consider its work. **No structured checks,
  and no ifcopenshell checks from us** (the 'Run the deliverable' and ifcopenshell validation ideas wait for a
  later rung). Reasoning effort low, as rung 0 v5.
- **What we log:** every tool call, whether the agent ran `solution.py` on its own, calls and tokens from the
  proxy request log.

## Rung 1 first VM run (2026-11-27)

- **Flash (run-017) worked end to end:** 287 model calls (284 `bash`, 2 `write`), the agent ran `solution.py` on
  its own, and the result was a valid model that failed the clash gate (`ERR_CLASH`). Score 0.0. The failure
  mode moved from "script does not run" (3 of 4 rung 0 Flash observations) to the clash gate.
- **Neon (run-018) is invalid:** the first call returned HTTP 400, "Thinking budget is not supported for this
  model. Use thinking level instead". Pi decides the wire format from the model id (`usesGoogleThinkingLevel`)
  and does not know Gemini 4, so it sends `thinkingBudget`. `harnesses/pi-rung1/patch_pi.py` adds `gemini-4` to
  that rule in both installed copies at build time and fails the build if Pi changes. Verified against a mock
  endpoint (request now carries `thinkingLevel: LOW`). Neon is rerun as a new run.
- **Lesson for the write-up (engineering reasoning):** a harness that is off-the-shelf for one model family is
  not automatically valid for another; here the proxy, not the model, reported it, on the first call.

### Rung 1 Flash run (run-017): what the agent did, and two facts it settled (2026-11-27)

- **Effort:** 287 model calls (284 `bash`, 2 `write`), 42.6 M input tokens of which 41.4 M (97.1 %) were served from
  the prompt cache, 183.5 k output tokens. Rung 0 used 1 call and about 10 k input tokens on the same task.
- **Outcome:** valid model, clash gate failed (22 clashes of 299 pairs, all between pieces of the same service);
  connectivity gate passed; rules passed 4 of 11, failed 5, 2 not checked (the same two as in rung 0). If the gate
  had passed: compliance 0.826 x efficiency 0.689 = 0.569. Score 0.0.
- **The agent ran its own deliverable and used ifcopenshell.validate on its output, unprompted.** Its first command
  printed the ifcopenshell version. This settles an open item: **the task container has ifcopenshell 0.8.4.post1
  on Python 3.11**, so running the script there is representative of the grader's run (the grader uses the same
  Python 3.11 site-packages).
- **Audit (fair play):** two filesystem searches (`os.walk('/app')` for .py/.sh/.json/.md; `os.walk('/')` for names
  containing `dc_model` or `mep`). They returned only the task's own `solution.py` stub; nothing from the grader
  was visible in the task container. Kept as a standing check: every rung 1 trajectory is scanned for reads
  outside the task folder and `/tmp`.

## Input files are read once, as initial context (2026-11-27, user decision)

- **What the Flash run did (run-017):** besides the initial context it re-opened the drawings through `bash` and
  Python (it built `/tmp/A-601_clean.npy` from an input sheet and re-read details of it). That is a second way to
  read the inputs, so rung 1 was not "files as context only".
- **Rule:** in rung 1 the input files reach the model once, in the first message. **Input guard:** the harness
  lists the input file names and folders (`pi: GUARD`), and `task-tools.ts` refuses any `bash` command that names
  one (`INPUT_GUARD`, exit code 1, with a message). The agent's own files, including the deliverable stub in the
  output folder, stay available. Refusals are counted (`pi: TOOLS ... input_guard_refusals`).
- **Limits, stated plainly:** it is a string match on the command, so it stops the natural ways of re-reading (a
  file name or an input path in a command) but not a determined workaround (for example a glob). We do not
  touch the task container's files (moving or hiding inputs would be tampering with the evaluation container).
  Text inputs longer than the per-file limit (60,000 characters) are cut in the context and cannot be re-read;
  the drawings, which carry this task, are not affected. A task whose deliverable code must read the inputs when
  it runs is unaffected: only the agent's commands are guarded, not the grader's run.
- **Versions:** rung 1 v1 = no guard (run-017 Flash; Neon rerun in progress when this was decided); rung 1 v2 =
  guard, both models. Verified locally against a mock endpoint: the model's `cat input/A-101.png` came back as
  `INPUT_GUARD: refused`.

### Rung 1 v1 results, both models (2026-11-27)

| | Flash (run-017) | Neon (run-019) |
|---|---|---|
| model calls | 287 | 10 |
| input tokens (cached) | 42.6 M (97.1 %) | 335 k (70.9 %) |
| output tokens (reasoning) | 183.5 k | 31.5 k (15.6 k) |
| tools | bash 284, write 2 | bash 6, write 1, edit 2 |
| ran its own deliverable | yes | yes |
| commands that re-opened an input file (v1, no guard) | 10 | 0 |
| grader | valid model, clash gate failed | valid model, clash gate failed |
| compliance, if the gate had passed | 4 of 11 passed, 0.569 | 6 of 11 passed, 0.600 |
| score | 0.0 | 0.0 |

- Both models now deliver a script that runs and writes a valid model (rung 0: 5 of 8 observations did not). Both
  stop at the clash gate. Neon needed 10 calls where Flash needed 287.
- Input re-reads are a Flash behaviour: 10 commands that named an input (it decoded the PNG sheets in Python); Neon
  never did. This is the baseline for the v2 input guard. (The extractor command that the harness itself runs is
  not counted.)
- Both rung 1 v1 runs are single observations; repeats are needed before any claim about the loop.

### What "input tokens" means in the rung 1 numbers (2026-11-27, after a user question)

- **The input figure is the sum, over every model call, of the whole prompt of that call**: the initial context, the
  model's own earlier replies and every tool result the harness sent back, all re-sent each time. Flash run-017:
  first call 11,110 tokens (the initial context), growing to 331,455 at call 287; sum 42,605,226 over 287 calls
  (average 148,450). Neon run-019: 11,268 growing to 49,483; sum 335,329 over 10 calls.
- **Three useful splits, to report side by side:** (1) the sum of all prompts (what the model processed),
  (2) of which served from the prompt cache (Flash 41.35 M, Neon 237.7 k), and so (3) the new, uncached input
  (Flash 1.25 M, Neon 97.6 k). A fourth, the context size at the last call, shows how large the conversation grew.
- **Cross-check pending:** these are Pi's own usage figures, logged per reply. The proxy request log (in the
  bucket, `ple-proxy-requests.jsonl`) is the ground truth and has not yet been compared for rung 1.

## Call budget guard: 20 model calls per task (2026-11-27, user decision, after a cost estimate)

- **Why:** run-017 (Flash, rung 1) used 287 calls and a conversation of 331 k tokens; at list prices a Flash run
  could cost $5 to $33 for one task, so a full pass over 15 or 29 tasks could cost hundreds of dollars. Neon did the
  same task in 10 calls.
- **How:** `harness.py` counts model replies (every reply, with or without a tool call, is one call). After the
  20th reply, its tool calls are allowed to finish, then Pi is stopped (`PI_MAX_CALLS` overrides the 20; default 20).
  A reply with no tool call is the final answer and ends the run by itself. The system note tells the model the
  budget and to write a first version early. On a stop, `final_message` says the budget was used up and that the
  deliverables were not reviewed afterwards. The log has `pi: BUDGET {max_calls, replies, stopped_by_budget}`.
- **Tests:** `test_budget.py` (counting, waiting for the last reply's tool calls, a final answer at the limit,
  killing a cancelled process). Run: `cd harnesses/pi-rung1 && python3 -m unittest test_budget`.
- **Versions:** rung 1 v1 = no guard, no budget (run-017, run-019); the v2 job (input guard only) was started and
  **cancelled** after 16 minutes when the budget was decided, never recorded; v3 = input guard + 20-call budget.
- **Why 20 is also a finding:** the efficiency criterion asks for score against calls; a capped run shows what the
  loop can do inside a fixed budget, and a task that is not finished in 20 calls is itself a result.

## Finding to write up: the model writes its own checks, unprompted, and one is wrong (2026-11-27, user observation)

- **Observed:** in rung 1 v1 both models verified their output with checks they wrote themselves, although the
  harness asks only for a review in the system note and offers no check. Flash: 6 schema validations, 10 pairwise
  geometry clash checks (first at step 245 of 295). Neon: 3 validations, 2 clash checks (the first at step 19 of 21).
  Counts are keyword matches over the commands (`ifcopenshell.validate`; `clash` with `bbox`/`geom`/`overlap`).
- **Right:** schema validation (gate 0 passed in both); Neon's first clash check found 8 overlaps in its room rebuild
  and the final model has none.
- **Wrong:** the clash checks skip same-service pairs (4 of Flash's 10, both of Neon's), contradicting the task's
  "overlapping another by > 2 mm anywhere"; the grader found 22 same-service overlaps in each run.
- **Use in the write-up:** insight and failure analysis (criterion 1). Journal section 6a; the report page
  (`docs/rung1-v1-report.md`). Caveat to state there: one run per model, keyword counts, no repeats yet.

## What the 16 clear_height violations are (2026-11-27, user question)

- **Fact (grader report, all five runs that reached the rules):** the 16 violating items are sprinkler heads, named
  `SPK-A01...`, `SPR-IA01...` or `SPR-BC-W1...` by the model, all with their underside at 1,890 mm above the finished
  floor (1,870 mm in run-017), against the 2,600 mm headroom the rule asks for. The 63 ceiling heads pass.
- **They are where the drawings put them.** The models' reconciliation notes read F-101 as 16 in-aisle heads hung under
  the cold-aisle containment roofs with the deflector at +1,890 mm. The count matches (16). So the model did not
  make a modelling mistake here; a flat 2,600 mm rule applied to a head the drawings place at 1,890 mm fails.
- **Likely explanation (not proven):** the rule is meant not to apply to heads inside a containment aisle, and the
  grader decides that by recognising the containment roof. Support: `wide_obstruction_needs_sprinkler` (roofs wider
  than 1,200 mm) found nothing to check in any run, although every model built 1,400 mm roofs, so the grader
  appears not to see the roofs as roofs; with no roof seen, the heads are not "under containment" and the headroom
  rule applies to them. It fits the same hidden naming contract as `tray_below_tile`. The other reading (a
  deliberate conflict between the drawing and the rule, meant to be flagged in the reconciliation log) is not
  excluded; we cannot tell the two apart without the grader's rules, which we do not read.
- **What we may do about it:** look only in public competition documents for the class/name convention; do not raise
  the heads to 2,600 mm, which would contradict the drawing and the sprinkler rules that already pass.
- **Cost:** 16 violations of 85 to 102 items checked. They lower the compliance factor (0.83 to 0.92 across the five
  runs); they do not trigger a gate, so on their own they would not zero the score.

## Why the clash check was wrong: tracing the reasoning (2026-11-27, user request)

Limit first: the logs hold the models' commands, code comments and results, not their hidden thinking (Neon's 15.6 k
reasoning tokens are not recorded as text). So the 'why' below is read from the code and its comments, not from the
thoughts.

- **The 22 overlaps are the joints.** Neon's `add_rect_segment` draws each piece as a box from the centre of one
  junction to the centre of the next. At a junction the next piece starts at the centre line of the one it meets, so
  the two boxes overlap by about half a width (tray 683 mm wide: about 340 mm; busway 128 mm; pipe 168 mm). The
  count fits exactly: overlaps = segments minus 1 for each service (tray 8 segments, 7 overlaps; busway 8, 7; chilled
  water 9, 8; total 22; Flash: 25 segments, 22 overlaps).
- **Neon:** excluded same-service pairs in its first clash check (step 19 of 21), with the comment *they meet at
  tees/elbows*.
- **Flash:** at step 245 it quoted the task's definition in a comment ("one solid overlapping another by > 2 mm
  anywhere"), at step 259 wrote an all-pairs detector ("check ALL pairs for clash"), and at step 280 wrote the final
  check with *Don't check elements of same service network*. At step 286 it printed "EXACTLY ZERO HARD CLASHES ANYWHERE
  IN THE ENTIRE MODEL" from that check.
- **The final messages overstate what was tested.** Flash: "Pairwise 3D mesh clash check verified 0 hard clashes
  across all 38,503 element pairs" (38,503 is every pair of its 278 solids, including the pairs its check skipped).
  Neon: "bounding-box clash check across all 279 elements: 0 hard clashes (> 2 mm)". A rubric judge reads this text.
- **The heights.** Flash's comments record both facts and never reconcile them: from drawing A-301 section 3,
  "IN-AISLE HEAD + 1890 mm FF (under containment roof, roof underside = 2000 mm)" (step 87), and "headroom rule:
  2600 mm min headroom in aisles and circulation spaces" (step 211). Neon defined `MIN_CLEAR_HEIGHT = 2600` and
  placed the heads at 1,890 mm with no comment on the difference. Neither wrote down a decision about the conflict.

## Rung 1 v3 results: input guard and 20-call budget (2026-11-27, run-020 Flash, run-021 Neon)

| | Flash (run-020) | Neon (run-021) |
|---|---|---|
| model calls | 20 of 20, stopped by the budget | 10 of 20, finished by itself |
| tools | bash 20, write 0 | bash 6, write 1, edit 2 |
| input tokens (cached) | 243,918 (158,276) | 338,103 (275,093) |
| output tokens (thinking) | 1,716 (not reported) | 36,140 (15,252) |
| input guard refusals | 0 | 0 |
| ran its own script | no | yes |
| result | **no deliverable written** (`ERR_NO_SUBMISSION`, stub never replaced) | valid model; clash gate failed: 25 overlaps, all same-service (9 / 8 / 8) |
| score if gates had passed | n/a | 0.586 |
| actual score | 0.0 | 0.0 |

- **The budget guard works as built** (counts, stops after the last reply's tools, writes an honest final message), and
  it is the first time the cap changes an outcome: Flash needed 287 calls in v1; with 20 it never wrote the file.
  Neon is unaffected: 10 calls in both versions, the same clash failure.
- **Flash spent its 20 calls on reconnaissance, not on the task.** 12 of its commands probed the container: version
  checks, `pip list`, `which tesseract`, importing cv2 and PIL (neither installed), and searches for the property-set
  definitions and for grader files. One `grep -r "Pset_DCM" /` ran into the 600 s command limit. It wrote nothing,
  although the system note says to put a first version of every deliverable in place early.
- **Fair-play flag (write up, and fix in the harness):** its commands included
  `find /app /home -name "*dc_model*" -o -name "*grader*"` and `find / -name "*mep_routing*"`, i.e. a search for grader
  files. They returned only the task folder; no grader, test or reference file is visible in the task container (checked
  in the results). The model was hunting for the `Pset_DCM_*` definitions that the task requires but never states, which
  also bears on the naming-contract hypothesis. A submitted harness must not do this (rules: do not inspect grading
  scripts), so rung 1 needs an explicit instruction against it, and the harness should log such commands.
- **Candidate changes for v4 (not built, awaiting a decision):** (1) a line in the system note: do not search the
  container for grading, test or reference files; the task and its files are all there is; (2) log a `SCAN` count of
  commands that match grader/test/verifier/reward patterns; (3) budget awareness: the extension appends a line such as
  "5 model calls left: write your deliverable now" to tool results near the limit, since the note alone did not make
  Flash write early.

## State of the organizers' repository on the VM (2026-11-27, read-only report `research/ple-state.txt`)

- Clone at `~/ple`, origin `https://github.com/SophusRosendahl/ple.git` (the participant's own copy), commit `5cf736f`
  of 2026-11-23, "Add Gemini 4 Carbon, Neon, and Hydrogen to the Google-sponsored models".
- **No local changes:** `git status --porcelain` and `git diff --stat` are empty. So the grader, task images and
  `eval/run.py` we run are exactly that commit, not edited by us. Ignored files: `.venv/`, `__pycache__/`, `local.env`,
  `uv.lock` (none is grader code).
- **Not verified:** that the commit equals the organizers' upstream at the same hash, or whether upstream has newer
  commits. Check by comparing the hash against the organizers' repository. Run records written from now on store the
  repository commit (`env.ple_commit`); earlier runs (up to run-021) do not.
- Machine: 32 CPUs and 126 GB of memory, against 2 CPUs and 4 GB for the serve container in the real evaluation.

## Sponsored endpoints and container limits, from the organizers' own files (2026-11-27, `research/runner-limits.txt`)

- **Endpoints (docs/models.md):** every Google-sponsored Gemini model is served over "OpenAI Chat Completions, Gemini API"
  (both surfaces). For local runs the docs say you need "a proxy that serves the same model names": the kit's
  `kit/model_proxy/start.sh` starts a LiteLLM proxy "backed by Vertex AI in your own Google Cloud project", and its
  `config.yaml` maps every sponsored model to `vertex_ai/<model>` (including `gemini-4-neon`, `gemini-3.8-flash`).
  The backend behind the real sponsored endpoint is not stated; the `google-cloud/` prefix and the proxy design
  suggest Vertex AI. The participant's own-key route `gemini/<model>` is Google AI Studio (`generativelanguage.googleapis.com`),
  a different service.
- **Limits:** `kit/build.py` applies "the evaluation server's limits (8 CPUs, 16 GiB RAM, 4096 processes, 8 GiB file
  size)" to the build container, capped at what the local Docker daemon has. `kit/check.py` gives the local task
  container the smallest dev task's resources (2 CPUs, 4 GB) for the smoke task. `eval/run.py` itself sets no CPU or
  memory (no match); the task containers get their limits from each task's `task.toml`, which Harbor applies
  (`research/task_resources.json`: this task 2 CPUs and 4,096 MB). So each trial's containers are already limited
  individually; the 32-CPU machine only decides how many trials run side by side (5). **Not verified:** that the
  limits are enforced inside the container; the environment audit prints `cpu.max` and `memory.max` from inside it.

## Rung 2 definition (2026-11-27, user decision) and its build

- **What changes from rung 1:** (1) the agent gets the `read` tool and **the data is not in the first message**: the
  message is the task instruction plus a plain list of the input files (paths and sizes); (2) no input guard; (3) the
  system note explicitly asks for the method: write the requirements as a numbered list quoting the instruction
  (no narrowing; assumptions listed apart), read the files one by one and note what was taken from each, check the
  ingestion and re-read when unsure, define a check per requirement from the requirement text before building, build a
  first version early, run the checks, double-check at the end, and report which checks were run and what each covered
  ("do not claim more than you tested"). The checks are the agent's own and requested by prompt: no harness-run check.
- **Unchanged, so the comparison with rung 1 isolates this change:** Pi loop, tools write/edit/bash (read added),
  reasoning effort low, images at original size, the Neon thinking-level patch, the call budget mechanism.
- **Call budget 40 (rung 1 used 20):** reading 7 drawings alone takes 7 calls; 20 is too few for this method. 40 is a
  guess to be revisited after the first run; `PI_MAX_CALLS` overrides it. Neon needed 10 calls in rung 1, Flash did not
  finish in 20.
- **Found while testing the `read` tool against a mock task container:** the extension's own `read` tool shrank a
  3000 x 2000 image to 2000 x 1333, because Pi's `images.autoResize: false` setting does not apply to a tool the
  extension creates. `task-tools.ts` now passes `autoResizeImages: false` to `createReadToolDefinition`; verified:
  the model receives 3000 x 2000. (Without it rung 2 would have compared a downscaled read with rung 1's originals.)
- **Logged for the report:** `pi: TOOLS` now has `reads` (path to times opened, so re-reads are visible) and `written`
  (paths written or edited, in order, which shows whether requirements.md, data.md and the checks were created).
- **Entry:** `harnesses/pi-rung2`; VM script `infra/gcp-vm/rung2.sh`; label `rung 2 v1`.

## Do tool calls have to be one per model call? (2026-11-27, user question)

- **No.** A model may put several tool calls in one reply; that is one model call. Pi runs them in parallel by default
  (`executeToolCallsParallel` in its agent loop) and returns all results together; the budget guard already handles it
  (it waits for every tool call of the last allowed reply).
- **Our models never did it, unprompted.** Replies with more than one tool call: Flash v1 0 of 296, Neon v1 0 of 22,
  Flash v3 0 of 31, Neon v3 0 of 22. So "reading 7 drawings takes 7 calls" in the rung 2 notes was an assumption about
  behaviour, supported by these logs, not a limit of the system.
- **Effect of batching:** fewer calls and less wall time, not fewer tokens (every image still enters the context once).
  It also lowers the call-budget pressure that stopped Flash in rung 1 v3.
- **Decision (user): ask for batching by default.** Done in rung 2 v2 (below); rung 1 is left as measured. The original plan follows for the record.
- **Plan:** let rung 2 v1 finish as the baseline (does it batch on its own? almost certainly not), then rung 2 v2 adds one
  line to the system note: make independent tool calls together in one reply, for example reading several files at once,
  since every reply counts against the budget. One change, measured against v1. The call and tool counts per reply are
  already in the logs, so the report can show it.

### Rung 2 v2 = rung 2 v1 plus batching (2026-11-27, user decision)

- The system note now says: when tool calls do not depend on each other, make them together in one reply (read all the
  files needed at once; put several commands into one bash call), because every reply counts against the budget. The
  step 'read the input files one by one' became 'read every input file you need, several at once if you like'.
- Pi bash makes the command side easy (chained commands in one call); reading the drawings still needs the `read` tool
  (only it returns images to the model), several `read` calls in one reply run in parallel.
- `VERSION` is `rung 2 v2`; `infra/gcp-vm/rung2.sh` labels runs `rung 2 v2`. The VM is running rung 2 v1 (baseline);
  v2 is queued behind it, so the pair measures exactly this change. What to look at in the results: replies with more
  than one tool call, total calls, wall time, and whether the 40-call budget still binds.

## Environment audit results (2026-11-27, run-022, a diagnostic, marked invalid in the tracker)

What a model can see and reach in the task container, listed from inside it by a harness that makes no model calls:

- **Limits enforced, confirmed from inside:** cgroup `cpu.max 200000 100000` (2 CPUs), `memory.max 4294967296` (4 GiB),
  `pids.max 4096`, although `nproc` still says 32. So each trial's task container is capped to its task's own limits.
- **What is visible:** Debian 13, Python 3.11 with ifcopenshell, the task folder (`input/` with the 7 PNGs, `output/solution.py`
  stub), `/filesystem` as a link to it, empty `/home`, a nearly empty `/root`. Environment variable names only: `GPG_KEY HOME
  HOSTNAME LANG PATH PLEBENCH_EXEC_ID PWD PYTHON_SHA256 PYTHON_VERSION SHLVL`; no keys. No file named like a grader, test,
  verifier, reward or answer outside Python packages. Three bind mounts from the host: `/logs/agent`, `/logs/artifacts`,
  `/logs/verifier` (where the trial's logs and later the grader's reports go; nothing in them during the agent's run).
  The agent runs as root and everything in the container is writable.
- **MISMATCH:** the audit's connection test to `1.1.1.1:53` **succeeded**. The competition says the task container has no network
  at all; on this VM it has the Docker default. No agent used it: none of 6 rung 1 and rung 2 runs has a command touching
  curl, wget, pip install, apt, git clone or a URL. But a harness that relied on the network would pass here and fail in the
  evaluation, so this is a fidelity gap to close. Where the setting lives is being looked up (`research/network-settings.txt`).
- The journal's account of how closely our environment matches the evaluation must carry this item until it is fixed.

## Rung 2 v1 results (2026-11-27, run-023 Flash, run-024 Neon)

| | Flash (run-023) | Neon (run-024) |
|---|---|---|
| calls | 40 of 40, stopped by the budget | 12 of 40, finished |
| tools | read 21, bash 18, write 1 | read 8, bash 4, write 4, edit 1 |
| replies with more than one tool call | 0 | 0 |
| input tokens (cached) | 612,534 (446,705) | 336,957 (277,681) |
| output tokens (thinking) | 7,750 (not reported) | 37,046 (9,834) |
| wrote requirements.md | yes (the only file it wrote) | yes, plus data.md, checks.py, solution.py |
| ran its own checks | no | yes, twice |
| result | no deliverable (`ERR_NO_SUBMISSION`) | valid model; clash gate failed: 27 clashes |
| score if gates passed | n/a | **0.919** (compliance 0.919, route length factor 1.000: 227 m against 260.6 m) |

- **Neon followed the method, and the method caught a real error.** Its first run of its checks printed `FAIL: Schema
  validation found 8 errors` (the invalid-IFC failure seen twice in rung 0); it fixed the script and the second run printed
  PASS on all checks. It still ended with an invalid-free but clashing model: its checks printed `PASS: Zero hard clashes
  (> 2 mm)` while the grader found 27 (8 in its own room rebuild, 19 same-service). The requirement was written down and a
  check existed; the check was still wrong. **The content of requirements.md and checks.py was not recorded**, so the reason
  cannot be read: the task container is discarded and the trajectory logs only the byte count of a write. Fixed for rung 2 v2:
  the harness now logs the text files in `/tmp/scratch` at the end (`pi: SCRATCH[...]`), and the report shows them.
- **Route length improved sharply** (factor 1.000 against 0.65 to 0.69 in rung 1) with the same model; one run, so not yet a
  finding. If it holds, it is the largest change so far and the clash gate is the only thing between this run and 0.919.
- **Flash spent its whole budget reading.** 8 input reads, then 13 reads of crops it made of the drawings with bash (zooming
  on schedules and notes), 18 bash calls, and one file written. No batching. It never reached the deliverable: the batching line
  of rung 2 v2 and the budget are the two levers; the crops show the model chose to look closely at the drawings.

### Correction: the "no network" mismatch is NOT established (2026-11-27, same day)

- **What the organizers' own configuration says** (`research/network-settings.txt`): the task's `task.toml` sets
  `network_mode = "no-network"` (3 times, including its `[environment]`), and Harbor 0.20 enforces network policies through
  an egress-control sidecar (`harbor-docker-egress-control-sidecar`, `docker-compose-no-network.yaml`). `eval/run.py` itself
  sets no network option; it rewrites `task.toml` only to allow the judge host for verifier networks.
- **So my statement above, that the audit's `CONNECT 1.1.1.1 OK` shows the task container has the Docker default network, is
  withdrawn as unproven.** A TCP connect can succeed through a transparent proxy or sidecar that accepts the connection and
  carries nothing. (Tested here in the cloud session: even a connect to an address with nothing behind it succeeds.)
- **Audit v2** replaces the connect test with requests that need a reply: DNS lookup, an HTTP GET, a TCP request to
  `1.1.1.1:80`, a connect to an unroutable address, plus the routing table and network devices. Only its result decides.

## Rungs 0 to 2 do not run ifcopenshell (2026-11-27, user decision)

- **Decision:** in rungs 0 to 2 the agent must not be able to run ifcopenshell; that comes in a later rung ("run and validate").
  Rung 0 has no tools, so it already holds. In rungs 1 and 2 it is enforced **by construction, not by instruction**: the harness
  writes a stub package `ifcopenshell/__init__.py` into `/tmp/.rung_blocked` in the task container, and every bash command starts
  with `PYTHONPATH` pointing at it, so `import ifcopenshell` (and running a script that imports it) raises
  `IFCOPENSHELL_BLOCKED`. The image and the grader's own run of the deliverable are untouched, the stub is removed at the end of the
  run, and each refused import is counted (`ifcopenshell_blocked` in `pi: TOOLS`). One factual sentence in the system note tells the
  model it cannot import the library in this run and that the script it delivers will be run later with it. Verified against a
  real ifcopenshell install and end to end through Pi with a mock task container. A determined workaround (unsetting the variable,
  `python -S`) is possible; the count and the commands are logged.
- **What this does to the runs so far.** Rung 1 v1 to v3 and rung 2 v1 (runs 017 to 021, 023, 024) let the agent run ifcopenshell
  and its own script. They are not rung 1 or rung 2 as now defined; they are early evidence for the later rung: with the library and
  the ability to run its script, both models delivered scripts that run and valid models (rung 0: 5 of 8 did not), still failing on
  clashes. Keep them in the tracker and the write-up under that heading, and rerun the rungs under the new condition:
  **rung 1 v4** (v3 plus the block) and **rung 2 v2** (v1 plus block, batching and scratch logging).
- **Consequence for rung 2's method:** its checks cannot open the IFC, so they will be plain-Python checks of the agent's own numbers
  (positions, extents, clearances). That is a better test of whether requirements-first checking works without the safety net.
- **Task container's ifcopenshell and the installability question:** the task image already has ifcopenshell 0.8.4.post1 on Python
  3.11 (verified by the audit and by the agents' own output), and the task container has no network, so nothing can or needs to be
  installed there. For our own serve container, the build step runs with internet; installing the pinned library into a fresh
  Python 3.12 environment, the way our `install` does, works here (0.8.4, `validate` and `api` import); not yet tested inside the
  organizers' `debian:bookworm` builder.

### Audit v2 result: the task container's network (2026-11-27, run-025, a diagnostic)

| Test from inside the task container | Result |
|---|---|
| DNS lookup `example.com` | resolves (172.66.147.243), through Docker's resolver at 127.0.0.11 |
| HTTP GET `example.com` | **fails**: remote end closed the connection without a response |
| TCP request to `1.1.1.1:80` (HEAD) | connects, reply is empty |
| TCP connect to `10.255.255.1:80`, an address with nothing behind it | "connects" |
| TCP connect to `8.8.8.8:443` | "connects" |

- **Reading:** connections are accepted locally and carry nothing: a transparent egress block, as configured (`network_mode =
  "no-network"` in the task, enforced by Harbor's egress-control sidecar). **No data left or arrived**, so the earlier worry
  (task container with open internet) is withdrawn. The cgroup limits are as before (2 CPUs, 4 GiB, 4,096 processes).
- **What still differs from a hard `--network none`** (which the kit's own smoke check uses): DNS resolves and a connect is
  accepted instead of failing at once. For an agent the outcome is the same, a request that returns nothing; for a harness that
  retried or waited on the network it would cost time. We do not know how the real evaluation isolates the container; it is
  stated to have no network, and ours behaves the same for every request that needs a reply.
- No agent used the network in any run so far (checked: no curl, wget, pip install, apt, git clone or URL in any command).

## Rung 1 v4 and rung 2 v2 results (2026-11-27; runs 026 to 029; ifcopenshell not available to the agent)

Full write-up: `docs/rung1v4-rung2v2-report.md` and the report page. In short, one run per cell:

- **run-028, Neon, rung 1 v4: score 0.921, all gates passed** (valid IFC, zero clashes, connectivity 22/22). 9 calls. Its joints butt:
  the entry segment ends at the face of the spine and each branch starts at the spine's other face. It wrote its own plain-Python
  verification and never ran its script. First nonzero score on this task.
- **run-029, Neon, rung 2 v2:** 20 same-service overlaps. Its `checks.py` (now readable thanks to the scratch logging) compares
  segments of different services only; the requirements quote the "anywhere" rule correctly. The check encodes a narrower reading
  without saying so, and the connectivity check counts overlapping segments as connected.
- **Flash, both rungs:** no deliverable (20 calls of bash in rung 1 v4; 40 calls of reading, cropping and notes in rung 2 v2).
- **No batching** in any of the four runs although rung 2 v2's note asks for it: 0 of 180 agent steps held more than one tool call.
- The block held: 0 refusals for Neon, 1 and 2 for Flash.
- **Caveat:** n = 1 per cell. The pass could be luck; the repeats decide. Do not describe rung 1 as better than rung 2 from this.

## Neon only for now (2026-11-27, user decision)

- **Decision:** continue with Gemini 4 Neon alone. Flash delivered nothing in rung 1 v4 and rung 2 v2 (both budget-limited, mostly
  exploration and reading) and scored 0 in every rung it ran, so it is parked as probably a poor fit for this task; it stays in the
  record (runs 001 to 027) and in the write-up as the cross-model observation made so far.
- **Not forgotten:** the competition's cross-model criterion asks for at least two models on all 29 development tasks and a single
  committed `google-cloud/<id>`. That is a later step: choose the second model then (not necessarily Flash).
- **Next run:** five repeats each of rung 1 v4 and rung 2 v2 on Neon (labels end `repeat 1` to `repeat 5`), on top of run-028 and
  run-029, to measure how often a run passes and to compare the two rungs on more than one observation each. About 1 USD per run.

## Neon repeats: rung 1 v4 against rung 2 v2 (2026-11-27; runs 028 to 039, six runs each, ifcopenshell blocked)

Table by version (all Neon runs so far): `docs/ladder-results.md`, generated by `research/rung_summary.py`.

| | Rung 1 v4 (6 runs) | Rung 2 v2 (6 runs) |
|---|---|---|
| passed all gates | **2** (0.921, 0.612) | **0** |
| mean score | 0.256 | 0.000 |
| invalid IFC (`ERR_VALIDATE`) | 2 | **0** |
| clash gate failed | 2 | **6** |
| same-service overlaps in the failing clash runs | 25, 38 | 8 to 22 in all six |
| overlaps inside the model's own room rebuild | 0 of 4 runs with clash data | **4 of 6** (1, 13, 8, 10) |
| route length at or below the reference (factor 1.000) | 1 of 4 with a route | **5 of 6** |
| score if the clash gate had passed | 0.921, 0.612, 0.590, 0.586 | 0.916, 0.918, 0.918, 0.921, 0.591, 0.923 |
| calls, prompt tokens, minutes (means) | 8, 302 k, 6.1 | 9, 276 k, 6.6 |

- **Pass rate is not distinguishable yet:** 2 of 6 against 0 of 6 (two-sided Fisher exact test about 0.45). Say "no difference shown", not "rung 1 is better".
- **The two rungs fail differently.** Rung 1 v4 sometimes writes an invalid IFC blind (2 of 6; rung 0 had the same, 2 of 4), which a run-and-validate step would catch.
  Rung 2 never did (0 of 6): the requirements-and-checks method removed the invalid-IFC failures and gave a route at the reference length in 5 of 6, at the price of
  failing the clash gate every time: the same-service overlap was present in 6 of 6, the self-check's blind spot seen in run-029.
- **Rung 2 introduced overlaps in its own room rebuild (4 of 6) that rung 1 v4 did not have.** Unexplained; its scratch files are logged and can be read.
- **If the clash gate were cleared, rung 2 would average about 0.87** (hypothetical scores above); that is the size of what one general fix to the clash check is worth.
- **Not explained:** run-032 (passed, 0.612) has almost no joint-related comments in its script, so "butt joints" explains run-028 but not necessarily every pass.
- **Cost:** about 8 to 9 calls and 5 to 7 minutes per run; roughly 1 USD at list prices.
- **Candidates for the next change**, each one change, ranked by what the evidence supports:
  1. **Rung 2 with a literal-check rule stated generally:** when checking a requirement, test it on every item it covers; do not exclude a group unless the
     instruction says so, and say which groups a check covers. Targets the one failure that appears in 12 of 12 clash-gate runs of rung 2 and in the rung 1 failures.
  2. **The later rung, ifcopenshell allowed (run and validate):** removes the invalid-IFC failures of rung 1 v4, and shows whether the agent then finds
     the overlaps itself (rung 1 v1 to v3 and rung 2 v1, which had it, still failed the clash gate, so do not expect it to fix clashes alone).
  3. **Batching:** the instruction did nothing; only worth a stronger form if calls become the bottleneck, which they are not for Neon (8 to 9 per run).

## Why rung 2 fails where rung 1 sometimes succeeds (2026-11-27, user request to look deeper)

Full analysis: `docs/why-rung2-struggles.md`. Short version: in rung 2 the instruction to derive a check per requirement turned the universal clash
rule into category checks scoped to the agent's design (route vs background, route vs a route of a different service, equipment vs columns), so same-service
overlaps (6 of 6) and roof-against-door overlaps (3 runs) were never compared, and every rung 2 run ended with its own "all checks passed". Rung 1's
unprompted checks were generic sweeps over all solids and found the roof-and-door overlaps every time; the two passes were the runs that compared same-service
pieces (run-028 reported them as a separate category, run-032 swept the real built solids through a stand-in for ifcopenshell). Both rungs test the plan, not the
built solids, because ifcopenshell is blocked. Rung 2's better validity (0 of 6 invalid, against 2 of 6) fits invalid scripts reusing one shape representation
across products; hypothesis only.

## Rung 2 v3: one sentence to test why the clash checks were narrow (2026-11-27, user decision)

- **Question** (from `docs/why-rung2-struggles.md`): did rung 2's wording ("define a check for each requirement") cause clash checks scoped to the agent's design, or is leaving same-service pieces out the model's own prior?
- **Change, v2 to v3, nothing else:** one sentence in step 3: *where a requirement is about every item or every pair of items (for example that no two items overlap, or that every item meets a limit), write that check as one sweep over every item or every pair, with nothing excluded; if you leave anything out, say what and why in the check's own output.* The example is deliberately generic, not the task's own wording ("anywhere"), so this tests the principle, not a hint about this task.
- **How to read the result** (six runs, Neon, ifcopenshell blocked, compared with the six of v2): same-service pieces now compared in the checks and the clash gate cleared more often = the wording was a cause; the checks still skip same-service pairs, or say they are left out because they are joints = the exclusion is the model's prior, and a different lever is needed (a check against the built solids, or an example of the failure). Read each run's `checks.py` (logged) for the scope, not only the grade.

## Rung 2 v3 results (2026-11-27; runs 040 to 045, Neon, six runs): the wording explains the scope, not the belief

0 of 6 passed (same as v2). Own-room overlaps fell from 4 of 6 to 1 of 6, so the narrow background scope was caused by the wording. All six runs still leave same-service
pieces out of the sweep, and now say so (in the check's output and in the final message), giving the reason they already believed. Details and the next candidate in
`docs/why-rung2-struggles.md`. Table of all versions: `docs/ladder-results.md`.

## Failure analysis across the four hypotheses (2026-11-27, user request): `docs/failure-analysis.md`

Reading: not the main cause (70-number cross-run consensus; position-dependent gates pass). Requirements: captured completely, drift in scope when turned into checks
(same-service pairs, headroom applied to routes only, never to the 16 heads). Check design: the main cause (9 of 12 first runs passed; same belief in design and check;
tests the plan, not the built solids). Adaptation: fine when a check fails, but the work ends at the first all-pass and no check was ever shown to fail.
Four candidate changes listed there (independent checker, negative controls, scope audit, print the excluded group); none run yet.

## Rung 3 proposed: robust engine, an independent checker, a designer who reviews (2026-11-27, revised after user feedback)

First draft (requirements ledger with quote validation; exemptions needing a quoted source) **rejected by the user: quotes can be fabricated.** Revised design in
`docs/architecture-rung3.md`, figures 4 and 5: (1) an engine with a prepopulated check library (plus custom checks), strict defaults (all pairs, nothing excluded unless
declared), scope facts, an injected-fault self-test and an objective tracker; (2) a **checker**, a separate model call that sees only the task text and the library, writes
the check configuration before the design exists; (3) the **designer** (main agent) binds roles to its item kinds, evaluates and reviews, may amend checks, with every
narrowing logged and shown; the harness appends an evidence block to the final message. Nothing depends on the agent being truthful about itself. Four decisions open;
not built.

### Rung 3 decisions taken (2026-11-27, user)

The sub-agent is the **check-builder** (it programs the checks); it runs **once**, before the design, from the task text and the library; the checks are **fixed** afterwards (the
designer reviews and may record a concern, shown in the evidence block); library **plus custom checks**; designer budget **40** calls (check-builder calls counted
separately); **sub-agents always run on a different model** from the designer. Open: the competition says the declared `model_api` must match the model the harness calls, so
a submitted entry may not be allowed a second model; a read-only lookup of the organizers' `docs/rules.md` is running. Local experiments may use a different model; the
setting is one line.

## Rung 3 engine built and validated; the second-model rule (2026-11-27)

- **Built:** `harnesses/pi-rung3/engine.py` (check library: all-pairs overlap with strict defaults and declared exclusions, clearance incl. best-axis, z-range, nearest-within, connectivity and reach,
  coverage along a line, counts, length sum, sandboxed custom checks; scope facts; injected-fault self-test; objective tracker; report rendering) and `test_engine.py` (28 tests, including a
  property test that the self-test predicts exactly what the real check does, and a 2,400-item speed test: 0.6 s for the suite).
- **Validated against the grader:** strict all-pairs `no_overlap` on the solids of 12 delivered models reproduces the grader's clash list pair for pair (20, 21, 21, 25, 13, 38, 30, 23, 23, 22
  and 0, 0). `research/engine_vs_grader.py`. Details in `docs/architecture-rung3.md`.
- **Rules:** `rules.md` "the model_api ... must match the model your harness actually calls"; `models.md` "Call only the model you declared"; the evaluation key works only for the declared model.
  A sub-agent on a different model is therefore **research only**; the submittable harness uses the declared model with a fresh context. The check-builder's model is a setting.
- **Tool bug found and fixed:** vertex data was read from a freed temporary (garbage values such as 6e284); the earlier cross-run geometry comparison was affected and was not used for any conclusion.
- **Open:** Mode A (plan, `model_items()`) or Mode B (the harness runs the script with the real library and reads the IFC; the agent only sees the report).

### Sub-agent model, settled (2026-11-27, user)

A different model for the sub-agent cannot be forced (and a submitted entry may only call its declared model), so **the check-builder runs on the declared model with a fresh context**. The independence
the design relies on is independence of context: it never sees the design, the notes or the drawings. Whether the model's own prior about joints survives that is what the experiment shows. A
different-model ablation stays possible (the model is a setting) but is not planned.

## Rung 3 v1 built (harnesses/pi-rung3, VERSION "rung 3 v1")

- **Engine messages are the core contribution.** Every library check now says where, by how much and what to change: overlaps are clustered by cause with the exact shortening; clearance gives per-axis gaps and the move; z-range groups items with one cause and names what sits in the band; nearest-within gives direction and shortfall; connected names the closest pair across the gap; coverage lists the unserved intervals; a custom check's error names its line. A check that examined 0 items is an ERROR, not a pass (a role typo can no longer pass silently), and an unbound role lists the kinds present. 41 engine tests.
- **ifcopenshell is enabled** (no stub). The agent calls one tool, `evaluate(ifc, run?)`: it runs the build command, reads the IFC, validates the schema (validator output translated, e.g. WR11 "one representation shared by N products" becomes "create a new representation per product"), extracts element boxes, resolves roles, runs the fixed checks. Schema errors come first.
- **Check-builder** (`checkbuilder.py`): one fresh-context call on the declared model, task text only, reply is JSON (requirements, roles as kind globs, library checks, unchecked requirements, objective). Validated; one retry with the error messages; fallback is a bare overlap sweep, logged as `CHECKBUILDER FAILED`. Its calls are logged as `checkbuilder:` lines and kept out of the designer's 40-call budget.
- **Designer tools** (`task-tools.ts`, relay routes in `taskbridge.py`): `evaluate` and `note_concern`. The checks are fixed; a concern is recorded and shown with every later report.
- Roles are glob patterns over `IfcClass/ObjectType`, resolved against the kinds actually in the delivered model.
- Tested: unit tests, the tool on real IFC files, and the whole harness against a fake model server (check-builder call, designer calls, both tools, relay and Pi extension). Not yet run against a real model.

## Check-builder is now an agent that tests its own work (rung 3 v1)

- Before: one call, structural validation only, no way to see whether its checks work. Now a Pi agent with one tool, `test_checks(config)`, and a budget of 10 calls (separate from the designer's 40).
- `test_checks` validates the configuration, then `probe.py` builds a tiny synthetic model from the configuration's own role globs, plants one clean case and one known fault per check, runs the checks, and returns [ok]/WRONG rows plus the exact message the designer would read on failure. A WRONG row means the check is miswired (role typo, scope that leaves the pair out, limit on the wrong side).
- Its briefing now says how its checks are used: the designer calls `evaluate` after every build, reads the report, cannot edit checks, only record a concern. A too-strict check wastes effort, a lax or missing one lets a defect through, an unmatched role is an error the designer cannot fix. Custom checks must write their own located, quantified messages. It is told to review its work against the task text once more before replying.
- Fallbacks: if the final reply is unusable, the last configuration that passed `test_checks`; failing that, a bare overlap sweep (logged).
- Limits: probes use the globs' own kind names, so they cannot tell whether the globs match the designer's real kinds; custom checks have no generic probe; it still sees only the task text, not the input files.

## Rung 3 v1, first Neon run (run-046): invalid as a test of the engine

- Result: score 0.925, valid, 0 clashes, connectivity gate passed, 14 designer calls, 7.7 min. The check-builder used 2 calls and 1 `test_checks` round (all probes ok) and produced 14 requirements and its checks.
- **But the engine never ran.** The designer's single `evaluate` call crashed: `ifcopenshell.validate(express_rules=True)` imports `_pytest`, absent from the serve venv. The designer wrote its own `verify.py` and recorded a `note_concern` describing the failure. The 0.925 therefore says nothing about the engine; it says what rung 2 style self-checking reaches when the model also has ifcopenshell.
- **Why my tests missed it:** my local test venv had pytest installed, and the fake-model end-to-end run used that venv. Reproduced in a clean venv; fixed by pinning `pytest==8.3.5` and by making a validator failure non-fatal (the report says schema validation was unavailable and the run is not marked READY).
- Lesson for the write-up: a tool that fails in the evaluator's environment fails silently for the score; the harness must log and surface tool failures, and tests must run in the same environment the build produces. Run-046 is marked invalid and kept.
- Side result worth a second look: with ifcopenshell enabled and the same low effort, Neon passed every gate on this task (rung 2 v3, where ifcopenshell was blocked: 0 of 6 valid, every run a clash). Enabling ifcopenshell may account for most of the change, which the engine ablation has to separate.

## Rung 3 v1, second Neon run (run-047): the engine ran, the score is 0.000; why

- **Result.** Score 0.0: valid IFC, 0 clashes, but gate 2 (connectivity) failed: cable tray and busway "nothing within 2500 mm of the service entry at (200, 3360)", and rows A, B, E, F barely covered (0.03 to 0.15). 10 designer calls, 3 `evaluate` calls (all returned a real report), 4 concerns. Check-builder: 3 calls, 2 `test_checks` rounds, all probes ok. Run-046 (engine void) scored 0.925 with the same setup, so one run each says little about the mean: a single sample.
- **Three separate failures, all in the check-builder's configuration, none in the designer:**
  1. **Three custom checks were broken.** Headroom (R5), sprinkler clearance (R6) and the PDU zone (R8) all raised `TypeError: 'int' object is not subscriptable`: the code looped over `helpers['select'](...)`, which returns indices, and treated them as items. These were exactly the requirements the earlier analysis found agents miss. The probes did not run custom code, so `test_checks` said all ok. The designer saw ERROR on all three in every evaluation and filed concerns, correctly, but had no working check.
  2. **The service-entry requirement was left "unchecked".** The entry coordinates are on the M-101 and E-101 drawings, which the check-builder never sees; its own note says so. The connectivity check passed (each network connected) while the grader failed it (networks not fed from the entry). Information that exists only in the input files cannot reach a check-builder that sees only the task text.
  3. **The row-coverage check measured the wrong thing.** `coverage_along` judged each rack (1200 mm deep) as its own line, so it could pass while the grader, which judges whole rows, failed 4 of 6.
- **Fixes made (v1, untested on a model):** `helpers['items_of']` returns item dicts and the prompt shows a worked example and states that `select` returns indices; `test_checks` now runs every custom check on a synthetic model and reports an error with its line (the run-047 bug is a unit test); `coverage_along` gets `merge_lines` (racks side by side are one row, judged along its whole length).
- **Not fixed: failure 2.** Two options: let the check-builder read the input files (it then sees the drawings and can fill in the entry point, at the cost of its independence from the designer's reading, since both read the same drawings), or let the designer supply data-derived parameters to fixed checks. Left for the user to decide.

## Rung 3 v2: one agent does everything and may rewrite its checker (replaces v1's static flow)

- **Why.** v1 was a fixed pipeline: a check-builder agent writes the checks from the task text, then the designer builds against checks it cannot change. Run-047 showed the cost: the check-builder could not see the drawings (service-entry coordinates), its broken custom checks and its wrong row-coverage check stayed in force, and the designer could only file concerns. The user asked to simplify first.
- **v2.** One Pi agent, 40 calls, two new tools. `set_checks(config)` installs the checker (whole configuration each time), validates it and probes it with planted faults (the same `probe.py`, now also running custom code); `evaluate(ifc, run?)` builds and validates the IFC and runs the installed checks. The agent reads the drawings first, so it can encode numbers that live only there, writes the checks before it builds, and rewrites them when they are wrong. The check-builder agent, `note_concern` and the separate budget are gone. `checkbuilder.py` became `catalogue.py` (the text the agent is given plus the structural validation).
- **The risk this opens, and how it is made visible.** An agent that can edit its own judge can loosen it to pass. The prompt forbids loosening or deleting a check just to make the design pass and requires a summary of what was rewritten and why. Every installed version is logged (`pi: CHECKS vN` with the full configuration and a change list: checks added, removed, edited, roles changed), each evaluation names the checks version and states what was rewritten since the previous evaluation, and the grader's score is independent, so a loosened check shows up as READY with a failing grader. Whether the agent loosens checks is something the runs can now measure.
- **What stays from v1:** the engine and its diagnostics, the IFC bridge and validator messages, the probes, the call budget guard, ifcopenshell enabled, pytest pinned for the validator.
- **Not yet tried on a model.** Figures 4 and 5 (workflow and architecture) still show the v1 pipeline and need redrawing for v2.

## Rung 3 v2 results (runs 048 to 050) and v3 instructions

- Three Neon runs of v2: 0.940, 0.921, 0.923; all valid, 0 clashes, connectivity gate passed; 7 to 11 designer calls, 2 to 4 `evaluate` calls, 2 to 3 `set_checks` calls. Every agent read the drawings, put the service entry (0, 9900) into its checks, fixed bugs in its own custom checks after the probes flagged them, and none loosened a requirement (run-050 removed a `same_group` exclusion from its clash check).
- **What it does not show.** Run-046 (ifcopenshell enabled, engine void) scored 0.925, inside the v2 range. So the gain over rung 2 v3 (0 of 6 valid) is mostly ifcopenshell; the engine's own contribution is untested (needs the ablation: same harness, engine off).
- **v3 = v2 + better instructions** (the user asked to make sure the agent is instructed properly to use the engine before more runs): the catalogue now explains how to read the report line by line (CAUSE lines are one fix for N findings; ERROR means a broken check, repair it; INSIDE THE EXCLUDED PAIRS; kinds no check selects; SELF-TEST blind spots; objective and best so far), tells the agent to evaluate after every change with its build command in `run`, to list requirements with no check after installing the checks, to use the remaining budget on the objective once every check passes, and to review its checks against the instruction before finishing. The agents were using 7 to 11 of 40 calls and stopping at READY.
- Tool results (what `set_checks` and `evaluate` returned) are now logged as `pi: RESULT[...]`, because the relay trajectory does not hold them; v2's analysis had to infer what the agent saw.

## Rung 3 v3 results (runs 051 to 053): a plateau at 0.92, and why

- Scores 0.921, 0.923, 0.925 (v2: 0.940, 0.921, 0.923; run-046 with the engine void: 0.925). All valid, 0 clashes, connectivity passed, 11 to 12 designer calls, 2 to 3 `evaluate` calls. Agents followed the new instructions: they evaluated after changes and used the spare calls to shorten the route (208k to 194k, 218k to 197k, 215k to 181k mm), but that did not move the score: the grader's objective was already 1.0, and combined score = 1 - violation rate when the gates pass.
- **What caps the score.** In every one of these six runs the grader reports the same two violated rules: `clear_height` (16 in-aisle sprinkler heads, underside at 1,890 mm, needs 2,600 mm; TIA-942) and, in five of six, `tray_stack_headroom` (4). Violation rate 20/266 = 0.075 is exactly 1 - 0.925. Run-048 (0.940) had only the 16.
- **Why the engine does not catch it.** Each agent wrote its headroom check for the MEP routes only (C5 "MEP in valid overhead or plenum band", 16 items examined). The sprinkler heads are in scope for the grader's rule and out of scope for the agent's check. The report even told the agent "kinds that no check selects: none", because a count check on sprinkler heads counts as selecting them. Two engine flaws: (1) the scope fact treats a count check as coverage; (2) only `no_overlap` reports what its scope leaves out (shadow overlaps); `z_range` and the others stay silent about the kinds they never examined.
- **Proposed fix (not built).** Per-kind scope facts that count only geometric checks, and a scope shadow for `z_range`: apply the same limit to the kinds the check did not examine and report, grouped by kind, the elements that would violate it (skipping floor-standing items), without counting them. This is the same mechanism as the clash check's shadow overlaps, applied to every check.
