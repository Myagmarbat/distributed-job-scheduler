# Distributed Job Scheduler Roadmap

This roadmap turns the current MVP into a production-ready distributed job scheduler while keeping work separable across agents. The current baseline includes FastAPI job submission, database-backed queueing, worker execution, retries/dead-lettering, tests, Docker Compose, Kubernetes manifests, and Terraform scaffolding.

## Delivery Principles

- Preserve at-least-once execution semantics; every handler must be idempotent.
- Prefer small, reviewable issues with one owner and clear acceptance criteria.
- Keep queue, worker runtime, API, deployment, and test work independently mergeable.
- Require observable behavior before scaling behavior.
- Treat deployment artifacts as contracts; code changes that need infra changes must document that dependency in the issue.

## Milestone 1: MVP Hardening

Goal: make the existing database-backed scheduler reliable enough for shared staging and local development.

Target outcome:
- API, worker, and database queue behavior are deterministic under normal retry and failure cases.
- Local setup is documented and repeatable.
- The project has enough tests to catch regressions in job state transitions.

GitHub issues:

1. API contract cleanup
   - Owner lane: code writer
   - Scope: validate job creation inputs, document response shapes, and standardize error payloads.
   - Acceptance criteria:
     - Job creation rejects malformed `job_type`, payload, and retry fields with stable 4xx responses.
     - API responses include job id, state, attempts, and timestamps needed by clients.
     - Tests cover successful submission and validation failures.

2. Worker state transition audit
   - Owner lane: code writer
   - Scope: verify queued, running, retrying, succeeded, failed, and dead-lettered transitions.
   - Acceptance criteria:
     - A failed job retries until `max_attempts`.
     - A job exceeding retries is dead-lettered exactly once.
     - Worker errors do not leave jobs permanently stuck in `running`.
     - Tests cover success, retry, dead-letter, and unexpected handler exception paths.

3. Database queue locking review
   - Owner lane: architect
   - Scope: define the expected locking model for concurrent workers and document DB-specific behavior.
   - Acceptance criteria:
     - An ADR documents SQLite and PostgreSQL behavior differences.
     - The selected locking approach prevents duplicate claim under PostgreSQL.
     - Follow-up implementation issues are created if code changes are required.

4. Local developer runbook
   - Owner lane: project manager
   - Scope: document common local commands, environment variables, and debugging steps.
   - Acceptance criteria:
     - Docs explain API startup, one-shot worker execution, Docker Compose startup, migrations, and tests.
     - Docs include the expected local URLs and sample `curl` job creation command.

Milestone exit criteria:
- Unit and integration tests pass locally.
- Two workers can run concurrently against PostgreSQL without duplicate job completion in the supported path.
- README or docs describe the supported local workflow.

## Milestone 2: Observability And Operations

Goal: make scheduler behavior inspectable before adding queue backends or production traffic.

Target outcome:
- Operators can see job throughput, failure rates, retry pressure, queue latency, and worker health.
- Logs can correlate API-created jobs with worker execution.

GitHub issues:

1. Structured logging
   - Owner lane: code writer
   - Scope: add structured logs around job creation, claim, start, retry, success, failure, and dead-letter.
   - Acceptance criteria:
     - Every job lifecycle log includes job id, job type, state, attempt, and worker identifier when available.
     - Exceptions include stack traces without leaking secrets.
     - Tests or smoke checks verify key log fields.

2. Metrics specification
   - Owner lane: architect
   - Scope: define counters, gauges, and histograms for scheduler operation.
   - Acceptance criteria:
     - ADR lists metric names, labels, cardinality limits, and alert intent.
     - Metrics cover queue depth, claim latency, run duration, success count, retry count, dead-letter count, and worker loop errors.

3. Health and readiness endpoints
   - Owner lane: code writer
   - Scope: expose API health, database readiness, and worker readiness conventions.
   - Acceptance criteria:
     - API health endpoint distinguishes process liveness from DB readiness.
     - Kubernetes probes can use stable endpoints or commands.
     - Tests cover healthy and database-unavailable behavior where practical.

4. Operational dashboard and alert backlog
   - Owner lane: DevOps
   - Scope: define dashboard panels and alert thresholds for staging.
   - Acceptance criteria:
     - Dashboard backlog includes panels for queue depth, oldest queued job age, retry rate, dead-letter rate, worker error rate, and p95 run duration.
     - Alert backlog includes actionable thresholds and runbook links.

Milestone exit criteria:
- A staging operator can identify whether failures are caused by API input, queue backlog, worker crashes, handler errors, or database connectivity.
- Lifecycle logs and metrics use consistent job identifiers.

## Milestone 3: Production Deployment Path

Goal: make deployment repeatable and safe for a first production environment.

Target outcome:
- Infrastructure, container release, migrations, and runtime configuration are explicit.
- Rollouts can be performed without losing queued jobs.

GitHub issues:

1. Container release workflow
   - Owner lane: DevOps
   - Scope: publish versioned images and define promotion from staging to production.
   - Acceptance criteria:
     - Images are tagged with immutable version identifiers.
     - Promotion does not require rebuilding the image.
     - Rollback steps are documented.

2. Migration deployment strategy
   - Owner lane: architect
   - Scope: define when and how Alembic migrations run.
   - Acceptance criteria:
     - ADR covers online migration expectations and rollback limits.
     - Deployment checklist states whether migrations run as a job, init container, or release step.
     - Risky migrations require a separate plan before implementation.

3. Secrets and configuration plan
   - Owner lane: DevOps
   - Scope: define required environment variables, secret sources, and per-environment defaults.
   - Acceptance criteria:
     - Staging and production config values are inventoried.
     - Secrets are not stored in repository files.
     - Missing required configuration fails fast.

