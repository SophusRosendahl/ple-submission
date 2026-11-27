# How a run works, in one picture

Read the picture top to bottom. The numbers are your seven questions:
1 what starts it, 2 how the model reads data, 3 where data lives, 4 what it can call, 5 how it talks to the
evaluator, 6 how the evaluator works (and its LLM), 7 how the report is written.

```mermaid
sequenceDiagram
  participant E as Evaluator<br/>eval/run.py and Harbor
  participant T as Task container<br/>holds the files, drawings,<br/>deliverables. No network
  participant H as Our harness<br/>serve container
  participant M as Model<br/>via the proxy to Vertex AI
  participant V as Grader<br/>runs after the harness is done
  participant J as Judge LLM<br/>rubric tasks only
  participant R as Report files<br/>in the trial folder

  rect rgba(100,150,200,0.13)
    Note over E,H: 1. WHAT STARTS IT
    E->>T: start the task container
    E->>H: start the serve container, open a WebSocket
    E->>H: task: instruction, working folder, time limits
  end

  rect rgba(100,180,130,0.13)
    Note over E,M: 2-5. THE WORK. 2 reading and 3 data stay in the task container. 4 the harness can only ask for four things: exec, read_file, write_file, http. 5 every ask gets an answer with the same id
    loop until the harness says it is done
      H->>E: read_file / exec / write_file, with an id
      E->>T: do it in the task container
      T-->>E: file bytes or command output
      E-->>H: result with the same id
      H->>M: request: text, images, results so far
      M-->>H: reply: text, or the next thing to do
      Note over H,M: rung 0: our harness does the reading for the model. rung 1: the model's reply asks for the next read or command
    end
    H->>E: done with a final message
    Note over E,H: at the time limit the evaluator sends cancel and the harness must answer done
  end

  rect rgba(210,150,80,0.13)
    Note over E,J: 6. GRADING: a verifier runs in a container built from the task image
    E->>V: grade
    V->>T: read the deliverables
    T-->>V: the files
    V->>V: checks: plain code, no LLM
    opt rubric and checks-judge tasks
      V->>J: deliverable and rubric, via the proxy
      J-->>V: scores and reasons
    end
  end

  rect rgba(170,110,190,0.13)
    Note over V,R: 7. THE REPORT
    V->>R: reward.json, metrics.json, artifacts.json
    E->>R: read them, write results.json
    Note over R: our tracker, check table and journal read these
  end
```

## The same seven answers, in a line each

1. **Starts:** the evaluator starts a task container and a serve container (our harness), opens a WebSocket and sends the task.
2. **Reads:** rung 0, our harness reads the files and attaches them to one request. Rung 1, the model asks for each file with a `read` tool.
3. **Lives:** files, drawings, notes and deliverables are in the task container. The harness only ever sees what it asks for.
4. **Calls:** four actions only: `exec`, `read_file`, `write_file`, `http` (to the task's own tool servers, none here). Plus `log`, `usage`, `done`, `error` going the other way.
5. **Talks:** JSON messages over the WebSocket. Each ask has an id and gets one result back. The harness ends with `done`; at the time limit the evaluator sends `cancel`.
6. **Grades:** after the harness is done, a verifier runs in a container built from the task image. Task types: checks (plain code), rubric (an LLM judge), checks-judge (both). The judge is reached through the same model proxy.
7. **Reports:** the grader writes `reward.json`, `metrics.json`, `artifacts.json`; the evaluator collects them into `results.json`; our tracker, check table and journal are built from those.

What we do not know: the grader's internals (we do not open them) and exactly what the LLM judge is shown.
