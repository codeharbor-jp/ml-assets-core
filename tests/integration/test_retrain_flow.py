# ruff: noqa: E402

from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import sys
import types

prefect_stub = types.ModuleType("prefect")


def _flow(name: str | None = None):
    def decorator(fn):
        def wrapped(*args, **kwargs):
            return fn(*args, **kwargs)

        wrapped.__name__ = fn.__name__
        return wrapped

    return decorator


def _get_run_logger():
    class _Logger:
        def info(self, *args, **kwargs) -> None:
            return None

    return _Logger()


prefect_stub.flow = _flow
prefect_stub.get_run_logger = _get_run_logger
sys.modules["prefect"] = prefect_stub

from application.flows.core_backtest import core_backtest_flow
from application.flows.core_retrain import CoreRetrainResult, core_retrain_flow
from application.flows.core_theta_opt import core_theta_opt_flow
from application.flows.dependencies import FlowDependencies, configure_flow_dependencies
from application.services import (
    BacktestRequest,
    BacktestResult,
    Backtester,
    ThetaOptimizationPlan,
    ThetaOptimizationRequest,
    ThetaOptimizationResult,
    ThetaOptimizer,
    ThetaScorer,
)
from application.services.backtester import BacktestEngineClient, StressEvaluator, StressScenario
from domain import DatasetPartition, ModelArtifact, ThetaParams, ThetaRange
from application.usecases import (
    LearningRequest,
    LearningResponse,
    LearningUseCase,
)
from application.usecases.inference import InferenceRequest, InferenceResponse, InferenceUseCase
from application.usecases.ops import OpsCommand, OpsResponse, OpsUseCase
from application.usecases.publish import PublishRequest, PublishResponse, PublishUseCase


def make_artifact(model_version: str = "model-001") -> ModelArtifact:
    now = datetime.now(timezone.utc)
    return ModelArtifact(
        model_version=model_version,
        created_at=now,
        created_by="integration-test",
        ai1_path=Path("/tmp/ai1.pkl"),
        ai2_path=Path("/tmp/ai2.pkl"),
        feature_schema_path=Path("/tmp/schema.json"),
        params_path=Path("/tmp/params.yaml"),
        metrics_path=Path("/tmp/metrics.json"),
        code_hash="codehash",
        data_hash="datahash",
    )


# Dummy implementations for flow dependencies ---------------------------------
class DummyLearningUseCase(LearningUseCase):
    def execute(self, request: LearningRequest) -> LearningResponse:
        artifact = make_artifact()
        return LearningResponse(
            model_artifact=artifact,
            backtest_metrics={"sharpe": 1.4},
            theta_params=ThetaParams(
                theta1=0.7,
                theta2=0.3,
                updated_at=datetime.now(timezone.utc),
                updated_by="tests",
                source_model_version=artifact.model_version,
            ),
            diagnostics={"duration": 12.0},
        )


