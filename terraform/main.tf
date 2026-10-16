terraform {
  required_version = ">= 1.5"
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {}

resource "docker_network" "app" {
  name = "devsecops-net"
}

resource "docker_volume" "db_data" {
  name = "devsecops-db-data"
}

resource "docker_image" "db" {
  name         = "postgres:16-alpine"
  keep_locally = true
}

resource "docker_image" "api" {
  name         = var.api_image
  keep_locally = true
}

resource "docker_container" "db" {
  name  = "tf-db"
  image = docker_image.db.image_id

  networks_advanced {
    name = docker_network.app.name
  }

  env = [
    "POSTGRES_USER=${var.db_user}",
    "POSTGRES_PASSWORD=${var.db_password}",
    "POSTGRES_DB=${var.db_name}",
  ]

  volumes {
    volume_name    = docker_volume.db_data.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U ${var.db_user} -d ${var.db_name}"]
    interval = "5s"
    timeout  = "5s"
    retries  = 5
  }
}

resource "docker_container" "api" {
  name            = "tf-api"
  image           = docker_image.api.image_id
  restart         = "on-failure"
  max_retry_count = 5

  networks_advanced {
    name = docker_network.app.name
  }

  env = [
    "DATABASE_URL=postgresql://${var.db_user}:${var.db_password}@tf-db:5432/${var.db_name}",
  ]

  ports {
    internal = 8000
    external = var.api_port
    ip       = "127.0.0.1"
  }

  depends_on = [docker_container.db]
}