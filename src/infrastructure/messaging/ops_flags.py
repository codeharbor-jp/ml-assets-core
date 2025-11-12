"""
Ops フラグ管理のリポジトリ定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class OpsFlagSnapshot:
    """
    Ops フラグのスナップショット。
    """

    global_halt: bool
    halted_pairs: Sequence[str]
    flatten_pairs: Sequence[str]
    leverage_scale: float
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.leverage_scale <= 0:
            raise ValueError("leverage_scale は正の値である必要があります。")


class OpsFlagRepository(Protocol):
    """
    Ops フラグの取得・更新を行うインターフェース。
    """

    def get_snapshot(self) -> OpsFlagSnapshot:
        ...

    def set_global_halt(self, value: bool, *, reason: str) -> None:
        ...

    def set_halted_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        ...

    def set_flatten_pairs(self, pairs: Sequence[str], *, reason: str) -> None:
        ...

    def set_leverage_scale(self, value: float, *, reason: str) -> None:
        ...

