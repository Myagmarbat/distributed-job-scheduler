# ADR 0003: At-Least-Once Execution and Dead Lettering

## Status

Accepted

## Context

Distributed workers cannot guarantee exactly-once side effects. A worker can fail
after performing an external action but before recording success. Queue backends can
also redeliver work.

The scheduler needs predictable retry behavior and a terminal state for jobs that
continue to fail.

## Decision

Provide at-least-once execution and require idempotent handlers.

On handler error, increment `attempt_count`, store the latest error, clear lease
metadata, and either:

- set `status = retrying` when `attempt_count < max_attempts`; or
- set `status = dead_lettered` when `attempt_count >= max_attempts`.

Dead-lettered jobs are not automatically retried. Re-drive must be an explicit
operator action.

## Consequences

- Handlers must make external side effects idempotent.
- Job creation idempotency does not imply execution idempotency.
- The latest error is retained for diagnosis.
- Immediate retry is simple but may amplify transient failures.
- Backoff can be added later by advancing `scheduled_at` before setting `retrying`.

## Future Considerations

- Retry policies by job type.
- Exponential backoff with jitter.
- Dead-letter listing, filtering, and explicit re-drive APIs.
- Distinguishing retryable and non-retryable handler failures.
