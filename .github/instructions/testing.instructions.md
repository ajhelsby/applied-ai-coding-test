---

## applyTo: "**/*"

# Testing strategy

## Test directory structure

Place tests in layer-specific directories under `tests/`:

- `tests/unit/` — isolated unit tests
- `tests/integration/` — PostgreSQL and Redis integration tests
- `tests/load/` — application load and breaking-point tests
- `tests/docker/` — Docker Compose topology and environment tests

Keep shared helpers, fixtures, workflow definitions, and test utilities in common locations such as `tests/helpers/` or `tests/fixtures/`. Reuse them across test layers where appropriate.

## Test layer responsibilities

Each test layer has a distinct purpose:

| Layer       | External dependencies           | Primary purpose                                                        |
| ----------- | ------------------------------- | ---------------------------------------------------------------------- |
| Unit        | None                            | Verify individual application/domain behaviour in isolation            |
| Integration | PostgreSQL + Redis              | Verify real component interactions and persistence/messaging behaviour |
| Load        | PostgreSQL + Redis              | Find performance limits, contention, and breaking points               |
| Docker      | Full Docker Compose environment | Prove the application runs correctly as deployed and scales correctly  |

Do not require tests in one layer to prove behaviour that belongs to another layer.

## Unit tests

Unit tests must run without any external services.

### Rules

- Do not connect to PostgreSQL.
- Do not connect to Redis.
- Do not require Docker.
- Do not depend on network access.
- Keep tests deterministic and fast.
- Mock or fake infrastructure boundaries where necessary.
- Prefer testing observable behaviour of the component under test rather than implementation details.

Unit tests should cover logic such as:

- DAG validation rules
- Dependency validation
- Cycle detection
- DAG construction/traversal
- State transition rules
- Template parsing
- Template resolution using supplied in-memory data
- Readiness calculations using supplied node state
- Failed dependency propagation
- Input/output transformations
- Handler behaviour where infrastructure is not required
- Retry/backoff decision logic
- Idempotency decision logic using in-memory fakes
- Error handling and edge cases

### Domain validation exception

Extensible domain validation rules may be tested directly at rule level.

Place these tests under:

`tests/unit/app/domain/validation/`

Each validation rule should have independent tests covering valid and invalid scenarios, including structured domain errors.

### Unit test boundaries

Do not test PostgreSQL queries, Redis Streams behaviour, transaction semantics, locking, or real message delivery in unit tests.

Those behaviours belong in integration tests.

## Integration tests

Integration tests use real external dependencies.

### Environment

Integration tests assume:

- PostgreSQL is running.
- Redis is running.
- Tests can create and clean up their own database data.
- Tests can interact with real Redis Streams.

Do not replace PostgreSQL or Redis with mocks when testing integration behaviour.

### Coverage

Integration tests should verify cross-component behaviour including:

- PostgreSQL persistence and retrieval
- SQLAlchemy mappings and transactions
- PostgreSQL state transitions
- PostgreSQL row-level locking/concurrency behaviour
- Redis Streams publishing and consumption
- Consumer groups
- Task acknowledgement
- Event publishing
- Orchestrator ↔ PostgreSQL ↔ Redis interactions
- Worker ↔ Redis ↔ PostgreSQL interactions
- Transactional outbox behaviour
- Worker idempotency across multiple processes
- Retry persistence and redelivery
- Failure propagation
- End-to-end workflow execution using real PostgreSQL and Redis

Verify boundary contracts including:

- Serialization/deserialization
- JSON payloads
- Message formats
- Persistence consistency
- Retry and failure behaviour
- Duplicate message handling
- Transaction rollback/recovery
- Concurrent processing

Integration tests should exercise realistic workflow definitions, including:

- Linear workflows
- Parallel branches
- Fan-out/fan-in
- Nested data passing
- Failed dependencies
- Retries
- Duplicate task delivery

## Load tests

Load tests use the real application and external dependencies.

Assume PostgreSQL and Redis are running.

The purpose of load tests is not simply to demonstrate that the happy path works. They should deliberately increase load until the application's performance or correctness limits become visible.

### Test areas

Test combinations of:

- Concurrent workflow submissions
- Concurrent workflow triggers
- Multiple workflows executing simultaneously
- Large numbers of nodes
- High fan-out/fan-in
- Many concurrent workers
- High Redis message throughput
- PostgreSQL contention
- Concurrent state transitions
- Duplicate task/event delivery
- Large workflow inputs and outputs

### Load progression

Run tests at increasing levels of intensity, for example:

1. Baseline
2. Moderate concurrency
3. High concurrency
4. Sustained load
5. Stress beyond expected operating load

Record useful measurements such as:

- Requests per second
- Workflow completion rate
- End-to-end execution latency
- Node execution latency
- Redis throughput/consumer lag
- PostgreSQL connection/transaction behaviour
- Error rate
- Retry rate
- Resource utilisation where available

### Breaking-point testing

Load tests should actively try to expose failure modes.

Look for:

- Database connection exhaustion
- Redis consumer lag
- Worker saturation
- Orchestrator contention
- PostgreSQL lock contention
- Duplicate dispatch
- Lost or duplicated events
- Increasing workflow latency
- Memory growth
- Unbounded queues/backlogs
- Incorrect workflow state under high concurrency
- Fan-in races
- Retry storms

A load test may intentionally fail once the application's breaking point is reached. The purpose is to identify and document the limit, not to force every stress test to pass.

Where practical, establish a baseline expected operating level and distinguish it from the measured breaking point.

## Docker topology tests

Docker tests validate the complete Docker Compose environment rather than individual components.

Tests should run against the actual Compose configuration and container images.

### Required topology

At minimum, validate a scaled deployment such as:

```bash
docker compose -f docker/docker-compose.yml up --build --scale api=3 --scale worker=4
```

### Validate

- Images build successfully.
- Containers start successfully.
- Health checks/readiness work correctly.
- API containers can communicate with required services.
- Workers can communicate with Redis and PostgreSQL.
- Service discovery works through Compose networking.
- Multiple API instances operate correctly.
- Multiple Worker instances operate correctly.
- Workflows can be submitted and executed through the deployed topology.
- Parallel workflows execute correctly across multiple workers.
- Container restarts do not permanently lose workflow state.
- Redis/PostgreSQL dependency failures behave appropriately.
- The complete workflow lifecycle works through the exposed API.

### Docker failure testing

Where practical, test operational scenarios such as:

- Restarting an API container during workflow execution.
- Restarting a Worker during task processing.
- Running multiple Worker replicas.
- Temporarily making Redis unavailable.
- Temporarily making PostgreSQL unavailable.
- Verifying recovery after dependencies return.

The goal is to prove that the application behaves correctly as a distributed deployment, not merely that the containers start.

## Cross-cutting best practices

- Tests must be deterministic and independently repeatable.
- Prefer behaviour and contract assertions over implementation-specific call assertions.
- Cover unhappy paths at least as thoroughly as happy paths.
- Test concurrency explicitly where the application relies on concurrency guarantees.
- Control clocks, randomness, and timing wherever possible.
- Avoid arbitrary sleeps in tests; use polling, events, or explicit synchronisation with bounded timeouts.
- Integration and Docker tests must clean up resources they create.
- Keep unit tests fast enough to run on every change.
- Run integration, load, and Docker tests in appropriate CI stages.
- Reuse realistic workflow fixtures across integration, load, and Docker tests.
- Do not duplicate the same test across layers unless the layer adds meaningful coverage.
- When a requirement concerns infrastructure correctness, test it with the real infrastructure rather than mocking it.
