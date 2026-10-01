output "database_url" {
  description = "Admin connection string for the inventory database"
  value       = "postgresql://admin:${var.postgres_password}@localhost:${var.postgres_port}/assets"
  sensitive   = true
}

output "servers" {
  description = "Running fake servers and their images"
  value       = { for name, server in module.server : name => server.image }
}
