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


class ThetaScorer(Protocol):
    """
    θ 候補にスコアを付与するインターフェース。
    """

    def score(self, params: ThetaParams, history: Sequence[Mapping[str, float]]) -> float:
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


class ThetaOptimizer(ThetaOptimizationService):
    """
    粗グリッド探索と Optuna の結果を統合し、制約を満たす θ を選択する実装。
    """

    def __init__(
        self,
        *,
        grid_strategy: GridSearchStrategy,
        optuna_strategy: OptunaOptimizationStrategy,
        constraint_evaluator: ConstraintEvaluator,
        scorer: ThetaScorer,
    ) -> None:
        self._grid_strategy = grid_strategy
        self._optuna_strategy = optuna_strategy
        self._constraint_evaluator = constraint_evaluator
        self._scorer = scorer

    def optimize(self, request: ThetaOptimizationRequest) -> ThetaOptimizationResult:
        plan = request.plan
        grid_candidates = list(self._grid_strategy.generate_candidates(request.range, plan.grid_steps))
        feasible = [c for c in grid_candidates if self._constraint_evaluator.validate(c, plan.constraints)]

        if not feasible:
            feasible = [request.initial_params]

        base_scores = {candidate: self._scorer.score(candidate, request.score_history) for candidate in feasible}
        best_grid_candidate = max(feasible, key=lambda candidate: base_scores[candidate])
        best_grid_score = base_scores[best_grid_candidate]

        optuna_candidate = self._optuna_strategy.optimize(
            theta_range=request.range,
            trials=plan.optuna_trials,
            timeout_seconds=plan.optuna_timeout_seconds,
            base_candidates=tuple(feasible),
            constraints=plan.constraints,
        )

        if not self._constraint_evaluator.validate(optuna_candidate, plan.constraints):
            selected_candidate = best_grid_candidate
            selected_score = best_grid_score
        else:
            optuna_score = self._scorer.score(optuna_candidate, request.score_history)
            if optuna_score >= best_grid_score:
                selected_candidate = optuna_candidate
                selected_score = optuna_score
            else:
                selected_candidate = best_grid_candidate
                selected_score = best_grid_score

        diagnostics = {
            "grid_candidates": float(len(grid_candidates)),
            "feasible_candidates": float(len(feasible)),
            "selected_from_optuna": 1.0 if selected_candidate is optuna_candidate else 0.0,
            "best_grid_score": best_grid_score,
        }

        return ThetaOptimizationResult(
            params=selected_candidate,
            score=selected_score,
            diagnostics=diagnostics,
        )

