from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from application.services.trainer import (
    ModelArtifactBuilder,
    ThetaEstimator,
    TimeSeriesCVStrategy,
    Trainer,
    TrainingRequest,
    TrainingResult,
)
from domain import CalibrationMetrics, DatasetPartition, ModelArtifact, ThetaParams


def make_partition() -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol="EURUSD",
        year=2024,
        month=1,
        last_timestamp=datetime(2024, 1, 31, 23, tzinfo=timezone.utc),
        bars_written=120,
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=False,
        data_hash="hash123",
    )


class DummyCV(TimeSeriesCVStrategy):
    def split(
        self,
        *,
        partition: DatasetPartition,
        features: Sequence[Mapping[str, float]],
        labels: Sequence[int],
    ) -> Iterable[tuple[Sequence[int], Sequence[int]]]:
        indices = list(range(len(features)))
        mid = len(indices) // 2 or 1
        yield indices[:mid], indices[mid:]


class DummyBackend:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []
        self.coefficients: list[float] = []

    def fit(
        self,
        *,
        train_features: Sequence[Mapping[str, float]],
        train_labels: Sequence[int],
        valid_features: Sequence[Mapping[str, float]],
        valid_labels: Sequence[int],
        params: Mapping[str, float],
    ) -> Mapping[str, float]:
        self.calls.append(self.name)
        return {
            "loss": 0.1 + 0.05 * len(self.calls),
            "accuracy": 0.8 + 0.01 * len(self.calls),
        }

    def calibrate(
        self,
        *,
        valid_features: Sequence[Mapping[str, float]],
        valid_labels: Sequence[int],
    ) -> CalibrationMetrics:
        return CalibrationMetrics(
            brier_score=0.2,
            expected_calibration_error=0.05,
            maximum_calibration_error=0.1,
            log_loss=0.3,
            sample_size=len(valid_labels) or 1,
        )

    def dump_state(self) -> Mapping[str, object]:
        return {"weights": self.coefficients or [0.1, 0.2]}


class DummyMetricsRepository:
    def __init__(self) -> None:
        self.records: dict[str, Mapping[str, float]] = {}

    def store(self, model_version: str, metrics: Mapping[str, float]) -> None:
        self.records[model_version] = dict(metrics)


class DummyArtifactBuilder(ModelArtifactBuilder):
    def build(
        self,
        *,
        request: TrainingRequest,
        metrics: Mapping[str, float],
        model_state: Mapping[str, Mapping[str, object]] | None = None,
    ) -> ModelArtifact:
        return ModelArtifact(
            model_version=request.metadata.get("model_version", "test-model"),
            created_at=datetime.now(timezone.utc),
            created_by="trainer",
            ai1_path=Path("/tmp/ai1.pkl"),
            ai2_path=Path("/tmp/ai2.pkl"),
            feature_schema_path=Path("/tmp/schema.json"),
            params_path=Path("/tmp/params.yaml"),
            metrics_path=Path("/tmp/metrics.json"),
            code_hash="codehash",
            data_hash=request.partition.data_hash,
        )


class DummyThetaEstimator(ThetaEstimator):
    def estimate(
        self,
        *,
        request: TrainingRequest,
        cv_metrics: Mapping[str, float],
        calibration_metrics: CalibrationMetrics,
    ) -> ThetaParams:
        return ThetaParams(
            theta1=cv_metrics.get("ai1_cv_accuracy", 0.7),
            theta2=0.3,
            updated_at=datetime.now(timezone.utc),
            updated_by="trainer",
            source_model_version=request.metadata.get("model_version", "test-model"),
        )


def make_features(size: int = 6) -> list[Mapping[str, float]]:
    return [{"f1": float(i), "f2": float(i % 3)} for i in range(size)]


def make_labels(size: int = 6, *, positive_every: int = 2) -> list[int]:
    return [1 if i % positive_every == 0 else 0 for i in range(size)]


def test_trainer_runs_cv_and_persists_metrics() -> None:
    repo = DummyMetricsRepository()
    trainer = Trainer(
        cv_strategy=DummyCV(),
        backend_ai1=DummyBackend("ai1"),
        backend_ai2=DummyBackend("ai2"),
        artifact_builder=DummyArtifactBuilder(),
        theta_estimator=DummyThetaEstimator(),
        metrics_repository=repo,
    )

    request = TrainingRequest(
        partition=make_partition(),
        features=make_features(),
        labels_ai1=make_labels(),
        labels_ai2=make_labels(positive_every=3),
        params_ai1={"max_depth": 3},
        params_ai2={"max_depth": 2},
        metadata={"model_version": "model-001"},
    )

    result = trainer.run(request)

    assert isinstance(result, TrainingResult)
    assert "ai1_cv_loss" in result.cv_metrics
    assert "ai2_cv_accuracy" in result.cv_metrics
    assert result.artifact.theta_params.source_model_version == "model-001"
    assert repo.records["model-001"]["ai1_cv_loss"] == result.cv_metrics["ai1_cv_loss"]
    assert result.artifact.calibration_metrics.sample_size == len(request.features)

