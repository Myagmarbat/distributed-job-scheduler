# Distributed Job Scheduler Architecture

## Scope

This project is a Python distributed job scheduler with a FastAPI write/read API,
database-backed job state, and one or more worker processes that execute registered
job handlers.

The `jobs` table is the durable source of truth for lifecycle state. The system
can use the database itself as the queue for the smallest deployments, or use a
Valkey/Redis-compatible queue as the delivery layer when worker polling pressure
needs to move off PostgreSQL.

## Components

- API service: accepts job creation, lookup, listing, and cancellation requests.
- Job repository: owns durable job state transitions in the database.
- Queue adapter: exposes `enqueue(queue_name, job_id, priority, scheduled_at)`
  and `dequeue(queue_names)`.
- Worker runtime: polls queues, leases jobs, invokes handlers, and records outcomes.
- Handler registry: maps `job_type` values to executable Python callables.
- Database: stores job payload, status, scheduling metadata, attempts, locks, result,
  errors, and idempotency keys.
- Valkey: optional fast delivery layer for ready job ids. PostgreSQL remains the
  authority for lease and completion state.

## Job Model

A job is the durable unit of work. Key fields are:

- `id`: scheduler-generated job identifier.
- `queue_name`: logical queue, defaulting to `default`.
- `job_type`: handler lookup key.
- `payload`: JSON input passed to the handler.
- `status`: lifecycle state.
- `priority`: higher values are selected before lower values.
- `scheduled_at`: earliest time the job is eligible to run.
- `max_attempts` and `attempt_count`: retry budget.
- `locked_by` and `locked_until`: worker lease metadata.
- `result` and `error`: terminal or latest failure details.
- `idempotency_key`: optional client-supplied key for duplicate create suppression.

## Job Lifecycle

The normal lifecycle is:

1. `queued`: the API creates a job row. With the database queue, the row itself is
   the queue entry.
2. `running`: a worker dequeues an eligible job id and acquires a lease.
3. `succeeded`: the handler returns successfully and the worker stores the result.

Failure and control paths are:

- `retrying`: the handler raises an exception and the job still has attempts left.
- `dead_lettered`: the handler raises an exception and `attempt_count` reaches
  `max_attempts`.
- `canceled`: a caller cancels a job before successful completion or dead-lettering.
- `failed`: reserved for a non-retryable terminal failure mode; it is modeled but
  not currently used by the MVP worker.

Eligible jobs are those in `queued` or `retrying` status with `scheduled_at <= now`.
The database-backed queue selects by `priority DESC`, then `scheduled_at ASC`, then
`created_at ASC`.

```text
create
  |
  v
queued ---- cancel ----> canceled
  |
  | dequeue + lease
  v
running ---- success ---> succeeded
  |
  | handler error, attempts remain
  v
retrying --- dequeue + lease ---> running
  |
  | handler error, attempts exhausted
  v
dead_lettered
```

## At-Least-Once Execution

The scheduler provides at-least-once execution, not exactly-once execution.

At-least-once means a persisted, eligible job should eventually be offered to a
worker while capacity is available, but a handler may run more than once. Duplicate
execution can happen when:

- a worker completes external side effects and crashes before marking the job
  `succeeded`;
- a worker exceeds its lease and another worker acquires the same job;
- the queue backend redelivers a message;
- a race occurs around dequeue or lease acquisition.

Handler implementations must therefore be idempotent. They should use stable
operation keys, natural uniqueness constraints, or downstream idempotency APIs when
performing side effects. The scheduler's `idempotency_key` only deduplicates job
creation requests; it does not make handler execution exactly once.

## Queue Abstraction And Scale Path

The `JobQueue` interface deliberately moves only job ids plus scheduling metadata:

- `enqueue(queue_name, job_id, priority, scheduled_at)`: makes a persisted job
  visible to the named queue.
- `dequeue(queue_names)`: returns the next candidate job id for one of the queues.

The database adapter implements `enqueue` as a no-op because job visibility is
derived from the row's status and schedule. The Valkey adapter stores ready job
ids in sorted sets keyed by schedule time and tracks priority metadata so workers
can prefer high-priority due jobs without scanning the database on every poll.

