## ml-assets-core 実装TODOロードマップ v2（本番実装フェーズ）

### フェーズ概要
- v1 で整備したスケルトン／CI 基盤を土台に、要件書に記載された本番機能を段階的に実装する。
- 各カテゴリは「実装」「テスト」「ドキュメント」「運用移行」をワンセットで完了させる。
- 依存の強い順に着手し、完了時には成果物（PR・ドキュメント・設定差分）をドキュメントへリンクする。

### 1. ドメインロジック本実装
- [x] ラベリング（AI1/AI2/AI3）/ポジションサイズ/リスク判定サービスを実装し、要件書の規則・閾値を網羅する。
- [x] ドメインサービスのユニットテストを作成し、代表ケース・境界ケース・エラーパスを検証する。
- [x] ドメインイベント発火と監査ペイロードの仕様を確定し、`tests/unit/domain/`にイベント検証テストを整備する。

### 2. 特徴量生成・データアクセスポイント統合
- [x] `FeatureBuilderService` に data-assets-pipeline との連携、特徴量キャッシュ、`feature_schema.json` 整合性検証を実装。
- [x] `DatasetCatalogBuilder` に `dataset_index` 出力・`__quarantine.json` ハンドリング・DQレポート生成を追加。
- [x] `storage.yaml`/`ml_core_storage.yaml` を作成し、本番・検証環境のストレージパスと権限設計を確定。

### 3. 学習・評価パイプライン完成
- [x] `TrainerService` に時系列CV・Walk-Forward・キャリブレーション処理を実装し、メトリクス保存・失敗時ハンドリングを追加。
- [x] `BacktesterService` に backtest-assets-engine 連携・ストレスシナリオ処理・評価ロジックを実装。
- [x] `ThetaOptimizationService` に粗グリッド＋Optuna探索・制約検証・CIガードを実装し、テストで再現性を確認。
- [x] Prefect `core_retrain_flow` から学習→BT→θ最適化→採用判定→配布までを通しで動作させ、integration テストを整備。

### 4. 推論・Ops連携の本実装
- [x] 推論ワーカー（Redis心拍・β中立ロジック・valid_until 管理）の実装と負荷テストを実施。
- [x] FastAPI `/inference`・`/ops` エンドポイントに RBAC・承認フロー・監査ログ記録を実装。
- [x] Opsフラグ (`core:ops:flags`) の整合性チェックと CLI/ API/ ワーカー間の競合回避制御を実装。

### 5. インフラ接続・外部サービス統合
- [x] PostgreSQL リポジトリ・Config API クライアント・Redis Gateways を実装し、統合テストで接続確認を行う。
- [x] TwelveData/Secondary プロバイダを実装し、`sources.yaml` の優先度・フェイルオーバを反映させる。
- [x] IaC（Terraform/Helm など）で Prefect Work Pool・Redis・PostgreSQL の構築手順を docs/ と deployments/ に記載。

### 6. 観測性・セキュリティ・ガバナンス
- [x] Prometheus メトリクス・OpenTelemetry トレースを本実装し、SLO/アラート設計を docs/ にまとめる。
- [x] Slack/PagerDuty 通知テンプレートを整備し、重大度別ルーティングを Prefect/OPS から呼び出せるようにする。
- [x] モデル署名検証・設定変更ワークフロー・監査ログ WORM 保存を実装し、セキュリティレビューを実施。
- [x] API スキーマ・Runbook・DR 手順を整備し、ドキュメントレビューと承認フローを実施。

### 7. E2E テストとリリース準備
- [x] データ取得→学習→バックテスト→θ更新→推論→Redis配信の E2E シナリオテストを作成。
- [x] Great Expectations または同等ツールでデータ品質チェックを自動化し、CI に統合。
- [x] リリース判定基準（メトリクス/監査ログ/カバレッジ/SLO）を明文化し、ローンチチェックリストを作成。

---

## ml-assets-core 実装TODOロードマップ v3（本番強化フェーズ）

### フェーズ概要
- v2 で構築したアプリケーション基盤をベースに、要件書に残る未実装領域（実データ連携、観測性、IaC、運用体制）を仕上げ、本番稼働に耐える状態へ仕上げる。
- 実データ接続 → 観測・通知 → IaC/配布 → Analytics → QA/E2E の順に進め、各ステップでテスト・ドキュメント・運用手順をセットで整備する。

