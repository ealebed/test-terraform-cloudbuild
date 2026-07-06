module "example_bucket" {
  source = "git::https://github.com/ealebed/gcp-terraform-modules.git?ref=storage-bucket/v1.0.0"

  project = var.project_id
  bucket = {
    name     = var.bucket_name
    location = var.region
    labels = {
      managed_by = "terraform"
      repo       = "test-terraform-cloudbuild"
    }
  }
}
