# 外部サービス連携まとめ (PostgreSQL / Config API / Slack)

本ドキュメントでは、ml-assets-core が依存する外部サービスの接続要件と設定例、ローカルでの検証方法を整理する。

## 共通事項
- 設定値は **YAML のみが唯一の正**。コード内でフォールバックを持たない。
- 全環境で `configs/base/` を正とし、差分は `configs/envs/<env>/` に最小限記載する。
- 設定変更時は Config API 経由で PR → 検証 → 承認 → 適用のフローを必須とする。

## PostgreSQL (model_registry / audit)

| 項目 | 説明 |
| ---- | ---- |
| `database.postgres.dsn` | `postgresql://<user>:<pass>@<host>:<port>/<db>` 形式で必ず指定。 |
| `pool` | min/max/timeout を YAML で定義し、psycopg の ConnectionPool に渡す。 |
| `statement_timeout_ms` | 長時間クエリ検知用。既定は 30,000ms。 |
| `search_path` | `core`, `audit`, `public` の順で指定。 |
| `schemas` | 各テーブルが所属するスキーマ名。 |

参考: `configs/examples/external_services.example.yaml` の `database` セクション。

## Config API

| 項目 | 説明 |
| ---- | ---- |
| `config_api.base_url` | Config 管理サービスのベース URL。環境毎に必須。 |
| `api_token` | Bearer トークン。Vault 等で安全に管理し、開発用以外では平文を避ける。 |
| `timeout_seconds` / `retries` | httpx クライアントのタイムアウト・リトライ設定。 |
| `verify_ssl` | 内部 CA を利用する場合は `true` で CA 証明書をインストールする。 |

ユースケース: `ConfigManagementService` が Config API クライアント経由で PR 作成・承認・適用を実行する。

## Slack 通知

| 項目 | 説明 |
| ---- | ---- |
| `notifications.slack.webhook_url` | Incoming Webhook URL。環境毎に必須。 |
| `channel` | 通知先チャンネル。例: `#ml-ops`。 |
| `username` | 通知時に表示する Bot 名。 |
| `timeout_seconds` | 通知 HTTP リクエストのタイムアウト。 |
| `enabled` | false にすると通知を抑止 (検証環境向け)。 |

Ops ユースケースは監査ログと Redis 連携に加えて、Slack 通知を送信する。

## マーケットデータソース (`sources.yaml`)

| 項目 | 説明 |
| ---- | ---- |
| `sources.providers[].name` | プロバイダ識別子。例: `twelvedata`, `secondary_rest`。 |
| `sources.providers[].priority` | フェイルオーバ時の優先順位（小さいほど先に試行）。 |
| `sources.providers[].settings.base_url` | API ベース URL。環境差分は `configs/envs/<env>/sources.yaml` で上書きする。 |
| `sources.providers[].settings.api_key` / `auth_token` | `$ENV_VAR` 形式で環境変数を参照。未設定の場合は起動時にエラー。 |
| `sources.providers[].settings.timeout_seconds` | HTTP タイムアウト秒。 |
| `sources.providers[].settings.max_retries` | プロバイダ内部での再試行回数。 |
| `sources.providers[].settings.retry_backoff_seconds` | 再試行間隔の秒数。 |
| `sources.failover.max_attempts` | プロバイダ群全体のフェイルオーバ試行回数。 |
| `sources.failover.backoff_seconds` | フェイルオーバ試行間の待機時間。 |

`MarketDataProviderFactory` は `sources.yaml` から設定を読み込み、`TwelveData` → `Secondary` の順でフェイルオーバを行う。

## Prometheus / OpenTelemetry

| 項目 | 説明 |
| ---- | ---- |
| `metrics.provider` | `prometheus` を指定するとエクスポータが有効化される。 |
| `metrics.options.host` / `port` | `/metrics` エンドポイントを公開するアドレスとポート。`port<=0` の場合は公開しない。 |
| `metrics.options.histogram_buckets` | メトリクスごとのヒストグラムバケットを秒/ミリ秒単位で定義。 |
| `metrics.options.default_labels` | すべてのメトリクスに付与するデフォルトラベル（例: `service`, `environment`）。 |
| `metrics.options.otel.*` | OTLP エクスポータ設定。`endpoint`、`timeout_seconds`、`service_name` などを定義。 |

`PrometheusMetricsConfigurator` が HTTP サーバを起動し、`MetricsRecorder` により `inference_latency_ms`、`core_retrain_duration_seconds` 等のメトリクスが更新される。`otel.enabled=true` の場合は OTLP へスパンが送信される。

## WORM アーカイブ / バックアップ

| 項目 | 説明 |
| ---- | ---- |
| `storage.worm_root` | 監査ログを WORM 形式で保存するパス。`WormArchiveWriter.append` がこのディレクトリ配下に `record_type/YYYY/YYYYMM/` 構造で JSON を作成し、パーミッションを `444` に設定する。 |
| `storage.backups_root` | オフラインバックアップ（スナップショットや圧縮アーカイブ）を一時的に格納するパス。IaC でマウントする永続ボリュームを想定。 |
| `deployments/terraform` | Prefect Work Pool / Redis / PostgreSQL を構築する Terraform テンプレート。`terraform output` の値を ml-assets-core の設定 (`configs/envs/<env>/`) に反映する。 |
| `deployments/helm/prefect-worker` | Prefect Worker を Kubernetes に展開する Helm チャート。Terraform を使わない環境でも統一したデプロイが可能。 |

## 設定例

```
See configs/examples/external_services.example.yaml
```

## PagerDuty 通知

| 項目 | 説明 |
| ---- | ---- |
| `notifications.pagerduty.routing_key` | PagerDuty Events API のルーティングキー。必須。 |
| `default_severity` | 省略時の重大度（`critical`, `error`, `warning`, `info` 等）。 |
| `source` / `component` / `group` | インシデントの属性として付与される文字列。 |
| `enabled` | false にすると通知を抑止。 |
| `timeout_seconds` | HTTP タイムアウト。 |

`PagerDutyNotifier` は `events.pagerduty.com/v2/enqueue` に JSON を送信し、Ops/Prefect フローから重大イベント通知を行う。

## ローカル検証手順

1. `.env` / `configs/envs/dev/` に DSN・Webhook・Config API エンドポイントを設定。
2. `docker compose build ml-core` で依存ライブラリを更新。
3. `docker compose run --rm ml-core pytest` で外部連携の統合テストを実行。
   - `tests/integration/test_external_integrations.py` が Slack/Webhook/Config API/OPS 連携をモックで検証する。
4. 開発用の Config API / Slack モックを用意する場合は `scripts/` にあるスタブサーバを利用する（TODO: 将来追加）。

