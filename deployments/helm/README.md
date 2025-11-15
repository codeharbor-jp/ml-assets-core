# Helm チャート

`prefect-worker/` は ml-assets-core 専用の Prefect Worker デプロイメントを Kubernetes に展開するための簡易チャートです。Terraform で Work Pool を作成しない場合でも、このチャートを利用すれば既存クラスタへワーカーを追加できます。

```bash
helm upgrade --install ml-assets-core-worker ./prefect-worker \
  --namespace ml-assets-core \
  --set image.repository=asia-northeast1-docker.pkg.dev/prod/ml-assets-core/worker \
  --set image.tag=2025-01-15 \
  --set prefect.apiUrl=https://prefect.example.com/api \
  --set prefect.apiKeySecretRef.name=prefect-api-key \
  --set prefect.workPool=ml-assets-core-prod
```

Secrets はあらかじめ `kubectl create secret generic prefect-api-key --from-literal=api-key=***` 等で作成してください。