4. Production readiness checklist
   - Owner lane: project manager
   - Scope: assemble a go/no-go checklist across app, tests, infra, observability, and rollback.
   - Acceptance criteria:
     - Checklist includes owners, evidence links, and final approval fields.
     - It covers backup/restore, migrations, deploy, rollback, monitoring, alerts, and incident handoff.

Milestone exit criteria:
- Staging deployment can be recreated from documented steps.
- A failed deployment can be rolled back while preserving existing queued jobs.
- Required dashboards and alerts exist before production traffic.

## Milestone 4: Scale And Queue Abstraction

Goal: scale beyond the database queue once usage data shows the need.

Target outcome:
- The project can add Valkey, Redis-compatible, or Kafka-style queue adapters without changing the API contract or worker handler contract.

GitHub issues:

1. Queue backend decision ADR
   - Owner lane: architect
   - Scope: compare database queue, Valkey, and Kafka-style backends for workload fit.
   - Acceptance criteria:
     - ADR defines throughput assumptions, ordering needs, retry semantics, dead-letter handling, and operational cost.
     - Decision states what remains database-backed, if anything.

2. Queue adapter contract tests
   - Owner lane: test agent
   - Scope: define reusable tests every queue backend must pass.
   - Acceptance criteria:
     - Contract tests cover enqueue, claim, ack, retry, dead-letter, visibility timeout or equivalent lease behavior, and concurrency.
     - Existing database queue passes the contract tests.

3. First external queue adapter
   - Owner lane: code writer
   - Scope: implement the selected external queue backend behind the existing queue interface.
   - Acceptance criteria:
     - Adapter passes contract tests.
     - Runtime configuration can select the backend.
     - Failure behavior is documented, including reconnection and partial outage cases.

4. Load and soak test suite
   - Owner lane: test agent
   - Scope: add tests for sustained throughput, retry pressure, and worker concurrency.
   - Acceptance criteria:
     - Test plan defines target job rates and duration.
     - Results report throughput, p95 queue latency, p95 run duration, retry rate, and error rate.
     - Known limits are converted into backlog issues.

Milestone exit criteria:
- Queue backend can be changed through configuration.
- Contract tests prevent semantic drift between backends.
- Load test results justify the selected backend and worker scaling model.

## Milestone 5: Multi-Tenant And Advanced Scheduling

Goal: add product-facing scheduler capabilities after the core runtime is observable and scalable.

Target outcome:
- Users can schedule delayed and recurring work with tenant-aware fairness and quota controls.

GitHub issues:

1. Delayed job scheduling
   - Owner lane: code writer
   - Scope: support jobs that become eligible at a future timestamp.
   - Acceptance criteria:
     - API can create delayed jobs.
     - Workers do not claim jobs before the scheduled time.
     - Tests cover due, not-yet-due, and overdue jobs.

2. Recurring schedule design
   - Owner lane: architect
   - Scope: design recurring jobs without double-firing during worker restarts or deploys.
   - Acceptance criteria:
     - ADR defines schedule representation, clock assumptions, idempotency keys, catch-up behavior, and missed-run policy.
     - Implementation issues are split into API, storage, worker, and tests.

3. Tenant quotas and fairness
   - Owner lane: architect
   - Scope: define tenant isolation, rate limits, and fair job claiming.
   - Acceptance criteria:
     - ADR defines tenant model, quota dimensions, enforcement point, and failure responses.
     - Test plan covers noisy-neighbor scenarios.

4. Job management API
   - Owner lane: code writer
   - Scope: add list, inspect, cancel, and retry controls.
   - Acceptance criteria:
     - API supports filtering by state, job type, tenant when available, and creation time.
     - Canceling a queued job prevents execution.
     - Manual retry of eligible failed jobs is audited and tested.

Milestone exit criteria:
- Delayed jobs work in production.
- Recurring jobs have an approved design before implementation.
- Tenant fairness and quota behavior are specified before accepting multi-tenant workloads.

## Parallel-Agent Workflow

Use lanes to avoid edit conflicts:

- Project manager: `docs/` planning, roadmaps, checklists, issue grooming, acceptance criteria.
- Architect: `docs/adr/` and design notes. Implementation changes require a separate code-owner issue.
- Code writer: `app/`, Alembic migrations, and code-facing docs only when tied to an implementation issue.
- Test agent: `tests/`, test plans under `docs/test-plans/`, and fixtures needed for coverage.
- DevOps: `deploy/`, Docker, CI/CD, environment docs, and deployment runbooks.
- DigitalOcean resources agent: `deploy/terraform/`, DigitalOcean registry, DOKS, Managed PostgreSQL, VPC, and environment secret wiring.

The detailed parallel-agent contract is in
[Agent Operating Model](agent-operating-model.md).

Coordination rules:

- One GitHub issue should have one primary owner, one lane, and one explicit list of touched paths.
- Cross-lane issues must name the handoff artifact, such as an ADR, test plan, migration plan, or deployment checklist.
- Agents should announce intended files before editing and avoid touching paths outside their lane.
- If an agent finds unrelated edits, they must preserve them and narrow their change instead of reverting.
- Merge order should be docs/design first, then tests or contract tests, then implementation, then deployment.
- Any issue that changes job semantics must include acceptance tests or a documented reason tests are deferred.

## Issue Template

Use this structure when opening GitHub issues:

```markdown
## Summary

## Owner Lane

## Touched Paths

## Dependencies

## Acceptance Criteria

## Test Evidence

## Rollback Or Follow-Up Notes
```

## Near-Term Backlog Priority

1. Database queue locking review.
2. Worker state transition audit.
3. API contract cleanup.
4. Local developer runbook.
5. Structured logging.
6. Metrics specification.
7. Health and readiness endpoints.
8. Migration deployment strategy.
