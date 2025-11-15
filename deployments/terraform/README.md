# ml-assets-core Terraform スタック

このディレクトリには、ml-assets-core が依存する Prefect Work Pool・Redis・PostgreSQL を最小構成で準備する Terraform テンプレートを格納しています。各環境ごとに `tfvars` を用意し、環境名を `-var-file` で指定してください。

## 事前準備

- Terraform >= 1.6
- 適切なクラウドプロバイダ資格情報（例: AWS IAM、GCP Service Account、または自前 Kubernetes クラスタ）
- Prefect Cloud / Prefect OSS API キー

## ファイル構成

- `main.tf`  
  各モジュール（Kubernetes 上の Prefect Worker Deployment、Bitnami Redis、AWS RDS PostgreSQL 等）を組み合わせるルート定義。
- `variables.tf`  
  環境固有の値（VPC、サブネット、バージョン、認証情報）をまとめた宣言。
- `outputs.tf`  
  接続情報（Redis URL、PostgreSQL DSN、Prefect Work Pool 名）を出力。
- `work_pools.tf`  
  Prefect Work Pool と Deployment 用の `prefect` provider リソース定義。
- `README.md`（本ファイル）

## 典型的な適用手順

```bash
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars
```

## 任意の環境変数

| 変数名 | 用途 | 備考 |
| --- | --- | --- |
| `TF_VAR_prefect_api_url` | Prefect API URL | OSS の場合は `http://<prefect-host>:4200/api` |
| `TF_VAR_prefect_api_key` | Prefect API キー | Prefect Cloud を利用する際に必須 |
| `TF_VAR_redis_password` | Redis AUTH パスワード | `docker compose` との整合を取る |
| `TF_VAR_postgres_admin_password` | PostgreSQL 管理ユーザパスワード |`ml-assets-core` アプリユーザとは別管理 |

## 注意事項

- テンプレートでは AWS EKS + RDS + Elasticache を例示していますが、Provider を切り替えれば他クラウドでも利用できます。
- Prefect Worker には Secrets を Kubernetes Secret 経由で注入する想定です。Helm チャート例については `../helm/` を参照してください。
- Terraform state は `GCS/Azure Blob/S3` などリモートバックエンドに保存することを推奨します。

