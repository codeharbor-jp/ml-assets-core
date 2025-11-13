from datetime import datetime, timezone
from typing import Mapping, Sequence

from application.services.theta_optimizer import (
    ConstraintEvaluator,
    GridSearchStrategy,
    OptunaOptimizationStrategy,
    ThetaOptimizer,
    ThetaOptimizationPlan,
    ThetaOptimizationRequest,
    ThetaScorer,
)
from domain import ThetaParams, ThetaRange


class DummyGridStrategy(GridSearchStrategy):
    def generate_candidates(self, theta_range: ThetaRange, steps: Mapping[str, int]) -> Sequence[ThetaParams]:
        return [
            ThetaParams(theta1=theta_range.theta1_min, theta2=theta_range.theta2_min, updated_at=datetime.now(timezone.utc), updated_by="grid"),
            ThetaParams(theta1=theta_range.theta1_max, theta2=theta_range.theta2_max, updated_at=datetime.now(timezone.utc), updated_by="grid"),
        ]


class DummyOptunaStrategy(OptunaOptimizationStrategy):
    def optimize(
        self,
        *,
        theta_range: ThetaRange,
        trials: int,
        timeout_seconds: int | None,
        base_candidates: Sequence[ThetaParams],
        constraints: Mapping[str, float],
    ) -> ThetaParams:
        return ThetaParams(
            theta1=(theta_range.theta1_min + theta_range.theta1_max) / 2,
            theta2=(theta_range.theta2_min + theta_range.theta2_max) / 2,
            updated_at=datetime.now(timezone.utc),
            updated_by="optuna",
        )


class DummyConstraintEvaluator(ConstraintEvaluator):
    def validate(self, params: ThetaParams, constraints: Mapping[str, float]) -> bool:
        delta_limit = constraints.get("max_delta", 0.1)
        baseline_theta1 = constraints.get("baseline_theta1", params.theta1)
        baseline_theta2 = constraints.get("baseline_theta2", params.theta2)
        return (
            abs(params.theta1 - baseline_theta1) <= delta_limit
            and abs(params.theta2 - baseline_theta2) <= delta_limit
        )


class DummyScorer(ThetaScorer):
    def score(self, params: ThetaParams, history: Sequence[Mapping[str, float]]) -> float:
        history_best = max((record.get("score", 0.0) for record in history), default=0.0)
        distance_penalty = abs(params.theta1 - 0.7) + abs(params.theta2 - 0.3)
        return history_best - distance_penalty


def test_theta_optimizer_selects_best_candidate() -> None:
    optimizer = ThetaOptimizer(
        grid_strategy=DummyGridStrategy(),
        optuna_strategy=DummyOptunaStrategy(),
        constraint_evaluator=DummyConstraintEvaluator(),
        scorer=DummyScorer(),
    )

    theta_range = ThetaRange(theta1_min=0.6, theta1_max=0.8, theta2_min=0.2, theta2_max=0.4, max_delta=0.05)
    initial_params = ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="baseline")
    plan = ThetaOptimizationPlan(
        grid_steps={"theta1": 3, "theta2": 3},
        optuna_trials=20,
        constraints={"max_delta": 0.1, "baseline_theta1": initial_params.theta1, "baseline_theta2": initial_params.theta2},
    )
    history = [
        {"theta1": 0.68, "theta2": 0.32, "score": 1.2},
        {"theta1": 0.72, "theta2": 0.28, "score": 1.1},
    ]

    request = ThetaOptimizationRequest(
        range=theta_range,
        initial_params=initial_params,
        plan=plan,
        score_history=history,
        metadata={"trigger": "unit-test"},
    )

    result = optimizer.optimize(request)

    assert isinstance(result.params, ThetaParams)
    assert 0.6 <= result.params.theta1 <= 0.8
    assert result.diagnostics["grid_candidates"] == 2.0

