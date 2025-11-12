"""
バックテストおよびストレス評価サービスの定義。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

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
    ) -> Mapping[str, float]:
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

