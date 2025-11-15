"""
backtest_policy.yaml の読み取りと整形ロジック。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

def _require_mapping(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} セクションが存在しないか形式が不正です。")
    return value


def _parse_datetime(value: object, *, field: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} は ISO8601 形式で指定してください。") from exc
    raise ValueError(f"{field} は ISO8601 文字列で指定してください。")


def _to_float(value: object, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} は数値で指定してください。") from exc


@dataclass(frozen=True)
class EvaluationThresholds:
    min_sharpe: float
    max_drawdown: float
    min_trades: float
    max_halt_rate: float


@dataclass(frozen=True)
class StressScenarioConfig:
    name: str
    parameters: Mapping[str, float]


@dataclass(frozen=True)
class EngineRunConfig:
    timeframe: str
    dataset_root: str
    period_start: datetime
    period_end: datetime
    cost_table_path: str
    universe_path: str
    output_root: str | None = None

    def to_mapping(self) -> Mapping[str, str]:
        return {
            "timeframe": self.timeframe,
            "dataset_root": self.dataset_root,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "cost_table_path": self.cost_table_path,
            "universe_path": self.universe_path,
            **({"output_root": self.output_root} if self.output_root else {}),
        }


@dataclass(frozen=True)
class BacktestPolicy:
    entry_rule: Mapping[str, float | bool]
    exit_rule: Mapping[str, float | bool]
    costs: Mapping[str, float]
    stress_scenarios: Sequence[StressScenarioConfig]
    evaluation: EvaluationThresholds
    engine: EngineRunConfig

    @staticmethod
    def from_mapping(mapping: Mapping[str, object]) -> "BacktestPolicy":
        entry_rule = dict(_require_mapping(_require_mapping(mapping, "entry_rule"), "value"))
        exit_rule = dict(_require_mapping(_require_mapping(mapping, "exit_rule"), "value"))
        costs = dict(_require_mapping(_require_mapping(mapping, "costs"), "value"))

        evaluation_mapping = _require_mapping(_require_mapping(mapping, "evaluation"), "value")
        evaluation = EvaluationThresholds(
            min_sharpe=_to_float(evaluation_mapping.get("min_sharpe"), field="evaluation.min_sharpe"),
            max_drawdown=_to_float(evaluation_mapping.get("max_drawdown"), field="evaluation.max_drawdown"),
            min_trades=_to_float(evaluation_mapping.get("min_trades"), field="evaluation.min_trades"),
            max_halt_rate=_to_float(evaluation_mapping.get("max_halt_rate"), field="evaluation.max_halt_rate"),
        )

        stress_value = _require_mapping(_require_mapping(mapping, "stress"), "value")
        stress_scenarios: list[StressScenarioConfig] = []
        for scenario_name, raw_values in stress_value.items():
            if isinstance(raw_values, Mapping):
                params = {str(key): _to_float(val, field=f"stress.{scenario_name}") for key, val in raw_values.items()}
                stress_scenarios.append(StressScenarioConfig(name=scenario_name, parameters=params))
                continue
            values: Sequence[object]
            if isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
                values = list(raw_values)
            else:
                values = [raw_values]
            for idx, entry in enumerate(values):
                params = {"value": _to_float(entry, field=f"stress.{scenario_name}")}
                name = scenario_name if len(values) == 1 else f"{scenario_name}_{idx + 1}"
                stress_scenarios.append(StressScenarioConfig(name=name, parameters=params))

        engine_mapping = _require_mapping(mapping, "engine")
        period_mapping = _require_mapping(engine_mapping, "period")
        engine = EngineRunConfig(
            timeframe=str(engine_mapping.get("timeframe", "")) or "1h",
            dataset_root=str(engine_mapping.get("dataset_root") or ""),
            period_start=_parse_datetime(period_mapping.get("start"), field="engine.period.start"),
            period_end=_parse_datetime(period_mapping.get("end"), field="engine.period.end"),
            cost_table_path=str(engine_mapping.get("cost_table_path") or ""),
            universe_path=str(engine_mapping.get("universe_path") or ""),
            output_root=str(engine_mapping.get("output_root")) if engine_mapping.get("output_root") else None,
        )

        if not engine.dataset_root:
            raise ValueError("engine.dataset_root は必須です。")
        if not engine.cost_table_path or not engine.universe_path:
            raise ValueError("engine.cost_table_path / engine.universe_path は必須です。")

        return BacktestPolicy(
            entry_rule=entry_rule,
            exit_rule=exit_rule,
            costs=costs,
            stress_scenarios=tuple(stress_scenarios),
            evaluation=evaluation,
            engine=engine,
        )

