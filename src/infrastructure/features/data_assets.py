"""
data-assets-pipeline からの出力を利用した特徴量生成・キャッシュ管理。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence, cast

from domain import DatasetPartition

from application.services.feature_builder import FeatureCache, FeatureGenerator, FeatureVector

from ..storage.filesystem import LocalFileSystemStorageClient
from ..storage.json_parquet import JsonParquetReader, JsonParquetWriter
from ..storage.path_resolver import StoragePathResolver, StoragePathError
from ..storage.storage_client import ObjectStorageClient, StorageError


def _partition_directory(root: Path, partition: DatasetPartition) -> Path:
    return (
        Path(root)
        / partition.timeframe
        / partition.symbol
        / f"{partition.year:04d}-{partition.month:02d}"
    )


class DataAssetsFeatureGenerator(FeatureGenerator):
    """
    data-assets-pipeline が生成するカノニカルデータを元に簡易特徴量を構築する。

    実運用では専用の特徴量定義を読み込み高度な処理を行うことを想定しているが、
    現段階では再現性の高い最小構成として `close` とリターン、出来高を出力する。
    """

    def __init__(
        self,
        *,
        path_resolver: StoragePathResolver,
        storage_client: ObjectStorageClient | None = None,
        parquet_reader: JsonParquetReader | None = None,
        canonical_filename: str = "canonical.json",
    ) -> None:
        self._path_resolver = path_resolver
        self._storage = storage_client or LocalFileSystemStorageClient()
        self._reader = parquet_reader or JsonParquetReader()
        self._canonical_filename = canonical_filename

        self._canonical_root = self._resolve_or_raise("canonical_root")

    def generate(
        self,
        *,
        partition: DatasetPartition,
        feature_spec: Mapping[str, str],
        preprocessing: Mapping[str, str],
    ) -> Iterable[FeatureVector]:
        canonical_path = (
            _partition_directory(self._canonical_root, partition) / self._canonical_filename
        )
        if not self._storage.exists(canonical_path):
            raise StorageError(f"カノニカルデータが存在しません: {canonical_path}")

        canonical_rows = self._reader.read(canonical_path)
        feature_rows: list[dict[str, float]] = []
        previous_close: float | None = None
        ema_delta: float = 0.0
        peak_close: float | None = None

        for row in canonical_rows:
            timestamp = row.get("timestamp")
            if timestamp is None:
                raise StorageError(f"canonical 行に timestamp が存在しません: {canonical_path}")

            close_raw = row.get("close")
            if close_raw is None:
                raise StorageError("canonical 行に close が存在しません。")
            try:
                close_value = float(str(close_raw))
            except (TypeError, ValueError):
                raise StorageError("canonical 行の close を float に変換できません。")  # noqa: TRY003

            volume_raw = row.get("volume", 0.0)
            try:
                volume_value = float(str(volume_raw))
            except (TypeError, ValueError):
                raise StorageError("canonical 行の volume を float に変換できません。")  # noqa: TRY003

            if previous_close is None:
                ret = 0.0
            else:
                ret = close_value - previous_close
            previous_close = close_value

            ema_delta = 0.2 * ret + 0.8 * ema_delta

            if peak_close is None or close_value > peak_close:
                peak_close = close_value
            assert peak_close is not None  # for type checker
            drawdown = (peak_close - close_value) / peak_close if peak_close > 0 else 0.0

            rho_var = (ret ** 2) if ret else 0.0
            atr_ratio = 1.0 + abs(ret)

            feature_row = {
                "close": close_value,
                "return": ret,
                "volume": volume_value,
                "z": ret,
                "delta_z_ema": ema_delta,
                "rho_var_180": abs(rho_var),
                "atr_ratio": atr_ratio,
                "drawdown_recent": drawdown,
            }

            feature_rows.append(feature_row)

        return tuple(feature_rows)

    def _resolve_or_raise(self, key: str) -> Path:
        try:
            return self._path_resolver.resolve(key)
        except StoragePathError as exc:
            raise StorageError(f"storage 設定から '{key}' を解決できません。") from exc


@dataclass
class FeatureSchemaArtifacts:
    schema_path: Path
    report_path: Path


class DataAssetsFeatureCache(FeatureCache):
    """
    特徴量キャッシュを `features_root` 配下に書き出す実装。
    """

    def __init__(
        self,
        *,
        path_resolver: StoragePathResolver,
        storage_client: ObjectStorageClient | None = None,
        parquet_reader: JsonParquetReader | None = None,
        parquet_writer: JsonParquetWriter | None = None,
        schema_filename: str = "feature_schema.json",
        preprocess_report_filename: str = "preprocess_report.json",
    ) -> None:
        self._path_resolver = path_resolver
        self._storage = storage_client or LocalFileSystemStorageClient()
        self._reader = parquet_reader or JsonParquetReader()
        self._writer = parquet_writer or JsonParquetWriter()
        self._schema_filename = schema_filename
        self._preprocess_report_filename = preprocess_report_filename

        self._features_root = self._resolve_or_raise("features_root")

    def exists(self, *, partition: DatasetPartition, feature_hash: str) -> bool:
        return self._storage.exists(self._feature_path(partition, feature_hash))

    def load(self, *, partition: DatasetPartition, feature_hash: str) -> Iterable[FeatureVector]:
        path = self._feature_path(partition, feature_hash)
        if not self._storage.exists(path):
            raise StorageError(f"特徴量キャッシュが存在しません: {path}")
        return cast(Iterable[FeatureVector], self._reader.read(path))

    def store(
        self,
        *,
        partition: DatasetPartition,
        feature_hash: str,
        features: Iterable[FeatureVector],
        schema_hash: str,
    ) -> None:
        feature_list: list[dict[str, float]] = [dict(item) for item in features]
        feature_path = self._feature_path(partition, feature_hash)
        directory = feature_path.parent
        self._storage.makedirs(directory)
        self._writer.write(feature_path, feature_list)

        artifacts = FeatureSchemaArtifacts(
            schema_path=directory / self._schema_filename,
            report_path=directory / self._preprocess_report_filename,
        )
        schema_document = _build_feature_schema(feature_list, schema_hash=schema_hash)
        preprocess_report = _build_preprocess_report(feature_list)

        with artifacts.schema_path.open("w", encoding="utf-8") as handle:
            json.dump(schema_document, handle, ensure_ascii=False, indent=2, sort_keys=True)

        with artifacts.report_path.open("w", encoding="utf-8") as handle:
            json.dump(preprocess_report, handle, ensure_ascii=False, indent=2, sort_keys=True)

    def invalidate(self, *, partition: DatasetPartition, reason: str) -> None:  # noqa: ARG002
        # 理由は監査ログに利用することを想定しているが、現段階ではファイル削除のみ実施。
        feature_dir = self._partition_dir(partition)
        if feature_dir.exists():
            for candidate in feature_dir.glob("*.parquet"):
                candidate.unlink()

    def _partition_dir(self, partition: DatasetPartition) -> Path:
        return _partition_directory(self._features_root, partition)

    def _feature_path(self, partition: DatasetPartition, feature_hash: str) -> Path:
        return self._partition_dir(partition) / f"{feature_hash}.parquet"

    def _resolve_or_raise(self, key: str) -> Path:
        try:
            return self._path_resolver.resolve(key)
        except StoragePathError as exc:
            raise StorageError(f"storage 設定から '{key}' を解決できません。") from exc


def _build_feature_schema(
    features: Sequence[FeatureVector],
    *,
    schema_hash: str,
) -> Mapping[str, object]:
    row_count = len(features)
    fields = _infer_fields(features)
    numeric_stats = _numeric_statistics(features)

    return {
        "schema_hash": schema_hash,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": row_count,
        "fields": fields,
        "numeric_stats": numeric_stats,
    }


def _build_preprocess_report(features: Sequence[FeatureVector]) -> Mapping[str, object]:
    numeric_stats = _numeric_statistics(features)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(features),
        "numeric_stats": numeric_stats,
    }


def _infer_fields(features: Sequence[FeatureVector]) -> list[Mapping[str, object]]:
    keys: set[str] = set()
    for row in features:
        keys.update(row.keys())

    field_documents: list[Mapping[str, object]] = []
    for key in sorted(keys):
        sample_value = next((row[key] for row in features if key in row), None)
        field_documents.append(
            {"name": key, "type": _infer_type(sample_value)}
        )
    return field_documents


def _numeric_statistics(features: Sequence[FeatureVector]) -> Mapping[str, Mapping[str, float]]:
    stats: dict[str, Mapping[str, float]] = {}
    numeric_keys = {
        key for row in features for key, value in row.items() if isinstance(value, (int, float))
    }
    for key in numeric_keys:
        values = [float(row[key]) for row in features if key in row]
        if not values:
            continue
        stats[key] = {
            "min": min(values),
            "max": max(values),
            "mean": mean(values),
        }
    return stats


def _infer_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "float"
    return "string"

