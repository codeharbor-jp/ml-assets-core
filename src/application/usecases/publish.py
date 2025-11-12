"""
モデル配布ユースケースのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from ...domain import ModelArtifact, ThetaParams


@dataclass(frozen=True)
class PublishRequest:
    """
    モデル配布ユースケースの入力。
    """

    artifact: ModelArtifact
    theta_params: ThetaParams
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishResponse:
    """
    モデル配布ユースケースの出力。
    """

    status: str
    audit_record_id: str
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class RegistryUpdater(Protocol):
    """
    model_registry を更新するインターフェース。
    """

    def update(self, artifact: ModelArtifact, theta_params: ThetaParams) -> str:
        ...


class NotificationService(Protocol):
    """
    配布結果を外部へ通知するインターフェース。
    """

    def notify(self, status: str, message: str, metadata: Mapping[str, str]) -> None:
        ...


class PublishUseCase(Protocol):
    """
    モデル配布ユースケース。
    """

    def execute(self, request: PublishRequest) -> PublishResponse:
        ...

