## ml-assets-core 要件仕様 v1

### 目的・責務
- data-assets-pipeline のカノニカル/特徴基礎を用い、AI1（回帰確率）/AI2（リスク）/AI3（スケール）を学習・推論し、統合判定で signal を生成する。月次の再学習・θ最適化・モデル登録・配布を担う。

### システム構成・実行モデル
- インフラ三層構成: 学習・分析層は PostgreSQL、運用層は各推論プロセス内の SQLite、即時通信は Redis（Pub/Sub または Hash）を用いてシグナル共有を行う。
- 実行モデル: シングルスレッド×マルチプロセス構成を基本とし、1プロセスが 5〜10 ペアを担当。OS レベルのマルチプロセスで GIL を回避し、高信頼の独立再起動性を確保する。
- プロセス監視: systemd/supervisor による死活監視と自動再起動が必須。Redis ハートビート監視で通信断を検知し、運用層は定期的に PostgreSQL へ集約する。
- データフロー: TwelveData などのデータソース → data-assets-pipeline → 本システム（学習/推論）→ Redis シグナル → MT5 EA 等が受信。Σ AI モデルは SFTP/共有ストレージ経由で配布する。

### 入出力（契約）
- 入力
  - データ: `canonical_bar` と派生（β, spread, z, ATR, ρ）
  - 設定: `core_policy.yaml`, `retrain_policy.yaml`, `backtest_policy.yaml`
- 出力
  - モデル: `model_ai1.pkl`, `model_ai2.pkl`, `feature_schema.json`, `params.yaml(θ1/θ2/M等)`
  - シグナル: Redis/JSON（id, timestamp, pair_id, legs[symbol,side,beta_weight], z_score, return_prob, risk_score, theta1/2, risk_flag, position_scale, model_version, valid_until, metadata）

### データ取得・前処理パイプライン連携
- data-assets-pipeline が TwelveData API から取得したデータを UTC 揃え・シンボル正規化し、欠損/外れ値/DQ 検査を行った後に `canonical_bar`・派生特徴量を生成する。
- DQ ルール: 欠損は連続 2 本以下を前方埋め+線形補間、>2 本で隔離。±8σ の価格変化は除外、`quality_flag` に `missing/outlier/conflict` 等を記録。β 安定度異常は注意フラグ。
- レート制限とフェイルオーバ: REST/WS の rate limit を `pipeline_policy.yaml` で管理し、WS 断時は REST で再同期。指数バックオフ＋ジッタ、サーキットブレーカ（open→half-open→close）を実装する。
- データソース抽象化: `MarketDataProvider` インターフェースを実装したアダプタ層を備え、`sources.yaml` に定義された複数プロバイダ（例: TwelveData, Secondary REST）が優先度・フェイルオーバ規約に従って動作する。新規プロバイダ追加時もカノニカルスキーマで統一し、下流モジュールはソース差異を意識せず運用できる。
- パーティション管理: timeframe×symbol×年月フォルダに Parquet（Snappy 圧縮）と `__meta.json` を保存し、`counts`（bars_written, missing_gaps, filled_bars, outlier_bars, spike_flags）と `last_ts` を記録する。品質閾値超過時は `__quarantine.json` を併置し、理由・閾値・対象期間・担当者を保持する。
- 下流利用方針: ml-assets-core は `__quarantine.json` が存在するパーティションを学習・検証対象から自動除外し、`metadata.filled`/`metadata.spike_flag` を入力特徴の品質フラグとして扱う。`__meta.json` の `missing_gaps` や `outlier_bars` を用いてデータセット健全性を前処理段階で検証する。
- パーティションと保持: `timeframe/symbol/YYYY-MM` 単位で保存し、`data_retention.yaml` に従って raw/canonical/features/snapshots を管理する。ウォーターマークによる idempotent 再実行を必須とする。
- 設定キー（例）: `timeframe_default`, `timeframe_allowed`, `history_lookback_months`, `retry_max`, `freshness_budget_seconds`, `dq_thresholds`, `sources.providers[*]`。

