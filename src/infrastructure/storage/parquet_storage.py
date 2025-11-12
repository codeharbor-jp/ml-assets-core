"""
Parquet データセットアクセスのスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .checksum import ChecksumCalculator
from .storage_client import ObjectStorageClient, StorageError


class ParquetReader(Protocol):
    def read(self, path: Path) -> Sequence[Mapping[str, object]]:
        ...


class ParquetWriter(Protocol):
    def write(self, path: Path, rows: Sequence[Mapping[str, object]]) -> None:
        ...


@dataclass
class ParquetDatasetStorage:
    """
    パーティション毎の Parquet データ読み書きを担当。
    """

    storage_client: ObjectStorageClient
    reader: ParquetReader
    writer: ParquetWriter
    checksum_calculator: ChecksumCalculator

    def load_partition(self, path: Path) -> Sequence[Mapping[str, object]]:
        if not self.storage_client.exists(path):
            raise StorageError(f"Parquet ファイルが存在しません: {path}")
        return self.reader.read(path)

    def save_partition(self, path: Path, rows: Sequence[Mapping[str, object]]) -> str:
        parent = path.parent
        self.storage_client.makedirs(parent)
        self.writer.write(path, rows)
        return self.checksum_calculator.from_path(path)

