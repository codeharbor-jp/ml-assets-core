"""
BacktestRequest を簡易生成するファクトリ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from application.services.backtester import BacktestRequest, StressScenario
from domain import ModelArtifact, ThetaParams

from .policy import BacktestPolicy


@dataclass
class BacktestRequestFactory:
    """
    config/policy から BacktestRequest を構築する責務を持つクラス。
    """

    policy: BacktestPolicy

    def build(
        self,
        *,
        artifact: ModelArtifact,
        theta_params: ThetaParams,
        engine_overrides: Mapping[str, str] | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> BacktestRequest:
        params = {
            "theta1": theta_params.theta1,
            "theta2": theta_params.theta2,
            **{f"entry_{key}": value for key, value in self.policy.entry_rule.items()},
            **{f"exit_{key}": value for key, value in self.policy.exit_rule.items()},
            **{f"cost_{key}": value for key, value in self.policy.costs.items()},
        }

        engine_config = dict(self.policy.engine.to_mapping())
        if engine_overrides:
            engine_config.update({str(key): str(value) for key, value in engine_overrides.items()})

        request_metadata = {
            "model_version": artifact.model_version,
            "code_hash": artifact.code_hash,
        }
        if metadata:
            request_metadata.update({str(key): str(value) for key, value in metadata.items()})

        stress_scenarios = [
            StressScenario(name=scenario.name, parameters=scenario.parameters)
            for scenario in self.policy.stress_scenarios
        ]

        return BacktestRequest(
            model_artifact=artifact,
            params=params,
            engine_config=engine_config,
            stress_scenarios=stress_scenarios,
            metadata=request_metadata,
        )

