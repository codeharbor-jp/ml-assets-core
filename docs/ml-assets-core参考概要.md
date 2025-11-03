# ml-assets-core 層：要件仕様書

## ✅ 目的

data-assets-pipeline が生成した高品質な学習データをもとに、AIモデルを構築・評価・推論し、リアルタイムで取引signalを生成する。安定的かつ再現可能な学習フローと、自動再学習・発注連携機能を備える。

---

## ✅ 主な責務

| 区分 | 内容 |
| ---- | ---- |
| **学習** | PostgreSQLから特徴量＋ラベルを取得し、LightGBM/XGBoostモデルを訓練。 |
| **評価** | クロスバリデーション・バックテストで勝率、平均損益、最大DD、Sharpe比を算出。 |
| **推論** | 最新データ（SQLite/Redis）を使い、モデルからエントリー確率を算出。 |
| **signal生成** | `signal.json` にentry/exit/hold指令を書き出し、MT5 EAが監視。 |
| **再学習** | cronで毎月 or 指定閾値（精度低下）で自動再訓練。 |
| **モデル管理** | `best_model.pkl` とメタ情報をバージョン管理。 |
| **プロセス設計** | シングルスレッド × マルチプロセス構成。5〜10ペア単位で独立稼働。 |
| **フィードバック制御** | バックテスト結果・運用KPIを取り込み、閾値超過時に再学習・停止判定。 |

---

## ✅ モデル構成

| モデル名 | 用途 | 入力特徴量 | 出力 |
| ---- | ---- | ---- | ---- |
| **AI1（回帰モデル）** | zスコア回帰、乖離確率算出 | spread, vol, β, corr, z変化率など | return_prob ∈ [0,1] |
| **AI2（リスクモデル）** | “やらない勇気”判定（取引回避判定） | ATR_ratio, vol_jump, β安定性など | risk_score ∈ [0,1] |
| **AI3（ポジション調整）** | 取引サイズ最適化 | spread_vol, liquidity_score, pnl_std | position_scale (0.0-1.0) |
| **統合意思決定** | AI1とAI2の出力を統合し、Entry条件 `return_prob > θ1` & `risk_score < θ2` を判定。 | return_prob, risk_score, position_scale | entry/exit/hold signal, risk_flag |

---

## ✅ 学習フロー

1. PostgreSQLから指定ペアの特徴量＋ラベルを取得。
2. 前処理：特徴量正規化、欠損補完、カテゴリ変換、feature schema との整合性確認。
3. 学習セット／検証セットに分割（例：Purged TimeSeries 5-fold）。
4. LightGBM/XGBoostで訓練。Optuna などでハイパーパラメータ最適化を実施。
5. 評価指標を算出（AUC, Sharpe, WinRate, Brier Score）。
6. 最良モデルを `best_model.pkl` として保存。
7. メタ情報（精度・パラメータ・学習データ期間）をPostgreSQLへ書き込み。
8. バックテスト層へモデルIDとパラメータセットを通知。

---

## ✅ 推論・signal生成

- 新データ取得 → 特徴量更新 → モデル推論 → signal生成
- 統合ロジックで `return_prob > θ1` かつ `risk_score < θ2` を満たす場合のみエントリー signal を出力。閾値はバックテスト結果に基づきベイズ最適化で定期更新。`risk_flag` は `risk_score >= θ2` の場合に 1 として付与。
- signalフォーマット：

```json
{
  "timestamp": "2025-10-14T12:35:00Z",
  "pair": "XAU/USD vs XAG/USD",
  "z_score": 2.15,
  "return_prob": 0.82,
  "risk_score": 0.18,
  "entry": "SELL_XAUUSD, BUY_XAGUSD",
  "confidence": 0.82,
  "risk_flag": 0,
  "theta1": 0.75,
  "theta2": 0.30,
  "position_scale": 0.65
}
```

- signalはRedis経由で共有し、MT5 EAが即時発注。
- 取引結果（fills）は `result.json` → Redis → PostgreSQL `live_trades` に取り込み、モデル評価に反映。

---

## ✅ 自動再学習フロー

- cronで毎月モデル更新。以下を自動実行：

  1. 最新データ取得・学習再実行。
  2. 性能劣化（Sharpe < 前回×0.9、AUC < 0.02低下）時のみ採用。
  3. ベイズ最適化で `θ1`, `θ2` を更新し、risk_score の分布や risk_flag 発生率に基づいてやらない勇気戦略を再調整。
  4. SFTPでWindows環境にmodel.pkl転送。
  5. 自動バックテスト後に採用判定。
  6. 採用時に `model_registry` テーブルへ登録し、旧モデルは保管。

