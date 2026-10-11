terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # For team use, move state to a GCS bucket:
  # backend "gcs" {
  #   bucket = "<your-tfstate-bucket>"
  #   prefix = "ajio-ops"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  services = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iamcredentials.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "ajio-ops"
  location      = var.region
  format        = "DOCKER"
  description   = "Container images for the order service"

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database_instance" "orders" {
  name             = "ajio-orders-pg"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled = true
    }
  }

  deletion_protection = false # demo project; set true for real workloads

  depends_on = [google_project_service.enabled]
}

resource "google_sql_database" "orders" {
  name     = "orders"
  instance = google_sql_database_instance.orders.name
}

resource "google_sql_user" "app" {
  name     = "ajio"
  instance = google_sql_database_instance.orders.name
  password = var.db_password
}

resource "google_secret_manager_secret" "database_url" {
  secret_id = "ajio-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+psycopg2://%s:%s@/%s?host=/cloudsql/%s",
    google_sql_user.app.name,
    var.db_password,
    google_sql_database.orders.name,
    google_sql_database_instance.orders.connection_name,
  )
}

resource "google_service_account" "run" {
  account_id   = "ajio-order-service"
  display_name = "Order service runtime"
}

resource "google_project_iam_member" "run_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_secret_manager_secret_iam_member" "run_secret" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}

resource "google_cloud_run_v2_service" "api" {
  name                = "ajio-order-service"
  location            = var.region
  deletion_protection = false

  template {
    service_account = google_service_account.run.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.max_instances
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.orders.connection_name]
      }
    }

    containers {
      image = var.image

      ports {
        container_port = 8000
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        period_seconds    = 5
        failure_threshold = 10
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_iam_member.run_secret,
    google_project_iam_member.run_sql,
  ]

  lifecycle {
    # CI/CD owns the deployed image after the first apply.
    ignore_changes = [template[0].containers[0].image]
  }
}

# Public access for the demo. Remove for internal-only services.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
