"""
θ 最適化用の探索戦略実装。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from application.services.theta_optimizer import GridSearchStrategy, OptunaOptimizationStrategy
from domain import ThetaParams, ThetaRange


def _linspace(min_value: float, max_value: float, steps: int) -> list[float]:
    if steps <= 1:
        return [(min_value + max_value) / 2]
    step_size = (max_value - min_value) / (steps - 1)
    return [min_value + idx * step_size for idx in range(steps)]


@dataclass
class UniformGridSearchStrategy(GridSearchStrategy):
    """
    θ1/θ2 を均等分割して候補を生成する戦略。
    """

    clock: callable = lambda: datetime.now(timezone.utc)

    def generate_candidates(self, theta_range: ThetaRange, steps: Mapping[str, int]) -> Sequence[ThetaParams]:
        theta1_steps = max(int(steps.get("theta1", 1)), 1)
        theta2_steps = max(int(steps.get("theta2", 1)), 1)

        theta1_values = _linspace(theta_range.theta1_min, theta_range.theta1_max, theta1_steps)
        theta2_values = _linspace(theta_range.theta2_min, theta_range.theta2_max, theta2_steps)

        candidates: list[ThetaParams] = []
        for theta1 in theta1_values:
            for theta2 in theta2_values:
                candidates.append(
                    ThetaParams(
                        theta1=theta1,
                        theta2=theta2,
                        updated_at=self.clock(),
                        updated_by="grid-search",
                    )
                )
        return candidates


@dataclass
class RandomOptunaStrategy(OptunaOptimizationStrategy):
    """
    Optuna 風のランダム探索を行う簡易実装。
    Baseline に近い候補を優先的に返す。
    """

    rng: random.Random = random.Random()
    clock: callable = lambda: datetime.now(timezone.utc)

    def optimize(
        self,
        *,
        theta_range: ThetaRange,
        trials: int,
        timeout_seconds: int | None,
        base_candidates: Sequence[ThetaParams],
        constraints: Mapping[str, float],
    ) -> ThetaParams:
        baseline_theta1 = float(constraints.get("baseline_theta1", theta_range.theta1_min))
        baseline_theta2 = float(constraints.get("baseline_theta2", theta_range.theta2_min))
        max_delta = float(constraints.get("max_delta", theta_range.max_delta))

        def _distance(candidate: ThetaParams) -> float:
            return abs(candidate.theta1 - baseline_theta1) + abs(candidate.theta2 - baseline_theta2)

        def _within_delta(candidate: ThetaParams) -> bool:
            return (
                abs(candidate.theta1 - baseline_theta1) <= max_delta
                and abs(candidate.theta2 - baseline_theta2) <= max_delta
            )

        best_candidate = base_candidates[0] if base_candidates else self._sample(theta_range)
        best_distance = _distance(best_candidate)

        search_trials = max(trials, 1)
        for _ in range(search_trials):
            candidate = self._sample(theta_range)
            if not _within_delta(candidate):
                continue
            distance = _distance(candidate)
            if distance < best_distance:
                best_candidate = candidate
                best_distance = distance

        return best_candidate

    def _sample(self, theta_range: ThetaRange) -> ThetaParams:
        theta1 = self.rng.uniform(theta_range.theta1_min, theta_range.theta1_max)
        theta2 = self.rng.uniform(theta_range.theta2_min, theta_range.theta2_max)
        return ThetaParams(theta1=theta1, theta2=theta2, updated_at=self.clock(), updated_by="theta-optuna")

