"""
OPS コマンドユースケースのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class OpsCommand:
    """
    Ops コマンドの入力。
    """

    command: str
    arguments: Mapping[str, str]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OpsResponse:
    """
    Ops コマンドの実行結果。
    """

    status: str
    message: str


class OpsExecutor(Protocol):
    """
    実際の Ops 操作（ハルト、フラッテン等）を実行する。
    """

    def execute(self, command: str, arguments: Mapping[str, str]) -> str:
        ...


class OpsUseCase(Protocol):
    """
    Ops コマンドのハンドラ。
    """

    def execute(self, command: OpsCommand) -> OpsResponse:
        ...

