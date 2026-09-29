variable "docker_host" {
  description = "Docker daemon socket"
  type        = string
  default     = "unix:///var/run/docker.sock"
}

variable "company" {
  description = "Prefix for every container, network, and volume"
  type        = string
  default     = "acme"
}

variable "postgres_port" {
  description = "Host port for the inventory database"
  type        = number
  default     = 5544
}

variable "postgres_password" {
  description = "Password for the admin database user"
  type        = string
  sensitive   = true
  default     = "acme-admin"
}

variable "servers" {
  description = "Fake servers to run, keyed by hostname"
  type = map(object({
    image   = string
    owner   = string
    env     = string
    role    = string
    command = optional(list(string))
  }))
}
