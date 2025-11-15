# 最終リリースチェックリスト (Observability / Security / E2E)

リリース判定時に必ず確認すべき項目を整理しました。  
チェックは **環境ごとに記録を残し (ノーション / Jira など)**、未完の項目がある状態で本番適用しないこと。

---

## 1. Observability

| # | チェック項目 | 手順 / コマンド | 備考 |
|---|--------------|-----------------|------|
| 1 | 構造化ログが有効になっているか | `SERVICE_ENV=<env> docker compose run --rm ml-core python -m bootstrap.check_logging` | JSON 形式で出力されること |
| 2 | Prometheus メトリクスがエクスポートされているか | `curl http://<host>:<metrics_port>/metrics | head` | `ml_assets_core_*` 系メトリクスが存在 |
| 3 | Prefect ラン (2.20 系) と連携できているか | Prefect UI で `core_retrain_flow` が成功しているかを確認 | 作業ログをスクリーンショット保存 |
| 4 | Slack 通知が受信できるか | `pytest tests/integration/test_external_integrations.py -k slack` | 通知先にメッセージが届くこと |
| 5 | Config API 連携の健全性 | `pytest tests/integration/test_external_integrations.py -k config` | 成功レスポンスを確認 |
| 6 | Release gate 自動チェック | `python scripts/checks/run_release_gate.py` | lint / mypy / データ品質 / pytest / E2E を一括実行 |
| 7 | データ品質メトリクス確認 | Prefect フロー実行後に `/api/v1/reports/dq` (将来実装予定) を確認 | 実装前は manual チェック |

## 2. Security

| # | チェック項目 | 手順 / コマンド | 備考 |
|---|--------------|-----------------|------|
| 1 | Secrets が YAML へ平文で残っていないか | `rg -n "TOKEN" configs` | トークンは Secret Manager / Vault を参照すること |
| 2 | TLS / Verify 設定が適切か | `config_api.verify_ssl = true`、Slack Webhook も HTTPS のみを使用 | 自己署名の場合は CA を配布 |
| 3 | DB アカウント権限の確認 | `psql` で読み取り専用 / 書き込み専用ユーザが分離されているか | Runbook に記録 |
| 4 | 監査ログの保管先 | `audit.*` テーブルに対して retention 設定を確認 | 90 日保持 (重大ログは 5 年) |
| 5 | 依存ライブラリの危険性チェック | `pip-audit` or `safety check` を実行 | クリティカルな CVE がないこと |

## 3. End-to-End (E2E) 検証

| # | チェック項目 | 手順 / コマンド | 備考 |
|---|--------------|-----------------|------|
| 1 | ローカル E2E スモーク | `pytest tests/integration/test_retrain_flow.py` | Prefect フローの疎結合テスト |
| 2 | 外部サービスも含む統合 | `pytest tests/integration/test_external_integrations.py` | Config API / Slack / Ops をモック |
| 3 | 手動シナリオ (運用系) | 1. Config API で PR 作成 → Approve → Apply<br>2. OPS API で halt → resume | Slack 通知と Redis 更新を確認 |
| 4 | データセットを使った学習ジョブ | `python scripts/manual_tests/run_retrain_smoke.py --env stg` (将来追加) | 実データ環境での smoke チェック |
| 5 | E2E パイプライン自動テスト | `pytest tests/integration/test_end_to_end_pipeline.py` | データ取得→特徴量→リスク→Analytics まで検証 |
| 6 | 回帰テスト一式 | `docker compose run --rm ml-core pytest` | CI と同じコマンドで実施 |

## 4. リリース Go/No-Go 判定

- [ ] 上記 Observability/Security/E2E のチェックがすべて ✅ である
- [ ] Prefect Server / Agent が 2.20 系で稼働していることを最終確認
- [ ] Slack #ml-ops にリリース開始・完了通知を送信
- [ ] Config 変更申請 (PR) とリリース承認者が 2 名以上確認済み
- [ ] Rollback 手順の最終確認 (モデルロールバック / Config ロールバック)

## 補足

- 追加で必要なチェック項目があれば追記し、履歴を残すこと。
- 実装済みテストは `pytest` ターゲットを明記し、未実装の場合は Runbook に手順を記載する。

