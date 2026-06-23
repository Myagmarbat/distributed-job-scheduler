# ADR 0004: DigitalOcean Deployment Shape

## Status

Accepted

## Context

The project includes a Dockerfile and compose setup with separate API and worker
processes backed by PostgreSQL. The production deployment should keep that process
split so web request throughput and job execution throughput can scale
independently.

## Decision

Deploy the scheduler to DigitalOcean as containerized API and worker components
sharing a managed PostgreSQL database.

The baseline shape is:

- Build one container image from the project Dockerfile.
- Push the image to a registry.
- Run an API component with the default uvicorn command.
- Run a worker component with `python -m app.worker.main`.
- Store job state, leases, attempts, and results in DigitalOcean Managed
  PostgreSQL.
- Configure services with `DATABASE_URL`, `WORKER_ID`, and `LEASE_SECONDS`.

DigitalOcean Kubernetes is the preferred first production target for this repo
because the project already includes Kubernetes deployments, a migration job,
horizontal pod autoscalers, and Terraform-managed DOKS resources. App Platform
remains a possible simpler staging target, but production automation should use
the checked-in Kubernetes and Terraform contracts.

## Consequences

- API and worker scaling are independent.
- PostgreSQL availability directly affects both job submission and execution.
- The MVP does not require Valkey, Kafka, or a separate broker.
- Database connection limits must be considered when scaling workers.
- Worker ids should be unique enough for lock ownership and log diagnosis.
- Kubernetes rollout, migration, and rollback behavior must be kept compatible
  with the GitHub Actions deploy workflow.

## Future Considerations

- Add a dedicated queue service when database polling becomes a bottleneck.
- Add migrations as an explicit release step.
- Add observability for queue depth, job latency, attempts, dead-letter count, and
  lease expirations.
- Add deployment runbooks for worker scale-out, stuck job inspection, and
  dead-letter re-drive.
