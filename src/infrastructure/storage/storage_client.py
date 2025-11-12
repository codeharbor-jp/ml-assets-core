"""
オブジェクトストレージ/NAS への抽象クライアント。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol


class StorageError(RuntimeError):
    """ストレージ操作に関する例外。"""


class ObjectStorageClient(Protocol):
    """
    オブジェクトストレージの基本操作を定義。
    """

    def exists(self, path: Path) -> bool:
        ...

    def open_read(self, path: Path) -> BinaryIO:
        ...

    def open_write(self, path: Path) -> BinaryIO:
        ...

    def listdir(self, path: Path) -> list[Path]:
        ...

    def remove(self, path: Path) -> None:
        ...

    def makedirs(self, path: Path) -> None:
        ...

