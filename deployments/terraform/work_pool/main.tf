variable "work_pool_name" {
  type = string
}

variable "image_repo" {
  type = string
}

variable "image_tag" {
  type = string
}

variable "namespace" {
  type = string
}

variable "kubernetes_namespace" {
  type = string
}

variable "concurrency_limit" {
  type    = number
  default = 4
}

variable "work_queue_names" {
  type    = list(string)
  default = ["default"]
}

variable "redis_host" {
  type = string
}

variable "postgres_connection_uri" {
  type = string
}

resource "kubernetes_namespace" "prefect" {
  metadata {
    name = var.namespace
  }
}

resource "kubernetes_secret" "prefect_infra" {
  metadata {
    name      = "${var.work_pool_name}-infra"
    namespace = var.namespace
  }

  data = {
    REDIS_URL    = var.redis_host
    POSTGRES_URL = var.postgres_connection_uri
  }
}

resource "prefect_work_pool" "this" {
  name         = var.work_pool_name
  type         = "kubernetes"
  description  = "ml-assets-core Prefect Work Pool"
  queue_config = jsonencode({ queues = var.work_queue_names })
}

resource "prefect_deployment" "core_retrain" {
  name            = "core-retrain"
  flow_name       = "core_retrain_flow"
  work_pool_name  = prefect_work_pool.this.name
  description     = "ml-assets-core retraining pipeline"

  schedules = [
    {
      cron         = "0 */6 * * *"
      timezone     = "UTC"
      is_active    = true
      max_active_runs = 1
    }
  ]

  tags = ["ml-assets-core", "retrain"]

  infrastructure_overrides = jsonencode({
    image       = "${var.image_repo}:${var.image_tag}"
    namespace   = var.kubernetes_namespace
    env = {
      PREFECT_LOGGING_LOGLEVEL = "INFO"
    }
    job_watch_timeout_seconds = 600
  })
}

output "prefect_work_pool_name" {
  value = prefect_work_pool.this.name
}



