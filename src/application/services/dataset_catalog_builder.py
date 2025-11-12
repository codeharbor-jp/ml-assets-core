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


class DatasetCatalogBuilder:
    """
    パーティション情報からカタログを生成する。
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

