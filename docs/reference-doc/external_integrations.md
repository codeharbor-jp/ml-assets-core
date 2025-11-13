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

## 設定例

```
See configs/examples/external_services.example.yaml
```

## ローカル検証手順

1. `.env` / `configs/envs/dev/` に DSN・Webhook・Config API エンドポイントを設定。
2. `docker compose build ml-core` で依存ライブラリを更新。
3. `docker compose run --rm ml-core pytest` で外部連携の統合テストを実行。
   - `tests/integration/test_external_integrations.py` が Slack/Webhook/Config API/OPS 連携をモックで検証する。
4. 開発用の Config API / Slack モックを用意する場合は `scripts/` にあるスタブサーバを利用する（TODO: 将来追加）。

