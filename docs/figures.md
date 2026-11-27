# Schematics for the write-up

Three figures, redrawn to match what is built (2026-11-27). Sources are the `.mmd` files in `docs/figures/`; the PNGs
are rendered at 2x with mermaid-cli (`mmdc -p pp.json -i X.mmd -o X.png -s 2`). Regenerate after any change to the
harness.

## Figure 1. How a run works

![How a run works](figures/fig1-how-a-run-works.png)

The evaluator starts the task container (the files, no network) and our harness, relays every read, run and write the
agent asks for, and grades the files on disk afterwards. The language model is one shared box: the agent asks it for
its next action, and the evaluator asks it for rubric scores on judged tasks. Every arrow has a reply.

## Figure 2. The ladder: one change per rung

![The ladder](figures/fig2-the-ladder.png)

Rung 0 is one model call. Rung 1 adds a loop and tools with the same information up front. Rung 2 moves the data out of
the first message, adds the `read` tool, and asks for a method (requirements, data check, checks, double-check).
Guards shown are the ones built into that version: the input guard and 20-call budget in rung 1, the 40-call budget in
rung 2. Versions are listed in `docs/harness-versions.md`.

## Figure 3. The agent loop (rungs 1 and 2)

![The agent loop](figures/fig3-the-agent-loop.png)

Each model reply is one call. A reply with a tool call runs the tool through the evaluator and returns the result; a
reply with no tool call is the final answer. If the call budget runs out, the harness lets the last reply's tools
finish, stops the agent, and sends an honest note as the final message. Either way the evaluator then grades the files.

## Figure 4. The structured workflow (rung 3, proposed)

![The structured workflow](figures/fig4-structured-workflow.png)

A check-builder (a sub-agent with a fresh context that sees only the task) programs the checks once, from a prepopulated library, before the design exists. The designer builds, binds the check-builder's roles to its own item kinds, evaluates, and reviews; the checks stay as built. The engine's report is made of facts it computed: failures, what was examined, which kinds no check touches, which checks missed an injected fault. The designer's concerns are recorded and shown with the engine's evidence.

## Figure 5. The parts of the structured workflow (proposed)

![The parts of the structured workflow](figures/fig5-structured-architecture.png)

The engine (check library and evaluation) runs in the serve container, outside the task container and outside the agent's code. Strict defaults, scope facts, an injected-fault self-test and an objective tracker; the designer cannot make it skip a pair, and the check-builder never sees the design.
