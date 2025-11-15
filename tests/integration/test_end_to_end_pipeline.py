from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from application.services.analytics import AnalyticsCache, AnalyticsRepository, AnalyticsService, MetricsPayload, MetricsQuery
from application.services.feature_builder import FeatureBuildRequest, FeatureBuilder
from domain import DataQualitySnapshot, DatasetPartition
from domain.models import Signal, SignalLeg, ThetaParams, TradeSide
from domain.services import (
    LabelingConfig,
    PositionSizingConfig,
    ProportionalPositionSizingService,
    RuleBasedLabelingService,
    RuleBasedRiskAssessmentService,
    RiskConfig,
)
from domain.services.interfaces import LabelingInput, PositionSizingRequest, RiskAssessmentRequest
from infrastructure.features import DataAssetsFeatureCache, DataAssetsFeatureGenerator, JsonFeatureHasher
from infrastructure.storage import StoragePathResolver
from quality import DQExpectations, validate_dataset


class _InMemoryConfigRepository:
    def __init__(self, storage_config: Mapping[str, object]) -> None:
        self._storage_config = storage_config

    def load(self, name: str, *, environment: str) -> Mapping[str, object]:  # noqa: ARG002
        if name != "storage":  # pragma: no cover - 本テストでは storage のみ使用
            raise KeyError(name)
        return {"storage": dict(self._storage_config)}


class _InMemoryAnalyticsRepository(AnalyticsRepository):
    def __init__(self) -> None:
        self._records: dict[str, list[Mapping[str, float]]] = {
            "model": [],
            "trading": [],
            "data_quality": [],
            "risk": [],
        }

    def record(self, category: str, payload: Mapping[str, float]) -> None:
        self._records.setdefault(category, []).append(dict(payload))

    def fetch_model_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:  # noqa: ARG002
        return tuple(self._records.get("model", []))

    def fetch_trading_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:  # noqa: ARG002
        return tuple(self._records.get("trading", []))

    def fetch_data_quality_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:  # noqa: ARG002
        return tuple(self._records.get("data_quality", []))

    def fetch_risk_metrics(self, query: MetricsQuery) -> Sequence[Mapping[str, float]]:  # noqa: ARG002
        return tuple(self._records.get("risk", []))


class _InMemoryAnalyticsCache(AnalyticsCache):
    def __init__(self) -> None:
        self._cache: dict[str, Mapping[str, object]] = {}

    def get(self, key: str) -> Mapping[str, object] | None:
        return self._cache.get(key)

    def set(self, key: str, payload: Mapping[str, object], ttl_seconds: int) -> None:  # noqa: ARG002
        self._cache[key] = dict(payload)


