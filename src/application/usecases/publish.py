"""
モデル配布ユースケースのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Protocol

from domain import ModelArtifact, ThetaParams

from infrastructure.storage import ModelArtifactDistributor, ModelDistributionResult, WormAppendResult, WormArchiveWriter


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


class ModelPublishService(PublishUseCase):
    """
    モデル成果物の配布・レジストリ更新・通知を担う実装。
    """

    def __init__(
        self,
        *,
        distributor: ModelArtifactDistributor,
        registry_updater: RegistryUpdater,
        notification_service: NotificationService | None = None,
        worm_writer: WormArchiveWriter | None = None,
        clock: callable | None = None,
    ) -> None:
        self._distributor = distributor
        self._registry_updater = registry_updater
        self._notification = notification_service
        self._worm_writer = worm_writer
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, request: PublishRequest) -> PublishResponse:
        distributed = self._distribute_artifacts(request)
        audit_record_id = self._update_registry(request)
        self._record_worm_log(request, distributed, audit_record_id)
        self._notify(request, distributed, audit_record_id)
        diagnostics = {
            "artifact_count": float(len(distributed.checksums)),
            "bytes_written": float(sum(len(value) for value in distributed.checksums.values())),
        }
        return PublishResponse(status="success", audit_record_id=audit_record_id, diagnostics=diagnostics)

    def _distribute_artifacts(self, request: PublishRequest) -> ModelDistributionResult:
        artifact = request.artifact
        metadata = {
            "created_at": artifact.created_at.isoformat(),
            "created_by": artifact.created_by,
            "code_hash": artifact.code_hash,
            "data_hash": artifact.data_hash,
            **request.metadata,
        }
        artifacts = {
            "model_ai1": artifact.ai1_path,
            "model_ai2": artifact.ai2_path,
            "feature_schema": artifact.feature_schema_path,
            "params": artifact.params_path,
            "metrics": artifact.metrics_path,
        }
        return self._distributor.distribute(
            model_version=artifact.model_version,
            artifacts=artifacts,
            metadata=metadata,
        )

    def _update_registry(self, request: PublishRequest) -> str:
        return self._registry_updater.update(request.artifact, request.theta_params)

    def _record_worm_log(
        self,
        request: PublishRequest,
        distribution: ModelDistributionResult,
        audit_record_id: str,
    ) -> WormAppendResult | None:
        if not self._worm_writer:
            return None
        payload = {
            "model_version": request.artifact.model_version,
            "audit_record_id": audit_record_id,
            "destination": str(distribution.destination),
            "checksums": distribution.checksums,
            "metadata": request.metadata,
            "created_at": self._clock().isoformat(),
        }
        return self._worm_writer.append("model_publish", payload)

    def _notify(
        self,
        request: PublishRequest,
        distribution: ModelDistributionResult,
        audit_record_id: str,
    ) -> None:
        if not self._notification:
            return
        message = f"model_version={request.artifact.model_version} distributed to {distribution.destination}"
        metadata = {
            "audit_record_id": audit_record_id,
            "artifact_count": str(len(distribution.checksums)),
            "model_version": request.artifact.model_version,
        }
        self._notification.notify("success", message, metadata)

