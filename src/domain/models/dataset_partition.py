"""
データセットパーティションのドメインエンティティ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DatasetPartition:
    """
    timeframe/symbol/月単位で管理されるデータパーティション情報。
    """

    timeframe: str
    symbol: str
    year: int
    month: int
    last_timestamp: datetime
    bars_written: int
    missing_gaps: int
    outlier_bars: int
    spike_flags: int
    quarantine_flag: bool
    data_hash: str

    def __post_init__(self) -> None:
        if not self.timeframe:
            raise ValueError("timeframe は必須です。")
        if not self.symbol:
            raise ValueError("symbol は必須です。")
        if not 1 <= self.month <= 12:
            raise ValueError("month は 1 から 12 の範囲で指定してください。")
        for field_name in ("bars_written", "missing_gaps", "outlier_bars", "spike_flags"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} は 0 以上である必要があります。")
        if self.bars_written == 0:
            raise ValueError("bars_written は 1 以上である必要があります。")
        if self.last_timestamp.year != self.year or self.last_timestamp.month != self.month:
            raise ValueError("last_timestamp が year/month と一致していません。")
        if not self.data_hash:
            raise ValueError("data_hash は必須です。")

