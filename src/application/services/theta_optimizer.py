"""
θ最適化サービスのプロトコル定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from domain import ThetaParams, ThetaRange


class GridSearchStrategy(Protocol):
    """
    粗グリッド探索を行う戦略。
    """

    def generate_candidates(self, theta_range: ThetaRange, steps: Mapping[str, int]) -> Sequence[ThetaParams]:
        ...


class OptunaOptimizationStrategy(Protocol):
    """
    Optuna による探索をカプセル化する戦略。
    """

    def optimize(
        self,
        *,
        theta_range: ThetaRange,
        trials: int,
        timeout_seconds: int | None,
        base_candidates: Sequence[ThetaParams],
        constraints: Mapping[str, float],
    ) -> ThetaParams:
        ...


class ConstraintEvaluator(Protocol):
    """
    θ 更新の制約評価。
    """

    def validate(self, params: ThetaParams, constraints: Mapping[str, float]) -> bool:
        ...


@dataclass(frozen=True)
class ThetaOptimizationPlan:
    """
    粗グリッド探索と Optuna 探索の設定。
    """

    grid_steps: Mapping[str, int]
    optuna_trials: int
    optuna_timeout_seconds: int | None = None
    constraints: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ThetaOptimizationRequest:
    """
    θ最適化の入力。
    """

    range: ThetaRange
    initial_params: ThetaParams
    plan: ThetaOptimizationPlan
    score_history: Sequence[Mapping[str, float]]
    metadata: Mapping[str, str] = field(default_factory=dict)


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
    粗グリッド→Optuna探索のフローを統括するサービス。
    """

    def optimize(self, request: ThetaOptimizationRequest) -> ThetaOptimizationResult:
        ...

