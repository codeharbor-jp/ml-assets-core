from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pytest

from application.services.feature_builder import FeatureBuilder
from application.usecases.learning import LearningRequest, LearningService
from domain import DatasetPartition, ThetaRange
from domain.services import LabelingConfig, RuleBasedLabelingService
from infrastructure.features import DataAssetsFeatureCache, DataAssetsFeatureGenerator, JsonFeatureHasher
from infrastructure.storage import StoragePathResolver
from infrastructure.training import LocalModelArtifactBuilder, LogisticModelTrainer, RollingTimeSeriesCV, SimpleThetaEstimator
from application.services.trainer import Trainer


class DummyMetricsRepository:
    def __init__(self) -> None:
        self.records: dict[str, Mapping[str, float]] = {}

    def store(self, model_version: str, metrics: Mapping[str, float]) -> None:
        self.records[model_version] = dict(metrics)


class _StubConfigRepository:
    def __init__(self, mapping: Mapping[str, object]) -> None:
        self._mapping = mapping

    def load(self, name: str, *, environment: str) -> Mapping[str, object]:  # noqa: ARG002
        return self._mapping[name]


@pytest.fixture()
def storage_roots(tmp_path: Path) -> StoragePathResolver:
    (tmp_path / "storage" / "models").mkdir(parents=True)
    config = {
        "storage": {
            "canonical_root": str(tmp_path / "canonical"),
            "features_root": str(tmp_path / "features"),
            "snapshots_root": str(tmp_path / "snapshots"),
            "models_root": str(tmp_path / "storage" / "models"),
            "worm_root": str(tmp_path / "storage" / "worm"),
            "backups_root": str(tmp_path / "storage" / "backups"),
        }
    }
    repository = _StubConfigRepository(config)
    resolver = StoragePathResolver(config_repository=repository, environment="dev")
    return resolver


def _prepare_canonical(resolver: StoragePathResolver) -> DatasetPartition:
    canonical_root = Path(resolver.resolve("canonical_root"))
    target_dir = canonical_root / "1h" / "EURUSD" / "2025-01"
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_path = Path(__file__).resolve().parents[2] / "fixtures" / "data_quality" / "sample_canonical.json"
    target_file = target_dir / "canonical.json"
    target_file.write_text(sample_path.read_text(encoding="utf-8"), encoding="utf-8")
    return DatasetPartition(
        timeframe="1h",
        symbol="EURUSD",
        year=2025,
        month=1,
        last_timestamp=datetime(2025, 1, 2, tzinfo=timezone.utc),
        bars_written=3,
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=False,
        data_hash="sample_hash",
    )


def test_learning_service_runs_training_pipeline(storage_roots: StoragePathResolver) -> None:
    partition = _prepare_canonical(storage_roots)

    feature_generator = DataAssetsFeatureGenerator(path_resolver=storage_roots)
    feature_cache = DataAssetsFeatureCache(path_resolver=storage_roots)
    feature_hasher = JsonFeatureHasher()
    feature_builder = FeatureBuilder(cache=feature_cache, generator=feature_generator, hasher=feature_hasher)

    labeling_service = RuleBasedLabelingService(LabelingConfig())

    trainer = Trainer(
        cv_strategy=RollingTimeSeriesCV(folds=2, min_train_size=2, holdout_size=1),
        backend_ai1=LogisticModelTrainer(),
        backend_ai2=LogisticModelTrainer(),
        artifact_builder=LocalModelArtifactBuilder(path_resolver=storage_roots),
        theta_estimator=SimpleThetaEstimator(),
        metrics_repository=DummyMetricsRepository(),
    )

    service = LearningService(
        feature_builder=feature_builder,
        labeling_service=labeling_service,
        trainer=trainer,
    )

    request = LearningRequest(
        partitions=(partition,),
        feature_spec={},
        preprocessing={},
        theta_range=ThetaRange(theta1_min=0.6, theta1_max=0.9, theta2_min=0.2, theta2_max=0.5, max_delta=0.1),
        metadata={"requested_by": "unit-test"},
    )

    response = service.execute(request)

    assert response.model_artifact.model_version.startswith("model_")
    assert response.model_artifact.ai1_path.exists()
    assert response.theta_params["theta1"] > 0
    assert response.backtest_metrics

    stored = json.loads(response.model_artifact.ai1_path.read_text(encoding="utf-8"))
    assert "weights" in stored
