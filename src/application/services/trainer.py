"""
学習・検証・キャリブレーションを統括する Trainer サービスの定義。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from typing import Callable, Iterable, Mapping, Protocol, Sequence

from domain import CalibrationMetrics, DatasetPartition, ModelArtifact, ThetaParams

from application.observability import metrics_recorder, telemetry_span

FeatureVector = Mapping[str, float]


class TimeSeriesCVStrategy(Protocol):
    """
    時系列クロスバリデーションの戦略。
    """

    def split(
        self,
        *,
        partition: DatasetPartition,
        features: Sequence[FeatureVector],
        labels: Sequence[int],
    ) -> Iterable[tuple[Sequence[int], Sequence[int]]]:
        ...


class ModelTrainerBackend(Protocol):
    """
    実際のモデル学習 backend（LightGBM, XGBoost等）をカプセル化するインターフェース。
    """

    def fit(
        self,
        *,
        train_features: Sequence[FeatureVector],
        train_labels: Sequence[int],
        valid_features: Sequence[FeatureVector],
        valid_labels: Sequence[int],
        params: Mapping[str, float],
    ) -> Mapping[str, float]:
        ...

    def calibrate(
        self,
        *,
        valid_features: Sequence[FeatureVector],
        valid_labels: Sequence[int],
    ) -> CalibrationMetrics:
        ...

    def dump_state(self) -> Mapping[str, object]:
        """学習済みモデルのシリアライズ可能な状態を返す。"""


class MetricsRepository(Protocol):
    """
    学習・検証メトリクスの保存先。
    """

    def store(self, model_version: str, metrics: Mapping[str, float]) -> None:
        ...


class ModelArtifactBuilder(Protocol):
    """
    学習済みモデルアーティファクトを作成するファクトリ。
    """

    def build(
        self,
        *,
        request: "TrainingRequest",
        metrics: Mapping[str, float],
        model_state: Mapping[str, Mapping[str, object]] | None = None,
    ) -> ModelArtifact:
        ...


class ThetaEstimator(Protocol):
    """
    学習メトリクスから θ パラメータを推定する。
    """

    def estimate(
        self,
        *,
        request: "TrainingRequest",
        cv_metrics: Mapping[str, float],
        calibration_metrics: CalibrationMetrics,
    ) -> ThetaParams:
        ...


@dataclass(frozen=True)
class TrainingRequest:
    """
    学習ジョブの入力。
    """

    partition: DatasetPartition
    features: Sequence[FeatureVector]
    labels_ai1: Sequence[int]
    labels_ai2: Sequence[int]
    params_ai1: Mapping[str, float]
    params_ai2: Mapping[str, float]
    calibration: bool = True
    random_seed: int | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        lengths = {len(self.features), len(self.labels_ai1), len(self.labels_ai2)}
        if len(set(lengths)) != 1:
            raise ValueError("features とラベル列の長さが一致しません。")


@dataclass(frozen=True)
class TrainingArtifact:
    """
    学習済みモデルアーティファクトのメタ情報を保持。
    """

    artifact: ModelArtifact
    theta_params: ThetaParams
    calibration_metrics: CalibrationMetrics


@dataclass(frozen=True)
class TrainingResult:
    """
    学習ジョブの結果。
    """

    artifact: TrainingArtifact
    cv_metrics: Mapping[str, float]
    diagnostics: Mapping[str, str] = field(default_factory=dict)


class TrainerService(Protocol):
    """
    学習・CV・キャリブレーション処理を提供するサービス。
    """

    def run(self, request: TrainingRequest) -> TrainingResult:
        ...


class Trainer(TrainerService):
    """
    CV → 本学習 → キャリブレーション → 成果物生成までを統括する実装。
    """

    def __init__(
        self,
        *,
        cv_strategy: TimeSeriesCVStrategy,
        backend_ai1: ModelTrainerBackend,
        backend_ai2: ModelTrainerBackend,
        artifact_builder: ModelArtifactBuilder,
        theta_estimator: ThetaEstimator,
        metrics_repository: MetricsRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._cv_strategy = cv_strategy
        self._backend_ai1 = backend_ai1
        self._backend_ai2 = backend_ai2
        self._artifact_builder = artifact_builder
        self._theta_estimator = theta_estimator
        self._metrics_repository = metrics_repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, request: TrainingRequest) -> TrainingResult:
        with telemetry_span(
            "trainer.run",
            {
                "partition.symbol": request.partition.symbol,
                "partition.timeframe": request.partition.timeframe,
            },
        ):
            start = time.perf_counter()

            result = self._run_training(request)
            model_version = result.artifact.artifact.model_version
            duration = time.perf_counter() - start
            metrics_recorder.observe_training_duration(model_version, duration)
            metrics_recorder.increment_retrain_success("success")
            return result

    def _run_training(self, request: TrainingRequest) -> TrainingResult:
        cv_ai1 = []
        cv_ai2 = []
        splits = list(
            self._cv_strategy.split(
                partition=request.partition,
                features=request.features,
                labels=request.labels_ai1,
            )
        )
        if not splits:
            # 単純にホールドアウト無しで全量学習
            splits = [(
                tuple(range(len(request.features))),
                tuple(range(len(request.features))),
            )]

        for train_idx, valid_idx in splits:
            train_features = _select(request.features, train_idx)
            valid_features = _select(request.features, valid_idx)
            train_labels_ai1 = _select(request.labels_ai1, train_idx)
            valid_labels_ai1 = _select(request.labels_ai1, valid_idx)
            train_labels_ai2 = _select(request.labels_ai2, train_idx)
            valid_labels_ai2 = _select(request.labels_ai2, valid_idx)

            metrics_ai1 = self._backend_ai1.fit(
                train_features=train_features,
                train_labels=train_labels_ai1,
                valid_features=valid_features,
                valid_labels=valid_labels_ai1,
                params=request.params_ai1,
            )
            metrics_ai2 = self._backend_ai2.fit(
                train_features=train_features,
                train_labels=train_labels_ai2,
                valid_features=valid_features,
                valid_labels=valid_labels_ai2,
                params=request.params_ai2,
            )
            cv_ai1.append(metrics_ai1)
            cv_ai2.append(metrics_ai2)

        cv_metrics = {
            **_aggregate_metrics(cv_ai1, prefix="ai1_cv_"),
            **_aggregate_metrics(cv_ai2, prefix="ai2_cv_"),
            "folds": float(len(splits)),
        }

        calibration_metrics = self._run_calibration(request)
        theta_params = self._theta_estimator.estimate(
            request=request,
            cv_metrics=cv_metrics,
            calibration_metrics=calibration_metrics,
        )

        model_state = {
            "ai1": dict(self._backend_ai1.dump_state()),
            "ai2": dict(self._backend_ai2.dump_state()),
        }

        artifact = self._artifact_builder.build(
            request=request,
            metrics=cv_metrics,
            model_state=model_state,
        )
        training_artifact = TrainingArtifact(
            artifact=artifact,
            theta_params=theta_params,
            calibration_metrics=calibration_metrics,
        )

        diagnostics = {
            "trained_at": self._clock().isoformat(),
            "sample_size": str(len(request.features)),
        }

        if self._metrics_repository is not None:
            self._metrics_repository.store(artifact.model_version, cv_metrics)

        return TrainingResult(artifact=training_artifact, cv_metrics=cv_metrics, diagnostics=diagnostics)

    def _run_calibration(self, request: TrainingRequest) -> CalibrationMetrics:
        if not request.calibration:
            # キャリブレーション無効時は簡易メトリクスを返す
            positive = sum(request.labels_ai1)
            size = max(len(request.labels_ai1), 1)
            rate = positive / size
            return CalibrationMetrics(
                brier_score=rate * (1 - rate),
                expected_calibration_error=0.0,
                maximum_calibration_error=0.0,
                log_loss=0.0,
                sample_size=max(1, size),
            )

        return self._backend_ai1.calibrate(
            valid_features=request.features,
            valid_labels=request.labels_ai1,
        )


def _select(sequence: Sequence, indices: Sequence[int]) -> list:
    return [sequence[i] for i in indices]


def _aggregate_metrics(metrics: Sequence[Mapping[str, float]], *, prefix: str) -> dict[str, float]:
    if not metrics:
        return {}
    aggregated: dict[str, list[float]] = {}
    for metric in metrics:
        for key, value in metric.items():
            aggregated.setdefault(key, []).append(value)
    return {f"{prefix}{key}": float(mean(values)) for key, values in aggregated.items()}

