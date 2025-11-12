"""
θ範囲を表す値オブジェクト。
"""

from __future__ import annotations

from dataclasses import dataclass


def _validate_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} は 0.0 以上 1.0 以下である必要があります。")


@dataclass(frozen=True)
class ThetaRange:
    """
    θ探索・制約で使用する上限・下限を表す値オブジェクト。

    Attributes:
        theta1_min: θ1 の下限。
        theta1_max: θ1 の上限。
        theta2_min: θ2 の下限。
        theta2_max: θ2 の上限。
        max_delta: 連続更新時の最大変動幅。
    """

    theta1_min: float
    theta1_max: float
    theta2_min: float
    theta2_max: float
    max_delta: float

    def __post_init__(self) -> None:
        _validate_probability(self.theta1_min, "theta1_min")
        _validate_probability(self.theta1_max, "theta1_max")
        _validate_probability(self.theta2_min, "theta2_min")
        _validate_probability(self.theta2_max, "theta2_max")

        if self.theta1_min >= self.theta1_max:
            raise ValueError("theta1_min は theta1_max より小さい必要があります。")
        if self.theta2_min >= self.theta2_max:
            raise ValueError("theta2_min は theta2_max より小さい必要があります。")
        if self.max_delta <= 0:
            raise ValueError("max_delta は正の値である必要があります。")
        if self.max_delta > 1:
            raise ValueError("max_delta は 1 以下である必要があります。")

    def clamp_theta1(self, value: float) -> float:
        """θ1 を範囲内へ丸める。"""

        _validate_probability(value, "theta1")
        return min(max(value, self.theta1_min), self.theta1_max)

    def clamp_theta2(self, value: float) -> float:
        """θ2 を範囲内へ丸める。"""

        _validate_probability(value, "theta2")
        return min(max(value, self.theta2_min), self.theta2_max)

    def is_delta_allowed(self, previous: float, current: float) -> bool:
        """
        連続更新時の変動幅が許容値を超えていないか判定する。
        """

        _validate_probability(previous, "previous")
        _validate_probability(current, "current")
        return abs(previous - current) <= self.max_delta