### データアクセス・データセット組成
- ルートパス: `storage.yaml` の `backend` と参照先（NAS/S3/MinIO）を `ml_core_storage.yaml`（新設）から読み込み、`canonical_root`（例: `/mnt/archive/canonical`）、`features_root`（例: `/mnt/archive/features`）、`snapshots_root`（例: `/mnt/archive/snapshots`）を取得する。コード内にフォールバックを持たず、設定未定義の場合は起動時に例外で停止する。
- データカタログ: 再学習前に `catalog/index` を生成し、`canonical/{timeframe}/{symbol}/{YYYY-MM}` の `__meta.json` を収集して `dataset_index.parquet`（列: timeframe, symbol, year, month, last_ts, missing_gaps, outlier_bars, spike_flags, quarantine_flag, data_hash）を作成する。`catalog/index` は再学習ジョブ開始時に Prefect フローで更新し、学習ジョブはこのインデックスを唯一本として参照する。
- DQ フィルタ: `dataset_index` で `quarantine_flag=true` や `missing_gaps/bars_written > missing_rate`, `outlier_bars/bars_written > outlier_rate` を満たすパーティションを除外し、除外理由を `dataset_index_filtered.json` に記録して model_registry と共に保存する。
- 特徴量キャッシュ: 特徴量生成結果は `features_root/{timeframe}/{symbol}/{YYYY-MM}/{feature_hash}.parquet` に保存し、`feature_hash = sha256(feature_schema.json + preprocessing_config)` をキーとする。同ハッシュが存在すれば再計算をスキップし、差分のみを処理する。
- 正規化パラメータ: 前処理で算出した中央値/MAD・clip 閾値は `feature_schema.json` 内 `scalers` セクションに格納し、推論時に必ず同値を使用する。欠損補完や外れ値除外のログは `preprocess_report.json` に出力し保存する。

### ラベリング仕様（再掲・確定値）
- AI1: |z|≥2.0 で起点、M=48 内に |z|≤0.5 到達で 1、未到達 0。方向は符号で決定。速度過大（|Δz|EMA>0.12）は除外。
- AI2: `var(ρ,180)>0.025` or `ATR比>1.8` or `|Δz|EMA>0.12` or `dd_recent>0.07` で 1、他は 0。class_weight 上限 1:5。

### 特徴量（主要）
- スプレッド/標準化/速度: z, Δz, z_ema, atr_spread, half_life
- 相関/β: rho_rolling(180), beta_stability
- ボラ/トレンド: atr_A/B(14), atr_ratio, ema_gap_spread(12/26), slope_spread(20), rsi_spread(14)
- 正規化: ロバスト標準化（中央値/MAD）、主要は [-5,5] クリップ

### 学習・検証
- 時系列CV: Purged Grouped K=5（purge=24bars, embargo=24, min_block=240）
- Walk-Forward: 月次ステップ、最小学習360日相当バー
- 目的関数: AI1=logloss+校正、AI2=F1/PR-AUC（加重）
- キャリブレーション: Isotonic（検証Foldで学習）

### θ1/θ2 最適化
- 範囲: θ1∈[0.60,0.85], θ2∈[0.20,0.45]、粗グリッド→Optuna(50–100, ES=15)
- 目的: 年率 − λ_dd·MaxDD超過 − λ_trades·不足 − λ_stop·AI2 FP（dd=0.12, trades_min=150, λ=2.0/0.05/0.10）
- 安定化: |Δθ|≤0.03/回、EWMA(0.7/0.3)、データ不足で据え置き、95%CIガード

### 推論・signal 生成
- 判定: `return_prob>θ1 AND risk_score<θ2`、β中立で legs を構築、`position_scale` 適用
- レイテンシSLO: <200ms/ペア/バー、Redis 共有、`valid_until` で古い signal を抑止
- β中立実行: `universe.yaml` の `tick_size`・`lot_step`・`min_notional` を満たすよう両レッグの名目額を丸め、`cost_table.yaml` のコストを反映する。異通貨換算は最新 FX レートが必須で、`stale_threshold` 超過時は発注抑止する。

