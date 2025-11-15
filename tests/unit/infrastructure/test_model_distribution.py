from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.storage import (
    ModelArtifactDistributor,
    ModelDistributionResult,
    StoragePathResolver,
)
from infrastructure.storage.filesystem import LocalFileSystemStorageClient


class _StubConfigRepository:
    def __init__(self, storage_root: Path) -> None:
        self._storage_root = storage_root

    def load(self, name: str, *, environment: str) -> dict[str, object]:  # noqa: ARG002
        if name != "storage":
            raise KeyError(name)
        return {
            "storage": {
                "models_root": str(self._storage_root),
            }
        }


def _make_distributor(tmp_path: Path) -> tuple[ModelArtifactDistributor, Path]:
    models_root = tmp_path / "models"
    repository = _StubConfigRepository(models_root)
    resolver = StoragePathResolver(config_repository=repository, environment="dev")
    distributor = ModelArtifactDistributor(
        storage_client=LocalFileSystemStorageClient(),
        path_resolver=resolver,
    )
    return distributor, models_root


def test_distribute_writes_artifacts_and_checksums(tmp_path: Path) -> None:
    distributor, models_root = _make_distributor(tmp_path)

    ai1 = tmp_path / "ai1.bin"
    ai1.write_bytes(b"model-ai1")
    ai2 = tmp_path / "ai2.bin"
    ai2.write_bytes(b"model-ai2")

    result = distributor.distribute(
        model_version="v1",
        artifacts={
            "model_ai1": ai1,
            "model_ai2": ai2,
        },
        metadata={"created_by": "unit-test"},
    )

    assert isinstance(result, ModelDistributionResult)
    assert result.destination == models_root / "v1"
    assert (models_root / "v1" / "model_ai1.bin").exists()
    assert (models_root / "v1" / "model_ai2.bin").exists()
    assert (models_root / "v1" / "checksums.json").exists()

    # checksums.json should include metadata we passed
    payload = json.loads((models_root / "v1" / "checksums.json").read_text(encoding="utf-8"))
    assert payload["metadata"]["created_by"] == "unit-test"

    verified = distributor.verify(model_version="v1")
    assert verified == result.checksums


def test_verify_detects_checksum_mismatch(tmp_path: Path) -> None:
    distributor, models_root = _make_distributor(tmp_path)

    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"original")

    distributor.distribute(model_version="v2", artifacts={"model_ai1": artifact})

    target = models_root / "v2" / "model_ai1.bin"
    target.write_bytes(b"tampered")

    with pytest.raises(Exception):
        distributor.verify(model_version="v2")

