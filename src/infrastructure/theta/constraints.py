"""
θ 制約評価実装。
"""

from __future__ import annotations

from dataclasses import dataclass

from application.services.theta_optimizer import ConstraintEvaluator
from domain import ThetaParams


@dataclass(frozen=True)
class DeltaConstraintEvaluator(ConstraintEvaluator):
    """
    基準値からの差分（Δ）を制限する単純な ConstraintEvaluator。
    """

    default_max_delta: float
    baseline_theta1: float
    baseline_theta2: float

    def validate(self, params: ThetaParams, constraints: dict[str, float]) -> bool:
        max_delta = float(constraints.get("max_delta", self.default_max_delta))
        baseline_theta1 = float(constraints.get("baseline_theta1", self.baseline_theta1))
        baseline_theta2 = float(constraints.get("baseline_theta2", self.baseline_theta2))

        return (
            abs(params.theta1 - baseline_theta1) <= max_delta
            and abs(params.theta2 - baseline_theta2) <= max_delta
        )