### モデル管理/再学習
- 月次 cron（`retrain_cron`）で再学習→BT→採用判定→配布（SFTP/共有）
- model_registry: model_version, metrics, theta1/2, artifact_path, status
- バージョニング: `version = yyyyMMdd_HHmm + short_sha` を採用。最低 5 バージョン保持（`retrain_policy` は 10 推奨）、適用履歴は `audit.config_changes` に保存する。
- model_registry スキーマ: PostgreSQL `core.model_registry` テーブル（列: `model_version`, `status`, `created_at`, `created_by`, `dataset_index_path`, `feature_schema_path`, `model_ai1_path`, `model_ai2_path`, `params_yaml_path`, `metrics_json`, `theta1`, `theta2`, `code_hash`, `data_hash`, `seed`, `notes`）。ステータスは `draft|candidate|approved|rejected|deployed|rolled_back` とし、採否の理由を `notes` に必須記録する。
- アーティファクト保管: モデル・特徴量・θパラメータは `models_root/{model_version}/` に格納し、`checksums.json` に SHA256 を記録する。model_registry には格納先パスを保存し、`models_root` は設定で一元管理する。
- データ・コードハッシュ: 学習ジョブは使用データ範囲（timeframe, symbol, YYYY-MM）の MD5/SHA256 `data_hash` と Git commit `code_hash` を取得し、model_registry とバックテスト出力に必須保存する。
- メトリクス保存: 学習完了時に `metrics.json`（CV・OOS 指標, calibration metrics, feature importance）を保存し、Analytics API へ連携する。欠測時は採用判定を行わず `retrain_status=blocked` とする。

### オーケストレーション・ジョブ設計
- Orchestrator: Prefect 2.x を採用し、`core_retrain_flow`, `core_backtest_flow`, `core_theta_opt_flow`, `core_publish_flow` を定義。`retrain_cron` で `core_retrain_flow` を自動起動し、成功時にバックテスト→θ最適化→採用判定→配布のシリアルチェーンを Prefect の Subflow で管理する。
- フロー構成:
  - `core_retrain_flow`: データカタログ更新→特徴量生成→学習→校正→メトリクス保存
  - `core_backtest_flow`: 最新モデルと `backtest_policy.yaml` を読み込み、BT・ストレスを実行し `bt_summary` を生成
  - `core_theta_opt_flow`: θ探索（粗グリッド→Optuna）→制約評価→候補リスト作成
  - `core_publish_flow`: 採用チェックリスト→model_registry 更新→ Redis/推論プロセスへ適用通知
- Prefect 設定: 各フローは `deployment` として登録し、環境別（dev/stg/prod）の `work_pool` と `infrastructure`（Docker、Kubernetes 等）を設定。Slack/PagerDuty 通知は Prefect Blocks を通じ要件書の通知方針に従う。
- エラー処理: フロー失敗時は Prefect の自動再試行（指数バックオフ、最大 2 回）を設定し、失敗状態を `audit.retrain_runs` に `status=failed` として記録。連続失敗 2 回で `core.ops` へ警告を送信し、再学習を停止する。
- ハートビート: `core_retrain_flow` 中の長時間タスク（学習/Optuna/バックテスト）は Prefect `task` の `heartbeat` を 60 秒とし、停止検知時に `CORE_RETRAIN_HEARTBEAT` エラーを発報する。