### 1. データ連携とストレージ拡張
- [x] TwelveData / Secondary プロバイダ実装と `sources.yaml` 優先度・フェイルオーバロジックの組み込み。
- [x] data-assets-pipeline との API/ストレージ連携を実装し、`storage.yaml`/`ml_core_storage.yaml` の実環境パスと権限を確定。
- [x] `feature_schema.json`・`preprocess_report.json` 出力を本実装し、推論側へのスキーマ連携を完了する。

### 2. 観測性と通知インフラ
- [x] Prometheus エクスポータのメトリクス定義（inference_latency, core_retrain_duration など）を要件書に沿って実装。
- [x] OpenTelemetry トレース初期化と Prefect/task 連携を構築し、`ingest_run_id` を起点とした分散トレースを可視化。
- [x] Slack/PagerDuty 通知テンプレートを整備し、重大度別ルーティングを Prefect フローと Ops サービスから利用できるよう統合。

### 3. IaC・配布・運用整備
- [x] Prefect Work Pool / Redis / PostgreSQL を構築する Terraform/Helm テンプレートを `deployments/` に作成し、環境変数・シークレット管理をドキュメント化。
- [x] モデル配布（SFTP/共有ストレージ）と `models_root` 配下のチェックサム管理を実装し、配布 Runbook を更新。
- [x] 監査ログ WORM 保存と DR/バックアップ手順の IaC 連携、Ops Runbook（halt/flatten/resume）の詳細化を実施。

### 4. Analytics / ダッシュボード
- [x] FastAPI `GET /metrics/*` / `POST /reports/*` を実装し、Analytics API と Redis キャッシュを整備。
- [x] Next.js ダッシュボード（SSR+SWR）を仮実装し、主要 KPI（Sharpe, MaxDD, DQ 指標, Ops 状態）を可視化。
- [x] Prefect/再学習メトリクスをダッシュボードに取り込み、Slack 通知と連動するアラート設定を文書化。

### 5. データ品質・E2E 強化
- [x] Great Expectations（または同等ツール）でデータ品質テストを自動化し、CI と Prefect フローに統合。
- [x] 実データ取得→学習→バックテスト→θ更新→推論→Redis 配信→Analytics 集計までの E2E シナリオテストを構築。
- [x] リリースゲートスクリプトに DQ/E2E チェックを追加し、ローンチ可否判断の自動化を行う。

### 6. モデル学習・配布 本実装仕上げ
- [ ] LearningUseCase と TrainerService を本実装し、実データパーティションから特徴量生成→学習→成果物生成までを通せるようにする。
- [x] BacktesterService と ThetaOptimizationService をバックエンド実装に接続し、Prefect フローから再学習チェーンを実行可能にする。
- [ ] ModelPublishService と RegistryUpdater を本番ストレージ／PostgreSQL に連動させ、WORM ログ・通知まで含めた配布処理を完成させる。
- [ ] interfaces.api の DI 構成を本実装と接続し、FastAPI から学習／配布／Ops を発火できるエントリポイントを整備する。
- [ ] サンプル実データ（ダミーでも可）と Prefect フローのランブックを整備し、「データ投入→学習→配布」までの手順を再現できる状態にする。

---

## ml-assets-core 実装TODOロードマップ v1（スケルトン整備）

### 全体方針
- 要件書 `docs/ml-assets-core要件書.md` に記載された構成管理・アーキテクチャ原則を唯一の参照源とし、コード内フォールバックは厳禁。
- すべての設定値は `configs/` 配下の YAML を正とし、未定義の場合は起動時例外でフェイルファストする。
- Domain → Application → Infrastructure → Interfaces の依存方向を厳守し、DI/ファクトリを通じて疎結合を担保する。
- Prefect 2.x と Redis/PostgreSQL/オブジェクトストレージを前提に、環境差分は `configs/envs/{dev,stg,prod}` で管理する。

### 1. ブートストラップ・設定ロード
- [x] `src/bootstrap/` に DI コンテナ（例: `lagom`/`punq`/自前コンテナ）を実装し、設定ロード・ロギング・メトリクス初期化を集約。
- [x] `src/bootstrap/config_loader.py`（仮）で設定 YAML 群を読み込み、Pydantic `BaseSettings` 相当のバリデータを実装。
- [x] `configs/base/` に必須 YAML（`core_policy.yaml` 等）を配置し、`envs/*` は差分のみとする構成を定義。
- [x] 未定義キーを参照した場合に例外を送出するガードを実装し、ログに `{DOMAIN}_{CATEGORY}_{CODE}` 形式で出力。
- [x] Secrets/ENV の検証ロジックを実装し、`SERVICE_ENV` 毎に必須値を判定、欠損時は起動拒否。
- [x] 設定変更APIで利用する YAML スキーマ定義（`jsonschema` or `pydantic`）を `infrastructure/configs/schema_registry.py` として準備。

