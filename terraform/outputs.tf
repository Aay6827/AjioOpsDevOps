output "service_url" {
  description = "Public URL of the order service"
  value       = google_cloud_run_v2_service.api.uri
}

output "artifact_registry" {
  description = "Docker repository path for CI pushes"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "sql_connection_name" {
  description = "Cloud SQL connection name"
  value       = google_sql_database_instance.orders.connection_name
}
