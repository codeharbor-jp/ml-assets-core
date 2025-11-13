"""
データカタログ生成のスケルトン。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Protocol, Sequence

from domain import DataQualityFlag, DataQualitySnapshot, DatasetPartition


class MetadataLoader(Protocol):
    """
    パーティション付随のメタ情報を読み込む。
    """

    def load_snapshot(self, partition: DatasetPartition) -> DataQualitySnapshot:
        ...

    def load_metadata(self, partition: DatasetPartition) -> Mapping[str, str]:
        ...


class DataQualityEvaluator(Protocol):
    """
    DataQualitySnapshot から判定フラグを評価する。
    """

    def evaluate(self, snapshot: DataQualitySnapshot, thresholds: Mapping[str, float]) -> DataQualityFlag:
        ...


class ThresholdDataQualityEvaluator(DataQualityEvaluator):
    """
    DataQualitySnapshot.evaluate を用いて閾値ベースの判定を行うデフォルト実装。
    """

    REQUIRED_KEYS = ("missing", "outlier", "spike")

    def evaluate(self, snapshot: DataQualitySnapshot, thresholds: Mapping[str, float]) -> DataQualityFlag:
        for key in self.REQUIRED_KEYS:
            if key not in thresholds:
                raise KeyError(f"thresholds に '{key}' が定義されていません。")
        return snapshot.evaluate(
            missing_threshold=thresholds["missing"],
            outlier_threshold=thresholds["outlier"],
            spike_threshold=thresholds["spike"],
        )


@dataclass(frozen=True)
class DatasetCatalogEntry:
    """
    データカタログの1エントリ。
    """

    partition: DatasetPartition
    dq_snapshot: DataQualitySnapshot
    dq_flag: DataQualityFlag
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatasetCatalog:
    """
    カタログ全体とフィルタ済み結果。
    """

    generated_at: datetime
    entries: Sequence[DatasetCatalogEntry]
    filtered_entries: Sequence[DatasetCatalogEntry]
    thresholds: Mapping[str, float]


@dataclass(frozen=True)
class DatasetCatalogReport:
    """
    dataset_index / dataset_index_filtered の出力に相当するレポート。
    """

    generated_at: datetime
    thresholds: Mapping[str, float]
    records: Sequence[Mapping[str, object]]
    filtered_records: Sequence[Mapping[str, object]]
    totals: Mapping[str, int]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "thresholds": dict(self.thresholds),
            "totals": dict(self.totals),
            "records": [dict(record) for record in self.records],
            "filtered_records": [dict(record) for record in self.filtered_records],
        }

    @staticmethod
    def from_catalog(catalog: DatasetCatalog) -> "DatasetCatalogReport":
        records = [_entry_to_record(entry) for entry in catalog.entries]
        filtered = [_entry_to_record(entry) for entry in catalog.filtered_entries]
        totals = {
            "total": len(records),
            "filtered": len(filtered),
            "quarantine": sum(1 for entry in catalog.entries if entry.dq_flag == DataQualityFlag.QUARANTINE),
            "warnings": sum(1 for entry in catalog.entries if entry.dq_flag == DataQualityFlag.WARNING),
        }
        return DatasetCatalogReport(
            generated_at=catalog.generated_at,
            thresholds=catalog.thresholds,
            records=records,
            filtered_records=filtered,
            totals=totals,
        )


def _entry_to_record(entry: DatasetCatalogEntry) -> Mapping[str, object]:
    partition = entry.partition
    snapshot = entry.dq_snapshot
    return {
        "timeframe": partition.timeframe,
        "symbol": partition.symbol,
        "year": partition.year,
        "month": partition.month,
        "last_timestamp": partition.last_timestamp.isoformat(),
        "bars_written": snapshot.bars_written,
        "missing_gaps": snapshot.missing_gaps,
        "outlier_bars": snapshot.outlier_bars,
        "spike_flags": snapshot.spike_flags,
        "quarantined": snapshot.quarantined,
        "data_hash": partition.data_hash,
        "dq_flag": entry.dq_flag.value,
        "metadata": dict(entry.metadata),
    }


class DatasetCatalogBuilder:
    """
    パーティション情報からカタログおよびレポートを生成する。
    """

    def __init__(self, metadata_loader: MetadataLoader, dq_evaluator: DataQualityEvaluator) -> None:
        self._metadata_loader = metadata_loader
        self._dq_evaluator = dq_evaluator

    def build(
        self,
        partitions: Sequence[DatasetPartition],
        *,
        thresholds: Mapping[str, float],
    ) -> DatasetCatalog:
        entries: list[DatasetCatalogEntry] = []
        filtered: list[DatasetCatalogEntry] = []

        for partition in partitions:
            snapshot = self._metadata_loader.load_snapshot(partition)
            dq_flag = self._dq_evaluator.evaluate(snapshot, thresholds)
            metadata = self._metadata_loader.load_metadata(partition)
            entry = DatasetCatalogEntry(
                partition=partition,
                dq_snapshot=snapshot,
                dq_flag=dq_flag,
                metadata=metadata,
            )
            entries.append(entry)
            if dq_flag in (DataQualityFlag.OK, DataQualityFlag.WARNING):
                filtered.append(entry)

        return DatasetCatalog(
            generated_at=datetime.now(timezone.utc),
            entries=entries,
            filtered_entries=filtered,
            thresholds=thresholds,
        )

    def build_with_report(
        self,
        partitions: Sequence[DatasetPartition],
        *,
        thresholds: Mapping[str, float],
    ) -> tuple[DatasetCatalog, DatasetCatalogReport]:
        catalog = self.build(partitions, thresholds=thresholds)
        report = DatasetCatalogReport.from_catalog(catalog)
        return catalog, report

