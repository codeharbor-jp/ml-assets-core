"""
監査ログなどを WORM (Write Once Read Many) ストレージへ書き出すコンポーネント。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from uuid import uuid4

from .path_resolver import StoragePathResolver
from .storage_client import ObjectStorageClient, StorageError


@dataclass(frozen=True)
class WormAppendResult:
    record_type: str
    path: Path
    bytes_written: int


class WormArchiveWriter:
    """
    `worm_root/<record_type>/<YYYY>/<YYYYMM>/<timestamp>_<uuid>.json` 形式でファイルを作成し、
    書き込み後に読み取り専用に設定する。
    """

    def __init__(
        self,
        *,
        storage_client: ObjectStorageClient,
        path_resolver: StoragePathResolver,
    ) -> None:
        self._storage = storage_client
        self._path_resolver = path_resolver

    def append(self, record_type: str, payload: Mapping[str, object]) -> WormAppendResult:
        if not record_type:
            raise ValueError("record_type は必須です。")
        if not isinstance(payload, Mapping):
            raise TypeError("payload は Mapping である必要があります。")

        worm_root = self._resolve_worm_root()
        timestamp = datetime.now(timezone.utc)
        directory = self._build_directory(worm_root, record_type, timestamp)
        self._storage.makedirs(directory)

        filename = self._build_filename(record_type, timestamp)
        destination = directory / filename

        encoded = json.dumps(
            {
                "record_type": record_type,
                "created_at": timestamp.isoformat(),
                "payload": payload,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        with self._storage.open_write(destination) as handle:
            handle.write(encoded)

        try:
            os.chmod(destination, 0o444)
        except OSError as exc:  # pragma: no cover - 一部ファイルシステムで許可されない場合
            raise StorageError(f"WORM アーカイブのパーミッション変更に失敗しました: {destination}") from exc

        return WormAppendResult(record_type=record_type, path=destination, bytes_written=len(encoded))

    def _resolve_worm_root(self) -> Path:
        return self._path_resolver.resolve("worm_root")

    def _build_directory(self, root: Path, record_type: str, timestamp: datetime) -> Path:
        year = f"{timestamp.year:04d}"
        month = f"{timestamp.year:04d}{timestamp.month:02d}"
        return root / record_type / year / month

    def _build_filename(self, record_type: str, timestamp: datetime) -> str:
        suffix = timestamp.strftime("%Y%m%dT%H%M%S%f")[:-3]
        return f"{record_type}_{suffix}_{uuid4().hex}.json"

