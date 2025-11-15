from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.usecases.publish import (
    ModelPublishService,
    NotificationService,
    PublishRequest,
    PublishResponse,
    RegistryUpdater,
)
from domain import ModelArtifact, ThetaParams
from infrastructure.storage import ModelArtifactDistributor, ModelDistributionResult, WormAppendResult, WormArchiveWriter


def _make_artifact(model_version: str = "v1") -> ModelArtifact:
    now = datetime(2025, 1, 15, 12, tzinfo=timezone.utc)
    tmp = Path("/tmp")
    return ModelArtifact(
        model_version=model_version,
        created_at=now,
        created_by="unit-test",
        ai1_path=tmp / "ai1.bin",
        ai2_path=tmp / "ai2.bin",
        feature_schema_path=tmp / "schema.json",
        params_path=tmp / "params.yaml",
        metrics_path=tmp / "metrics.json",
        code_hash="abc123",
        data_hash="def456",
    )


def _make_theta() -> ThetaParams:
    return ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="unit-test")


def test_model_publish_service_runs_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    distributor = MagicMock(spec=ModelArtifactDistributor)
    distribution_result = ModelDistributionResult(
        model_version="v1",
        destination=tmp_path / "models" / "v1",
        checksums={"model_ai1.bin": "aaa"},
        metadata_path=tmp_path / "models" / "v1" / "checksums.json",
    )
    distributor.distribute.return_value = distribution_result

    registry_updater = MagicMock(spec=RegistryUpdater)
    registry_updater.update.return_value = "audit-123"

    notification = MagicMock(spec=NotificationService)

    worm_writer = MagicMock(spec=WormArchiveWriter)
    worm_writer.append.return_value = WormAppendResult(
        record_type="model_publish",
        path=tmp_path / "worm" / "model_publish" / "2025" / "202501" / "record.json",
        bytes_written=128,
    )

    service = ModelPublishService(
        distributor=distributor,
        registry_updater=registry_updater,
        notification_service=notification,
        worm_writer=worm_writer,
    )

    artifact = _make_artifact()
    request = PublishRequest(artifact=artifact, theta_params=_make_theta(), metadata={"trigger": "unit"})

    response = service.execute(request)

    assert isinstance(response, PublishResponse)
    assert response.status == "success"
    assert response.audit_record_id == "audit-123"
    distributor.distribute.assert_called_once()
    registry_updater.update.assert_called_once_with(artifact, request.theta_params)
    notification.notify.assert_called_once()
    worm_writer.append.assert_called_once()


def test_model_publish_service_without_optional_components(tmp_path: Path) -> None:
    distributor = MagicMock(spec=ModelArtifactDistributor)
    distributor.distribute.return_value = ModelDistributionResult(
        model_version="v2",
        destination=tmp_path / "models" / "v2",
        checksums={},
        metadata_path=tmp_path / "models" / "v2" / "checksums.json",
    )

    registry_updater = MagicMock(spec=RegistryUpdater)
    registry_updater.update.return_value = "audit-789"

    service = ModelPublishService(
        distributor=distributor,
        registry_updater=registry_updater,
    )

    response = service.execute(PublishRequest(artifact=_make_artifact("v2"), theta_params=_make_theta()))

    assert response.audit_record_id == "audit-789"
    assert response.status == "success"

