## ml-assets-core 実装TODOロードマップ v1

### 全体方針
- 要件書 `docs/ml-assets-core要件書.md` に記載された構成管理・アーキテクチャ原則を唯一の参照源とし、コード内フォールバックは厳禁。
- すべての設定値は `configs/` 配下の YAML を正とし、未定義の場合は起動時例外でフェイルファストする。
- Domain → Application → Infrastructure → Interfaces の依存方向を厳守し、DI/ファクトリを通じて疎結合を担保する。
- Prefect 2.x と Redis/PostgreSQL/オブジェクトストレージを前提に、環境差分は `configs/envs/{dev,stg,prod}` で管理する。

### 1. ブートストラップ・設定ロード
- [ ] `src/bootstrap/` に DI コンテナ（例: `lagom`/`punq`/自前コンテナ）を実装し、設定ロード・ロギング・メトリクス初期化を集約。
- [ ] `src/bootstrap/config_loader.py`（仮）で設定 YAML 群を読み込み、Pydantic `BaseSettings` 相当のバリデータを実装。
- [ ] `configs/base/` に必須 YAML（`core_policy.yaml` 等）を配置し、`envs/*` は差分のみとする構成を定義。
- [ ] 未定義キーを参照した場合に例外を送出するガードを実装し、ログに `{DOMAIN}_{CATEGORY}_{CODE}` 形式で出力。
- [ ] Secrets/ENV の検証ロジックを実装し、`SERVICE_ENV` 毎に必須値を判定、欠損時は起動拒否。
- [ ] 設定変更APIで利用する YAML スキーマ定義（`jsonschema` or `pydantic`）を `infrastructure/configs/schema_registry.py` として準備。

### 2. ドメイン層
- [ ] `src/domain/models/` に `Signal`, `ModelArtifact`, `DatasetPartition`, `ThetaParams` 等のエンティティを定義。
- [ ] `src/domain/value_objects/` に `ThetaRange`, `CalibrationMetrics`, `DataQualityFlag` などの VO を実装し不変性を担保。
- [ ] `src/domain/services/` でラベリング（AI1/AI2）、ポジションサイズ計算、リスク評価ロジックを実装。
- [ ] ドメインイベント（`ModelRetrained`, `BacktestCompleted`, `OpsHaltTriggered` 等）を `src/domain/events/` に定義。
- [ ] 単体テスト（`tests/unit/domain/`）で値検証・境界ケース（θ範囲・リスク閾値）を網羅。

### 3. アプリケーション層（サービス・ユースケース）
- [ ] `src/application/services/feature_builder.py` で `data-assets-pipeline` の成果物を取り込み、特徴量生成・キャッシュ管理（ハッシュキー）を実装。
- [ ] `src/application/services/trainer.py` に時系列CV・Walk-Forward・キャリブレーション処理を実装し、メトリクス保存APIに接続。
- [ ] `src/application/services/theta_optimizer.py` で粗グリッド→Optuna探索→制約チェック（Δθ制限・CIガード）を実装。
- [ ] `src/application/services/backtester.py` で backtest-assets-engine との契約（入力/出力）とストレスシナリオ評価を実装。
- [ ] `src/application/usecases/` に Learning / Inference / Publish / Ops などのユースケースを整備し、例外ハンドリング・監査イベント発火を統一。

### 4. インフラ層（リポジトリ・アダプタ）
- [ ] `src/infrastructure/repositories/model_registry_repository.py` を実装し、PostgreSQL `core.model_registry` にアクセス。SQLAlchemy or asyncpg を選定。
- [ ] `src/infrastructure/storage/` で Parquet/S3/NAS 操作、チェックサム計算、`dataset_index` の入出力を実装。
- [ ] `src/infrastructure/adapters/market_data_provider.py` に `MarketDataProvider` 抽象クラスと TwelveData/Secondary 実装を配置。`sources.yaml` の優先度ロジックを反映。
- [ ] Redis メッセージング（シグナル配信・Opsフラグ）を `src/infrastructure/messaging/redis_channel.py` として定義し、Pub/Sub & Hash アクセスを提供。
- [ ] `src/infrastructure/configs/config_api_client.py` で Config API の PR/検証/適用エンドポイントにアクセスするクライアントを実装。
- [ ] Prometheus/OpenTelemetry エクスポータを `src/infrastructure/metrics/` で実装し、Prefectタスクと整合するメトリクスを提供。

### 5. データアクセス・カタログ
- [ ] `storage.yaml` と `ml_core_storage.yaml` の読込モジュールを実装し、`canonical_root`/`features_root`/`snapshots_root` を解決。
- [ ] `dataset_index` 生成ロジックを `src/application/services/dataset_catalog_builder.py` に実装し、DQ判定と `dataset_index_filtered.json` の出力を担保。
- [ ] `__quarantine.json` の検出と除外処理を DataLoaderに組み込み、適用結果をログ出力。
- [ ] 特徴量キャッシュと `feature_schema.json` の整合性チェックを実装し、ハッシュ不一致時は再計算＋報告。

