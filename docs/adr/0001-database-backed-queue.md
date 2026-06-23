# ADR 0001: Use Database-Backed Queue for MVP

## Status

Accepted

## Context

The scheduler needs durable job creation, scheduling, worker selection, and status
tracking. The MVP already persists jobs in a relational database and supports
queued and retrying jobs through the same table.

Adding a separate broker at this stage would introduce another operational
dependency before the scheduler's lifecycle semantics are stable.

## Decision

Use the `jobs` table as the default queue for the MVP.

The queue abstraction remains part of the design. It moves only job ids and exposes
`enqueue(queue_name, job_id)` and `dequeue(queue_names)`. The database adapter treats
`enqueue` as a no-op because a committed job row is the queue record. `dequeue`
selects eligible rows by queue, status, schedule, priority, and creation time.

## Consequences

- PostgreSQL or SQLite is sufficient for local development and MVP deployment.
- Job state and queue visibility cannot diverge in the default adapter.
- Workers must still lease jobs before execution because dequeue only returns a
  candidate id.
- High-throughput deployments may encounter database contention before a dedicated
  queue backend would.
- Future Valkey, Kafka, or other adapters must preserve the database as the source
  of truth for lifecycle state.

## Production Notes

When running multiple PostgreSQL-backed workers, candidate selection and lease
acquisition should be made atomic with row-level locking or conditional updates.
The abstraction should not grow payload transport responsibilities unless the
database lifecycle contract is changed deliberately.