### 2. ドメイン層
- [x] `src/domain/models/` に `Signal`, `ModelArtifact`, `DatasetPartition`, `ThetaParams` 等のエンティティを定義。
- [x] `src/domain/value_objects/` に `ThetaRange`, `CalibrationMetrics`, `DataQualityFlag` などの VO を実装し不変性を担保。
- [x] `src/domain/services/` でラベリング（AI1/AI2）、ポジションサイズ計算、リスク評価ロジックを実装。
- [x] ドメインイベント（`ModelRetrained`, `BacktestCompleted`, `OpsHaltTriggered` 等）を `src/domain/events/` に定義。
- [x] 単体テスト（`tests/unit/domain/`）で値検証・境界ケース（θ範囲・リスク閾値）を網羅。

### 3. アプリケーション層（サービス・ユースケース）
- [x] `src/application/services/feature_builder.py` で `data-assets-pipeline` の成果物を取り込み、特徴量生成・キャッシュ管理（ハッシュキー）を実装。
- [x] `src/application/services/trainer.py` に時系列CV・Walk-Forward・キャリブレーション処理を実装し、メトリクス保存APIに接続。
- [x] `src/application/services/theta_optimizer.py` で粗グリッド→Optuna探索→制約チェック（Δθ制限・CIガード）を実装。
- [x] `src/application/services/backtester.py` で backtest-assets-engine との契約（入力/出力）とストレスシナリオ評価を実装。
- [x] `src/application/usecases/` に Learning / Inference / Publish / Ops などのユースケースを整備し、例外ハンドリング・監査イベント発火を統一。

### 4. インフラ層（リポジトリ・アダプタ）
- [x] `src/infrastructure/repositories/model_registry_repository.py` を実装し、PostgreSQL `core.model_registry` にアクセス。SQLAlchemy or asyncpg を選定。
- [x] `src/infrastructure/storage/` で Parquet/S3/NAS 操作、チェックサム計算、`dataset_index` の入出力を実装。
- [x] `src/infrastructure/adapters/market_data_provider.py` に `MarketDataProvider` 抽象クラスと TwelveData/Secondary 実装を配置。`sources.yaml` の優先度ロジックを反映。
- [x] Redis メッセージング（シグナル配信・Opsフラグ）を `src/infrastructure/messaging/redis_channel.py` として定義し、Pub/Sub & Hash アクセスを提供。
- [x] `src/infrastructure/configs/config_api_client.py` で Config API の PR/検証/適用エンドポイントにアクセスするクライアントを実装。
- [x] Prometheus/OpenTelemetry エクスポータを `src/infrastructure/metrics/` で実装し、Prefectタスクと整合するメトリクスを提供。

### 5. データアクセス・カタログ
- [x] `storage.yaml` と `ml_core_storage.yaml` の読込モジュールを実装し、`canonical_root`/`features_root`/`snapshots_root` を解決。
- [x] `dataset_index` 生成ロジックを `src/application/services/dataset_catalog_builder.py` に実装し、DQ判定と `dataset_index_filtered.json` の出力を担保。
- [x] `__quarantine.json` の検出と除外処理を DataLoaderに組み込み、適用結果をログ出力。
- [x] 特徴量キャッシュと `feature_schema.json` の整合性チェックを実装し、ハッシュ不一致時は再計算＋報告。

### 6. 推論・signal 生成
- [x] `src/interfaces/workers/inference_worker.py`（仮）でマルチプロセス推論ワーカーを設計し、Redis との心拍監視を統合。
- [x] 推論時のθ適用ロジック (`return_prob > θ1 && risk_score < θ2`) と β中立ポジション構築を Value Object/Service に切り出し。
- [x] `universe.yaml`, `cost_table.yaml` を参照したバリデーション・丸め・コスト反映処理を実装。
- [x] `valid_until` を用いた signal 抑制ロジックと Redis 更新時の競合回避（Lua スクリプト or WATCH/MULTI）を実装。
- [x] 推論レイテンシ計測・SLO監視をメトリクスに出力し、閾値超過時に Ops API へ通知。

### 7. Prefect フロー・オーケストレーション
- [x] `src/application/flows/core_retrain_flow.py` 等のフローを定義し、Subflow チェーン（再学習→BT→θ最適化→配布）を実装。
- [x] Prefect `deployment` 定義を `deployments/prefect/{dev,stg,prod}/` に作成し、`work_pool` とインフラ設定を明記。
- [x] 再試行ポリシー、ハートビート（60秒）、Slack/PagerDuty 通知設定を Prefect Blocks 経由で構成。
- [x] `core_publish_flow` 内で model_registry 更新・Redis通知・監査ログ登録を一貫して実施。

