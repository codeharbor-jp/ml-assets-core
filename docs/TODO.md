## ml-assets-core 実装TODO（優先度順）

### 0. ブートストラップ
- [ ] `pyproject.toml`（lightgbm/xgboost/optuna/pydantic/redis/sqlalchemy）
- [ ] `.env.example` と `config/`（core_policy.yaml, retrain_policy.yaml）

### 1. データ/特徴/ラベリング
- [ ] カノニカル読込レイヤ（DB/Parquet抽象）
- [ ] 特徴量パイプライン（z/Δz/z_ema/atr/ρ/β安定/half_life/ema_gap/slope等）
- [ ] ラベラー AI1/AI2（仕様書通りの窓/閾値/除外ルール）

### 2. データセット/検証
- [ ] 時系列CV（Purged K=5, purge/embargo/min_block）
- [ ] Walk-Forward（月次ステップ, 最小学習360日相当）
- [ ] 確率キャリブレーション（Isotonic）

### 3. 学習/最適化
- [ ] AI1/AI2 モデル学習（LightGBM 既定）とメトリクス算出（AUC/Brier/PR-AUC/F1）
- [ ] θ1/θ2 最適化（粗グリッド→Optuna, 目的関数/制約/安定化）

### 4. 推論/シグナル
- [ ] 統合判定 `return_prob>θ1 && risk_score<θ2`、β中立レッグ/丸めはBT準拠
- [ ] 出力スキーマ準拠（id, timestamp, pair_id, legs, z_score, return_prob, risk_score, theta1/2, risk_flag, position_scale, model_version, valid_until, metadata）
- [ ] Redis/SQLite 共有、レイテンシ<200ms/ペア

### 5. 再学習/モデル管理
- [ ] 再学習ランナー（cron/CLI）、A/B 比較→採用→配布
- [ ] model_registry I/O（version/metrics/theta/artifact_path/status）

### 6. 可観測性/アラート
- [ ] メトリクス: inference_latency/signals_per_min/retrain_duration
- [ ] エラーID: `CORE_INFER_LATENCY`, `CORE_MODEL_LOAD_FAIL`

### 7. テスト/CI
- [ ] 単体（前処理/特徴/ラベル/推論）、回帰（旧新BT比較）、統合、負荷（10ペア×1分）
- [ ] CI: lint/test/データスライスでサニティ


