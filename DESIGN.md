# Task Completion Event Processing Decisions

## 1) Duplicate completion events

**Decision:** Treat duplicate completion events for already-terminal nodes as **idempotent no-op success**.

**Why:**

- Redis stream delivery can be at-least-once, so duplicates are expected and should not break orchestration.
- A no-op outcome avoids corrupting persisted state and prevents duplicate downstream progression.
- This keeps completion handling deterministic and operationally resilient without adding unnecessary failure modes.

## 2) Workflow failure policy

**Decision:** Mark workflow execution as **FAILED immediately when any node fails**.

**Why:**

- This matches the current workflow invariant that node failure implies unsuccessful workflow completion.
- It keeps state transitions simple, explicit, and easy to reason about in asynchronous event processing.
- It avoids ambiguity about whether execution can continue, and prevents accidental downstream readiness after failure.

## 3) Worker completion event stream

**Decision:** Publish worker task completion events to a dedicated
`workflow.task-completions` Redis stream.

**Why:**

- It isolates the flat worker-completion event contract from the existing outbox event envelope
  on `workflow.events`.
- It permits an independent consumer group, retry behavior, and retention policy for completion
  processing.
- It prevents orchestrator consumers from having to parse and route unrelated event shapes from a
  shared stream.
