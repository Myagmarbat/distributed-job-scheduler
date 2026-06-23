# Distributed Job Scheduler

Python distributed job scheduler MVP with a FastAPI input API, database-backed worker
execution, CI, Docker, and DigitalOcean deployment scaffolding.

## System Shape

- FastAPI input API creates, lists, fetches, and cancels jobs.
- Worker processes lease eligible jobs and execute registered Python handlers.
- PostgreSQL stores job state, retries, leases, results, and idempotency keys.
- GitHub Actions runs lint, tests, image build, and DigitalOcean deployment.
- DigitalOcean Kubernetes runs horizontally scaled API and worker deployments.

## Local Development

```bash
uv sync --dev
uv run uvicorn app.api.main:app --reload
```

Create a job:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H 'content-type: application/json' \
  -d '{"job_type":"echo","payload":{"message":"hello"}}'
```

Run one worker loop:

```bash
uv run python -m app.worker.main
```

## Docker Compose

```bash
docker compose up --build
```

The API is available at `http://127.0.0.1:8000`.

## Architecture

- API persists jobs in PostgreSQL/SQLite.
- Workers poll due queued/retrying jobs through a queue interface.
- Execution is at-least-once; handlers must be idempotent.
- Failed jobs retry until `max_attempts`, then move to `dead_lettered`.
- The default MVP queue is database-backed. Add Valkey/Kafka adapters under
  `app/queue/` when scaling queue throughput.

More detail:

- [Architecture](docs/architecture.md)
- [Roadmap](docs/roadmap.md)
- [Agent operating model](docs/agent-operating-model.md)
- [Cost-conscious architecture](docs/cost-conscious-architecture.md)
- [DigitalOcean deployment runbook](docs/deployment-runbook.md)

## Agent Ownership

- Project manager: milestones, issues, acceptance criteria.
- Architect: ADRs for queue backend, retries, locking, deployment model.
- DevOps: Terraform, Kubernetes manifests, registry, GitHub environments.
- Code writer: API, worker runtime, queue adapters, handlers.
- Test agent: unit/integration/load/failure-mode tests.
- DigitalOcean resources agent: registry, DOKS, PostgreSQL, networking, secrets.
