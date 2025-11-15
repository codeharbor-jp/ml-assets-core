"""
ローカルファイルシステムを ObjectStorageClient として扱う実装。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .storage_client import ObjectStorageClient, StorageError


class LocalFileSystemStorageClient(ObjectStorageClient):
    """
    開発環境やユニットテストで利用するローカルストレージクライアント。
    """

    def exists(self, path: Path) -> bool:
        return Path(path).exists()

    def open_read(self, path: Path) -> BinaryIO:
        resolved = Path(path)
        if not resolved.exists():
            raise StorageError(f"ファイルが存在しません: {resolved}")
        return resolved.open("rb")

    def open_write(self, path: Path) -> BinaryIO:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved.open("wb")

    def listdir(self, path: Path) -> list[Path]:
        resolved = Path(path)
        if not resolved.exists():
            return []
        return sorted(resolved.iterdir())

    def remove(self, path: Path) -> None:
        resolved = Path(path)
        if resolved.exists():
            resolved.unlink()

    def makedirs(self, path: Path) -> None:
        Path(path).mkdir(parents=True, exist_ok=True)

