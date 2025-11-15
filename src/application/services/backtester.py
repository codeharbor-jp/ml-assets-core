"""
バックテストおよびストレス評価サービスの定義。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from prefect import get_run_logger

from application.observability import metrics_recorder, telemetry_span

from domain import ModelArtifact


class BacktestEngineClient(Protocol):
    """
    backtest-assets-engine とのインターフェース。
    """

    def run(
        self,
        *,
        model_artifact: ModelArtifact,
        params: Mapping[str, float],
        config: Mapping[str, str],
        stress_scenarios: Sequence["StressScenario"],
    ) -> Mapping[str, object]:
        ...


@dataclass(frozen=True)
class StressScenario:
    """
    ストレステストシナリオの定義。
    """

    name: str
    parameters: Mapping[str, float]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name は必須です。")


class StressEvaluator(Protocol):
    """
    Backtest 結果を用いてストレス評価を行うインターフェース。
    """

    def evaluate(
        self,
        *,
        base_metrics: Mapping[str, float],
        stress_metrics: Mapping[str, Mapping[str, float]],
    ) -> Mapping[str, float]:
        ...


@dataclass(frozen=True)
class BacktestRequest:
    """
    バックテスト実行の入力。
    """

    model_artifact: ModelArtifact
    params: Mapping[str, float]
    engine_config: Mapping[str, str]
    stress_scenarios: Sequence[StressScenario]
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResult:
    """
    バックテストの出力。
    """

    summary_metrics: Mapping[str, float]
    stress_metrics: Mapping[str, Mapping[str, float]]
    evaluation: Mapping[str, float]
    diagnostics: Mapping[str, float] = field(default_factory=dict)


class BacktesterService(Protocol):
    """
    バックテストとストレス評価を統括するサービス。
    """

    def run(self, request: BacktestRequest) -> BacktestResult:
        ...


class Backtester(BacktesterService):
    """
    backtest-assets-engine の結果を集約し、ストレス評価と診断情報を生成する実装。
    """

    def __init__(self, engine: BacktestEngineClient, stress_evaluator: StressEvaluator) -> None:
        self._engine = engine
        self._stress_evaluator = stress_evaluator

    def run(self, request: BacktestRequest) -> BacktestResult:
        with telemetry_span(
            "backtester.run",
            {"model_version": request.model_artifact.model_version},
        ):
            start = time.perf_counter()
            try:
                logger = get_run_logger()
            except Exception:  # pragma: no cover - Prefect が無い環境では標準ロガーを利用
                logger = logging.getLogger("ml_assets_core.backtester")
            logger.info("Starting backtest for model_version=%s", request.model_artifact.model_version)

            response = self._engine.run(
                model_artifact=request.model_artifact,
                params=request.params,
                config=request.engine_config,
                stress_scenarios=request.stress_scenarios,
            )

            summary = _extract_mapping(response, "summary", fallback={})
            stress = _extract_nested_mapping(response, "stress", fallback={})
            diagnostics = _extract_mapping(response, "diagnostics", fallback={})

            evaluation = self._stress_evaluator.evaluate(
                base_metrics=summary,
                stress_metrics=stress,
            )

            diagnostics = {
                **diagnostics,
                "requested_scenarios": float(len(request.stress_scenarios)),
            }

            duration = time.perf_counter() - start
            metrics_recorder.observe_backtest_duration(
                request.model_artifact.model_version,
                duration_seconds=duration,
            )
            logger.info(
                "Backtest completed for model_version=%s in %.2f seconds",
                request.model_artifact.model_version,
                duration,
            )

            return BacktestResult(
                summary_metrics=summary,
                stress_metrics=stress,
                evaluation=evaluation,
                diagnostics=diagnostics,
            )


def _extract_mapping(
    response: Mapping[str, object],
    key: str,
    *,
    fallback: Mapping[str, float],
) -> Mapping[str, float]:
    value = response.get(key, fallback)
    if not isinstance(value, Mapping):
        return fallback
    result: dict[str, float] = {}
    for metric_key, metric_value in value.items():
        try:
            result[str(metric_key)] = _to_float(metric_value)
        except (TypeError, ValueError):
            continue
    return result if result else fallback


def _extract_nested_mapping(
    response: Mapping[str, object],
    key: str,
    *,
    fallback: Mapping[str, Mapping[str, float]],
) -> Mapping[str, Mapping[str, float]]:
    value = response.get(key, fallback)
    if not isinstance(value, Mapping):
        return fallback
    nested: dict[str, Mapping[str, float]] = {}
    for scenario, metrics in value.items():
        if isinstance(metrics, Mapping):
            parsed: dict[str, float] = {}
            for metric_key, metric_value in metrics.items():
                try:
                    parsed[str(metric_key)] = _to_float(metric_value)
                except (TypeError, ValueError):
                    continue
            nested[str(scenario)] = parsed
    return nested


def _to_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))

