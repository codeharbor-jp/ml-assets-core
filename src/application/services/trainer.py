"""
学習・検証・キャリブレーションを統括する Trainer サービスの定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Protocol, Sequence

from ...domain import CalibrationMetrics, DatasetPartition, ModelArtifact, ThetaParams

FeatureVector = Mapping[str, float]


class TimeSeriesCVStrategy(Protocol):
    """
    時系列クロスバリデーションの戦略。
    """

    def split(self, *, partition: DatasetPartition, features: Sequence[FeatureVector], labels: Sequence[int]) -> Iterable[tuple[Sequence[int], Sequence[int]]]:
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


class MetricsRepository(Protocol):
    """
    学習・検証メトリクスの保存先。
    """

    def store(self, model_version: str, metrics: Mapping[str, float]) -> None:
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
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class TrainerService(Protocol):
    """
    学習・CV・キャリブレーション処理を提供するサービス。
    """

    def run(self, request: TrainingRequest) -> TrainingResult:
        ...

