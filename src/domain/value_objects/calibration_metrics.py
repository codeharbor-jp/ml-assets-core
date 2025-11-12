"""
キャリブレーション指標の値オブジェクト。
"""

from __future__ import annotations

from dataclasses import dataclass


def _validate_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} は 0 以上である必要があります。")


@dataclass(frozen=True)
class CalibrationMetrics:
    """
    推論確率のキャリブレーション品質を表す指標群。

    Attributes:
        brier_score: Brier score（0 以上）。
        expected_calibration_error: Expected Calibration Error（0 以上）。
        maximum_calibration_error: 最大キャリブレーション誤差（0 以上）。
        log_loss: 負対数尤度（0 以上）。
        sample_size: 評価に用いたサンプル数。
    """

    brier_score: float
    expected_calibration_error: float
    maximum_calibration_error: float
    log_loss: float
    sample_size: int

    def __post_init__(self) -> None:
        _validate_non_negative(self.brier_score, "brier_score")
        _validate_non_negative(self.expected_calibration_error, "expected_calibration_error")
        _validate_non_negative(self.maximum_calibration_error, "maximum_calibration_error")
        _validate_non_negative(self.log_loss, "log_loss")
        if self.sample_size <= 0:
            raise ValueError("sample_size は 1 以上である必要があります。")

    def is_within_thresholds(
        self,
        *,
        brier_limit: float,
        ece_limit: float,
        max_ce_limit: float,
    ) -> bool:
        """
        設定された閾値内に収まっているか判定する。
        """

        for name, value in [
            ("brier_limit", brier_limit),
            ("ece_limit", ece_limit),
            ("max_ce_limit", max_ce_limit),
        ]:
            if value < 0:
                raise ValueError(f"{name} は 0 以上である必要があります。")

        return (
            self.brier_score <= brier_limit
            and self.expected_calibration_error <= ece_limit
            and self.maximum_calibration_error <= max_ce_limit
        )

