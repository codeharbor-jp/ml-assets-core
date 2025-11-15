"""
ストレス評価実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from application.services.backtester import StressEvaluator

from .policy import EvaluationThresholds


@dataclass
class ThresholdStressEvaluator(StressEvaluator):
    """
    Sharpe/MaxDD/取引数/停止率の閾値で合否を判定するシンプルな Evaluator。
    """

    thresholds: EvaluationThresholds

    def evaluate(
        self,
        *,
        base_metrics: Mapping[str, float],
        stress_metrics: Mapping[str, Mapping[str, float]],
    ) -> Mapping[str, float]:
        sharpe = float(base_metrics.get("sharpe", 0.0))
        max_drawdown = float(base_metrics.get("max_dd", 0.0))
        trades = float(base_metrics.get("trades", 0.0))
        halt_rate = float(base_metrics.get("halt_rate", 0.0))

        worst_stress_dd = max(
            (metrics.get("max_dd", 0.0) for metrics in stress_metrics.values()),
            default=max_drawdown,
        )

        meets = (
            sharpe >= self.thresholds.min_sharpe
            and max_drawdown <= self.thresholds.max_drawdown
            and trades >= self.thresholds.min_trades
            and halt_rate <= self.thresholds.max_halt_rate
        )

        return {
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "trades": trades,
            "halt_rate": halt_rate,
            "worst_stress_dd": float(worst_stress_dd),
            "meets_thresholds": 1.0 if meets else 0.0,
        }

