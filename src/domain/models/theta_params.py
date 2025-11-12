"""
θ関連のパラメータエンティティ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ThetaParams:
    """
    θ閾値および関連メタデータ。
    """

    theta1: float
    theta2: float
    updated_at: datetime
    updated_by: str
    source_model_version: str | None = None

    def __post_init__(self) -> None:
        _validate_probability(self.theta1, "theta1")
        _validate_probability(self.theta2, "theta2")
        if not self.updated_by:
            raise ValueError("updated_by は必須です。")
        if self.source_model_version is not None and not self.source_model_version:
            raise ValueError("source_model_version は空文字列ではなく None か非空文字列で指定してください。")


def _validate_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} は 0.0 以上 1.0 以下である必要があります。")