### 設定/ENV
```yaml
# core_policy.yaml（抜粋）
theta1_initial: { value: 0.70 }
theta2_initial: { value: 0.30 }
theta_search_range: { value: { theta1: [0.60,0.85], theta2: [0.20,0.45] } }
```
- ENV: `POSTGRES_URL`, `REDIS_URL`, `SERVICE_ENV`, `LOG_LEVEL`, `TZ=UTC`
- 追加必須 ENV: `TWELVEDATA_API_KEY`, `STORAGE_BACKEND`, `ARCHIVE_PATH`, `SLACK_WEBHOOK_URL`, `PAGERDUTY_INTEGRATION_KEY`（環境に応じ必須）、`SERVICE_ENV` に応じたバリデーションを行い、不足時は起動を拒否する。
- 設定 YAML 管理: `core_policy.yaml`, `dd_policy.yaml`, `retrain_policy.yaml`, `pipeline_policy.yaml`, `data_retention.yaml`, `analytics_policy.yaml`, `backtest_policy.yaml`, `universe.yaml`, `cost_table.yaml`, `sources.yaml`, `slack_policy.yaml`, `runbook_policy.yaml` を単一の真実として扱う。コード内でフォールバック値を持たないこと。
- 観測設定: `observability_policy.yaml` を参照し、Prometheus エンドポイント（`metrics.port`）と通知ブロック（`notifications.slack.block_ref` 等）を統一管理する。data-assets-pipeline のメトリクス公開（`data_watermark_lag_seconds`, `data_bars_written_total`）と連携し、ml-assets-core 側のヘルスチェックでも活用する。

### 設定管理・ガバナンス
- ワークフロー: UI → Git → PR → 承認 → 適用 → 監査（`draft → pr_created → approved → merged → applied`）。高リスク変更は approver 2 名を要求。
- RBAC: `viewer/editor/approver/admin`。本番適用は approver 以上が必須。
- API: `POST /configs/validate/pr/approve/merge/apply/rollback` を FastAPI で提供し、PR 作成時に静的検証（YAML スキーマ、相互整合、リスク評価）を実施する。
- 監査: すべての状態遷移を `audit.config_changes` に保存し、Slack `#config-changes` へ通知。ロールバック時は `CONFIG_ROLLBACK` イベントを必ず記録する。

### バックテスト・コスト・ユニバース
- backtest-assets-engine との契約:
  - 入力: `canonical_bar`, モデル成果物、`params.yaml`, `cost_table.yaml`, `universe.yaml`, `bt_period`, `run_config`
  - 出力: `bt_summary`, `bt_trades`, `bt_daily_equity`, `bt_stress_results`（model_version, feature_schema_hash, code_hash, seed を付帯）
- ストレスシナリオ: ATR ノイズ注入、相関崩壊、コスト増、レイテンシ遅延、ギャップイベントを最低実装し、各シナリオの Sharpe/MaxDD を記録する。
- コストテーブル: `defaults`（commission/slippage/spread/swap）と銘柄別 `overrides`、時間帯別スリッページ係数を定義。バックテスト/運用両方で同一設定を参照する。
- ユニバース: ペア毎の `tick_size`, `lot_step`, `min_lot`, `min_notional_usd`, 取引時間帯、休場カレンダー、証拠金制約を `universe.yaml` に記載し、推論・バックテストでバリデーションする。
- 採用基準: `Sharpe > 1.2`, `MaxDD < 0.12`, `trades_per_year ≥ 150` を必須とし、旧モデル比で非劣性（Sharpe_new ≥ 0.95×old, MaxDD_new ≤ old+0.03）を満たさない場合は不採用。

### Analytics・可観測性
- KPI: モデル（AUC, Brier, PR-AUC, Calibration-ECE）、収益/リスク（年率, Sharpe, MaxDD, trades/yr, E/trade）、リスク運用（やらない勇気発動率, θ1/θ2 通過率, risk_flag precision/recall）、データ品質、運用 SLO を集計する。
- API/ダッシュボード: FastAPI で `GET /metrics/model|trading|data_quality|risk`, `POST /reports/generate` 等を提供し、Next.js ダッシュボード（SSR+SWR）で 10〜60 秒間隔の自動更新を実施。Redis `analytics_cache` に短期 TTL キャッシュを置く。
- 通知: 重大イベントは PagerDuty + Slack `#risk-alerts`、警告は Slack `#ml-ops`、情報は `#analytics-info`。テンプレートは `slack_policy.yaml` を参照。
- モニタリング: Prometheus メトリクス（例 `inference_latency_ms`, `signals_per_min`, `data_pipeline_lag_seconds`, `bt_run_duration`, `dq_fail_total`, `data_watermark_lag_seconds`, `data_bars_written_total`）を定義し、トレースでは ingest_run_id を親に紐付ける。ml-assets-core は data-assets-pipeline のメトリクスを参照し、データ鮮度遅延時に推論を抑止する。
- 再学習メトリクス: Prefect タスクに合わせて `core_retrain_duration_seconds`, `core_backtest_duration_seconds`, `core_theta_trials_total`, `core_theta_best_score` を Prometheus に出力し、Analytics で可視化する。
- エラー命名規約: `{DOMAIN}_{CATEGORY}_{CODE}`（例: `DATA_API_TIMEOUT`, `CORE_INFER_LATENCY`, `BT_STRESS_FAIL`）を採用し、`severity` と構造化ペイロード（event_id, occurred_at, details）を必須とする。

