## ml-assets-core 要件仕様 v1

### 目的・責務
- data-assets-pipeline のカノニカル/特徴基礎を用い、AI1（回帰確率）/AI2（リスク）/AI3（スケール）を学習・推論し、統合判定で signal を生成する。月次の再学習・θ最適化・モデル登録・配布を担う。

### 入出力（契約）
- 入力
  - データ: `canonical_bar` と派生（β, spread, z, ATR, ρ）
  - 設定: `core_policy.yaml`, `retrain_policy.yaml`, `backtest_policy.yaml`
- 出力
  - モデル: `model_ai1.pkl`, `model_ai2.pkl`, `feature_schema.json`, `params.yaml(θ1/θ2/M等)`
  - シグナル: Redis/JSON（id, timestamp, pair_id, legs[symbol,side,beta_weight], z_score, return_prob, risk_score, theta1/2, risk_flag, position_scale, model_version, valid_until, metadata）

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

### モデル管理/再学習
- 月次 cron（`retrain_cron`）で再学習→BT→採用判定→配布（SFTP/共有）
- model_registry: model_version, metrics, theta1/2, artifact_path, status

### 設定/ENV
```yaml
# core_policy.yaml（抜粋）
theta1_initial: { value: 0.70 }
theta2_initial: { value: 0.30 }
theta_search_range: { value: { theta1: [0.60,0.85], theta2: [0.20,0.45] } }
```
- ENV: `POSTGRES_URL`, `REDIS_URL`, `SERVICE_ENV`, `LOG_LEVEL`, `TZ=UTC`

### 可観測性/エラー
- Metrics: inference_latency, signals_per_min, retrain_duration
- エラーID例: `CORE_INFER_LATENCY`, `CORE_MODEL_LOAD_FAIL`

### テスト
- 単体（前処理/特徴/推論）、モデル（閾値未達で失敗）、回帰（旧新BT比較）、統合（AI1/AI2/統合判定整合）、負荷（10ペア×1分バー <200ms）

### 連携
- data-assets-pipeline（特徴基礎取得）、backtest-assets-engine（BT/ストレス）、ml-assets-analytics（KPI可視化/通知）