def test_end_to_end_pipeline(tmp_path: Path) -> None:
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "data_quality"
    dataset_path = fixtures_dir / "sample_canonical.json"
    expectations_path = fixtures_dir / "expectations.yaml"

    canonical_root = tmp_path / "canonical"
    features_root = tmp_path / "features"
    (canonical_root / "1h" / "EURUSD" / "2025-01").mkdir(parents=True)
    canonical_copy = canonical_root / "1h" / "EURUSD" / "2025-01" / "canonical.json"
    canonical_copy.write_text(dataset_path.read_text(encoding="utf-8"), encoding="utf-8")

    storage_repo = _InMemoryConfigRepository(
        {
            "canonical_root": str(canonical_root),
            "features_root": str(features_root),
            "snapshots_root": str(tmp_path / "snapshots"),
            "models_root": str(tmp_path / "models"),
            "worm_root": str(tmp_path / "worm"),
            "backups_root": str(tmp_path / "backups"),
        }
    )
    path_resolver = StoragePathResolver(config_repository=storage_repo, environment="dev")

    # データ品質チェック
    expectations_mapping = yaml.safe_load(expectations_path.read_text(encoding="utf-8"))
    expectations = DQExpectations.from_mapping(expectations_mapping)
    rows = json.loads(dataset_path.read_text(encoding="utf-8"))
    validate_dataset(rows, expectations)

    last_timestamp = datetime.fromisoformat(rows[-1]["timestamp"].replace("Z", "+00:00"))
    partition = DatasetPartition(
        timeframe="1h",
        symbol="EURUSD",
        year=last_timestamp.year,
        month=last_timestamp.month,
        last_timestamp=last_timestamp,
        bars_written=len(rows),
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=False,
        data_hash="hash-123",
    )

    dq_snapshot = DataQualitySnapshot(
        bars_written=len(rows),
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantined=False,
    )

    generator = DataAssetsFeatureGenerator(path_resolver=path_resolver)
    cache = DataAssetsFeatureCache(path_resolver=path_resolver)
    hasher = JsonFeatureHasher()
    builder = FeatureBuilder(cache=cache, generator=generator, hasher=hasher)

    request = FeatureBuildRequest(
        partition=partition,
        feature_spec={"schema": "v1"},
        preprocessing={"normalization": "standard"},
        dq_snapshot=dq_snapshot,
    )
    build_result = builder.build(request)
    assert build_result.features, "特徴量が生成されている必要があります。"

    # ラベリングとリスク評価
    labeling_service = RuleBasedLabelingService(LabelingConfig())
    labeling_output = labeling_service.generate(
        LabelingInput(partition=partition, features=list(build_result.features))
    )
    assert labeling_output.ai1_labels, "AI1ラベルが生成されている必要があります。"

    theta = ThetaParams(
        theta1=0.7,
        theta2=0.3,
        updated_at=datetime.now(timezone.utc),
        updated_by="test",
        source_model_version="v1",
    )
    signal = Signal(
        signal_id="sig-001",
        timestamp=last_timestamp,
        pair_id="EURUSD",
        legs=[
            SignalLeg(symbol="EURUSD", side=TradeSide.LONG, beta_weight=1.0, notional=100000.0)
        ],
        return_prob=0.6,
        risk_score=0.2,
        theta1=theta.theta1,
        theta2=theta.theta2,
        position_scale=1.0,
        model_version="v1",
        valid_until=last_timestamp + timedelta(hours=1),
    )

    metrics_row = build_result.features[-1]
    risk_service = RuleBasedRiskAssessmentService(RiskConfig())
    risk_result = risk_service.evaluate(
        RiskAssessmentRequest(signal=signal, metrics=metrics_row)
    )
    assert 0.0 <= risk_result.risk_score <= 1.0

    sizing_service = ProportionalPositionSizingService(PositionSizingConfig())
    scale = sizing_service.calculate(
        PositionSizingRequest(
            signal=signal,
            account_state={"equity": 100000.0},
            risk_parameters={"max_leverage": 2.0, "volatility": 1.0},
        )
    )
    assert scale > 0.0

    # Analytics 連携
    repo = _InMemoryAnalyticsRepository()
    repo.record("model", {"metric": "sharpe", "value": 1.2})
    repo.record("trading", {"metric": "pnl", "value": 5000.0})
    repo.record("data_quality", {"metric": "missing_rate", "value": 0.0})
    repo.record("risk", {"metric": "risk_score", "value": risk_result.risk_score})

    cache_backend = _InMemoryAnalyticsCache()
    analytics = AnalyticsService(repo, cache=cache_backend, cache_ttl_seconds=30)

    query = MetricsQuery(start=last_timestamp - timedelta(days=1), end=last_timestamp)
    model_metrics = analytics.get_model_metrics(query)
    assert any(row["metric"] == "sharpe" for row in model_metrics.data)

    # キャッシュ経由でも同じ結果が得られることを確認
    cached_metrics = analytics.get_model_metrics(query)
    assert isinstance(cached_metrics, MetricsPayload)
    assert [dict(row) for row in cached_metrics.data] == [dict(row) for row in model_metrics.data]

    risk_metrics = analytics.get_risk_metrics(query)
    assert any(row["metric"] == "risk_score" for row in risk_metrics.data)

    # レポート生成
    report = analytics.generate_report("combined", query)
    assert report.data, "レポートにはメトリクスが含まれている必要があります。"
