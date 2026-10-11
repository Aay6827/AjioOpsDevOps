variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-south1"
}

variable "image" {
  description = "Container image to deploy. Defaults to a placeholder so the first apply works before CI pushes an image."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_password" {
  description = "Password for the application database user"
  type        = string
  sensitive   = true
}

variable "max_instances" {
  description = "Cloud Run max instances (keeps cost bounded)"
  type        = number
  default     = 3
}
