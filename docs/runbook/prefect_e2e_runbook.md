## Prefect E2E ランブック（サンプルデータ編）

本書は `SERVICE_ENV=dev` を前提に、公式サンプルデータを使って
「データ投入 → DQ チェック → 再学習 → 配布」を Docker/Prefect 上で再現する手順をまとめる。

### 前提
- Docker / docker compose が利用可能であること
- `SERVICE_ENV` / `POSTGRES_URL` / `REDIS_URL` など dev 設定が `.env` で定義済み
- `configs/envs/dev/*.yaml` が最新化されていること

### 1. サンプルデータの投入
`samples/data/sample_canonical.json` は `tests` と同じ 1h EURUSD のダミー canonical データである。
以下のコマンドで `storage.canonical_root`（`training.yaml` で指定）配下にコピーされる。

```bash
docker compose run --rm ml-core \
  python -m interfaces.cli data seed-sample --env dev \
    --timeframe 1h --symbol EURUSD --month 2025-01
```
（ローカル検証で既存 canonical を汚したくない場合は `--output-root /tmp/canonical` を指定）

- 既に `canonical.json` が存在する場合は `--force` で上書き可能。
- 同ディレクトリに `dq_expectations.yaml` もコピーされる。

### 2. データ品質チェック
Prefect フロー実行前に公式 DQ 期待値で検証する。

```bash
docker compose run --rm ml-core \
  python scripts/quality/run_data_quality_checks.py \
    --dataset samples/data/sample_canonical.json \
    --expectations samples/data/expectations.yaml
```

### 3. Prefect 再学習フローの実行
`runtime.build_learning_components()` で構成された依存関係を使用して
`core_retrain_flow` を起動する。必要に応じて `--with-backtest` などの
オプションを python 側に追加してもよい。

```bash
docker compose run --rm ml-core \
  python -m application.flows.core_retrain
```

実行後は `models_root/<model_version>/` にモデル一式、
`storage/features_root` に特徴量キャッシュが生成される。

### 4. バックテスト・配布フロー
`core_retrain_flow` が成功したら、必要に応じて個別フローも実行する。

```bash
docker compose run --rm ml-core python -m application.flows.core_backtest
docker compose run --rm ml-core python -m application.flows.core_publish
```

`core_publish_flow` は `runtime.build_publish_components()` が作成した
`ModelPublishService` を用い、PostgreSQL `core.model_registry` と WORM ログを更新する。

### 5. 成果物の確認
1. `models_root/<model_version>/checksums.json` に全アーティファクトのハッシュが記録されていること
2. `worm_root/model_publish/...` に監査ファイルが作成されていること
3. `postgres` の `core.model_registry` に最新バージョンが `deployed` として登録されていること
4. Slack/PagerDuty（dev ではダミーでも可）に通知が飛んでいること

### 6. 片付け
検証後は以下を実施して環境をクリーンに戻す。

- `docker compose down --volumes` で開発用コンテナを停止
- `storage` ディレクトリ配下の `canonical/features/models/worm` を削除
- 必要に応じて `prefect deployment delete` でテスト用デプロイメントを削除

