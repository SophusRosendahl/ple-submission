# Harness architecture

A rendered version with diagrams: <https://claude.ai/artifact/Fw9bEUMMUYkLdNfyutRf24> (private to the
repo owner).

Pi runs the agent loop. Our Python controller owns the workflow: which stage the task is in, what
each stage must produce, and what the model is told. The model works inside the stages.

## Components

| Component | Runs in | Role |
|---|---|---|
| `harness.py` + `workflow/` (controller) | serve container, Python | owns the workflow state; runs stage checkers; serves an HTTP API on localhost; writes the final message |
| Pi, RPC mode | serve container, subprocess | agent loop: model calls, reasoning replay, images, compaction, retries |
| `task-tools.ts` | inside Pi | read (with images), write, edit and bash, redirected to the task container |
| `workflow.ts` | inside Pi | thin: the stop gate, the status block, and the workflow tools, each forwarding to the controller's API |
| `plecheck/` (check library) | task container, uploaded to `/tmp/wf/lib/` at task start | stage contract checks and generic deliverable checks; stdlib Python, plus ifcopenshell etc. where the task image has them |

All workflow artifacts live in `/tmp/wf/` in the task container, outside every graded path.

## How workflow state reaches the model

| Channel | Pi mechanism | When | Kept in transcript |
|---|---|---|---|
| System prompt | `--append-system-prompt` | once, never changes | yes |
| Stage brief | in the `submit_stage` result that opens a stage (first one in the opening prompt) | stage start | yes |
| Status block | `context` event appends it as the last message | every model request | no, rebuilt each time |
| Tool results | our tools' return values | on demand | yes |
| Gate message | `agent_before_settle` adds a message and sets `continue: true` | when the model tries to stop | yes |

## Workflow tools (Pi extension tools, logic in the controller)

- `submit_stage()`: runs the current stage's checker. Pass: opens the next stage and returns its
  brief. Fail: returns a numbered list of what is wrong.
- `evaluate()`: emits the deliverables from `design/` into a staging folder, runs the library checks
  and the agent's `evaluator.py` on them, returns the breakdown. The controller keeps the best valid
  result and snapshots it to `/tmp/wf/best/`.
- `check(name, args)`: runs one library check.
- `reopen_stage(stage, reason)`: goes back; the reason is logged and later stages need re-checking.

The tool set is the same in every stage (prompt caching).

## Control

- One continuous Pi run; stage changes happen inside it.
- The model cannot stop before the freeze stage passes. After three stop attempts in one stage
  without progress, the controller logs it and moves to freeze.
- Freeze reserve (about 25 minutes before the deadline): the controller steers the model to freeze.
- Hard deadline: the controller stops Pi, restores the best snapshot to the deliverable paths
  without the model, and sends `done`.

## Later

The controller's HTTP API is the only interface the tools use, so the same tools can be offered as
an MCP server for other agents without rewriting the logic.
