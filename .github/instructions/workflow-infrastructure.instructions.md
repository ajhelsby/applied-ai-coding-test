---
applyTo: "**/*"
---

# Workflow infrastructure skill

## Architectural boundaries

- Treat PostgreSQL as the authoritative system of record for workflow and execution state.
- Treat Redis as an asynchronous transport mechanism only; never persist canonical workflow state in Redis.
- Keep transport contracts and state models decoupled so Redis can be replaced without data migration concerns.

## Initialization and runtime topology

- Follow the external initialization pattern for infrastructure dependencies:
  - PostgreSQL schema/state setup via migration/init flow.
  - Redis stream and consumer-group setup via dedicated Redis init flow.
- Application services (`api`, `orchestrator`, `worker`) should depend on successful infrastructure initialization, not perform ad-hoc bootstrapping logic inline.

## Configuration and security

- All connection details must be environment-driven (for example `DATABASE_URL`, `REDIS_URL`).
- Never hardcode credentials, hostnames, ports, or secrets in source.
- Prefer environment templates and documented defaults over implicit fallback values for critical infrastructure URLs.

## Messaging reliability principles

- Assume at-least-once delivery for asynchronous messaging.
- Use Redis Streams with consumer groups for orchestrator/worker consumption patterns.
- Acknowledge messages only after successful processing.
- Design consumers so pending/unacknowledged messages are recoverable.
- Prevent duplicate concurrent processing under normal operation through consumer-group semantics and per-instance consumer identities.

## Testing expectations for infrastructure changes

- Validate cross-service behavior with integration/docker-level tests.
- Cover publish, consume, acknowledge, and pending recovery behavior for Redis Streams changes.
- Keep tests deterministic and focused on externally observable behavior.
