"""
設定変更フローを扱うユースケース。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


@dataclass(frozen=True)
class ConfigValidationRequest:
    payload: Mapping[str, object]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigPRRequest:
    payload: Mapping[str, object]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConfigApproveRequest:
    pr_id: str
    comment: str | None = None


@dataclass(frozen=True)
class ConfigMergeRequest:
    pr_id: str


@dataclass(frozen=True)
class ConfigApplyRequest:
    pr_id: str


@dataclass(frozen=True)
class ConfigRollbackRequest:
    pr_id: str
    reason: str | None = None


@dataclass(frozen=True)
class ConfigOperationResult:
    action: str
    payload: Mapping[str, object]


class ConfigAPI(Protocol):
    """
    Config API クライアントのプロトコル。
    """

    def validate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        ...

    def create_pr(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        ...

    def approve(self, pr_id: str, *, comment: str | None = None) -> Mapping[str, object]:
        ...

    def merge(self, pr_id: str) -> Mapping[str, object]:
        ...

    def apply(self, pr_id: str) -> Mapping[str, object]:
        ...

    def rollback(self, pr_id: str, *, reason: str | None = None) -> Mapping[str, object]:
        ...


class ConfigManagementUseCase(Protocol):
    """
    Config API を介した設定変更フローのユースケース。
    """

    def validate(self, request: ConfigValidationRequest) -> ConfigOperationResult:
        ...

    def create_pr(self, request: ConfigPRRequest) -> ConfigOperationResult:
        ...

    def approve(self, request: ConfigApproveRequest) -> ConfigOperationResult:
        ...

    def merge(self, request: ConfigMergeRequest) -> ConfigOperationResult:
        ...

    def apply(self, request: ConfigApplyRequest) -> ConfigOperationResult:
        ...

    def rollback(self, request: ConfigRollbackRequest) -> ConfigOperationResult:
        ...


class ConfigManagementService(ConfigManagementUseCase):
    """
    Config API クライアントを用いて設定変更操作を実行する実装。
    """

    def __init__(self, client: ConfigAPI) -> None:
        self._client = client

    def validate(self, request: ConfigValidationRequest) -> ConfigOperationResult:
        payload = {**request.payload, "metadata": dict(request.metadata)}
        result = self._client.validate(payload)
        return ConfigOperationResult(action="validate", payload=result)

    def create_pr(self, request: ConfigPRRequest) -> ConfigOperationResult:
        payload = {**request.payload, "metadata": dict(request.metadata)}
        result = self._client.create_pr(payload)
        return ConfigOperationResult(action="create_pr", payload=result)

    def approve(self, request: ConfigApproveRequest) -> ConfigOperationResult:
        result = self._client.approve(request.pr_id, comment=request.comment)
        return ConfigOperationResult(action="approve", payload=result)

    def merge(self, request: ConfigMergeRequest) -> ConfigOperationResult:
        result = self._client.merge(request.pr_id)
        return ConfigOperationResult(action="merge", payload=result)

    def apply(self, request: ConfigApplyRequest) -> ConfigOperationResult:
        result = self._client.apply(request.pr_id)
        return ConfigOperationResult(action="apply", payload=result)

    def rollback(self, request: ConfigRollbackRequest) -> ConfigOperationResult:
        result = self._client.rollback(request.pr_id, reason=request.reason)
        return ConfigOperationResult(action="rollback", payload=result)