---

## ✅ 評価・監視

| 指標 | 内容 |
| ---- | ---- |
| **Sharpe比** | 安定性指標。月次再学習時に閾値チェック。 |
| **勝率 / 平均損益** | 学習・BT時の主要指標。 |
| **やらない勇気発動率** | AI2がTrade拒否した割合。過少/過多を検知。 |
| **再学習ログ** | PostgreSQLへ保存。性能推移をml-assets-analyticsが可視化。 |
| **推論遅延** | signal生成までの処理時間。閾値超過時にアラート。 |
| **再学習成否** | 学習ジョブの成功/失敗、所要時間、使用GPU/CPU。 |

---

## ✅ 実行コンポーネント

- `trainer`：Airflow/Prefect タスク。モデル学習、評価、メタ情報登録。
- `inference_worker`：常駐プロセス。Redis/SQLite からデータ取得し推論。
- `signal_dispatcher`：Redis Pub/Sub で signal を配信。
- `model_registry`：PostgreSQL テーブル。モデルID、性能、学習条件、feature_schema ハッシュ。
- `feature_validator`：data-assets-pipeline の最新スキーマと diff を検証。

---

## ✅ 品質管理

- Feature drift 検知：`population stability index` や `mean shift` を ml-assets-analytics へ通知。
- モデルドリフト検知：実運用勝率 vs バックテスト勝率を比較し、乖離 > 15% で再学習トリガ。
- リスク制御整合性：AI2 の risk_score 分布が偏りすぎないか監視し、`risk_score < θ2` の通過率が 5〜40% になるように調整。risk_flag が連続発生する場合は閾値または特徴量を再評価。
- ランタイムバージョン固定：Docker イメージで Python / ライブラリをピン固定。
- seed 管理：学習ごとに seed を記録し再現性確保。
- signal保存時には `core_policy.yaml` 設定値（θ、risk_flag、レバ縮小率）を含め、`audit.config_changes` の履歴と突合できるようにする。

---

## ✅ テスト戦略

- 単体テスト：前処理関数、特徴量生成、推論ロジック、シリアライザ。
- モデルテスト：学習結果の指標が閾値を下回った場合に失敗。
- 回帰テスト：既存モデルと新モデルのバックテスト結果を比較し、改善がない場合に採用保留。
- 統合テスト：AI1・AI2 の出力と統合ロジックの整合性を検証（例：return_prob が低い場合や risk_score が高い場合に適切にブロック/flag されるか）。
- 負荷テスト：同時に 10 ペア×1分バー更新を処理し遅延 < 200ms を維持。
- 災害復旧テスト：model.pkl 消失時に model_registry から再取得できるかを確認。

---

## ✅ ログ・監視

- 主要ログ：`train.log`, `inference.log`, `signal_dispatch.log`
- 指標採取：Prometheus エクスポータで `inference_latency`, `signals_per_min`, `retrain_duration`
- エラーハンドリング：致命エラーは Slack / PagerDuty 通知、再試行ロジック付き。
- モデルバージョン：`signals` にモデルIDを付与し、運用後の検証を容易化。

---

## ✅ 他層との連携

| 入出力 | 対象層 | 内容 |
| ---- | ---- | ---- |
| 入力 | data-assets-pipeline | 特徴量＋ラベルデータ取得（RiskScore 用リスク特徴量を含む） |
| 入力 | backtest-assets-engine | バックテスト結果、再学習判定シグナル（閾値 θ1, θ2 の評価含む） |
| 出力 | ml-assets-analytics | モデル評価・signal・損益レポート提供（やらない勇気率、risk_score 分布、θ1/θ2 採用値など指標含む） |
| 出力 | Redis, SQLite | リアルタイム運用用キャッシュ |
| 出力 | backtest-assets-engine | モデルID、ハイパーパラメータ、評価指標、閾値 θ1/θ2 |

---

## ✅ 今後の拡張

- AutoML（TabPFN など）との比較検証でモデル多様化。
- オンライン学習（river）による逐次更新オプション。
- GPU 加速（LightGBM GPU、Rapids）を用いた再学習時間短縮。
- 取引戦略別（ペア分類）にモデルを分割し、専門化を推進。

## ✅ パラメータ管理（core_policy.yaml）

