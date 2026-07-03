variable "project_id" {
  description = "GCP project ID where resources are created"
  type        = string
}

variable "region" {
  description = "Default GCP region"
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Globally unique name for the example Cloud Storage bucket"
  type        = string
}

variable "module_ref" {
  description = "Git ref for the storage-bucket module (tag, branch, or commit)"
  type        = string
  default     = "master"
}
