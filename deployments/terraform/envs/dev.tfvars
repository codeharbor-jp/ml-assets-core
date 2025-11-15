aws_region                 = "ap-northeast-1"
namespace                  = "ml-assets-core-dev"
kube_cluster_endpoint      = "<DEV_K8S_ENDPOINT>"
kube_cluster_ca            = "<BASE64_CA_CERT>"
kube_auth_token            = "<K8S_BEARER_TOKEN>"

redis_password             = "dev-redis-password"
postgres_admin_user        = "mlassets_admin"
postgres_admin_password    = "dev-postgres-password"
postgres_security_group_id = "<sg-xxxxxxxx>"
postgres_subnet_ids        = ["subnet-aaa", "subnet-bbb"]

prefect_api_url            = "http://prefect-dev.internal:4200/api"
prefect_api_key            = "<PREFECT_API_KEY>"
prefect_work_pool_name     = "ml-assets-core-dev"
prefect_worker_image_repo  = "asia-northeast1-docker.pkg.dev/dev/ml-assets-core/worker"
prefect_worker_image_tag   = "latest"
prefect_worker_concurrency = 2
prefect_work_queues        = ["default", "backtest"]

