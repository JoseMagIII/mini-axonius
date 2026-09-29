resource "docker_network" "acme" {
  name = "${var.company}-net"
}

resource "docker_image" "postgres" {
  name         = "postgres:17-alpine"
  keep_locally = true
}

resource "docker_volume" "postgres" {
  name = "${var.company}-pgdata"
}

resource "docker_container" "postgres" {
  name  = "${var.company}-postgres"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_DB=assets",
    "POSTGRES_USER=admin",
    "POSTGRES_PASSWORD=${var.postgres_password}",
  ]

  ports {
    internal = 5432
    external = var.postgres_port
  }

  volumes {
    volume_name    = docker_volume.postgres.name
    container_path = "/var/lib/postgresql/data"
  }

  networks_advanced {
    name = docker_network.acme.name
  }

  healthcheck {
    test     = ["CMD", "pg_isready", "-U", "admin", "-d", "assets"]
    interval = "2s"
    retries  = 15
  }

  wait = true
}

module "server" {
  source   = "./modules/server"
  for_each = var.servers

  hostname = each.key
  company  = var.company
  network  = docker_network.acme.name
  image    = each.value.image
  owner    = each.value.owner
  env      = each.value.env
  role     = each.value.role
  command  = each.value.command
}
