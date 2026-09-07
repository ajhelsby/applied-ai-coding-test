---
applyTo: "**/*"
---

# Testing strategy

## Test directory structure

- Place tests in layer-specific directories under `tests/`:
  - `tests/unit/`
  - `tests/integration/`
  - `tests/load/`
  - `tests/docker/`
- Keep shared helpers/fixtures in a common location (for example `tests/helpers/` or `tests/fixtures/`) and reuse them across layers where appropriate.

## Unit tests (controller-level API tests)

- In this repository, "unit tests" are endpoint-focused tests at the controller/API boundary.
- Do not spend effort on method-level tests for internal implementation details.
- Test endpoint permutations thoroughly: success, validation failures, auth/permission failures, not found, conflict, downstream failure, and key edge-case inputs.
- Assert externally observable behavior: status code, response shape/body, and side effects.
- If behavior cannot be reached through real endpoint execution, remove or refactor that code instead of adding synthetic tests for it.
- Keep tests deterministic, isolated, and fast.

## Persistence expectations

- Unit tests may validate PostgreSQL persistence behavior that is directly observable via endpoint behavior.
- Do not treat cross-component data handoff as unit-test scope.

## Integration tests

- Use integration tests for cross-service and external integration behavior:
  - service-to-service calls and orchestration
  - Redis interactions (read/write/invalidation/failure paths)
  - PostgreSQL interactions across component boundaries
- Verify boundary contracts, serialization, retries/timeouts, and failure propagation between systems.

## Load tests

- Load tests are distinct from integration tests, even when they exercise overlapping logic.
- Reuse shared business flows, contracts, and fixtures from integration testing where possible.
- Execute with different intensity: higher concurrency, longer duration, and performance/SLO assertions.

## Docker topology tests

- Include environment-level tests that validate scaled compose topologies, including:
  - `docker compose -f docker/docker-compose.yml up --build --scale api=3 --scale worker=4`
- Validate build/startup, health/readiness, networking/service discovery, dependency connectivity, and basic workload behavior in scaled deployments.

## Cross-cutting best practices

- Keep test suites deterministic, independent, and behavior-focused.
- Use clear assertions on contracts/behavior rather than internal call choreography.
- Prioritize unhappy-path coverage to match happy-path depth.
- Keep unit/controller suites fast for PR feedback loops; run heavier integration/load suites in appropriate CI stages.
- Avoid flaky tests by controlling clocks, randomness, and external dependencies.