### 6. 推論・signal 生成
- [ ] `src/interfaces/workers/inference_worker.py`（仮）でマルチプロセス推論ワーカーを設計し、Redis との心拍監視を統合。
- [ ] 推論時のθ適用ロジック (`return_prob > θ1 && risk_score < θ2`) と β中立ポジション構築を Value Object/Service に切り出し。
- [ ] `universe.yaml`, `cost_table.yaml` を参照したバリデーション・丸め・コスト反映処理を実装。
- [ ] `valid_until` を用いた signal 抑制ロジックと Redis 更新時の競合回避（Lua スクリプト or WATCH/MULTI）を実装。
- [ ] 推論レイテンシ計測・SLO監視をメトリクスに出力し、閾値超過時に Ops API へ通知。

### 7. Prefect フロー・オーケストレーション
- [ ] `src/application/flows/core_retrain_flow.py` 等のフローを定義し、Subflow チェーン（再学習→BT→θ最適化→配布）を実装。
- [ ] Prefect `deployment` 定義を `deployments/prefect/{dev,stg,prod}/` に作成し、`work_pool` とインフラ設定を明記。
- [ ] 再試行ポリシー、ハートビート（60秒）、Slack/PagerDuty 通知設定を Prefect Blocks 経由で構成。
- [ ] `core_publish_flow` 内で model_registry 更新・Redis通知・監査ログ登録を一貫して実施。

### 8. API / インターフェース層
- [ ] FastAPI `src/interfaces/api/` で `configs`, `metrics`, `reports`, `ops` エンドポイントを実装。RBACと承認フローを組み込む。
- [ ] `POST /configs/*` 系で YAML スキーマ検証・リスク評価を行い、監査ログ（`audit.config_changes`）へ書き込み。
- [ ] `/ops/halt|flatten|resume|rollback` エンドポイントに承認フロー・Opsフラグ更新・監査記録を実装。
- [ ] Analytics ダッシュボード向け API を `GET /metrics/*` として実装し、Redis `analytics_cache` に TTL キャッシュを導入。
- [ ] CLI（Typer）を `src/interfaces/cli/` に実装し、手動再学習・診断コマンドを提供（ただし本番運用は Prefect 経由）。

### 9. 観測性・モニタリング
- [ ] Prometheus メトリクス（推論レイテンシ、シグナル数、DQ 指標、Prefectタスク指標）を `metrics.port` で公開。
- [ ] OpenTelemetry トレーシングを導入し、`ingest_run_id` を親コンテキストに紐付け。
- [ ] Slack/PagerDuty 通知テンプレートを `slack_policy.yaml` に従って整備し、重大度別ルーティングを実装。
- [ ] ロギングフォーマット（構造化JSON+`severity`）を統一し、監査ログは WORM 対応ストレージへ送信。

### 10. テスト戦略
- [ ] `tests/unit/` にドメイン・アプリケーションのユニットテストを整備。ラベリング、θ検証、ポジションサイズ計算をカバレッジ対象。
- [ ] `tests/integration/` で Repositories/Storage/Config Resolver/Redis をモック or コンテナで検証。
- [ ] `tests/e2e/` で データカタログ→学習→推論→シグナル配信 のフローをシミュレーションするシナリオを作成。
- [ ] Great Expectations or 独自ロジックでデータ品質のコンフォーマンス・テストを構築。
- [ ] CI（GitHub Actions 等）で mypy（厳格設定）・pytest・lint（ruff/black）・OpenAPI スキーマ検証を実行。

### 11. ドキュメント・ガバナンス
- [ ] `docs/` にデータディクショナリ、API スキーマ、モデル運用Runbookを最新版として整備。
- [ ] 設定変更ワークフロー（`draft → pr_created → approved → merged → applied`）の手順書を文書化。
- [ ] `docs/runbook/` に Ops 系手順（ハルト・ロールバック・カナリア再開）を詳細化。
- [ ] 仕様変更時に要件書差分を記録するテンプレートを作成し、スプリントレビューで報告できる状態にする。

### 12. セキュリティ・Ops
- [ ] TLS 終端・RBAC・2FA 前提のインフラ構成文書を整備し、Secrets は Vault/ENV で注入する実装を確認。
- [ ] モデル署名検証を導入し、未署名アーティファクトは `core_publish_flow` で拒否。
- [ ] DR/バックアップ手順を `deployments/` or `docs/` に記載し、四半期の DR テスト自動化タスクを Prefect で管理。
- [ ] 監査ログ（`audit.*`）の保存先とローテーションポリシーを定義し、WORM ストレージ設定を確認。

### 13. 移行・初期セットアップ
- [ ] 既存 data-assets-pipeline 出力のスナップショットを取得し、`dataset_index` 初期化手順を文書化。
- [ ] Prefect ワークプール・エージェントの配置計画と IaC（Terraform/Helm 等）を `deployments/` 配下に整理。
- [ ] Redis/PostgreSQL/ストレージ接続のヘルスチェックCLIを実装し、初回セットアップ時の検証に用いる。

### 14. リスク・オープン課題
- [ ] β中立ロジックの検証データセットが未確定のため、`tests/fixtures/` にサンプルを整備する必要あり。
- [ ] 二次データソースの SLA/レート制限情報が未決定。`sources.yaml` を仮パラメータで開始し、確定次第更新。
- [ ] Prefect 環境（Docker/K8s）の具体条件が未提示。インフラチームと要件擦り合わせが必要。
- [ ] Analytics API との契約詳細（認証方式）が未確定。別紙ドキュメント取得後に実装開始。

---
- 本TODOは実装進捗に合わせて随時更新し、各タスク完了時は該当セクションに結果とリンク（PR/ドキュメント）を追記すること。

