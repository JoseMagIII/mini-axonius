terraform {
  required_providers {
    docker = {
      source = "kreuzwerker/docker"
    }
  }
}

variable "hostname" { type = string }
variable "company" { type = string }
variable "network" { type = string }
variable "image" { type = string }
variable "owner" { type = string }
variable "env" { type = string }
variable "role" { type = string }

variable "command" {
  type    = list(string)
  default = null
}

resource "docker_image" "this" {
  name         = var.image
  keep_locally = true
}

resource "docker_container" "this" {
  name     = "${var.company}-${var.hostname}"
  hostname = var.hostname
  # The image name (not its ID) is what the Docker adapter reads back as the software version.
  image   = docker_image.this.name
  command = var.command
  restart = "unless-stopped"

  # Set explicitly: some Docker runtimes add these defaults, which Terraform would otherwise see as drift.
  log_driver = "json-file"
  log_opts = {
    max-size = "20m"
    max-file = "5"
  }

  networks_advanced {
    name = var.network
  }

  # The Docker adapter reads these labels, the same way a cloud adapter reads tags.
  labels {
    label = "acme.managed"
    value = "true"
  }
  labels {
    label = "acme.owner"
    value = var.owner
  }
  labels {
    label = "acme.env"
    value = var.env
  }
  labels {
    label = "acme.role"
    value = var.role
  }
}

output "image" {
  value = var.image
}
