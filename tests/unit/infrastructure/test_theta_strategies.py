from __future__ import annotations

import random

from datetime import datetime, timezone

import pytest

from domain import ThetaParams, ThetaRange
from infrastructure.theta import (
    DeltaConstraintEvaluator,
    HistoricalThetaScorer,
    RandomOptunaStrategy,
    UniformGridSearchStrategy,
)


def test_uniform_grid_strategy_generates_candidates() -> None:
    strategy = UniformGridSearchStrategy(clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    theta_range = ThetaRange(theta1_min=0.6, theta1_max=0.8, theta2_min=0.2, theta2_max=0.4, max_delta=0.1)
    candidates = strategy.generate_candidates(theta_range, {"theta1": 2, "theta2": 3})
    assert len(candidates) == 6
    assert candidates[0].theta1 == pytest.approx(0.6)


def test_random_optuna_strategy_respects_constraints() -> None:
    strategy = RandomOptunaStrategy(rng=random.Random(0), clock=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    theta_range = ThetaRange(theta1_min=0.6, theta1_max=0.9, theta2_min=0.2, theta2_max=0.5, max_delta=0.1)
    base = [
        ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="base"),
    ]
    candidate = strategy.optimize(
        theta_range=theta_range,
        trials=20,
        timeout_seconds=None,
        base_candidates=tuple(base),
        constraints={"max_delta": 0.1, "baseline_theta1": 0.7, "baseline_theta2": 0.3},
    )
    assert abs(candidate.theta1 - 0.7) <= 0.1
    assert abs(candidate.theta2 - 0.3) <= 0.1


def test_delta_constraint_evaluator() -> None:
    evaluator = DeltaConstraintEvaluator(default_max_delta=0.1, baseline_theta1=0.7, baseline_theta2=0.3)
    params = ThetaParams(theta1=0.72, theta2=0.28, updated_at=datetime.now(timezone.utc), updated_by="tests")
    assert evaluator.validate(params, {})
    params_far = ThetaParams(theta1=0.9, theta2=0.1, updated_at=datetime.now(timezone.utc), updated_by="tests")
    assert not evaluator.validate(params_far, {})


def test_historical_theta_scorer_prefers_similar_history() -> None:
    scorer = HistoricalThetaScorer(
        max_drawdown_target=0.1,
        reference_theta1=0.7,
        reference_theta2=0.3,
    )
    history = [
        {"theta1": 0.7, "theta2": 0.3, "sharpe": 1.4, "max_dd": 0.08},
        {"theta1": 0.75, "theta2": 0.25, "sharpe": 1.2, "max_dd": 0.09},
    ]
    candidate_close = ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="tests")
    candidate_far = ThetaParams(theta1=0.85, theta2=0.2, updated_at=datetime.now(timezone.utc), updated_by="tests")

    assert scorer.score(candidate_close, history) > scorer.score(candidate_far, history)

