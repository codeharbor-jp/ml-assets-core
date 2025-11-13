from datetime import datetime, timezone
from typing import Mapping

from application.services.dataset_catalog_builder import (
    DataQualityEvaluator,
    DatasetCatalogBuilder,
    DatasetCatalogReport,
    MetadataLoader,
    ThresholdDataQualityEvaluator,
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


def make_partition(
    symbol: str,
    *,
    quarantine: bool = False,
    missing: int = 5,
    outliers: int = 0,
    spikes: int = 0,
) -> DatasetPartition:
    return DatasetPartition(
        timeframe="1h",
        symbol=symbol,
        year=2024,
        month=1,
        last_timestamp=datetime(2024, 1, 31, 23, tzinfo=timezone.utc),
        bars_written=100,
        missing_gaps=0 if quarantine else missing,
        outlier_bars=outliers,
        spike_flags=spikes,
        quarantine_flag=quarantine,
        data_hash="abc123",
    )


def test_dataset_catalog_filters_quarantine_partitions() -> None:
    partitions = [make_partition("EURUSD"), make_partition("USDJPY", quarantine=True)]
    builder = DatasetCatalogBuilder(DummyMetadataLoader(), DummyEvaluator())
    catalog = builder.build(partitions, thresholds={"missing": 0.1, "outlier": 0.1, "spike": 0.1})

    assert len(catalog.entries) == 2
    assert len(catalog.filtered_entries) == 1
    assert catalog.filtered_entries[0].partition.symbol == "EURUSD"


def test_build_with_report_generates_dataset_index() -> None:
    partitions = [
        make_partition("EURUSD", missing=5),
        make_partition("GBPUSD", missing=15),
        make_partition("USDJPY", quarantine=True),
    ]
    builder = DatasetCatalogBuilder(DummyMetadataLoader(), ThresholdDataQualityEvaluator())
    thresholds = {"missing": 0.1, "outlier": 0.1, "spike": 0.1}

    catalog, report = builder.build_with_report(partitions, thresholds=thresholds)

    assert isinstance(report, DatasetCatalogReport)
    assert catalog.generated_at == report.generated_at
    assert report.totals["total"] == 3
    assert report.totals["filtered"] == 1  # GBPUSD exceeds threshold, USDJPY quarantined
    record = next(rec for rec in report.records if rec["symbol"] == "GBPUSD")
    assert record["dq_flag"] == DataQualityFlag.MISSING.value
    report_dict = report.to_dict()
    assert "records" in report_dict and "filtered_records" in report_dict
    assert report_dict["totals"]["quarantine"] == 1

