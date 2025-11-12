"""
データ品質関連の値オブジェクト。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataQualityFlag(str, Enum):
    """
    データ品質フラグの列挙。
    """

    OK = "ok"
    MISSING = "missing"
    OUTLIER = "outlier"
    CONFLICT = "conflict"
    QUARANTINE = "quarantine"
    WARNING = "warning"


@dataclass(frozen=True)
class DataQualitySnapshot:
    """
    パーティションごとの品質指標を保持する値オブジェクト。

    Attributes:
        bars_written: 書き込まれたバー数。
        missing_gaps: 欠損ギャップ数。
        outlier_bars: 外れ値バー数。
        spike_flags: スパイク検知数。
        quarantined: 隔離対象かどうか。
    """

    bars_written: int
    missing_gaps: int
    outlier_bars: int
    spike_flags: int
    quarantined: bool

    def __post_init__(self) -> None:
        for name in ("bars_written", "missing_gaps", "outlier_bars", "spike_flags"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} は 0 以上である必要があります。")
        if self.bars_written == 0:
            raise ValueError("bars_written は 1 以上である必要があります。")

    def missing_rate(self) -> float:
        return self.missing_gaps / self.bars_written

    def outlier_rate(self) -> float:
        return self.outlier_bars / self.bars_written

    def spike_rate(self) -> float:
        return self.spike_flags / self.bars_written

    def evaluate(
        self,
        *,
        missing_threshold: float,
        outlier_threshold: float,
        spike_threshold: float,
    ) -> DataQualityFlag:
        """
        閾値に基づき品質フラグを判定する。
        """

        for name, value in [
            ("missing_threshold", missing_threshold),
            ("outlier_threshold", outlier_threshold),
            ("spike_threshold", spike_threshold),
        ]:
            if value < 0:
                raise ValueError(f"{name} は 0 以上である必要があります。")

        if self.quarantined:
            return DataQualityFlag.QUARANTINE
        if self.missing_rate() > missing_threshold:
            return DataQualityFlag.MISSING
        if self.outlier_rate() > outlier_threshold:
            return DataQualityFlag.OUTLIER
        if self.spike_rate() > spike_threshold:
            return DataQualityFlag.WARNING
        return DataQualityFlag.OK

