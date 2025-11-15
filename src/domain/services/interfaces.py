"""
ドメインサービスの主要インターフェース定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from ..models import DatasetPartition, Signal, ThetaParams
from ..value_objects import CalibrationMetrics, ThetaRange

FeatureVector = Mapping[str, float]


@dataclass(frozen=True)
class LabelingInput:
    """
    ラベリング処理に必要な入力。
    """

    partition: DatasetPartition
    features: Sequence[Mapping[str, object]]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LabelingOutput:
    """
    ラベリング処理の出力。

    Attributes:
        ai1_labels: AI1 用の 0/1 ラベル列。
        ai2_labels: AI2 用の 0/1 ラベル列。
        ai3_targets: AI3（スケール等）用の連続値。必要に応じて空配列を許容。
        calibration_metrics: 生成されたラベルに対するキャリブレーション指標。
    """

    ai1_labels: Sequence[int]
    ai2_labels: Sequence[int]
    ai3_targets: Sequence[float]
    calibration_metrics: CalibrationMetrics

    def __post_init__(self) -> None:
        lengths = {len(self.ai1_labels), len(self.ai2_labels), len(self.ai3_targets)}
        lengths.discard(0)
        if len(lengths) > 1:
            raise ValueError("AI ラベル/ターゲットの長さが一致していません。")


class LabelingService(Protocol):
    """
    AI1/AI2/AI3 のラベリングを行うサービス。
    """

    def generate(self, request: LabelingInput) -> LabelingOutput:
        ...


@dataclass(frozen=True)
class RiskAssessmentRequest:
    """
    リスク評価に必要な入力。
    """

    signal: Signal
    metrics: Mapping[str, float]


@dataclass(frozen=True)
class RiskAssessmentResult:
    """
    リスク評価の結果。
    """

    risk_score: float
    flags: Mapping[str, bool]

    def __post_init__(self) -> None:
        if not 0.0 <= self.risk_score <= 1.0:
            raise ValueError("risk_score は 0.0〜1.0 の範囲で指定してください。")


class RiskAssessmentService(Protocol):
    """
    シグナルのリスク評価を行うサービス。
    """

    def evaluate(self, request: RiskAssessmentRequest) -> RiskAssessmentResult:
        ...


@dataclass(frozen=True)
class ThetaOptimizationRequest:
    """
    θ最適化に必要な入力。
    """

    range: ThetaRange
    historical_metrics: Sequence[Mapping[str, float]]
    constraints: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ThetaOptimizationResult:
    """
    θ最適化の結果。
    """

    params: ThetaParams
    score: float
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class ThetaOptimizationService(Protocol):
    """
    θ探索・最適化を行うサービス。
    """

    def optimize(self, request: ThetaOptimizationRequest) -> ThetaOptimizationResult:
        ...


@dataclass(frozen=True)
class PositionSizingRequest:
    """
    ポジションサイズ計算に必要な入力。
    """

    signal: Signal
    account_state: Mapping[str, float]
    risk_parameters: Mapping[str, float]


class PositionSizingService(Protocol):
    """
    ポジションサイズを算出するサービス。
    """

    def calculate(self, request: PositionSizingRequest) -> float:
        ...


@dataclass(frozen=True)
class SignalAssemblyRequest:
    """
    シグナル生成のための組み立てリクエスト。
    """

    partition: DatasetPartition
    features: Sequence[FeatureVector]
    theta_params: ThetaParams
    metadata: Mapping[str, str] = field(default_factory=dict)


class SignalAssemblyService(Protocol):
    """
    生データ・特徴量から Signal を組み立てるドメインサービス。
    """

    def assemble(self, request: SignalAssemblyRequest) -> Sequence[Signal]:
        ...

