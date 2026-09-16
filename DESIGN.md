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

## 4) Malformed task message handling in Worker

**Decision:** For malformed or invalid task messages, publish a **failure completion event**
then acknowledge the task message.

**Why:**

- It preserves observability and auditability for invalid inputs instead of silently dropping them.
- It prevents poison messages from blocking stream progress while still signaling failure clearly.
- It aligns malformed-message outcomes with normal task failure reporting semantics.

## 5) Worker in-instance concurrency model

**Decision:** Use **bounded parallelism** (semaphore/worker pool) per worker instance.

**Why:**

- It allows concurrent task execution without letting one slow task block all intake.
- It provides predictable resource usage under load compared to unbounded fan-out.
- It combines safely with Redis consumer groups to support both vertical and horizontal scaling.

## 6) Worker shutdown behavior

**Decision:** For this coding test, stop consuming immediately on termination and cancel
in-flight work after a bounded timeout.

**Why:**

- It keeps shutdown behavior simple while ensuring the process releases its resources promptly.
- Unacknowledged tasks remain recoverable through Redis Streams' pending-message handling.
- In production, prefer a drain-first shutdown policy so active tasks can publish terminal events
  before the worker exits.

## 7) Unidentifiable malformed task handling

**Decision:** Publish malformed task messages that lack recoverable task identity to the
`workflow.task-dead-letter` Redis stream, then acknowledge the original message.

**Why:**

- A completion event cannot meet its correlation-field contract without a valid task, execution,
  and node identifier.
- A dead-letter record retains the source message and validation error for investigation.
- Acknowledging only after dead-letter publication prevents permanently pending poison messages
  without silently discarding them.

## 8) Worker structured logging format

**Decision:** Emit Worker logs as JSON through a standard-library logging formatter.

**Why:**

- JSON preserves task and stream correlation fields for machine parsing and log aggregation.
- The standard library keeps the coding-test deployment small and avoids a logging dependency.
- The formatter supports lifecycle, receipt, execution, completion, failure, and dead-letter events
  consistently.

## 9) Abandoned task recovery

**Decision:** Workers reclaim pending task messages through Redis Streams `XAUTOCLAIM` after a
configurable idle timeout.

**Why:**

- Tasks interrupted by a terminated worker can be retried by another worker instance.
- Reclaimed and newly delivered tasks follow the same bounded-concurrency processing path.
- The timeout avoids duplicate concurrent execution while allowing recovery from worker failure.

## 10) Concurrent fan-in completion coordination

**Decision:** Serialize completion processing for each workflow execution with a PostgreSQL
row-level lock on the workflow execution record.

**Why:**

- Multiple branch completions can arrive concurrently and must evaluate readiness from one
  consistent persisted state.
- Locking the execution row within the unit-of-work transaction prevents concurrent completion
  handlers from promoting the same fan-in node more than once.
- Completion persistence, readiness promotion, and workflow finalization remain authoritative in
  PostgreSQL, while task dispatch occurs after the transaction commits.
- The lock is scoped to one execution, so unrelated workflow executions can continue processing
  concurrently.

## 11) Worker task idempotency

**Decision:** Persist worker task-processing state in a dedicated PostgreSQL record keyed by the
task's deterministic `task_id`.

**Why:**

- Redis Streams provide at-least-once delivery, so the same task message may be delivered more
  than once.
- A PostgreSQL uniqueness constraint and atomic claim operation prevent multiple Worker processes
  from executing the same task concurrently.
- A dedicated task-processing record keeps message-delivery and retry state separate from the
  workflow node lifecycle represented by `node_executions`.
- Persisted completion state survives Worker restarts and allows completed duplicate deliveries to
  be acknowledged safely without invoking the handler again.
- PostgreSQL remains the authoritative source for idempotency state; Redis is used only as the
  asynchronous transport.
