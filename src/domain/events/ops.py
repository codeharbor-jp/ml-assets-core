"""
運用関連のドメインイベント。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .base import DomainEvent


@dataclass(frozen=True)
class OpsHaltTriggered(DomainEvent):
    """
    運用停止（ハルト/フラッテンなど）が発火したイベント。
    """

    level: str
    reason: str
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.level not in {"soft_halt", "hard_halt", "flatten"}:
            raise ValueError("level は soft_halt/hard_halt/flatten のいずれかを指定してください。")
        if not self.reason:
            raise ValueError("reason は必須です。")

