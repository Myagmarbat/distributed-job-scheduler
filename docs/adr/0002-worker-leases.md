# ADR 0002: Use Leases for Worker Ownership

## Status

Accepted

## Context

Workers can crash, restart, lose network access, or exceed expected handler runtime.
The scheduler needs a way to let another worker recover abandoned jobs without
requiring manual cleanup.

Permanent locks would strand work. No locks would allow uncontrolled concurrent
execution.

## Decision

Use time-bound database leases for worker ownership.

A worker may execute a job only after setting:

- `status = running`
- `locked_by = <worker id>`
- `locked_until = now + LEASE_SECONDS`
- `started_at = now`

Workers skip jobs with unexpired leases. Once a lease expires, another worker may
acquire the job and execute it again.

## Consequences

- Worker crashes recover automatically after the lease expires.
- Duplicate execution is possible and expected under the at-least-once contract.
- `LEASE_SECONDS` becomes an operational tuning parameter.
- Long-running jobs need either conservative lease sizing or a future heartbeat
  mechanism.
- Production PostgreSQL acquisition must be atomic to avoid concurrent ownership.

## Alternatives Considered

- Permanent worker locks: rejected because crashed workers would strand jobs.
- Broker-only acknowledgement: rejected because database state remains authoritative.
- Exactly-once locks: rejected because they are not realistic across process,
  database, and external side-effect boundaries.
