"""
ランタイム依存関係のビルダー。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence, Union

from application.services import Backtester, ThetaOptimizer
from application.services.theta_optimizer import ThetaOptimizationPlan
from domain import ThetaRange
from infrastructure import (
    BacktestEngineHttpClient,
    BacktestEngineSettings,
    BacktestPolicy,
    BacktestRequestFactory,
    ConfigRepository,
    DeltaConstraintEvaluator,
    HistoricalThetaScorer,
    JsonSchemaRegistry,
    RandomOptunaStrategy,
    ThresholdStressEvaluator,
    UniformGridSearchStrategy,
)
from infrastructure.theta import ThetaRequestFactory


@dataclass(frozen=True)
class BacktestComponents:
    service: Backtester
    policy: BacktestPolicy
    request_factory: BacktestRequestFactory


@dataclass(frozen=True)
class ThetaComponents:
    service: ThetaOptimizer
    request_factory: ThetaRequestFactory


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _environment() -> str:
    return os.getenv("SERVICE_ENV", "dev")


@lru_cache(maxsize=1)
def _config_repository() -> ConfigRepository:
    root = _project_root()
    schema_root = root / "configs" / "schemas"
    registry = JsonSchemaRegistry(schema_root)
    return ConfigRepository(root, registry)


def _section(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if isinstance(value, Mapping):
        return value
    return mapping


def build_backtest_components(environment: str | None = None) -> BacktestComponents:
    env = environment or _environment()
    repo = _config_repository()

    engine_raw = repo.load("backtest_engine", environment=env)
    engine_settings = BacktestEngineSettings.from_mapping(_section(engine_raw, "backtest_engine"))
    engine_client = BacktestEngineHttpClient(engine_settings)

    policy_raw = repo.load("backtest_policy", environment=env)
    policy = BacktestPolicy.from_mapping(policy_raw)

    stress_evaluator = ThresholdStressEvaluator(policy.evaluation)
    service = Backtester(engine_client, stress_evaluator)
    request_factory = BacktestRequestFactory(policy=policy)
    return BacktestComponents(service=service, policy=policy, request_factory=request_factory)


NumberLike = Union[float, int]


def _to_float(value: object, *, default: float | None = None, name: str = "value") -> float:
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"{name} が指定されていません。")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            value_str: str = value
            return float(value_str)
        except ValueError as exc:
            if default is not None:
                return default
            raise ValueError(f"{name} は数値である必要があります。") from exc
    if default is not None:
        return default
    raise ValueError(f"{name} は数値である必要があります。")


def _to_int(value: object, *, default: int | None = None, name: str = "value") -> int:
    default_float = float(default) if default is not None else None
    return int(_to_float(value, default=default_float, name=name))


def _range_pair(value: object, name: str) -> tuple[float, float]:
    if value is None or not isinstance(value, Sequence) or len(value) < 2:
        raise ValueError(f"{name} は2要素の配列で指定してください。")
    return (
        _to_float(value[0], name=f"{name}[0]"),
        _to_float(value[1], name=f"{name}[1]"),
    )


def _build_theta_range(core_policy: Mapping[str, object]) -> ThetaRange:
    search = _section(core_policy, "theta_search_range")
    theta1_min, theta1_max = _range_pair(search.get("theta1"), "theta_search_range.theta1")
    theta2_min, theta2_max = _range_pair(search.get("theta2"), "theta_search_range.theta2")
    constraints = _section(core_policy, "theta_constraints")
    max_delta = _to_float(search.get("max_delta", constraints.get("max_delta", 0.1)), name="theta_search_range.max_delta")
    return ThetaRange(
        theta1_min=theta1_min,
        theta1_max=theta1_max,
        theta2_min=theta2_min,
        theta2_max=theta2_max,
        max_delta=max_delta,
    )


def _build_theta_plan(core_policy: Mapping[str, object]) -> ThetaOptimizationPlan:
    plan_raw = core_policy.get("theta_plan", {})
    if isinstance(plan_raw, Mapping):
        grid_steps_raw = plan_raw.get("grid_steps", {"theta1": 3, "theta2": 3})
        if isinstance(grid_steps_raw, Mapping):
            grid_steps = {
                str(k): _to_int(v, default=3, name=f"theta_plan.grid_steps.{k}") for k, v in grid_steps_raw.items()
            }
        else:
            grid_steps = {"theta1": 3, "theta2": 3}
        optuna_trials = _to_int(plan_raw.get("optuna_trials"), default=20, name="theta_plan.optuna_trials")
        timeout_raw = plan_raw.get("optuna_timeout_seconds")
        optuna_timeout = _to_int(timeout_raw, name="theta_plan.optuna_timeout_seconds") if timeout_raw is not None else None
        constraints_raw = plan_raw.get("constraints", {})
        if isinstance(constraints_raw, Mapping):
            constraints = {str(k): _to_float(v, name=f"theta_plan.constraints.{k}") for k, v in constraints_raw.items()}
        else:
            constraints = {}
    else:
        grid_steps = {"theta1": 3, "theta2": 3}
        optuna_trials = 20
        optuna_timeout = None
        constraints = {}
    return ThetaOptimizationPlan(
        grid_steps=grid_steps,
        optuna_trials=optuna_trials,
        optuna_timeout_seconds=optuna_timeout,
        constraints=constraints,
    )


def _build_theta_defaults(core_policy: Mapping[str, object], theta_range: ThetaRange) -> tuple[float, float, float]:
    constraints = _section(core_policy, "theta_constraints")
    max_delta = _to_float(constraints.get("max_delta"), default=theta_range.max_delta, name="theta_constraints.max_delta")
    baseline_theta1 = _to_float(
        constraints.get("baseline_theta1"),
        default=(theta_range.theta1_min + theta_range.theta1_max) / 2,
        name="theta_constraints.baseline_theta1",
    )
    baseline_theta2 = _to_float(
        constraints.get("baseline_theta2"),
        default=(theta_range.theta2_min + theta_range.theta2_max) / 2,
        name="theta_constraints.baseline_theta2",
    )
    return max_delta, baseline_theta1, baseline_theta2


def build_theta_components(environment: str | None = None) -> ThetaComponents:
    env = environment or _environment()
    repo = _config_repository()
    core_raw = repo.load("core_policy", environment=env)
    core_policy = _section(core_raw, "core_policy")

    theta_range = _build_theta_range(core_policy)
    theta_plan = _build_theta_plan(core_policy)
    max_delta, baseline_theta1, baseline_theta2 = _build_theta_defaults(core_policy, theta_range)

    grid_strategy = UniformGridSearchStrategy()
    optuna_strategy = RandomOptunaStrategy()
    constraint_evaluator = DeltaConstraintEvaluator(
        default_max_delta=max_delta,
        baseline_theta1=baseline_theta1,
        baseline_theta2=baseline_theta2,
    )

    scoring_raw = core_policy.get("theta_scoring", {})
    if isinstance(scoring_raw, Mapping):
        max_dd_target = _to_float(scoring_raw.get("max_drawdown_target"), default=0.12, name="theta_scoring.max_drawdown_target")
    else:
        max_dd_target = 0.12
    scorer = HistoricalThetaScorer(
        max_drawdown_target=max_dd_target,
        reference_theta1=baseline_theta1,
        reference_theta2=baseline_theta2,
    )

    service = ThetaOptimizer(
        grid_strategy=grid_strategy,
        optuna_strategy=optuna_strategy,
        constraint_evaluator=constraint_evaluator,
        scorer=scorer,
    )
    request_factory = ThetaRequestFactory(theta_range=theta_range, plan=theta_plan)
    return ThetaComponents(service=service, request_factory=request_factory)