```yaml
theta1_initial:
  value: 0.70
  label_ja: "θ1初期値"
  description: "return_prob の初期閾値"

theta2_initial:
  value: 0.30
  label_ja: "θ2初期値"
  description: "risk_score の初期閾値"

theta_search_range:
  value:
    theta1: [0.60, 0.85]
    theta2: [0.20, 0.45]
  label_ja: "θ探索範囲"
  description: "ベイズ最適化で探索するレンジ"

theta_step:
  value: 0.01
  label_ja: "θ探索刻み"
  description: "初期グリッド探索の刻み幅"

risk_label_dd_threshold:
  value: 0.06
  label_ja: "リスクラベルDD閾値"
  description: "過去DDが閾値を超えたらリスクラベル=1"

risk_label_vol_ratio:
  value: 1.8
  label_ja: "リスクラベルATR比"
  description: "ATR比が閾値超過でリスクラベル=1"

risk_label_corr_drop:
  value: -0.15
  label_ja: "リスクラベル相関低下"
  description: "相関変化が閾値以下でリスクラベル=1"
```

*上記は `config/core_policy.yaml` に定義し、UI→Git→PR→承認→適用→SQL監査ログのフローで運用する。*

## ✅ 再学習ポリシー（retrain_policy.yaml）

```yaml
retrain_cron:
  value: "0 3 1 * *"
  label_ja: "再学習スケジュール"
  description: "毎月1日 03:00 UTC"

retrain_retry_max:
  value: 2
  label_ja: "再学習リトライ回数"

retrain_retry_delay_minutes:
  value: 60
  label_ja: "リトライ待機時間"

retrain_notification_channel:
  value: "#ml-ops"
  label_ja: "再学習通知チャネル"

model_version_retention:
  value: 5
  label_ja: "モデル保持数"
```

*変更履歴は `audit.config_changes` テーブルへ保存し、Slack 通知はアラート用途に限定する。*

## ✅ モデル登録テーブル（model_registry）

| カラム名 | 型 | コメント |
| --- | --- | --- |
| `model_version` | `text` | `yyyyMMdd_HHmm` 形式 |
| `model_type` | `text` | `AI1`, `AI2`, `AI3` |
| `status` | `text` | `active`, `archived`, `rejected` |
| `train_period_start`/`end` | `date` | 学習期間 |
| `theta1`/`theta2` | `numeric(6,4)` | 採用時の閾値 |
| `metrics` | `jsonb` | Sharpe, WinRate 等 |
| `artifact_path` | `text` | S3 or ファイルパス |
| `notes` | `text` | コメント |
| `created_at` / `updated_at` | `timestamptz` | |

## ✅ 再学習記録（retrain_runs）

```yaml
retrain_runs_table:
  value: "audit.retrain_runs"
  label_ja: "再学習実行テーブル"
  description: "再学習ジョブの実行履歴"

retrain_runs_columns:
  value:
    - { name: "run_id", type: "uuid", comment: "再学習ジョブID" }
    - { name: "started_at", type: "timestamptz", comment: "開始時刻" }
    - { name: "ended_at", type: "timestamptz", comment: "終了時刻" }
    - { name: "status", type: "text", comment: "success/failed/retrying/aborted" }
    - { name: "retry_count", type: "smallint", comment: "リトライ回数" }
    - { name: "model_version", type: "text", comment: "新モデル版" }
    - { name: "theta1", type: "numeric(6,4)", comment: "探索結果θ1" }
    - { name: "theta2", type: "numeric(6,4)", comment: "探索結果θ2" }
    - { name: "metrics", type: "jsonb", comment: "評価指標" }
    - { name: "log_path", type: "text", comment: "ログファイルパス" }
    - { name: "error_message", type: "text", comment: "失敗時の要約" }
  label_ja: "再学習カラム定義"
  description: "再学習テーブルのカラムリスト"
```

*再学習は cron 実行 → `audit.retrain_runs` 登録 → 成功/失敗応じて Slack 通知 → モデル登録・BT合格で本番反映という手順を踏む。*

## ✅ シグナルテーブル設定（signals_policy.yaml）

```yaml
signals_table:
  value: "core.signals_live"
  label_ja: "シグナルテーブル"
  description: "リアルタイムシグナルの保存先"

signals_history_table:
  value: "core.signals_history"
  label_ja: "シグナル履歴テーブル"
  description: "日次アーカイブ用"
```

## ✅ アーカイブ設定（signals_policy.yaml）

```yaml
archive_target:
  value: "NAS"
  label_ja: "アーカイブ先"
  description: "`NAS` / `LOCAL` / `S3` / `WASABI` / `B2` を環境変数で切り替え"

archive_path:
  value: "/mnt/archive/signals"
  label_ja: "アーカイブパス"
  description: "NASまたはローカルの保存先。S3の場合はバケット名。"
```
