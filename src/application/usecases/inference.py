"""
推論ユースケースのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from domain import Signal, ThetaParams


@dataclass(frozen=True)
class InferenceRequest:
    """
    推論ユースケースの入力。
    """

    partition_ids: Sequence[str]
    theta_params: ThetaParams
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class InferenceResponse:
    """
    推論ユースケースの出力。
    """

    signals: Sequence[Signal]
    diagnostics: Mapping[str, object] = field(default_factory=dict)


class SignalDispatcher(Protocol):
    """
    生成された Signal を下流へ送信するインターフェース。
    """

    def publish(self, signals: Sequence[Signal]) -> None:
        ...


class InferenceUseCase(Protocol):
    """
    推論処理のユースケース。
    """

    def execute(self, request: InferenceRequest) -> InferenceResponse:
        ...