### 運用 Runbook・Ops API
- 停止レベル: Soft Halt（新規停止）、Hard Halt（シグナル停止）、Flatten（ポジション強制クローズ）。トリガは `dd_policy.yaml` の `DD_WARN/DD_HALT/DD_FLATTEN`、`DD_*_PAIR`、データ鮮度・推論遅延 SLA 逸脱など。
- API: `POST /ops/halt|flatten|resume|rollback` を提供し、Redis `core:ops:flags`（global_halt, halted_pairs[], flatten_pairs[], leverage_scale）でランタイム制御する。
- 承認フロー: 停止は運用責任者の承認、再開はリスク管理者と運用責任者のダブルチェック（`resume_policy`）。ハルト解除はカナリア再開（20%）→ KPI 監視後に全体適用。
- ロールバック: θ・モデル・設定の各バージョンに対し `/ops/rollback` を提供。Sharpe -20% または MaxDD +3% 超で即時実行し、監査ログと Slack 通知を必須化。
- 監査: すべての `/ops/*` 実行は `audit.analytics_actions` に記録し、incident ログに時刻・実施者・理由・証跡を保存する。

### テスト
- 単体（前処理/特徴/推論）、モデル（閾値未達で失敗）、回帰（旧新 BT 比較）、統合（AI1/AI2/統合判定整合）、負荷（10 ペア×1 分バー <200ms）、E2E（データ取得→推論→Redis 配信→Analytics 集計）を網羅する。
- コンフォーマンステスト: ソース毎に取得→カノニカル変換→DQ→保存の E2E を定期実行し、スキーマ逸脱や欠損率閾値を検証する。

### 非機能要件（NFR）
- 性能: 推論レイテンシ <200ms/ペア/バー、Analytics API p95 <300ms、data freshness（1h 足）≤120s。
- 可用性: コア推論・シグナル配信 月間稼働率 ≥99.5%、ダッシュボード ≥99.0%。
- 容量/拡張性: 初期 20〜30 ペア、将来 50+ を想定しプロセス水平分割でスケール。canonical データ 36 ヶ月保持。
- セキュリティ: TLS 終端、RBAC、2FA、環境変数/ Vault によるシークレット管理、署名済みモデルのみ適用、設定変更は承認必須。
- 監査/ログ: ログ保持 90 日（重大ログ 5 年）、設定変更・再学習・適用・/ops 実行を `audit.*` 系に記録。WORM ストレージで監査ログを保護。
- DR/バックアップ: DB 日次スナップショット + オフサイト、モデル/レポートは S3/MinIO バージョニング。四半期ごとに DR テストを実施。

### コード構成・フォルダガイド
- ルート直下
  - `src/`: 本体コード。アーキテクチャ原則（Domain/Application/Infrastructure/Interfaces）に沿って分割する。
  - `configs/`: 設定 YAML 群（`core_policy.yaml` 等）。`base/` を正とし、`envs/{dev,stg,prod}` は差分のみ記載。
  - `deployments/`: Prefect デプロイ登録やインフラ IaC。`prefect/{dev,stg,prod}` に各環境の deployment 定義を配置。
  - `notebooks/`: 実験用 Jupyter。成果は `/reports` や `/docs` に昇格し、ノートブック単体を本番根拠にしない。
  - `reports/`: 再学習やバックテスト結果のレポート（PDF/CSV）。`model_version` 単位で保存。
  - `scripts/`: 運用スクリプト（バックフィル、手動再学習、ローカル検証）。本番実行は Prefect API を介する。
  - `tests/`: `unit/`, `integration/`, `e2e/`, `fixtures/` を持つテスト群。pytest/Great Expectations の設定を含む。
