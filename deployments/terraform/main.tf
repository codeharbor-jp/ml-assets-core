terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    prefect = {
      source  = "PrefectHQ/prefect"
      version = "~> 0.2.3"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "kubernetes" {
  host                   = var.kube_cluster_endpoint
  cluster_ca_certificate = base64decode(var.kube_cluster_ca)
  token                  = var.kube_auth_token
}

provider "helm" {
  kubernetes {
    host                   = var.kube_cluster_endpoint
    cluster_ca_certificate = base64decode(var.kube_cluster_ca)
    token                  = var.kube_auth_token
  }
}

provider "prefect" {
  api_url = var.prefect_api_url
  api_key = var.prefect_api_key
}

# --- Redis --------------------------------------------------------------------

resource "helm_release" "redis" {
  name       = "ml-assets-core-redis"
  repository = "https://charts.bitnami.com/bitnami"
  chart      = "redis"
  version    = "19.5.1"

  namespace        = var.namespace
  create_namespace = true

  values = [
    yamlencode({
      architecture = "standalone"
      auth = {
        enabled  = true
        password = var.redis_password
      }
      persistence = {
        enabled = true
        size    = "20Gi"
      }
    })
  ]
}

# --- PostgreSQL ---------------------------------------------------------------

module "postgres" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.5"

  identifier = "ml-assets-core-pg"

  engine               = "postgres"
  engine_version       = var.postgres_engine_version
  family               = "postgres${replace(var.postgres_engine_version, ".", "")}"
  instance_class       = var.postgres_instance_class
  allocated_storage    = 50
  max_allocated_storage = 200

  username = var.postgres_admin_user
  password = var.postgres_admin_password

  vpc_security_group_ids = [var.postgres_security_group_id]
  subnet_ids             = var.postgres_subnet_ids
  publicly_accessible    = false

  backup_window      = "03:00-04:00"
  maintenance_window = "sun:04:00-sun:05:00"
  backup_retention_period = 7

  enabled_cloudwatch_logs_exports = ["postgresql"]
  deletion_protection             = true
}

# --- Prefect Work Pool --------------------------------------------------------

module "prefect_work_pool" {
  source = "./work_pool"

  namespace              = var.namespace
  work_pool_name         = var.prefect_work_pool_name
  image_repo             = var.prefect_worker_image_repo
  image_tag              = var.prefect_worker_image_tag
  concurrency_limit      = var.prefect_worker_concurrency
  work_queue_names       = var.prefect_work_queues
  kubernetes_namespace   = var.namespace
  redis_host             = helm_release.redis.status[0].url
  postgres_connection_uri = module.postgres.db_instance_endpoint
}


