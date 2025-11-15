output "redis_host" {
  description = "Redis connection endpoint"
  value       = helm_release.redis.status[0].url
}

output "postgres_endpoint" {
  description = "PostgreSQL endpoint for application use"
  value       = module.postgres.db_instance_endpoint
}

output "prefect_work_pool_name" {
  description = "Prefect Work Pool name"
  value       = module.prefect_work_pool.prefect_work_pool_name
}