Workers must still validate and lease the job in the database before executing
it. Valkey is a delivery accelerator, not the lifecycle authority. If Valkey is
empty or loses ephemeral entries, the adapter falls back to the database queue so
persisted jobs can still be recovered.

The database remains the source of truth for lifecycle state. Queue backends are
delivery mechanisms, not authorities for job completion.

## Lease and Locking Model

Workers do not own jobs permanently. They acquire time-bound leases:

- `locked_by` records the worker id.
- `locked_until` records when another worker may take over.
- `status` moves to `running` when the lease is acquired.

A worker may execute only after successful lease acquisition. If `locked_until` is
in the future, another worker should skip the job. If the lease expires, another
worker may reacquire and rerun the job.

For production PostgreSQL deployments, lease acquisition should be a single atomic
database operation, either using row-level locking such as `SELECT ... FOR UPDATE
SKIP LOCKED` inside a transaction or a conditional update that checks status and
lease expiry. This prevents multiple workers from simultaneously believing they
own the same job. Broker-backed queues still need the same database lease guard.

Lease duration is configured with `LEASE_SECONDS`. It should be longer than normal
handler runtime and shorter than the maximum acceptable recovery time after a worker
crash. Long-running handlers should either complete within the lease or add a
heartbeat/lease-extension mechanism before production use.

## Retry and Dead-Letter Semantics

On handler failure, the worker:

1. increments `attempt_count`;
2. stores the latest error string;
3. clears lease fields;
4. moves the job to `retrying` when attempts remain;
5. moves the job to `dead_lettered` when attempts are exhausted.

The MVP retries immediately because no retry delay or backoff is applied after
failure. A future backoff policy should set `scheduled_at` to a future time before
marking the job `retrying`.

Dead-lettered jobs are terminal for automatic execution. Operators can inspect the
stored payload, latest error, attempt count, and timestamps. Re-drive should be an
explicit operation that creates a new job or resets a dead-lettered job under
operator control; automatic re-drive would hide persistent handler or payload
problems.

## Cancellation

Cancellation is best-effort. A job in `queued` or `retrying` can be marked
`canceled` before a worker leases it. A job that is already `running` may have its
database state changed, but the current MVP does not interrupt the executing
handler. Handlers that need cooperative cancellation should periodically check job
state or receive a cancellation signal in a future runtime contract.

## DigitalOcean Deployment Shape

The intended DigitalOcean shape is:

- Container registry: stores the API/worker image built from the project Dockerfile.
- App Platform or Droplet-backed runtime:
  - API component runs the default `uvicorn app.api.main:app` command.
  - Worker component runs `python -m app.worker.main`.
- Managed PostgreSQL: primary durable store for jobs, leases, and results.
- Secrets/configuration:
  - `DATABASE_URL`
  - `WORKER_ID`
  - `LEASE_SECONDS`
- Horizontal scaling:
  - scale API containers for request throughput;
  - scale worker containers for execution throughput;
  - keep all workers pointed at the same PostgreSQL database.

For the MVP, PostgreSQL is both state store and queue. If queue throughput or
contention becomes a bottleneck, add a dedicated queue backend while preserving the
database as the lifecycle authority.

## Operational Invariants

- A job must be persisted before it is enqueued.
- Workers must lease before executing.
- Terminal states are not automatically reprocessed.
- Handler code must tolerate duplicate execution.
- Queue adapters must not bypass database lifecycle checks.
- External queue backends are allowed to lose delivery entries; persisted jobs
  must remain recoverable through the database-backed queue path.
- Retry policy must never exceed `max_attempts`.
- Dead-letter re-drive must be explicit and auditable.

## Related ADRs

- [ADR 0001: Use Database-Backed Queue for MVP](adr/0001-database-backed-queue.md)
- [ADR 0002: Use Leases for Worker Ownership](adr/0002-worker-leases.md)
- [ADR 0003: At-Least-Once Execution and Dead Lettering](adr/0003-at-least-once-retries-dead-letter.md)
- [ADR 0004: DigitalOcean Deployment Shape](adr/0004-digitalocean-deployment.md)
