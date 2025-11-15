from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

import pytest

from domain import DatasetPartition

from infrastructure.features.data_assets import (
    DataAssetsFeatureCache,
    DataAssetsFeatureGenerator,
    _numeric_statistics,
)
from infrastructure.storage.filesystem import LocalFileSystemStorageClient
from infrastructure.storage.path_resolver import StoragePathResolver
from infrastructure.storage.json_parquet import JsonParquetReader, JsonParquetWriter


class _StubConfigRepository:
    def __init__(self, base: Mapping[str, object]) -> None:
        self._base = base

    def load(self, name: str, *, environment: str) -> Mapping[str, object]:  # noqa: ARG002
        if name == "storage":
            return self._base
        raise KeyError(name)


def _make_partition() -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol="EURUSD",
        year=2024,
        month=1,
        last_timestamp=datetime(2024, 1, 31, 23, 0, 0, tzinfo=timezone.utc),
        bars_written=2,
        missing_gaps=0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=False,
        data_hash="hash123",
    )


def test_feature_generator_loads_canonical_and_builds_features(tmp_path: Path) -> None:
    canonical_root = tmp_path / "canonical"
    features_root = tmp_path / "features"
    snapshots_root = tmp_path / "snapshots"
    models_root = tmp_path / "models"

    partition = _make_partition()
    canonical_dir = canonical_root / "1h" / "EURUSD" / "2024-01"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    canonical_file = canonical_dir / "canonical.json"

    with canonical_file.open("w", encoding="utf-8") as handle:
        json.dump(
            [
                {"timestamp": "2024-01-01T00:00:00Z", "close": 1.0, "volume": 100},
                {"timestamp": "2024-01-01T01:00:00Z", "close": 1.1, "volume": 120},
            ],
            handle,
        )

    repository = _StubConfigRepository(
        {
            "storage": {
                "canonical_root": str(canonical_root),
                "features_root": str(features_root),
                "snapshots_root": str(snapshots_root),
                "models_root": str(models_root),
                "worm_root": str(tmp_path / "worm"),
                "backups_root": str(tmp_path / "backups"),
            }
        }
    )
    resolver = StoragePathResolver(config_repository=repository, environment="dev")
    generator = DataAssetsFeatureGenerator(path_resolver=resolver)

    features = list(generator.generate(partition=partition, feature_spec={}, preprocessing={}))

    assert len(features) == 2
    assert features[0]["close"] == 1.0
    assert features[1]["return"] == pytest.approx(0.0999999999, rel=1e-6)
    for row in features:
        for required_key in ("z", "delta_z_ema", "rho_var_180", "atr_ratio", "drawdown_recent"):
            assert required_key in row


def test_feature_cache_writes_schema_and_report(tmp_path: Path) -> None:
    storage_config = {
        "storage": {
            "canonical_root": str(tmp_path / "canonical"),
            "features_root": str(tmp_path / "features"),
            "snapshots_root": str(tmp_path / "snapshots"),
            "models_root": str(tmp_path / "models"),
            "worm_root": str(tmp_path / "worm"),
            "backups_root": str(tmp_path / "backups"),
        }
    }
    repository = _StubConfigRepository(storage_config)
    resolver = StoragePathResolver(config_repository=repository, environment="dev")

    cache = DataAssetsFeatureCache(
        path_resolver=resolver,
        storage_client=LocalFileSystemStorageClient(),
        parquet_reader=JsonParquetReader(),
        parquet_writer=JsonParquetWriter(),
    )
    partition = _make_partition()
    features = [
        {"close": 1.0, "return": 0.0, "z": 0.0, "delta_z_ema": 0.0, "rho_var_180": 0.0, "atr_ratio": 1.0, "drawdown_recent": 0.0},
        {"close": 1.1, "return": 0.1, "z": 0.1, "delta_z_ema": 0.02, "rho_var_180": 0.01, "atr_ratio": 1.1, "drawdown_recent": 0.0},
    ]

    cache.store(
        partition=partition,
        feature_hash="hash-abc",
        features=features,
        schema_hash="schema-hash",
    )

    stored_path = tmp_path / "features" / "1h" / "EURUSD" / "2024-01" / "hash-abc.parquet"
    assert stored_path.exists()

    schema_path = stored_path.parent / "feature_schema.json"
    report_path = stored_path.parent / "preprocess_report.json"
    assert schema_path.exists() and report_path.exists()

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["schema_hash"] == "schema-hash"
    assert schema["row_count"] == 2
    numeric = schema["numeric_stats"]
    assert numeric["close"]["max"] == pytest.approx(1.1)

    loaded = list(cache.load(partition=partition, feature_hash="hash-abc"))
    assert loaded[0]["close"] == 1.0

    cache.invalidate(partition=partition, reason="test")
    assert not stored_path.exists()


def test_numeric_statistics_handles_empty(tmp_path: Path) -> None:
    stats = _numeric_statistics([])
    assert stats == {}

