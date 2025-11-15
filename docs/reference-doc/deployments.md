## ml-assets-core デプロイメントガイド (IaC)

### 1. Terraform スタック

`deployments/terraform/` には以下のリソースを定義しています。

- Prefect Work Pool（`prefect_work_pool` モジュール）
- Bitnami Redis Helm リリース
- AWS RDS PostgreSQL（Terraform Registry の公式モジュールを使用）

```bash
cd deployments/terraform
terraform init
terraform plan -var-file=envs/dev.tfvars
terraform apply -var-file=envs/dev.tfvars
```

主な `tfvars` パラメータ:

| 変数 | 説明 |
| --- | --- |
| `kube_cluster_endpoint` / `kube_cluster_ca` / `kube_auth_token` | Prefect Worker をデプロイする Kubernetes クラスタ情報 |
| `redis_password` | Redis AUTH パスワード |
| `postgres_admin_password` | PostgreSQL 管理者パスワード |
| `prefect_api_url` / `prefect_api_key` | Prefect API 接続情報 |

Terraform の出力 (`terraform output`) から Redis URL / PostgreSQL エンドポイント / Work Pool 名を取得し、ml-assets-core の `configs/envs/<env>/` に反映します。

### 2. Helm チャート

`deployments/helm/prefect-worker` は Prefect Worker の Deployment を管理する Chart です。Terraform を用いずに、既存クラスタへワーカーを追加する際に利用できます。

```bash
helm upgrade --install ml-assets-worker ./deployments/helm/prefect-worker \
  --namespace ml-assets-core \
  --set image.repository=asia-northeast1-docker.pkg.dev/prod/ml-assets-core/worker \
  --set image.tag=2025-01-15 \
  --set prefect.apiUrl=https://prefect.prod/api \
  --set prefect.apiKeySecretRef.name=prefect-api-key \
  --set prefect.workPool=ml-assets-core-prod
```

### 3. DR / バックアップ整備

- RDS: `backup_retention_period = 7` で日次スナップショットを取得。重要リリース前には手動スナップショットを取得し、Terraform state と同じリージョン外にもコピーする。
- Redis: 永続化 (AOF) を有効化し、EBS スナップショットを週次で取得。
- Prefect: Cloud 利用時は Managed; OSS の場合は `terraform/outputs` の Work Pool 名を基に `prefect server export` を cron で実行する。

### 4. Secrets 管理

- API キーや DB パスワードは Terraform で直接扱わず、`TF_VAR_*` 環境変数や秘密管理サービス（AWS Secrets Manager, Hashicorp Vault 等）から注入する。
- Helm チャート利用時は `kubectl create secret generic prefect-api-key --from-literal=api-key=<token>` で事前作成。

### 5. 設定更新フロー

1. `configs/base/` / `configs/envs/<env>/` を更新し PR を作成。
2. Terraform Plan / Helm Diff を CI で実行し差分を確認。
3. レビュー後 `terraform apply` / `helm upgrade` を実施。
4. デプロイ後は `docs/runbook/model_release_runbook.md` の検証ステップに従い、メトリクス・ログ・WORM アーカイブの正常性を確認。


