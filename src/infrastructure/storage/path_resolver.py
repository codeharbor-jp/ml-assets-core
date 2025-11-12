"""
設定に基づきストレージパスを解決するモジュール。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..configs import ConfigRepository


class StoragePathError(RuntimeError):
    """必要なストレージ設定が不足している。"""


@dataclass
class StoragePathResolver:
    """
    設定に基づいて canonical/features/snapshots 等のパスを解決する。
    """

    config_repository: ConfigRepository
    environment: str

    def resolve(self, key: str) -> Path:
        storage_config = self._load_storage_config()
        if key not in storage_config:
            raise StoragePathError(f"storage.yaml に '{key}' が定義されていません。")
        raw_path = storage_config[key]
        if not isinstance(raw_path, str) or not raw_path:
            raise StoragePathError(f"storage key '{key}' の値が不正です。")
        return Path(raw_path)

    def _load_storage_config(self) -> Mapping[str, object]:
        data = self.config_repository.load("storage", environment=self.environment)
        return data  # type: ignore[return-value]