- `src/` 配下構成
```
src/
├─ bootstrap/              # DIコンテナ、設定ロード、ロギング初期化
├─ domain/
│  ├─ models/             # 主要エンティティ（Signal, ModelArtifact, DatasetPartition 等）
│  ├─ value_objects/      # θ・ラベル・特徴スキーマ等の値オブジェクト
│  ├─ services/           # ドメインロジック（ラベリング、ポジションサイズ計算 など）
│  └─ events/             # ドメインイベント（ModelRetrained 等）
├─ application/
│  ├─ usecases/           # 学習・推論・θ最適化・シグナル生成ユースケース
│  ├─ services/           # FeatureBuilder, Trainer, Calibrator, Backtester などのアプリケーションサービス
│  ├─ flows/              # Prefect フロー定義（core_retrain_flow など）
│  └─ orchestrations/     # ワークフロー補助ロジック（チェックリスト、承認フロー）
├─ infrastructure/
│  ├─ repositories/       # model_registry, dataset_index, meta ストア、Redis/SQLite アクセス
│  ├─ storage/            # Parquet/S3/NAS オペレーション、チェックサム管理
│  ├─ messaging/          # Redis Pub/Sub、Ops フラグ、通知チャンネル
│  ├─ metrics/            # Prometheus エクスポーター、OpenTelemetry 初期化
│  ├─ configs/            # YAML ローダ、スキーマバリデータ、Secrets Resolver
│  └─ adapters/           # data-assets-pipeline 連携、外部BTエンジン、Analytics API コネクタ
├─ interfaces/
│  ├─ api/                # FastAPI エンドポイント（Ops/Analytics/Config）
│  ├─ cli/                # Typer CLI（手動再学習、検証、メンテナンス）
│  └─ workers/            # 推論プロセス、Prefect Agent 等のエントリポイント
├─ shared/                # 共通ユーティリティ（型、例外、日時、ログフォーマッタ）
└─ settings.py            # pydantic Settings（最小限、bootstrap が参照）
```
- `tests/` 配下
```
tests/
├─ unit/                  # ドメイン・アプリケーション単体テスト
├─ integration/           # Repositories, Storage, Config Resolver の統合テスト
├─ e2e/                   # データカタログ→学習→推論→配信のエンドツーエンド
└─ fixtures/              # サンプルデータ、モックレスポンス、Great Expectations ベースライン
```
- 命名規則: Python パッケージは `snake_case`、クラスは `PascalCase`。Prefect フロー名は `{area}_{purpose}_flow`。テストは `test_*.py`。
- 依存関係: `domain` は他層へ依存しない。`application` は `domain` のみ参照。`infrastructure` は外部ライブラリと `domain/application` を使用可。`interfaces` は最上位で各層に依存する。循環を禁止し、mypy で `--disallow-any-generics` 等を活用する。

### ドキュメント・スキーマ管理
- OpenAPI: `/api/v1` をベースとし、FastAPI で `openapi.yaml` を管理。破壊的変更は `v2` を追加し、CI でスキーマ検証とプレビューを義務化。
- データディクショナリ: DB/Parquet/JSON の列仕様は Markdown 表で管理し、変更時は差分と影響範囲を明記。例: `bt_trades` の `trade_id`, `pair_id`, `timestamp_entry`, `qty_a/b`, `pnl` 等。
- 仕様更新: 要件書・参考設計書の差分は毎スプリントでレビューし、変更内容を `docs/` 配下に記録する。

### 連携
- data-assets-pipeline（特徴基礎取得）、backtest-assets-engine（BT/ストレス）、ml-assets-analytics（KPI 可視化/通知）と双方向の契約を明文化。設定変更やモデル更新は各サービスの監査テーブルと Slack 通知と連携する。

