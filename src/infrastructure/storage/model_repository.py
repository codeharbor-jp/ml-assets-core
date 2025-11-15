"""
モデルアーティファクトを `models_root` 配下に配布し、チェックサムを管理するコンポーネント。
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence

from .checksum import ChecksumCalculator
from .path_resolver import StoragePathResolver
from .storage_client import ObjectStorageClient, StorageError


@dataclass(frozen=True)
class ModelDistributionResult:
    model_version: str
    destination: Path
    checksums: Mapping[str, str]
    metadata_path: Path


class ModelArtifactDistributor:
    """
    学習済みモデルや θ パラメータを models_root にコピーし、チェックサムを JSON に記録する。
    既存のモデルバージョンが存在する場合は上書きする前にフォルダをクリアする。
    """

    def __init__(
        self,
        *,
        storage_client: ObjectStorageClient,
        path_resolver: StoragePathResolver,
        checksum_calculator: ChecksumCalculator | None = None,
    ) -> None:
        self._storage = storage_client
        self._path_resolver = path_resolver
        self._checksum = checksum_calculator or ChecksumCalculator()

    def distribute(
        self,
        *,
        model_version: str,
        artifacts: Mapping[str, Path],
        metadata: Mapping[str, object] | None = None,
    ) -> ModelDistributionResult:
        if not model_version:
            raise ValueError("model_version は必須です。")
        if not artifacts:
            raise ValueError("配布する artifacts が指定されていません。")

        destination_root = self._resolve_models_root() / model_version
        self._storage.makedirs(destination_root)
        self._cleanup_existing(destination_root, artifacts.keys())

        checksums: MutableMapping[str, str] = {}
        for logical_name, source_path in artifacts.items():
            if not isinstance(source_path, Path):
                raise TypeError(f"artifact '{logical_name}' のパスが Path 型ではありません。")
            if not source_path.exists():
                raise StorageError(f"アーティファクトファイルが存在しません: {source_path}")
            target_path = destination_root / f"{logical_name}{source_path.suffix}"
            self._copy_file(source_path, target_path)
            checksums[str(target_path.name)] = self._checksum.from_path(target_path)

        metadata_payload = {
            "model_version": model_version,
            "artifacts": list(checksums.keys()),
            "checksums": checksums,
            "metadata": metadata or {},
        }
        metadata_path = destination_root / "checksums.json"
        with self._storage.open_write(metadata_path) as handle:
            handle.write(json.dumps(metadata_payload, ensure_ascii=False, indent=2).encode("utf-8"))

        return ModelDistributionResult(
            model_version=model_version,
            destination=destination_root,
            checksums=checksums,
            metadata_path=metadata_path,
        )

    def verify(self, *, model_version: str) -> Mapping[str, str]:
        """
        `checksums.json` を読み込み、全ファイルのハッシュが一致するか確認する。
        """

        destination_root = self._resolve_models_root() / model_version
        metadata_path = destination_root / "checksums.json"
        if not metadata_path.exists():
            raise StorageError(f"checksums.json が存在しません: {metadata_path}")
        with metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        expected_checksums = payload.get("checksums")
        if not isinstance(expected_checksums, Mapping):
            raise StorageError(f"checksums.json の形式が不正です: {metadata_path}")

        mismatches: MutableMapping[str, str] = {}
        for filename, expected in expected_checksums.items():
            target = destination_root / filename
            if not target.exists():
                mismatches[filename] = "missing"
                continue
            actual = self._checksum.from_path(target)
            if actual != expected:
                mismatches[filename] = actual

        if mismatches:
            raise StorageError(f"チェックサム検証に失敗しました: {mismatches}")
        return expected_checksums

    def list_versions(self) -> Sequence[str]:
        models_root = self._resolve_models_root()
        entries = self._storage.listdir(models_root)
        return sorted(path.name for path in entries if path.is_dir())

    def _copy_file(self, source: Path, destination: Path) -> None:
        with source.open("rb") as src, self._storage.open_write(destination) as dst:
            shutil.copyfileobj(src, dst)

    def _resolve_models_root(self) -> Path:
        return self._path_resolver.resolve("models_root")

    def _cleanup_existing(self, destination: Path, logical_names: Sequence[str]) -> None:
        existing_files = self._storage.listdir(destination)
        valid_prefixes = {name for name in logical_names}
        for file_path in existing_files:
            if file_path.is_file():
                stem = file_path.stem
                if stem in valid_prefixes or file_path.name == "checksums.json":
                    self._storage.remove(file_path)

