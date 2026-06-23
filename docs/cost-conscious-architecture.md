# Cost-Conscious Architecture

The production Kubernetes design is intentionally scalable, but it is not the
right first step for a tiny cloud balance. Start with the smallest deployment
that proves the scheduler works, then promote the same app architecture to
managed services when usage justifies it.

## Recommended Phases

| Phase | Runtime | Database | When To Use |
| --- | --- | --- | --- |
| Local | Docker Compose | Postgres container | Development and demos. |
| Low-cost MVP | One DigitalOcean Droplet | Postgres container on the Droplet | Early testing with real network access and minimal spend. |
| Production MVP | DOKS API and worker deployments on minimal nodes | Small Managed PostgreSQL | Real users, backups, independent scaling, safer operations. |
| Scale-out | DOKS plus dedicated queue | Managed PostgreSQL plus Valkey/Kafka | High enqueue/dequeue rates or many workers. |

## Why Not Start With DOKS

DigitalOcean Kubernetes plus Managed PostgreSQL creates a good production base,
but it starts multiple paid resources immediately. A small balance can disappear
quickly before the scheduler has traffic. The low-cost MVP profile avoids that by
using one Droplet and Docker Compose.

## Low-Cost MVP Shape

```text
Clients
  |
  v
Single Droplet
  |-- api container
  |-- worker container
  |-- postgres container
```

This does not provide high availability. It is acceptable for early validation,
manual demos, and development environments. It keeps the same API, worker,
database schema, retry behavior, and handler contract as production.

## Bottleneck Strategy

The scheduler is designed so bottlenecks can be isolated:

- API bottleneck: add API replicas behind a load balancer.
- Worker bottleneck: add worker replicas.
- Database queue contention: tune indexes and claiming queries first.
- Database connection pressure: add pooling and cap worker concurrency.
- Queue throughput bottleneck: add Valkey, Redis-compatible, Kafka, or Redpanda
  as a delivery layer while PostgreSQL remains the lifecycle source of truth.

## Minimal Terraform

Use `deploy/terraform-minimal/` for a single Droplet:

```bash
cd deploy/terraform-minimal
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
```

Pass your DigitalOcean SSH key fingerprints so you can access the Droplet:

```bash
terraform apply \
  -var='ssh_key_fingerprints=["aa:bb:cc:..."]'
```

## Minimal Production Shape

Use `deploy/terraform/` when you want the scalable production architecture with
minimal hardware:

```text
DigitalOcean Kubernetes
  |-- one small node to start
  |-- API deployment with HPA
  |-- worker deployment with HPA
  |-- Valkey deployment for fast job delivery
  |-- migration job

DigitalOcean Managed PostgreSQL
  |-- one small node to start

DigitalOcean Container Registry
  |-- starter tier
```

This preserves the long-term architecture while avoiding a large initial
footprint. PostgreSQL remains the source of truth; Valkey accelerates delivery so
workers do not need to poll PostgreSQL for every job. It is not highly available
at the hardware layer until you raise the node counts.

Use the example variables:

```bash
cd deploy/terraform
terraform plan -var-file=minimal.tfvars.example
terraform apply -var-file=minimal.tfvars.example
```

Scale by raising `min_nodes`, `max_nodes`, `node_size`, `database_size`, and
`database_node_count` when traffic and budget justify it.
