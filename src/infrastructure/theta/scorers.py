"""
θ パラメータのスコアリング実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from application.services.theta_optimizer import ThetaScorer
from domain import ThetaParams


@dataclass
class HistoricalThetaScorer(ThetaScorer):
    """
    過去のスコア履歴と閾値に基づき θ 候補へスコアを付与する実装。
    """

    max_drawdown_target: float
    reference_theta1: float
    reference_theta2: float
    exploration_penalty: float = 0.2

    def score(self, params: ThetaParams, history: Sequence[Mapping[str, float]]) -> float:
        best_score = 0.0
        for record in history:
            sharpe = float(record.get("sharpe", record.get("score", 0.0)))
            max_dd = float(record.get("max_dd", 0.0))
            theta1_hist = float(record.get("theta1", params.theta1))
            theta2_hist = float(record.get("theta2", params.theta2))

            similarity = 1.0 - 0.5 * (
                abs(params.theta1 - theta1_hist) + abs(params.theta2 - theta2_hist)
            )
            similarity = max(similarity, 0.0)

            penalty = max(0.0, max_dd - self.max_drawdown_target) * 2.0
            adjusted_score = sharpe - penalty
            best_score = max(best_score, adjusted_score * similarity)

        exploration = self.exploration_penalty * (
            abs(params.theta1 - self.reference_theta1) + abs(params.theta2 - self.reference_theta2)
        )
        return best_score - exploration

