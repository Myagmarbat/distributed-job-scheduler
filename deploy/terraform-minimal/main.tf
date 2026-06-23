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
  default = "mvp"
}

variable "region" {
  type    = string
  default = "nyc3"
}

variable "droplet_name" {
  type    = string
  default = "scheduler-mvp"
}

variable "droplet_size" {
  type    = string
  default = "s-1vcpu-1gb"
}

variable "ssh_key_fingerprints" {
  type        = list(string)
  default     = []
  description = "DigitalOcean SSH key fingerprints allowed to access the Droplet."
}

resource "digitalocean_vpc" "scheduler" {
  name     = "scheduler-${var.environment}"
  region   = var.region
  ip_range = "10.30.0.0/16"
}

resource "digitalocean_droplet" "scheduler" {
  name     = var.droplet_name
  region   = var.region
  size     = var.droplet_size
  image    = "ubuntu-24-04-x64"
  vpc_uuid = digitalocean_vpc.scheduler.id
  ssh_keys = var.ssh_key_fingerprints
  tags     = ["scheduler", var.environment]

  user_data = <<-CLOUD_CONFIG
    #cloud-config
    package_update: true
    packages:
      - docker.io
      - docker-compose-v2
      - git
    runcmd:
      - systemctl enable docker
      - systemctl start docker
  CLOUD_CONFIG
}

resource "digitalocean_firewall" "scheduler" {
  name = "scheduler-${var.environment}"

  droplet_ids = [digitalocean_droplet.scheduler.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

output "droplet_ipv4_address" {
  value = digitalocean_droplet.scheduler.ipv4_address
}

output "ssh_command" {
  value = "ssh root@${digitalocean_droplet.scheduler.ipv4_address}"
}
