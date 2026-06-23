# Agent Operating Model

This project is built by parallel agents with separate ownership lanes. The lanes
let work proceed concurrently while preserving clear handoffs for architecture,
code, tests, infrastructure, and DigitalOcean resources.

## Agent Lanes

| Agent | Primary Scope | Typical Paths |
| --- | --- | --- |
| Project manager agent | Milestones, issues, acceptance criteria, release readiness | `docs/roadmap.md`, `docs/runbooks/`, issue templates |
| Architect agent | System design, ADRs, queue and scaling decisions | `docs/architecture.md`, `docs/adr/` |
| DevOps agent | CI/CD, Docker, Kubernetes manifests, deployment workflow | `.github/workflows/`, `Dockerfile`, `deploy/k8s/` |
| Code writer agent | FastAPI app, worker runtime, queue adapters, migrations | `app/`, `alembic/` |
| Test agent | Unit, integration, contract, and failure-mode coverage | `tests/`, `docs/test-plans/` |
| DigitalOcean resources agent | Cloud resource definitions and environment wiring | `deploy/terraform/`, environment secrets, registry and cluster setup |

## Parallel Work Rules

- Each issue has one primary agent, one owner lane, and an explicit list of
  expected touched paths.
- Cross-lane changes need a handoff artifact before implementation. Use an ADR
  for architecture decisions, a test plan for coverage strategy, or a runbook for
  operational changes.
- Agents announce intended files before editing. If another agent owns a path,
  coordinate through an issue comment or split the work.
- Design changes land before code changes when they alter job lifecycle,
  delivery guarantees, deployment shape, or scaling behavior.
- Tests or explicit test-gap notes accompany any change in API behavior, worker
  state transitions, queue semantics, migrations, or deployment automation.
- Deployment changes must name the required GitHub secrets and DigitalOcean
  resources before they are used by workflows.

## Delivery Flow

1. Project manager creates or updates the issue with acceptance criteria.
2. Architect records any decision that changes system behavior or operating
   assumptions.
3. Test agent adds failing or contract tests when practical.
4. Code writer or DevOps agent implements the change in its lane.
5. DigitalOcean resources agent updates cloud resources or secret requirements.
6. CI validates lint, tests, and container build.
7. Deploy workflow promotes a reviewed image to staging or production.

## Issue Template

```markdown
## Summary

## Owner Lane

## Touched Paths

## Dependencies

## Acceptance Criteria

## Test Evidence

## Deployment Or Rollback Notes
```