class DummyInferenceUseCase(InferenceUseCase):
    def execute(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(signals=[], metadata={"executed": "false"})


class DummyOpsUseCase(OpsUseCase):
    def execute(self, command: OpsCommand) -> OpsResponse:
        return OpsResponse(status="noop", message="not implemented")


class DummyPublishUseCase(PublishUseCase):
    def execute(self, request: PublishRequest) -> PublishResponse:
        return PublishResponse(status="deployed", audit_record_id="audit-001", diagnostics={"latency_ms": 12.0})


class DummyEngine(BacktestEngineClient):
    def run(
        self,
        *,
        model_artifact: ModelArtifact,
        params: Mapping[str, float],
        config: Mapping[str, str],
        stress_scenarios: Sequence[StressScenario],
    ) -> Mapping[str, object]:
        return {
            "summary": {"sharpe": 1.5, "max_dd": 0.08},
            "stress": {
                scenario.name: {"sharpe": 0.95, "max_dd": 0.11} for scenario in stress_scenarios
            },
            "diagnostics": {"engine_latency_ms": 45.0},
        }


class DummyStressEvaluator(StressEvaluator):
    def evaluate(
        self,
        *,
        base_metrics: Mapping[str, float],
        stress_metrics: Mapping[str, Mapping[str, float]],
    ) -> Mapping[str, float]:
        worst_dd = max((metrics["max_dd"] for metrics in stress_metrics.values()), default=base_metrics["max_dd"])
        return {"worst_max_dd": worst_dd}


class DummyThetaScorer(ThetaScorer):
    def score(self, params: ThetaParams, history: Sequence[Mapping[str, float]]) -> float:
        baseline = history[0]["score"] if history else 1.0
        return baseline - abs(params.theta1 - 0.7) - abs(params.theta2 - 0.3)


class DummyConstraintEvaluator:
    def validate(self, params: ThetaParams, constraints: Mapping[str, float]) -> bool:
        max_delta = constraints.get("max_delta", 0.1)
        baseline1 = constraints.get("baseline_theta1", params.theta1)
        baseline2 = constraints.get("baseline_theta2", params.theta2)
        return abs(params.theta1 - baseline1) <= max_delta and abs(params.theta2 - baseline2) <= max_delta


class DummyGridStrategy:
    def generate_candidates(self, theta_range: ThetaRange, steps: Mapping[str, int]) -> Sequence[ThetaParams]:
        return [
            ThetaParams(theta1=theta_range.theta1_min, theta2=theta_range.theta2_min, updated_at=datetime.now(timezone.utc), updated_by="grid"),
            ThetaParams(theta1=theta_range.theta1_max, theta2=theta_range.theta2_max, updated_at=datetime.now(timezone.utc), updated_by="grid"),
        ]


class DummyOptunaStrategy:
    def optimize(
        self,
        *,
        theta_range: ThetaRange,
        trials: int,
        timeout_seconds: int | None,
        base_candidates: Sequence[ThetaParams],
        constraints: Mapping[str, float],
    ) -> ThetaParams:
        return base_candidates[0]


def setup_flow_dependencies() -> None:
    configure_flow_dependencies(
        FlowDependencies(
            learning_usecase=DummyLearningUseCase(),
            inference_usecase=DummyInferenceUseCase(),
            publish_usecase=DummyPublishUseCase(),
            ops_usecase=DummyOpsUseCase(),
            backtester_service=Backtester(DummyEngine(), DummyStressEvaluator()),
            theta_optimizer=ThetaOptimizer(
                grid_strategy=DummyGridStrategy(),
                optuna_strategy=DummyOptunaStrategy(),
                constraint_evaluator=DummyConstraintEvaluator(),
                scorer=DummyThetaScorer(),
            ),
        )
    )


def test_core_backtest_flow_executes_with_dependencies() -> None:
    setup_flow_dependencies()
    artifact = make_artifact()
    result = core_backtest_flow(
        BacktestRequest(
            model_artifact=artifact,
            params={"theta1": 0.7},
            engine_config={"window": "30d"},
            stress_scenarios=[StressScenario(name="cost", parameters={"multiplier": 1.2})],
        )
    )
    assert isinstance(result, BacktestResult)
    assert result.summary_metrics["sharpe"] == 1.5


def test_core_theta_opt_flow_executes_with_dependencies() -> None:
    setup_flow_dependencies()
    theta_range = ThetaRange(theta1_min=0.6, theta1_max=0.8, theta2_min=0.2, theta2_max=0.4, max_delta=0.05)
    request = ThetaOptimizationRequest(
        range=theta_range,
        initial_params=ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="baseline"),
        plan=ThetaOptimizationPlan(grid_steps={"theta1": 3, "theta2": 3}, optuna_trials=10, constraints={"max_delta": 0.1}),
        score_history=[{"score": 1.1}],
    )
    result = core_theta_opt_flow(request)
    assert isinstance(result, ThetaOptimizationResult)


def test_core_retrain_flow_runs_full_chain() -> None:
    setup_flow_dependencies()

    learning_request = LearningRequest(
        partitions=[
            DatasetPartition(
                timeframe="1h",
                symbol="EURUSD",
                year=2024,
                month=1,
                last_timestamp=datetime(2024, 1, 31, 23, tzinfo=timezone.utc),
                bars_written=120,
                missing_gaps=0,
                outlier_bars=0,
                spike_flags=0,
                quarantine_flag=False,
                data_hash="hash123",
            )
        ],
        feature_spec={"version": "1"},
        preprocessing={"scaler": "robust"},
        theta_range=ThetaRange(theta1_min=0.6, theta1_max=0.8, theta2_min=0.2, theta2_max=0.4, max_delta=0.05),
        metadata={"run_id": "retrain-123"},
    )

    backtest_request = BacktestRequest(
        model_artifact=make_artifact("model-001"),
        params={"theta1": 0.7},
        engine_config={"window": "30d"},
        stress_scenarios=[StressScenario(name="latency", parameters={"ms": 100})],
    )
    theta_request = ThetaOptimizationRequest(
        range=learning_request.theta_range,
        initial_params=ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="baseline"),
        plan=ThetaOptimizationPlan(grid_steps={"theta1": 3, "theta2": 3}, optuna_trials=10, constraints={"max_delta": 0.1}),
        score_history=[{"score": 1.0}],
    )
    publish_request = PublishRequest(
        artifact=make_artifact("model-001"),
        theta_params=ThetaParams(theta1=0.7, theta2=0.3, updated_at=datetime.now(timezone.utc), updated_by="baseline"),
    )

    result = core_retrain_flow(
        learning_request,
        backtest_request=backtest_request,
        theta_request=theta_request,
        publish_request=publish_request,
        flow_metadata={"trigger": "unit"},
    )

    assert isinstance(result, CoreRetrainResult)
    assert result.learning.backtest_metrics["sharpe"] == 1.4
    assert result.backtest is not None
    assert result.theta is not None
    assert result.publish is not None

