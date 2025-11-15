from __future__ import annotations

import os
from pathlib import Path

import pytest

from infrastructure.storage import StoragePathResolver, WormArchiveWriter
from infrastructure.storage.filesystem import LocalFileSystemStorageClient


class _StubConfigRepository:
    def __init__(self, worm_root: Path) -> None:
        self._worm_root = worm_root

    def load(self, name: str, *, environment: str) -> dict[str, object]:  # noqa: ARG002
        if name != "storage":
            raise KeyError(name)
        return {"storage": {"worm_root": str(self._worm_root)}}


def test_worm_archive_makes_readonly_file(tmp_path: Path) -> None:
    worm_root = tmp_path / "worm"
    repository = _StubConfigRepository(worm_root)
    resolver = StoragePathResolver(config_repository=repository, environment="dev")
    writer = WormArchiveWriter(
        storage_client=LocalFileSystemStorageClient(),
        path_resolver=resolver,
    )

    result = writer.append(
        "audit",
        {
            "actor": "unit-test",
            "action": "deployed",
        },
    )

    assert result.path.exists()
    stat = os.stat(result.path)
    assert oct(stat.st_mode & 0o777) == "0o444"

    # 書き換えを試みると PermissionError になる
    with pytest.raises(PermissionError):
        result.path.write_text("mutate", encoding="utf-8")

