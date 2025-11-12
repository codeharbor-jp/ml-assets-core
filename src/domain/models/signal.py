"""
シグナル関連ドメインエンティティ。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Mapping, Sequence


class TradeSide(str, Enum):
    """取引方向。"""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class SignalLeg:
    """片側レッグの定義。"""

    symbol: str
    side: TradeSide
    beta_weight: float
    notional: float

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol は空文字列にできません。")
        if self.notional <= 0:
            raise ValueError("notional は正の値である必要があります。")


@dataclass(frozen=True)
class Signal:
    """
    推論結果として生成されるシグナル。
    """

    signal_id: str
    timestamp: datetime
    pair_id: str
    legs: Sequence[SignalLeg]
    return_prob: float
    risk_score: float
    theta1: float
    theta2: float
    position_scale: float
    model_version: str
    valid_until: datetime
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("signal_id は必須です。")
        if not self.pair_id:
            raise ValueError("pair_id は必須です。")
        if not self.model_version:
            raise ValueError("model_version は必須です。")
        if not self.legs:
            raise ValueError("legs は1件以上必要です。")
        for leg in self.legs:
            if leg.beta_weight == 0:
                raise ValueError("beta_weight はゼロではいけません。")

        _validate_probability(self.return_prob, "return_prob")
        _validate_probability(self.risk_score, "risk_score")
        _validate_probability(self.theta1, "theta1")
        _validate_probability(self.theta2, "theta2")

        if self.position_scale <= 0:
            raise ValueError("position_scale は正の値である必要があります。")
        if self.valid_until <= self.timestamp:
            raise ValueError("valid_until は timestamp より未来を指定してください。")


def _validate_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} は 0.0 以上 1.0 以下である必要があります。")

