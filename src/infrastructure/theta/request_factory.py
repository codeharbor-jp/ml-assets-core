"""
ThetaOptimizationRequest を構築するファクトリ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from application.services.theta_optimizer import ThetaOptimizationPlan, ThetaOptimizationRequest
from domain import ThetaParams, ThetaRange


@dataclass
class ThetaRequestFactory:
    """
    コアポリシーに基づき ThetaOptimizationRequest を構築する。
    """

    theta_range: ThetaRange
    plan: ThetaOptimizationPlan

    def build(
        self,
        *,
        initial_params: ThetaParams,
        score_history: Sequence[Mapping[str, float]],
        metadata: Mapping[str, str] | None = None,
    ) -> ThetaOptimizationRequest:
        constraints = dict(self.plan.constraints)
        constraints.setdefault("baseline_theta1", initial_params.theta1)
        constraints.setdefault("baseline_theta2", initial_params.theta2)
        constraints.setdefault("max_delta", self.theta_range.max_delta)

        plan = ThetaOptimizationPlan(
            grid_steps=self.plan.grid_steps,
            optuna_trials=self.plan.optuna_trials,
            optuna_timeout_seconds=self.plan.optuna_timeout_seconds,
            constraints=constraints,
        )

        return ThetaOptimizationRequest(
            range=self.theta_range,
            initial_params=initial_params,
            plan=plan,
            score_history=tuple(score_history),
            metadata=dict(metadata or {}),
        )

