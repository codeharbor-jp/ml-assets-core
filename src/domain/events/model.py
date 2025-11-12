"""
モデル関連のドメインイベント。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from ..models import ModelArtifact, ThetaParams
from ..value_objects import CalibrationMetrics
from .base import DomainEvent


@dataclass(frozen=True)
class ModelRetrained(DomainEvent):
    """
    再学習が完了し、新しいモデルアーティファクトが登録されたイベント。
    """

    artifact: ModelArtifact
    metrics: CalibrationMetrics


@dataclass(frozen=True)
class BacktestCompleted(DomainEvent):
    """
    バックテストが完了したイベント。
    """

    model_version: str
    summary_metrics: Mapping[str, float] = field(default_factory=dict)
    stress_results: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ThetaOptimized(DomainEvent):
    """
    θ最適化が完了し新しいパラメータが確定したイベント。
    """

    params: ThetaParams
    score: float
    diagnostics: Mapping[str, float] = field(default_factory=dict)