### 8. API / インターフェース層
- [x] FastAPI `src/interfaces/api/` で `configs`, `metrics`, `reports`, `ops` エンドポイントを実装。RBACと承認フローを組み込む。
- [x] `POST /configs/*` 系で YAML スキーマ検証・リスク評価を行い、監査ログ（`audit.config_changes`）へ書き込み。
- [x] `/ops/halt|flatten|resume|rollback` エンドポイントに承認フロー・Opsフラグ更新・監査記録を実装。
- [x] Analytics ダッシュボード向け API を `GET /metrics/*` として実装し、Redis `analytics_cache` に TTL キャッシュを導入。
- [x] CLI（Typer）を `src/interfaces/cli/` に実装し、手動再学習・診断コマンドを提供（ただし本番運用は Prefect 経由）。

### 9. 観測性・モニタリング
- [x] Prometheus メトリクス（推論レイテンシ、シグナル数、DQ 指標、Prefectタスク指標）を `metrics.port` で公開。
- [x] OpenTelemetry トレーシングを導入し、`ingest_run_id` を親コンテキストに紐付け。
- [x] Slack/PagerDuty 通知テンプレートを `slack_policy.yaml` に従って整備し、重大度別ルーティングを実装。
- [x] ロギングフォーマット（構造化JSON+`severity`）を統一し、監査ログは WORM 対応ストレージへ送信。

### 10. テスト戦略
- [x] `tests/unit/` にドメイン・アプリケーションのユニットテストを整備。ラベリング、θ検証、ポジションサイズ計算をカバレッジ対象。
- [x] `tests/integration/` で Repositories/Storage/Config Resolver/Redis をモック or コンテナで検証。
- [x] `tests/e2e/` で データカタログ→学習→推論→シグナル配信 のフローをシミュレーションするシナリオを作成。
- [x] Great Expectations or 独自ロジックでデータ品質のコンフォーマンス・テストを構築。
- [x] CI（GitHub Actions 等）で mypy（厳格設定）・pytest・lint（ruff/black）・OpenAPI スキーマ検証を実行。

### 11. ドキュメント・ガバナンス
- [x] `docs/` にデータディクショナリ、API スキーマ、モデル運用Runbookを最新版として整備。
- [x] 設定変更ワークフロー（`draft → pr_created → approved → merged → applied`）の手順書を文書化。
- [x] `docs/runbook/` に Ops 系手順（ハルト・ロールバック・カナリア再開）を詳細化。
- [x] 仕様変更時に要件書差分を記録するテンプレートを作成し、スプリントレビューで報告できる状態にする。

### 12. セキュリティ・Ops
- [x] TLS 終端・RBAC・2FA 前提のインフラ構成文書を整備し、Secrets は Vault/ENV で注入する実装を確認。
- [x] モデル署名検証を導入し、未署名アーティファクトは `core_publish_flow` で拒否。
- [x] DR/バックアップ手順を `deployments/` or `docs/` に記載し、四半期の DR テスト自動化タスクを Prefect で管理。
- [x] 監査ログ（`audit.*`）の保存先とローテーションポリシーを定義し、WORM ストレージ設定を確認。

### 13. 移行・初期セットアップ
- [x] 既存 data-assets-pipeline 出力のスナップショットを取得し、`dataset_index` 初期化手順を文書化。
- [x] Prefect ワークプール・エージェントの配置計画と IaC（Terraform/Helm 等）を `deployments/` 配下に整理。
- [x] Redis/PostgreSQL/ストレージ接続のヘルスチェックCLIを実装し、初回セットアップ時の検証に用いる。

### 14. リスク・オープン課題
- [x] β中立ロジックの検証データセットが未確定のため、`tests/fixtures/` にサンプルを整備する必要あり。
- [x] 二次データソースの SLA/レート制限情報が未決定。`sources.yaml` を仮パラメータで開始し、確定次第更新。
- [x] Prefect 環境（Docker/K8s）の具体条件が未提示。インフラチームと要件擦り合わせが必要。
- [x] Analytics API との契約詳細（認証方式）が未確定。別紙ドキュメント取得後に実装開始。

---
- 本TODOは実装進捗に合わせて随時更新し、各タスク完了時は該当セクションに結果とリンク（PR/ドキュメント）を追記すること。

