## モデル配布 / リカバリ Runbook

### 1. 配布前チェック
- `terraform output` で Redis / PostgreSQL / Prefect Work Pool の接続先を確認。
- `scripts/checks/run_release_gate.py` を実行し、lint/mypy/pytest が全て成功していることを確認。
- `ModelRegistry` の既存バージョンと衝突しないことを確認（`SELECT model_version FROM core.model_registry`）。

### 2. アーティファクト配布
1. `ml-core` Docker コンテナ上から `ModelArtifactDistributor.distribute` を実行。CLI 利用時は以下のスニペット例:
    ```python
    from infrastructure.storage import ModelArtifactDistributor, StoragePathResolver
    distributor = ModelArtifactDistributor(
        storage_client=LocalFileSystemStorageClient(),
        path_resolver=StoragePathResolver(config_repo, environment="prod"),
    )
    distributor.distribute(
        model_version="2025-01-15-v1",
        artifacts={
            "model_ai1": Path("artifacts/ai1.pkl"),
            "model_ai2": Path("artifacts/ai2.pkl"),
            "theta_params": Path("artifacts/theta.yaml"),
        },
        metadata={"actor": "release-bot", "git_sha": "abc123"},
    )
    ```
2. `checksums.json` が生成されたことを確認し、`distributor.verify` でハッシュ検証を実施。
3. Prefect / CLI からの自動化時は `runtime.build_publish_components()` を利用し、`ModelPublishService` と `PostgresRegistryUpdater` を同時に取得する:
    ```python
    from application.usecases import PublishRequest
    from runtime import build_publish_components

    components = build_publish_components(environment="prod")
    publish_service = components.service
    response = publish_service.execute(
        PublishRequest(
            artifact=model_artifact,
            theta_params=theta_params,
            metadata={"trigger": "prefect-flow"},
        )
    )
    print("audit_record", response.audit_record_id)
    ```
4. `PostgresRegistryUpdater` で `core.model_registry` を更新し、新バージョンを `deployed` ステータスへ変更。

### 3. Prefect フロー更新
- Terraform で Work Pool を管理している場合: `terraform apply -var-file=envs/prod.tfvars` を実行。
- Helm Deploy のみ更新する場合: `helm upgrade --install ml-assets-worker deployments/helm/prefect-worker -f overrides/prod.values.yaml`
  - 新バージョンの Docker イメージ Tag を `values.yaml` に設定。
  - `kubectl get pods -n ml-assets-core` で新しい Worker が稼働していることを確認。

### 4. WORM 監査ログ
- 監査イベント（config 更新、モデル配布結果）は `WormArchiveWriter.append` を利用して保管する。
- `worm_root/<record_type>/<YYYY>/<YYYYMM>/` にファイルが生成され、パーミッションが `444` になっていることを確認。

### 5. バックアップ / DR
- PostgreSQL: `aws rds create-db-snapshot --db-instance-identifier ml-assets-core-pg --db-snapshot-identifier ml-assets-core-pg-<timestamp>`
- Redis: EBS ボリュームに対して `aws ec2 create-snapshot` を実行し、`ml-assets-core-redis` タグを付与。
- WORM/Audit ログ: `aws s3 sync /var/lib/ml-assets-core/worm s3://ml-assets-core-audit/worm/ --storage-class GLACIER_IR`

### 6. ロールバック手順
1. Prefect Work Pool の該当デプロイメントを一時停止 (`prefect deployment pause`)。
2. Model Registry を以前の `model_version` に戻し、`ModelArtifactDistributor` で過去バージョンの整合性を確認。
3. Redis シグナル配布を停止（Ops コマンド `halt_global`）。
4. 影響範囲を Slack `#risk-alerts` に通知し、PagerDuty のインシデントをクローズ。

