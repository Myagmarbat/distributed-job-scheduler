terraform {
  required_version = ">= 1.8.0"

  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.50"
    }
  }
}

provider "digitalocean" {}

variable "environment" {
  type    = string
  default = "production"
}

variable "region" {
  type    = string
  default = "nyc3"
}

variable "registry_name" {
  type    = string
  default = "scheduler-registry"
}

variable "cluster_name" {
  type    = string
  default = "scheduler-prod"
}

variable "kubernetes_version" {
  type    = string
  default = "latest"
}

variable "node_size" {
  type    = string
  default = "s-1vcpu-2gb"
}

variable "min_nodes" {
  type    = number
  default = 1
}

variable "max_nodes" {
  type    = number
  default = 3
}

variable "database_name" {
  type    = string
  default = "scheduler-postgres"
}

variable "database_size" {
  type    = string
  default = "db-s-1vcpu-1gb"
}

variable "database_version" {
  type    = string
  default = "18"
}

variable "database_node_count" {
  type    = number
  default = 1
}

resource "digitalocean_vpc" "scheduler" {
  name     = "scheduler-${var.environment}"
  region   = var.region
  ip_range = "10.20.0.0/16"
}

resource "digitalocean_container_registry" "scheduler" {
  name                   = var.registry_name
  subscription_tier_slug = "starter"
}

resource "digitalocean_kubernetes_cluster" "scheduler" {
  name     = var.cluster_name
  region   = var.region
  version  = var.kubernetes_version
  vpc_uuid = digitalocean_vpc.scheduler.id

  node_pool {
    name       = "default"
    size       = var.node_size
    node_count = var.min_nodes
    auto_scale = true
    min_nodes  = var.min_nodes
    max_nodes  = var.max_nodes
    tags       = ["scheduler", var.environment]
  }

  maintenance_policy {
    day        = "sunday"
    start_time = "04:00"
  }
}

resource "digitalocean_database_cluster" "postgres" {
  name                 = var.database_name
  engine               = "pg"
  version              = var.database_version
  size                 = var.database_size
  region               = var.region
  node_count           = var.database_node_count
  private_network_uuid = digitalocean_vpc.scheduler.id
}

resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "k8s"
    value = digitalocean_kubernetes_cluster.scheduler.id
  }
}

output "cluster_name" {
  value = digitalocean_kubernetes_cluster.scheduler.name
}

output "registry_endpoint" {
  value = digitalocean_container_registry.scheduler.endpoint
}

output "database_private_uri" {
  value     = digitalocean_database_cluster.postgres.private_uri
  sensitive = true
}
