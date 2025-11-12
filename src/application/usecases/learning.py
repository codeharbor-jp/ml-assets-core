"""
再学習フローのユースケーススケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from ...domain import DatasetPartition, ModelArtifact, ThetaRange
from ..services import (
    BacktesterService,
    FeatureBuilderService,
    FeatureBuildRequest,
    ThetaOptimizationService,
    TrainerService,
    TrainingRequest,
)


@dataclass(frozen=True)
class LearningRequest:
    """
    再学習ユースケースの入力。
    """

    partitions: Sequence[DatasetPartition]
    feature_spec: Mapping[str, str]
    preprocessing: Mapping[str, str]
    theta_range: ThetaRange
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningResponse:
    """
    再学習ユースケースの出力。
    """

    model_artifact: ModelArtifact
    backtest_metrics: Mapping[str, float]
    theta_params: Mapping[str, float]
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class AuditLogger(Protocol):
    """
    ユースケースの監査イベントを記録する。
    """

    def log(self, event_name: str, payload: Mapping[str, str]) -> None:
        ...


class LearningUseCase(Protocol):
    """
    再学習のユースケース。
    """

    def execute(self, request: LearningRequest) -> LearningResponse:
        ...

