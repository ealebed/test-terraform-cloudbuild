module "example_bucket" {
  source = "git::https://github.com/ealebed/gcp-terraform-modules.git//storage-bucket?ref=${var.module_ref}"

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
