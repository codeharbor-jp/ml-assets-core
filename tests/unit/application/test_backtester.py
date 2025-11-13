from typing import Mapping

from application.services.backtester import (
    BacktestRequest,
    BacktestResult,
    Backtester,
    BacktestEngineClient,
    StressEvaluator,
    StressScenario,
)
from domain import ModelArtifact
from datetime import datetime, timezone
from pathlib import Path


class DummyEngine(BacktestEngineClient):
    def run(
        self,
        *,
        model_artifact: ModelArtifact,
        params: Mapping[str, float],
        config: Mapping[str, str],
        stress_scenarios: list[StressScenario],
    ) -> Mapping[str, object]:
        return {
            "summary": {"sharpe": 1.5, "max_dd": 0.08},
            "stress": {
                scenario.name: {"sharpe": 0.9, "max_dd": 0.12}
                for scenario in stress_scenarios
            },
            "diagnostics": {"run_time_sec": 42},
        }


class DummyStressEvaluator(StressEvaluator):
    def evaluate(
        self,
        *,
        base_metrics: Mapping[str, float],
        stress_metrics: Mapping[str, Mapping[str, float]],
    ) -> Mapping[str, float]:
        max_dds = [metrics["max_dd"] for metrics in stress_metrics.values()]
        worst_dd = max(max_dds) if max_dds else base_metrics.get("max_dd", 0.0)
        return {"worst_max_dd": worst_dd, "base_sharpe": base_metrics.get("sharpe", 0.0)}


def make_artifact() -> ModelArtifact:
    now = datetime.now(timezone.utc)
    return ModelArtifact(
        model_version="model-001",
        created_at=now,
        created_by="tester",
        ai1_path=Path("/tmp/ai1.pkl"),
        ai2_path=Path("/tmp/ai2.pkl"),
        feature_schema_path=Path("/tmp/schema.json"),
        params_path=Path("/tmp/params.yaml"),
        metrics_path=Path("/tmp/metrics.json"),
        code_hash="codehash",
        data_hash="datahash",
    )


def test_backtester_runs_engine_and_evaluates_stress() -> None:
    backtester = Backtester(DummyEngine(), DummyStressEvaluator())
    request = BacktestRequest(
        model_artifact=make_artifact(),
        params={"theta1": 0.7},
        engine_config={"horizon_days": "30"},
        stress_scenarios=[
            StressScenario(name="cost_increase", parameters={"multiplier": 1.5}),
            StressScenario(name="latency_spike", parameters={"latency_ms": 120}),
        ],
        metadata={"trigger": "unit-test"},
    )

    result = backtester.run(request)

    assert isinstance(result, BacktestResult)
    assert result.summary_metrics["sharpe"] == 1.5
    assert "cost_increase" in result.stress_metrics
    assert result.evaluation["worst_max_dd"] == 0.12
    assert result.diagnostics["requested_scenarios"] == len(request.stress_scenarios)

