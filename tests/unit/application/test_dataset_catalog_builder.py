from datetime import datetime, timezone
from typing import Mapping

from application.services.dataset_catalog_builder import (
    DataQualityEvaluator,
    DatasetCatalogBuilder,
    MetadataLoader,
)
from domain import DataQualityFlag, DataQualitySnapshot, DatasetPartition


class DummyMetadataLoader(MetadataLoader):
    def load_snapshot(self, partition: DatasetPartition) -> DataQualitySnapshot:
        return DataQualitySnapshot(
            bars_written=partition.bars_written,
            missing_gaps=partition.missing_gaps,
            outlier_bars=partition.outlier_bars,
            spike_flags=partition.spike_flags,
            quarantined=partition.quarantine_flag,
        )

    def load_metadata(self, partition: DatasetPartition) -> Mapping[str, str]:
        return {"symbol": partition.symbol}


class DummyEvaluator(DataQualityEvaluator):
    def evaluate(self, snapshot: DataQualitySnapshot, thresholds: Mapping[str, float]) -> DataQualityFlag:
        if snapshot.quarantined:
            return DataQualityFlag.QUARANTINE
        if snapshot.missing_rate() > thresholds["missing"]:
            return DataQualityFlag.MISSING
        return DataQualityFlag.OK


def make_partition(symbol: str, quarantine: bool = False) -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol=symbol,
        year=2024,
        month=1,
        last_timestamp=datetime(2024, 1, 31, 23, tzinfo=timezone.utc),
        bars_written=100,
        missing_gaps=5 if not quarantine else 0,
        outlier_bars=0,
        spike_flags=0,
        quarantine_flag=quarantine,
        data_hash="abc123",
    )


def test_dataset_catalog_filters_quarantine_partitions() -> None:
    partitions = [make_partition("EURUSD"), make_partition("USDJPY", quarantine=True)]
    builder = DatasetCatalogBuilder(DummyMetadataLoader(), DummyEvaluator())
    catalog = builder.build(partitions, thresholds={"missing": 0.1})

    assert len(catalog.entries) == 2
    assert len(catalog.filtered_entries) == 1
    assert catalog.filtered_entries[0].partition.symbol == "EURUSD"

