output "bucket_name" {
  description = "Name of the created Cloud Storage bucket"
  value       = module.example_bucket.name
}

output "bucket_url" {
  description = "Base URL of the created Cloud Storage bucket"
  value       = module.example_bucket.url
}
