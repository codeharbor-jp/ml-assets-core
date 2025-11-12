"""
リスク評価ロジックの実装。
"""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import RiskAssessmentRequest, RiskAssessmentResult, RiskAssessmentService


@dataclass(frozen=True)
class RiskConfig:
    var_limit: float = 0.025
    atr_ratio_limit: float = 1.8
    speed_limit: float = 0.12
    drawdown_limit: float = 0.07


class RuleBasedRiskAssessmentService(RiskAssessmentService):
    """
    要件に沿ったフラグベースのリスク評価。
    """

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or RiskConfig()

    def evaluate(self, request: RiskAssessmentRequest) -> RiskAssessmentResult:
        metrics = request.metrics
        cfg = self._config

        flags = {
            "rho_var": metrics.get("rho_var_180", 0.0) > cfg.var_limit,
            "atr_ratio": metrics.get("atr_ratio", 0.0) > cfg.atr_ratio_limit,
            "speed": abs(metrics.get("delta_z_ema", 0.0)) > cfg.speed_limit,
            "drawdown": metrics.get("drawdown_recent", 0.0) > cfg.drawdown_limit,
        }

        triggered = sum(1 for value in flags.values() if value)
        risk_score = min(1.0, triggered / max(len(flags), 1))
        return RiskAssessmentResult(risk_score=risk_score, flags=flags)

