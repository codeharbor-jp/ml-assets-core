"""
FastAPI 用の Pydantic スキーマ定義。
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from pydantic import BaseModel

from ...domain import DatasetPartition, ModelArtifact, ThetaParams
from ...domain.models.signal import Signal
from ...domain.value_objects import ThetaRange
from ...application.services import (
    BacktestRequest,
    BacktestResult,
    StressScenario,
    ThetaOptimizationPlan,
    ThetaOptimizationRequest,
    ThetaOptimizationResult,
    TrainingArtifact,
    TrainingResult,
)
from ...application.usecases import InferenceRequest, InferenceResponse, OpsCommand, OpsResponse, PublishResponse


class DatasetPartitionSchema(BaseModel):
    timeframe: str
    symbol: str
    year: int
    month: int
    last_timestamp: datetime
    bars_written: int
    missing_gaps: int
    outlier_bars: int
    spike_flags: int
    quarantine_flag: bool
    data_hash: str

    def to_domain(self) -> DatasetPartition:
        return DatasetPartition(**self.dict())


class TrainingRequestSchema(BaseModel):
    partition: DatasetPartition
    features: Sequence[Mapping[str, float]]
    labels_ai1: Sequence[int]
    labels_ai2: Sequence[int]
    params_ai1: Mapping[str, float]
    params_ai2: Mapping[str, float]
    calibration: bool = True
    random_seed: int | None = None
    metadata: Mapping[str, str] = {}


class TrainingResponseSchema(BaseModel):
    artifact: TrainingArtifact
    cv_metrics: Mapping[str, float]
    diagnostics: Mapping[str, float]

    @classmethod
    def from_result(cls, result: TrainingResult) -> "TrainingResponseSchema":
        return cls(
            artifact=result.artifact,
            cv_metrics=result.cv_metrics,
            diagnostics=result.diagnostics,
        )


class StressScenarioSchema(BaseModel):
    name: str
    parameters: Mapping[str, float]


class BacktestRequestSchema(BaseModel):
    model_artifact: ModelArtifact
    params: Mapping[str, float]
    engine_config: Mapping[str, str]
    stress_scenarios: Sequence[StressScenarioSchema]
    metadata: Mapping[str, str] = {}

    def to_domain(self) -> BacktestRequest:
        return BacktestRequest(
            model_artifact=self.model_artifact,
            params=self.params,
            engine_config=self.engine_config,
            stress_scenarios=[
                StressScenario(name=scenario.name, parameters=scenario.parameters)
                for scenario in self.stress_scenarios
            ],
            metadata=self.metadata,
        )


class BacktestResponseSchema(BaseModel):
    summary_metrics: Mapping[str, float]
    stress_metrics: Mapping[str, Mapping[str, float]]
    evaluation: Mapping[str, float]
    diagnostics: Mapping[str, float]

    @classmethod
    def from_result(cls, result: BacktestResult) -> "BacktestResponseSchema":
        return cls(
            summary_metrics=result.summary_metrics,
            stress_metrics=result.stress_metrics,
            evaluation=result.evaluation,
            diagnostics=result.diagnostics,
        )


class ThetaOptimizationPlanSchema(BaseModel):
    grid_steps: Mapping[str, int]
    optuna_trials: int
    optuna_timeout_seconds: int | None = None
    constraints: Mapping[str, float] = {}

    def to_domain(self) -> ThetaOptimizationPlan:
        return ThetaOptimizationPlan(
            grid_steps=self.grid_steps,
            optuna_trials=self.optuna_trials,
            optuna_timeout_seconds=self.optuna_timeout_seconds,
            constraints=self.constraints,
        )


class ThetaOptimizationRequestSchema(BaseModel):
    range: ThetaRange
    initial_params: ThetaParams
    plan: ThetaOptimizationPlan
    score_history: Sequence[Mapping[str, float]]
    metadata: Mapping[str, str] = {}


class ThetaOptimizationResponseSchema(BaseModel):
    params: ThetaParams
    score: float
    diagnostics: Mapping[str, float]

    @classmethod
    def from_result(cls, result: ThetaOptimizationResult) -> "ThetaOptimizationResponseSchema":
        return cls(
            params=result.params,
            score=result.score,
            diagnostics=result.diagnostics,
        )


class InferenceRequestSchema(BaseModel):
    partition_ids: Sequence[str]
    theta_params: ThetaParams
    metadata: Mapping[str, str] = {}

    def to_domain(self) -> InferenceRequest:
        return InferenceRequest(
            partition_ids=self.partition_ids,
            theta_params=self.theta_params,
            metadata=self.metadata,
        )


class InferenceResponseSchema(BaseModel):
    signals: Sequence[Signal]
    diagnostics: Mapping[str, float]

    @classmethod
    def from_result(cls, result: InferenceResponse) -> "InferenceResponseSchema":
        return cls(signals=result.signals, diagnostics=result.diagnostics)


class PublishRequestSchema(BaseModel):
    artifact: ModelArtifact
    theta_params: ThetaParams
    metadata: Mapping[str, str] = {}


class PublishResponseSchema(BaseModel):
    status: str
    audit_record_id: str
    diagnostics: Mapping[str, float]

    @classmethod
    def from_response(cls, response: PublishResponse) -> "PublishResponseSchema":
        return cls(
            status=response.status,
            audit_record_id=response.audit_record_id,
            diagnostics=response.diagnostics,
        )


class OpsCommandSchema(BaseModel):
    command: str
    arguments: Mapping[str, str]
    metadata: Mapping[str, str] = {}

    def to_domain(self) -> OpsCommand:
        return OpsCommand(
            command=self.command,
            arguments=self.arguments,
            metadata=self.metadata,
        )


class OpsResponseSchema(BaseModel):
    status: str
    message: str

    @classmethod
    def from_response(cls, response: OpsResponse) -> "OpsResponseSchema":
        return cls(status=response.status, message=response.message)

