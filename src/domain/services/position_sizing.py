"""
ポジションサイズ計算ロジック。
"""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import PositionSizingRequest, PositionSizingService


@dataclass(frozen=True)
class PositionSizingConfig:
    base_position: float = 1.0
    max_position_scale: float = 1.5
    min_position_scale: float = 0.1
    risk_per_trade_fraction: float = 0.02


class ProportionalPositionSizingService(PositionSizingService):
    """
    リスクスコアと口座状況に応じてポジションスケールを決定する実装。
    """

    def __init__(self, config: PositionSizingConfig | None = None) -> None:
        self._config = config or PositionSizingConfig()

    def calculate(self, request: PositionSizingRequest) -> float:
        cfg = self._config
        equity = request.account_state.get("equity", 0.0)
        available_leverage = request.risk_parameters.get("max_leverage", cfg.max_position_scale)
        max_scale = min(cfg.max_position_scale, available_leverage)
        min_scale = request.risk_parameters.get("min_position_scale", cfg.min_position_scale)
        base_position = request.risk_parameters.get("base_position", cfg.base_position)

        risk_budget = equity * cfg.risk_per_trade_fraction
        volatility = request.risk_parameters.get("volatility", 1.0)
        notional_constraint = risk_budget / max(volatility, 1e-6)

        risk_factor = max(0.0, min(1.0, 1.0 - request.signal.risk_score))
        scale = base_position * risk_factor

        # 口座規模とレバレッジ制約を考慮
        scale = min(scale, max_scale)
        scale = min(scale, notional_constraint if notional_constraint > 0 else max_scale)
        scale = max(scale, min_scale)
        return scale

