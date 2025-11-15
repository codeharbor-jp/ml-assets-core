variable "aws_region" {
  description = "AWS region for infrastructure deployment"
  type        = string
}

variable "kube_cluster_endpoint" {
  description = "Kubernetes API server endpoint"
  type        = string
}

variable "kube_cluster_ca" {
  description = "Base64 encoded Kubernetes cluster CA certificate"
  type        = string
}

variable "kube_auth_token" {
  description = "Kubernetes API access token"
  type        = string
  sensitive   = true
}

variable "namespace" {
  description = "Kubernetes namespace for ml-assets-core workloads"
  type        = string
  default     = "ml-assets-core"
}

variable "redis_password" {
  description = "Redis AUTH password"
  type        = string
  sensitive   = true
}

variable "postgres_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.5"
}

variable "postgres_instance_class" {
  description = "AWS RDS instance class for PostgreSQL"
  type        = string
  default     = "db.t4g.medium"
}

variable "postgres_admin_user" {
  description = "Master username for PostgreSQL"
  type        = string
  default     = "mlassets_admin"
}

variable "postgres_admin_password" {
  description = "Master password for PostgreSQL"
  type        = string
  sensitive   = true
}

variable "postgres_security_group_id" {
  description = "Security group ID allowing access to PostgreSQL"
  type        = string
}

variable "postgres_subnet_ids" {
  description = "Private subnet IDs for the PostgreSQL subnet group"
  type        = list(string)
}

variable "prefect_api_url" {
  description = "Prefect API base URL"
  type        = string
}

variable "prefect_api_key" {
  description = "Prefect API key for authentication"
  type        = string
  sensitive   = true
}

variable "prefect_work_pool_name" {
  description = "Name of Prefect Work Pool"
  type        = string
  default     = "ml-assets-core-workers"
}

variable "prefect_worker_image_repo" {
  description = "Container registry repo for Prefect worker image"
  type        = string
}

variable "prefect_worker_image_tag" {
  description = "Container image tag for Prefect worker"
  type        = string
}

variable "prefect_worker_concurrency" {
  description = "Concurrency limit for Prefect work pool"
  type        = number
  default     = 4
}

variable "prefect_work_queues" {
  description = "Prefect work queue names"
  type        = list(string)
  default     = ["default"]
}

