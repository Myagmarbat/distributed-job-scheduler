# DigitalOcean Deployment Runbook

This runbook describes the production path for the distributed job scheduler on
DigitalOcean. The target runtime is DigitalOcean Kubernetes with one API
deployment, one worker deployment, one Valkey delivery service, a migration job,
Managed PostgreSQL, and a DigitalOcean Container Registry image.

For a small balance, keep this scalable DOKS architecture but start with the
minimal hardware defaults in `deploy/terraform/minimal.tfvars.example`. Use
`deploy/terraform-minimal/` only when you want the cheapest possible single
Droplet demo instead of the production architecture.

## Resource Model

- DigitalOcean Container Registry stores immutable scheduler images.
- DigitalOcean Kubernetes runs API and worker pods.
- Valkey in Kubernetes delivers ready job ids without making PostgreSQL handle
  every dequeue poll.
- DigitalOcean Managed PostgreSQL stores jobs, leases, attempts, results, and
  idempotency keys.
- Kubernetes `scheduler-secrets` provides runtime configuration.
- HorizontalPodAutoscaler scales API and worker deployments independently.

## Required GitHub Secrets

| Secret | Purpose |
| --- | --- |
| `DO_ACCESS_TOKEN` | Authenticates `doctl` in GitHub Actions. |
| `DO_REGISTRY` | DigitalOcean registry name, not the full URL. |
| `DO_CLUSTER_NAME` | Target Kubernetes cluster name. |
| `DATABASE_URL` | SQLAlchemy URL for Managed PostgreSQL. |

Use the private PostgreSQL connection URI when deploying inside the same
DigitalOcean VPC.

`QUEUE_BACKEND=valkey` and `REDIS_URL=redis://scheduler-valkey:6379/0` are set in
the Kubernetes manifests for API and worker pods.

## Provision Infrastructure

Run Terraform from `deploy/terraform/` with a DigitalOcean token available to the
provider:

```bash
terraform init
terraform fmt -check
terraform validate
terraform plan -var-file=minimal.tfvars.example
terraform apply -var-file=minimal.tfvars.example
```

Commit `deploy/terraform/.terraform.lock.hcl` after provider initialization so CI
and operators use the same provider selection. Do not commit the local
`.terraform/` directory or state files.

Important outputs:

- `cluster_name`: use as `DO_CLUSTER_NAME`.
- `registry_endpoint`: confirms the registry endpoint.
- `database_private_uri`: convert to the SQLAlchemy `postgresql+psycopg://...`
  form and store as `DATABASE_URL`.

## First Deployment

1. Create GitHub environments named `staging` and `production`.
2. Add the required secrets to each environment.
3. Run the `Deploy` workflow manually.
4. Select the target environment and leave `image_tag` empty to deploy the
   triggering commit SHA.
5. Confirm the migration job completes.
6. Confirm both rollouts complete:

```bash
kubectl rollout status deployment/scheduler-api
kubectl rollout status deployment/scheduler-worker
kubectl rollout status deployment/scheduler-valkey
```

## Promotion

Use immutable image tags for promotion. Deploy the commit SHA that passed CI in
staging to production by running the `Deploy` workflow with `image_tag` set to
that SHA.

## Rollback

1. Re-run the `Deploy` workflow for the last known good image tag.
2. Confirm migration compatibility before rolling back application code. Database
   migrations are forward-only unless an ADR or release plan states otherwise.
3. Verify API and worker rollouts complete.
4. Inspect stuck or retrying jobs before increasing worker replica counts.

## Scaling

- API pods scale on CPU using `deploy/k8s/hpa.yaml`.
- Worker pods scale independently on CPU using `deploy/k8s/hpa.yaml`.
- PostgreSQL connection capacity is the main shared limit while the database is
  also the queue.
- Increase worker replicas gradually and monitor queue latency, retry rate, and
  dead-letter count.

## Operational Checks

```bash
kubectl get pods
kubectl get hpa
kubectl logs deployment/scheduler-api
kubectl logs deployment/scheduler-worker
kubectl logs deployment/scheduler-valkey
kubectl get jobs
```

API liveness uses `/healthz`. API readiness uses `/readyz`. Valkey uses TCP
probes. Workers currently use process health and Kubernetes restart behavior; add
an explicit worker readiness command before relying on advanced rollout gates.
