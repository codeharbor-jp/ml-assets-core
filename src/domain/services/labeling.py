"""
ルールベースのラベリングサービス実装。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Iterable, Mapping, Sequence, cast

from ..value_objects import CalibrationMetrics
from .interfaces import LabelingInput, LabelingOutput, LabelingService


@dataclass(frozen=True)
class LabelingConfig:
    """
    ラベリングルールの閾値設定。
    """

    ai1_entry_threshold: float = 2.0
    ai1_exit_threshold: float = 0.5
    ai1_lookahead: int = 48
    speed_limit: float = 0.12
    ai2_rho_var_limit: float = 0.025
    ai2_atr_ratio_limit: float = 1.8
    ai2_drawdown_limit: float = 0.07


class RuleBasedLabelingService(LabelingService):
    """
    要件仕様の閾値に基づいたラベリング実装。
    """

    REQUIRED_KEYS = {
        "z",
        "delta_z_ema",
        "rho_var_180",
        "atr_ratio",
        "drawdown_recent",
    }

    def __init__(self, config: LabelingConfig | None = None) -> None:
        self._config = config or LabelingConfig()

    def generate(self, request: LabelingInput) -> LabelingOutput:
        numeric_features: list[dict[str, float]] = []
        raw_features_iter = cast(Iterable[Mapping[str, object]], request.features)
        for feature in raw_features_iter:
            missing = self.REQUIRED_KEYS - feature.keys()
            if missing:
                missing_keys = ", ".join(sorted(missing))
                raise KeyError(f"特徴量に必要なキーが不足しています: {missing_keys}")
            numeric_entry: dict[str, float] = {}
            for key in self.REQUIRED_KEYS:
                numeric_entry[key] = _as_float(feature[key], key)
            numeric_features.append(numeric_entry)

        ai1_labels = self._generate_ai1_labels(numeric_features)
        ai2_labels = self._generate_ai2_labels(numeric_features)
        ai3_targets = self._generate_ai3_targets(ai1_labels, ai2_labels)
        metrics = self._build_calibration_metrics(ai1_labels)

        return LabelingOutput(
            ai1_labels=ai1_labels,
            ai2_labels=ai2_labels,
            ai3_targets=ai3_targets,
            calibration_metrics=metrics,
        )

    def _generate_ai1_labels(self, features: Sequence[Mapping[str, float]]) -> list[int]:
        cfg = self._config
        n = len(features)
        labels = [0] * n
        for idx, feature in enumerate(features):
            z_value = feature["z"]
            speed = abs(feature["delta_z_ema"])
            if abs(z_value) < cfg.ai1_entry_threshold or speed > cfg.speed_limit:
                continue

            horizon = min(n, idx + cfg.ai1_lookahead + 1)
            for future_idx in range(idx + 1, horizon):
                if abs(features[future_idx]["z"]) <= cfg.ai1_exit_threshold:
                    labels[idx] = 1
                    break
        return labels

    def _generate_ai2_labels(self, features: Sequence[Mapping[str, float]]) -> list[int]:
        cfg = self._config
        labels: list[int] = []
        for feature in features:
            rho_var = feature["rho_var_180"]
            atr_ratio = feature["atr_ratio"]
            delta_speed = abs(feature["delta_z_ema"])
            drawdown = feature["drawdown_recent"]

            flag = (
                rho_var > cfg.ai2_rho_var_limit
                or atr_ratio > cfg.ai2_atr_ratio_limit
                or delta_speed > cfg.speed_limit
                or drawdown > cfg.ai2_drawdown_limit
            )
            labels.append(1 if flag else 0)
        return labels

    def _generate_ai3_targets(self, ai1: Sequence[int], ai2: Sequence[int]) -> list[float]:
        """
        AI3（スケール）はリスク寄与度を参考に 0〜1 のスコアを生成する。
        現状はシンプルに「AI1 と AI2 の平均リスク」を 1 から引いた値を利用する。
        """

        targets: list[float] = []
        for label_ai1, label_ai2 in zip(ai1, ai2, strict=True):
            risk_factor = (label_ai1 + label_ai2) / 2.0
            target = max(0.0, min(1.0, 1.0 - risk_factor))
            targets.append(target)
        return targets

    def _build_calibration_metrics(self, ai1_labels: Sequence[int]) -> CalibrationMetrics:
        sample_size = len(ai1_labels)
        if sample_size == 0:
            return CalibrationMetrics(
                brier_score=0.0,
                expected_calibration_error=0.0,
                maximum_calibration_error=0.0,
                log_loss=0.0,
                sample_size=0,
            )

        positive_rate = sum(ai1_labels) / sample_size
        epsilon = 1e-6
        brier_score = positive_rate * (1.0 - positive_rate)
        log_loss = -(positive_rate * log(max(positive_rate, epsilon)) + (1.0 - positive_rate) * log(max(1.0 - positive_rate, epsilon)))

        return CalibrationMetrics(
            brier_score=brier_score,
            expected_calibration_error=0.0,
            maximum_calibration_error=0.0,
            log_loss=log_loss,
            sample_size=sample_size,
        )


def _as_float(value: object, key: str) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:  # pragma: no cover - 異常系
        raise ValueError(f"特徴量 {key} を float に変換できません。") from exc

